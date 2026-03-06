import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { MatTableModule , MatTableDataSource} from '@angular/material/table';
import { MatDialog } from '@angular/material/dialog';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSliderModule } from '@angular/material/slider';
import { ReactiveFormsModule } from '@angular/forms';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ProductService } from '../../services/product';
import { ChangeDetectorRef } from '@angular/core';
import { MatOptionModule } from '@angular/material/core';
import { MatSelectModule } from '@angular/material/select';
import { concatMap, Observable, Subject, Subscription } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar } from '@angular/material/snack-bar';
import { EditApprovePo } from '../edit-approve-po/edit-approve-po';
import { NgZone } from '@angular/core';

interface recentProduct{
  po_id: number;
  supplier: string;
  status: string;
  total_amount: number;
  expected_at: string;
  created_at: string;
}

@Component({
  selector: 'app-replenishment-recommendation',
  standalone: true,
  imports: [MatProgressBarModule, MatIconModule,CommonModule,FormsModule,MatFormFieldModule,MatInputModule,MatButtonModule,MatProgressSpinnerModule,ReactiveFormsModule,MatTableModule, MatSliderModule, MatOptionModule, MatSelectModule],
  templateUrl: './replenishment-recommendation.html',
  styleUrl: './replenishment-recommendation.scss'
})
export class ReplenishmentRecommendationComponent implements OnInit , OnDestroy{
  getRecommendationsForm!: FormGroup;
  displayedColumns: string[] = ['Metric', 'Value'];
  selectedDay: number = 15;
  dataSource:any= [];
  loading = false;
  isRecommendationLoading = false;
  poApprovalPending = false;
  errorMessage:string |null = null;
  private wsSubscription: Subscription | undefined;
  poId = 0;
  sku = '';
  recommendedQuantity = 0;
  supplier = '';
  suppliers = [{
    id: 1,
    name: 'FreshMart Distributors'
  },
  {
    id: 34,
    name: 'Global Foods Ltd'
  }];
  poColumns: string[] = ['po_id', 'supplier', 'status', 'total_amount', 'expected_at', 'created_at'];
  recentProducts: recentProduct[] = [];
  recentPoDataSource = new MatTableDataSource<recentProduct>();
  statusOptions = ['draft', 'approved'];
  private agentWorkingMessageQueue$= new Subject<string>();

  // New fields to control create button behavior
  canCreate = true;
  private _formChangeSub: Subscription | undefined;
  private lastCreatedStoreId: number | null = null;
  private lastCreatedSku: string | null = null;

  // New subscription to watch form changes for hiding the recommendation table
  private formWatcherSub: Subscription | undefined;
  private prevStoreId: number | null = null;
  private prevSku: string | null = null;

  constructor(private snack: MatSnackBar,private fb: FormBuilder, private dialog: MatDialog,private cdr: ChangeDetectorRef,private productService:ProductService, private zone: NgZone) {
  }

  storeIdList = [1045, 1050, 1055];
  storeList = [ { id: 1045, location: "Web Store" }, { id: 1050, location: "Bangalore Store" },
     { id: 1055, location: "New York Store" } ];
  skuList = ['22130', '21432', '21232', '37448', '37494A', '21700', '47556B', '22055', '37446', '84569D', '22209', '22210', '22208', '21428', '21430', '21884', '21882', '21880', '21883', '85049C', '85049F', '20862', '20864'];
  skuProductList = [{
    sku: 'POST',
    product_name: 'POSTAGE'
  },
  {
    sku: '22130',
    product_name: 'PARTY CONE CHRISTMAS DECORATION'
  },
  {
    sku: '21432',
    product_name: 'SET OF 3 CASES WOODLAND DESIGN'
  },
  {
    sku: '21232',
    product_name: 'STRAWBERRY CERAMIC TRINKET BOX'
  },
  {
    sku: '37448',
    product_name: 'CERAMIC CAKE DESIGN SPOTTED MUG'
  },
  {
    sku: '37494A',
    product_name: 'FAIRY CAKE CERAMIC BUTTER DISH'
  },
  {
    sku: '21700',
    product_name: 'BIG DOUGHNUT FRIDGE MAGNETS'
  },
  {
    sku: '47556B',
    product_name: 'TEA TIME TEA TOWELS'
  },
  {
    sku: '22055',
    product_name: 'MINI CAKE STAND  HANGING STRAWBERY'
  },
  {
    sku: '37446',
    product_name: 'MINI CAKE STAND WITH HANGING CAKES'
  },
  {
    sku: '84569D',
    product_name: 'PACK 6 HEART/ICE-CREAM PATCHES'
  },
  {
    sku: '22209',
    product_name: 'WOOD STAMP SET HAPPY BIRTHDAY'
  },
  {
    sku: '22210',
    product_name: 'WOOD STAMP SET BEST WISHES'
  },
  {
    sku: '22208',
    product_name: 'WOOD STAMP SET THANK YOU'
  },
  {
    sku: '21428',
    product_name: 'SET3 BOOK BOX GREEN GINGHAM FLOWER'
  },
  {
    sku: '21430',
    product_name: 'SET/3 RED GINGHAM ROSE STORAGE BOX'
  },
  {
    sku: '21884',
    product_name: 'CAKES AND BOWS GIFT  TAPE'
  },
  ]
  openEditDialog(): void {
    const dialogRef = this.dialog.open(EditApprovePo, {
      width: '600px',
      data: {
        poId: this.poId,
        sku: this.sku,
        recommendedQuantity: this.recommendedQuantity,
        supplier: this.suppliers.find(s => s.name.toLowerCase() == this.supplier.toLowerCase())?.id
      }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.loadRecentPurchaseOrders();
        this.snack.open('PO updated successfully!', 'Close', { duration: 2000 });
      }
    });
  }

  ngOnInit(): void {
    this.agentWorkingMessageQueue$.pipe(concatMap((msg)=> this.showAgentWorkingSnackBarMessage(msg))).subscribe();

    // Initialize form with nulls first
    this.getRecommendationsForm = this.fb.group({
      storeId: [null],
      sku: [null],
      forecastDays: [15]
    });

    // Once storeList and skuProductList are loaded (e.g., via API), set defaults
    const storeId = localStorage.getItem("replenish_store_id")
      ? Number(localStorage.getItem("replenish_store_id"))
      : (this.storeList && this.storeList.length > 0 ? this.storeList[0].id : null);

    const sku = localStorage.getItem("replenish_product_Id")
      ? localStorage.getItem("replenish_product_Id")
      : (this.skuProductList && this.skuProductList.length > 0 ? this.skuProductList[0].sku : null);

    this.getRecommendationsForm.patchValue({ storeId, sku });

    // initialize prev values so the first patchValue doesn't trigger clearing
    this.prevStoreId = storeId;
    this.prevSku = sku;

    // Watch for dropdown changes (storeId or sku). When either changes, hide the recommendation table and re-enable create.
    this.formWatcherSub = this.getRecommendationsForm.valueChanges.subscribe((vals: any) => {
      const storeChanged = vals.storeId !== this.prevStoreId;
      const skuChanged = vals.sku !== this.prevSku;

      if (storeChanged || skuChanged) {
        // Clear recommendation table and PO-specific fields
        if (this.dataSource && this.dataSource.length > 0) {
          this.dataSource = [];
        }
        this.poId = 0;
        this.sku = '';
        this.recommendedQuantity = 0;
        this.supplier = '';

        // Re-enable create button when user changes dropdowns
        this.canCreate = true;

        // If a websocket listener is active, stop it because the context changed
        this.stopWebsocketListener();

        this.cdr.detectChanges();
      }

      // update prev values for next comparison
      this.prevStoreId = vals.storeId;
      this.prevSku = vals.sku;
    });

    setTimeout(() => this.loadRecentPurchaseOrders());
  }

  //Load recent purchase orders
  loadRecentPurchaseOrders(): void{
      this.productService.getRecentPurchaseOrders().subscribe({
        next: (response) => {
          this.recentProducts = response;
          this.recentPoDataSource.data=response;
          this.cdr.detectChanges();
        },
        error: (err) => {
          console.error("Error loading Recent Purchase Orders!", err);
        }
      });
    }

    // Filter data by status
    applyFilter(selectedStatus:string): void{
      if (!selectedStatus) {
        this.recentPoDataSource.filter = '';
        return;
      }

      this.recentPoDataSource.filterPredicate = (data: recentProduct, filter: string) =>
        data.status.trim().toLowerCase() === filter.trim().toLowerCase();

      this.recentPoDataSource.filter = selectedStatus.trim().toLowerCase();
      this.cdr.detectChanges();
    }

  getRecommendations() {
    // Prevent repeated clicks when disabled or while loading
    if (!this.canCreate || this.isRecommendationLoading) {
      return;
    }

    // Start loading indicator
    this.isRecommendationLoading = true;
    this.errorMessage = null;
    this.cdr.detectChanges();

    console.groupCollapsed('getRecommendations — start');
    console.time('getRecommendations duration');

    // Log form inputs at start
    const skuInput = this.getRecommendationsForm.controls['sku'].value;
    const storeIdInput = this.getRecommendationsForm.controls['storeId'].value;
    const horizonDaysInput = this.getRecommendationsForm.controls['forecastDays'].value;
    console.log('Inputs', { sku: skuInput, storeId: storeIdInput, horizon_days: horizonDaysInput });

    const requestBody = {
      sku: skuInput,
      store_id: storeIdInput,
      horizon_days: horizonDaysInput
    };
    console.log('Request body prepared', requestBody);

    // Helper to safely stringify objects that might contain circular refs
    const safeStringify = (obj: any) => {
      try {
        return JSON.stringify(obj);
      } catch {
        const cache = new Set();
        return JSON.stringify(obj, (key, value) => {
          if (typeof value === 'object' && value !== null) {
            if (cache.has(value)) return '[Circular]';
            cache.add(value);
          }
          return value;
        });
      }
    };

    console.log('Calling listenToAgentUpdates()');
    this.listenToAgentUpdates();

    this.errorMessage = null;
    console.log('Cleared errorMessage', { errorMessage: this.errorMessage });

    this.cdr.detectChanges();
    console.log('Called cdr.detectChanges() after initial state updates');

    // Create recommendation
    console.log('Calling productService.getRecommendations()');
    this.productService.getRecommendations(requestBody).subscribe({
      next: (res) => {
        console.groupCollapsed('getRecommendations — next (success)');
        console.log('Raw response', safeStringify(res));

        this.isRecommendationLoading = false;
        console.log('State change', { isRecommendationLoading: this.isRecommendationLoading });

        // Remember the inputs used to create this recommendation
        this.lastCreatedStoreId = storeIdInput;
        this.lastCreatedSku = skuInput;

        // Now that we have a successful recommendation and the table will be shown,
        // disable the Create button until the user changes store or sku.
        this.canCreate = false;

        this.cdr.detectChanges();
        console.log('Called cdr.detectChanges() after receiving response');

        // Filter out Forecast CI and Forecast Mean
        const entries = Object.entries(res);
        console.log('Response entries count', entries.length);

        const filtered = entries
          .filter(([key]) => key !== 'Forecast CI' && key !== 'Forecast Mean');
        console.log('Filtered entries (excluded Forecast CI and Forecast Mean)', filtered.map(([k]) => k));

        this.dataSource = filtered
          .map(([key, value]) => ({
            Metric: key,
            Value: Array.isArray(value) ? value.join(',') : value
          }));
        console.log('Transformed dataSource', safeStringify(this.dataSource));

        // Assign specific fields
        this.poId = res['PO ID'];
        this.sku = res['SKU'];
        this.recommendedQuantity = res['Recommended Qty'];
        this.supplier = res['Supplier'];
        console.log('Assigned fields', {
          poId: this.poId,
          sku: this.sku,
          recommendedQuantity: this.recommendedQuantity,
          supplier: this.supplier
        });

        console.log('Calling loadRecentPurchaseOrders()');
        this.loadRecentPurchaseOrders();

        this.cdr.detectChanges();
        console.log('Called cdr.detectChanges() after processing success path');

        console.timeEnd('getRecommendations duration');
        console.groupEnd(); // end success group
        console.groupEnd(); // end main group
      },
      error: (err) => {
        console.groupCollapsed('getRecommendations — error');
        console.error('Received error from getRecommendations', safeStringify(err));

        console.log('Calling stopWebsocketListener() due to error');
        this.stopWebsocketListener();

        this.isRecommendationLoading = false;
        console.log('State change', { isRecommendationLoading: this.isRecommendationLoading });

        // Allow user to retry immediately after an error
        this.canCreate = true;

        this.errorMessage = err.error?.detail?.message
          ? err.error.detail.message
          : "Recommendation creation unsuccessful!";
        console.log('Set errorMessage', { errorMessage: this.errorMessage });

        this.cdr.detectChanges();
        console.log('Called cdr.detectChanges() after error handling');

        console.timeEnd('getRecommendations duration');
        console.groupEnd(); // end error group
        console.groupEnd(); // end main group
      }
    });
  }

  // Show which Agent is working behind the scene while creating recommendation
  private showAgentWorkingSnackBarMessage(message: string): Observable<any> {
    return new Observable((observer) => {
      const ref = this.snack.open(message, 'Close', { duration: 3000, horizontalPosition: 'center', verticalPosition: 'bottom', panelClass: ['ws-snackbar'] });
      ref.afterDismissed().subscribe(() => {
        observer.complete();
      });
    });
  }

  // Start listening to websocket to get status of type of agent working
  private listenToAgentUpdates() {
    if(this.wsSubscription){
      return;
    }
    this.wsSubscription = this.productService.connectToWebSocket().subscribe({
      next: (message) => {
          this.loading = true;
          this.agentWorkingMessageQueue$.next(message.status);
          this.cdr.detectChanges();
      },
    error: (err) => {
        this.loading = false;
        this.cdr.detectChanges();
      },
      complete: () => {
        this.loading = false;
        this.cdr.detectChanges();
      }
    })
  }

  // stop listening to websocket
  stopWebsocketListener() {
      if (this.wsSubscription) {
        this.wsSubscription.unsubscribe();
        this.wsSubscription = undefined;
      }
      this.productService.disconnectFromWebSocket();
  }

  // Approve Recommendation
  approveRecommendation() {
    this.poApprovalPending = true;
    let approvePoRequestBody = {
      "po_id": this.poId
    }
    this.productService.approvePurchaseOrder(approvePoRequestBody).subscribe({
      next: (res) => {
        this.poApprovalPending = false;
        this.loadRecentPurchaseOrders();
        this.cdr.detectChanges();
        this.snack.open('PO Approved!', 'Close', { duration: 2000 });
      },
      error: (err) => {
        this.poApprovalPending = false;
        this.cdr.detectChanges();
        console.error("Approve PO Error", err);
      }
    });
  }

  ngOnDestroy(){
    // stop listening to websocket
    this.stopWebsocketListener();
    if (this._formChangeSub) {
      this._formChangeSub.unsubscribe();
      this._formChangeSub = undefined;
    }
    if (this.formWatcherSub) {
      this.formWatcherSub.unsubscribe();
      this.formWatcherSub = undefined;
    }
  }
}
