import { isPlatformBrowser } from '@angular/common';
import { Inject, NgZone, PLATFORM_ID } from '@angular/core';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import {
  Component,
  ElementRef,
  OnInit,
  OnDestroy,
  ViewChild,
  AfterViewInit,
  ChangeDetectorRef,
  TemplateRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ProductService } from '../../services/product';
import { Chart, ChartType, registerables } from 'chart.js';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { AddProductComponent } from '../add-product/add-product';
import { MatButtonModule } from '@angular/material/button';
import { FormsModule } from '@angular/forms';
import { MatInputModule } from '@angular/material/input';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

Chart.register(...registerables);

interface Product {
  image_data?: string;
  product_name?: string;
  name?: string;
  sku: string;
  category?: string | null;
  store_id?: string | number | null;
  location?: string;
  on_hand?: number;
  in_transit?: number;
  safety_stock?: number;
  reorder_point?: number;
  status?: string;
  image?: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    MatTableModule,
    CommonModule,
    MatCardModule,
    MatSelectModule,
    MatProgressSpinnerModule,
    MatTabsModule,
    MatIconModule,
    MatFormFieldModule,
    MatButtonModule,
    MatDialogModule,
    FormsModule,
    MatInputModule
  ],
  templateUrl: './inventory-dashboard.html',
  styleUrls: ['./inventory-dashboard.scss']
})
export class DashboardComponent implements OnInit, AfterViewInit, OnDestroy {

  @ViewChild('doughnutCanvas') doughnutCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('doughnutContainer') doughnutContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('barCanvas') barCanvas!: ElementRef<HTMLCanvasElement>;

  dataSource: any = [];
  loading = false;
  activeCard: 'Low Stock Items' | 'Over Stock Items' | 'Critical Stock Items' | null = null;

  displayedPOColumns: string[] = ['image', 'name', 'sku', 'location', 'on_hand', 'in_transit', 'safety_stock', 'reorder_point', 'actions'];
  datasource = new MatTableDataSource<Product>();

  private doughnutChart?: Chart;
  private barChart?: Chart;

  // <-- initialize to true so template doesn't observe false->true during CD
  isDonutChartLoading = true;

  // show spinner while bar chart data is loading
  isBarChartLoading = true;

  totalSkus = 0;
  lowStock = 0;
  overStock = 0;
  critical = 0;

  displayedTabsColumns: string[] = [
    'image',
    'product',
    'sku',
    'location',
    'onHand',
    'inTransit',
    'safetyStock',
    'actions'
  ];

  tabsDataSource = new MatTableDataSource<Product>();
  currentTabName = '';

  isLoading = false;
  isKpiCardsLoading = false;

  // dialog refs and data for template dialog
  private currentDialogRef?: MatDialogRef<any>;
  currentDialogData: any = null;

  // forecast chart and loading state for dialog
  private forecastChart?: Chart;
  isForecastLoading = false;
  tempModelName = '';
  constructor(
    private snack: MatSnackBar,
    private cdr: ChangeDetectorRef,
    private productService: ProductService,
    private dialog: MatDialog,
    private router: Router,
    private ngZone: NgZone,
    @Inject(PLATFORM_ID) private platformid: Object
  ) { }

  ngAfterViewInit(): void {
    if (!isPlatformBrowser(this.platformid)) {
      return;
    }

    // create base donut chart after view init (deferred to avoid CD conflicts)
    setTimeout(() => {
      this.createDonutChart();

      // load charts after creation
      setTimeout(() => {
        this.isBarChartLoading = true; // start spinner for bar chart
        this.loadBarChartData();
        this.loadDoughnutChartData();
      }, 0);
    }, 0);
  }

  ngOnInit(): void {
    window.scrollTo(0, 0);
    this.loadInventoryOverviewData();
    localStorage.setItem("replenish_product_Id", "");
    localStorage.setItem("replenish_store_id", "");
    // this.loadLowStockItems();
    // other data loads that don't depend on view
    setTimeout(() => this.loadInventoryOverviewPurchaseOrderData());
  }

  loadInventoryOverviewPurchaseOrderData(): void {
    this.loading = true;
    this.cdr.detectChanges();
    this.productService.getAllSkuDetailsData().subscribe({
      next: (response) => {
        // map images but avoid heavy synchronous work if possible
        this.datasource.data = response.map((item: any) => ({
          ...item,
          image: item.image_data ? `data:image_data/jpeg;base64,${item.image_data}` : item.image || ''
        }));
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.loading = false;
        this.cdr.detectChanges();
        this.snack.open('Failed to load SKU inventory details.', 'Close', { duration: 2000 });
      }
    });
  }

  /** ADD PRODUCT */
  openAddProductDialog() {
    const ref = this.dialog.open(AddProductComponent, {
      width: '720px',
      data: { mode: 'add' as const }
    });

    ref.afterClosed().subscribe((result: Product | undefined) => {
      if (result) {
        this.loadInventoryOverviewPurchaseOrderData();
        this.cdr.detectChanges();
        this.snack.open('Product added successfully', 'Close', { duration: 2000 });
      }
    });
  }

  /** EDIT PRODUCT */
  openAddEditProductDialog(product: Product) {
    const ref = this.dialog.open(AddProductComponent, {
      width: '720px',
      data: { mode: 'edit' as const, product }
    });

    ref.afterClosed().subscribe((updated: Product | undefined) => {
      if (updated) {
        setTimeout(() => this.loadInventoryOverviewPurchaseOrderData());
        this.snack.open('Product updated successfully', 'Close', { duration: 2000 });
      }
    });
  }

  // ===================== TABS =====================
  onCardClick(cardName: any) {
    this.isLoading = true;
    this.activeCard = cardName;
    this.currentTabName = cardName;

    if (cardName === 'Low Stock Items') {
      setTimeout(() => this.loadLowStockItems(), 800);
    } else if (cardName === 'Over Stock Items') {
      setTimeout(() => this.loadOverStockItems(), 800);
    } else if (cardName === 'Critical Stock Items') {
      setTimeout(() => this.loadCriticalItems(), 800);
    }
  }

  // when Total SKUs card is clicked, show full table + charts
  onTotalSkusClick(): void {
    this.activeCard = null;
    this.currentTabName = '';
    // reload table and charts
    this.loadInventoryOverviewPurchaseOrderData();
    if (!this.doughnutChart) {
      this.createDonutChart();
    }
    this.isBarChartLoading = true;
    this.loadBarChartData();
    this.loadDoughnutChartData();
  }

  // ===================== DONUT CHART HELPERS =====================
  private ensureDonutChartExists(): boolean {
    if (!this.doughnutCanvas?.nativeElement) return false;

    if (!this.doughnutChart) {
      this.doughnutChart = new Chart(this.doughnutCanvas.nativeElement, {
        type: 'doughnut' as ChartType,
        data: {
          labels: [],
          datasets: [{
            data: [],
            backgroundColor: ['#4F378B', '#7766a6ff', '#a2aaf7ff', '#d0d3f8ff']
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'right' } }
        }
      });
    }
    return true;
  }

  loadDoughnutChartData(): void {
    if (!isPlatformBrowser(this.platformid)) return;

    this.productService.getDoughnutChartData().subscribe({
      next: (response) => {
        if (!this.ensureDonutChartExists()) {
          setTimeout(() => this.loadDoughnutChartData(), 50);
          return;
        }

        const colorMap: Record<string, string> = {
          'Critical Stock': 'rgba(218, 10, 7, 0.87)',
          'Over Stock': 'rgba(6, 141, 232, 0.7)',
          'Low Stock': 'rgba(255, 206, 86, 0.7)',
          'Optimal Stock': 'rgba(18, 72, 72, 0.92)'
        };

        const labels = Array.isArray(response)
          ? response.map((r: any) => r.label)
          : Object.keys(response || {});
        const data = Array.isArray(response)
          ? response.map((r: any) => Number(r.value) || 0)
          : Object.values(response || {}).map(v => Number(v) || 0);

        this.doughnutChart!.data.labels = labels;
        this.doughnutChart!.data.datasets[0].data = data;
        this.doughnutChart!.data.datasets[0].backgroundColor = labels.map(label => colorMap[label] || 'rgba(150,150,150,0.7)');
        this.doughnutChart!.update();

        this.isDonutChartLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isDonutChartLoading = false;
        this.cdr.detectChanges();
        this.snack.open('Error loading doughnut chart data!', 'Close', { duration: 2000 });
      }
    });
  }


  // ===================== BAR CHART =====================
  loadBarChartData(): void {
    // start spinner
    this.isBarChartLoading = true;
    this.cdr.detectChanges();

    const colorMap: any = {
      'Critical Stock': 'rgba(218, 10, 7, 0.87)',
      'Over Stock': 'rgba(6, 141, 232, 0.7)',
      'Low Stock': 'rgba(255, 206, 86, 0.7)',
      'Optimal Stock': 'rgba(18, 72, 72, 0.92)'
    };

    this.productService.getBarChartData().subscribe({
      next: (response) => {
        const allStatuses = new Set<string>();
        for (const store of Object.keys(response || {})) {
          (response[store] || []).forEach((item: any) => {
            if (item && item.Status) allStatuses.add(item.Status);
          });
        }

        const labels = Object.keys(response || {});
        const statusArray = Array.from(allStatuses);

        const datasets = statusArray.map(status => ({
          label: status,
          backgroundColor: colorMap[status] || 'rgba(150,150,150,0.7)',
          data: labels.map(store => {
            const match = (response[store] || []).find((x: any) => x.Status === status);
            return match ? Number(match.Count) || 0 : 0;
          })
        }));

        try {
          if (this.barChart) {
            this.barChart.destroy();
            this.barChart = undefined;
          }
        } catch { }

        if (!this.barCanvas?.nativeElement) {
          setTimeout(() => this.loadBarChartData(), 50);
          return;
        }

        try {
          this.barChart = new Chart(this.barCanvas.nativeElement, {
            type: 'bar' as ChartType,
            data: { labels, datasets },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              scales: { y: { beginAtZero: true } }
            }
          });
        } catch { }

        // stop spinner after chart created
        this.isBarChartLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isBarChartLoading = false;
        this.cdr.detectChanges();
        this.snack.open('Error loading bar chart data!', 'Close', { duration: 2000 });
      }
    });
  }

  private createDonutChart(): void {
    this.isBarChartLoading = true;
    if (!this.doughnutCanvas?.nativeElement) return;
    try { this.doughnutChart?.destroy(); } catch { }
    const colorMap: Record<string, string> = {
      'Critical Stock': 'rgba(218, 10, 7, 0.87)',
      'Over Stock': 'rgba(6, 141, 232, 0.7)',
      'Low Stock': 'rgba(255, 206, 86, 0.7)',
      'Optimal Stock': 'rgba(18, 72, 72, 0.92)'
    };
    const labels = ['Critical Stock', 'Over Stock', 'Low Stock', 'Optimal Stock'];
    this.doughnutChart = new Chart(this.doughnutCanvas.nativeElement, {
      type: 'doughnut' as ChartType,
      data: {
        labels,
        datasets: [{
          data: [],
          backgroundColor: labels.map(label => colorMap[label])
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'right' } }
      }
    });
    this.isBarChartLoading = false;
    this.cdr.detectChanges();
    // IMPORTANT: do not toggle isDonutChartLoading here.
  }

  //Load Low stock items
  loadLowStockItems(): void {
    this.isLoading = true;
    this.cdr.detectChanges();
    this.productService.getLowStockItems().subscribe({
      next: (response) => {
        this.isLoading = false;
        this.tabsDataSource.data = response.map((item: any) => ({
          ...item,
          image: item.image_data ? `data:image_data/jpeg;base64,${item.image_data}` : item.image || ''
        }));
        this.cdr.detectChanges();
      },
      error: () => {
        this.isLoading = false;
        this.tabsDataSource.data = [];
        this.cdr.detectChanges();
        this.snack.open('Error loading Low stock items!', 'Close', { duration: 2000 });
      }
    });
  }

  //Load over stock items
  loadOverStockItems(): void {
    this.isLoading = true;
    this.cdr.detectChanges();
    this.productService.getOverStockItems().subscribe({
      next: (response) => {
        this.isLoading = false;
        this.tabsDataSource.data = response.map((item: any) => ({
          ...item,
          image: item.image_data ? `data:image_data/jpeg;base64,${item.image_data}` : item.image || ''
        }));
        this.cdr.detectChanges();
      },
      error: () => {
        this.isLoading = false;
        this.tabsDataSource.data = [];
        this.cdr.detectChanges();
        this.snack.open('Error loading Over stock items!', 'Close', { duration: 2000 });
      }
    });
  }

  //Load Critical stock items
  loadCriticalItems(): void {
    this.isLoading = true;
    this.productService.getCriticalStockItems().subscribe({
      next: (response) => {
        this.isLoading = false;
        this.tabsDataSource.data = response.map((item: any) => ({
          ...item,
          image: item.image_data ? `data:image_data/jpeg;base64,${item.image_data}` : item.image || ''
        }));
        this.cdr.detectChanges();
      },
      error: () => {
        this.isLoading = false;
        this.tabsDataSource.data = [];
        this.cdr.detectChanges();
        this.snack.open('Error loading Critical stock items!', 'Close', { duration: 2000 });
      }
    });
  }

  loadInventoryOverviewData(): void {
    this.isKpiCardsLoading = true;
    this.productService.getInventoryOverviewData().subscribe({
      next: (response) => {
        this.isKpiCardsLoading = false;
        this.totalSkus = response.metrics.total_skus;
        this.lowStock = response.metrics.low_stock_items;
        this.overStock = response.metrics.overstock_items;
        this.critical = response.metrics.critical_items;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isKpiCardsLoading = false;
        this.cdr.detectChanges();
        this.snack.open('Error loading inventory overview data!', 'Close', { duration: 2000 });
      }
    });
  }

  // ===================== Replenish dialog (template) =====================
  openReplenishDialog(item: any, tpl: TemplateRef<any>) {
    this.currentDialogData = { ...item };
    this.currentDialogRef = this.dialog.open(tpl, {
      width: '900px', // desired width
      maxWidth: '95vw', // responsive cap
      height: '640px', // desired height
      maxHeight: '90vh', // responsive cap
      panelClass: 'replenish-large-dialog' // custom class for extra styling
    });

    // start forecast loading
    this.isForecastLoading = true;
    this.cdr.detectChanges();

    // prepare payload: use sku and store_id from item, horizon_days = 15
    const payload = {
      sku: String(item.sku ?? item.SKU ?? ''),
      store_id: Number(item.store_id ?? item.storeId ?? item.store ?? 0),
      horizon_days: 15
    };

    // call forecast API (ensure ProductService has getReplenishForecast)
    this.productService.getReplenishForecast(payload).subscribe({
      next: (resp: any) => {
        const forecast = resp?.result?.quantity_forecast || {};
        this.tempModelName = resp?.result?.model_name ?? '';
        const historical = Array.isArray(forecast.historical_data) ? forecast.historical_data : [];
        const forecastData = Array.isArray(forecast.forecast_data) ? forecast.forecast_data : [];

        // render chart after DOM is ready
        setTimeout(() => {
          this.renderForecastChart(historical, forecastData);
          this.isForecastLoading = false;
          // stop loader once chart is rendered (renderForecastChart will also set flag, but ensure here)
          // renderForecastChart sets isForecastLoading = false after chart creation
        }, 0);
      },
      error: (err: HttpErrorResponse) => {
        this.isForecastLoading = false;
        this.cdr.detectChanges();
        this.snack.open('Error loading replenishment forecast!', 'Close', { duration: 3000 });
      }
    });

    this.currentDialogRef.afterClosed().subscribe(() => {
      try { this.forecastChart?.destroy(); } catch { }
      this.forecastChart = undefined;
      this.currentDialogRef = undefined;
      this.currentDialogData = null;
    });
  }

  closeDialog() {
    this.currentDialogRef?.close();
  }

  submitReplenish() {
    this.currentDialogRef?.close({ action: 'viewed', sku: this.currentDialogData?.sku });
    this.currentDialogData = null;
  }

  // Render combined historical + forecast chart inside dialog
  private renderForecastChart(historical: Array<any>, forecastData: Array<any>) {
    const canvas = document.getElementById('forecastCanvas') as HTMLCanvasElement | null;
    if (!canvas) {
      setTimeout(() => this.renderForecastChart(historical, forecastData), 50);
      return;
    }

    try { this.forecastChart?.destroy(); } catch { }

    // prepare arrays
    const histDates = historical.map(h => h.date);
    const histValues = historical.map(h => Number(h.quantity) || 0);

    const fcDates = forecastData.map(f => f.date);
    const fcValues = forecastData.map(f => Number(f.predicted_quantity ?? f.predictedQuantity ?? 0));

    // Helper: check if an array is empty or contains only zeros
    const isAllZeros = (arr: number[]) => {
      if (!arr || arr.length === 0) return true;
      return arr.every(v => Number(v) === 0);
    };

    // If both historical and forecast are all zeros (or empty), show "no data" message
    if (isAllZeros(histValues) && isAllZeros(fcValues)) {
      // destroy any existing chart
      try { this.forecastChart?.destroy(); } catch { }
      this.forecastChart = undefined;

      // Replace canvas area with a centered message (preserve styling)
      const parent = canvas.parentElement;
      if (parent) {
        parent.style.background = '#F7F2FA';
        parent.style.padding = '8px';
        parent.style.borderRadius = '6px';
        // remove existing canvas to avoid confusion
        canvas.style.display = 'none';
        // create or reuse a message element
        let msg = parent.querySelector('.no-forecast-data') as HTMLDivElement | null;
        if (!msg) {
          msg = document.createElement('div');
          msg.className = 'no-forecast-data';
          msg.style.display = 'flex';
          msg.style.alignItems = 'center';
          msg.style.justifyContent = 'center';
          msg.style.height = '100%';
          msg.style.color = 'rgba(0,0,0,0.6)';
          msg.style.fontSize = '14px';
          msg.style.fontWeight = '500';
          parent.appendChild(msg);
        }
        msg.textContent = 'No data to generate chart';
      }

      // stop loader and update view
      this.isForecastLoading = false;
      this.cdr.detectChanges();
      return;
    }

    // If we reach here, there is at least some non-zero data — proceed to build labels/datasets
    const labels = [...histDates, ...fcDates];

    const histDataset = [...histValues, ...fcDates.map(() => null)];

    const forecastDataset: (number | null)[] = Array(labels.length).fill(null);
    const histLen = histDates.length;
    if (histLen > 0) {
      forecastDataset[histLen - 1] = histValues[histValues.length - 1] ?? 0;
    }
    for (let i = 0; i < fcValues.length; i++) {
      forecastDataset[histLen + i] = fcValues[i];
    }

    // ensure canvas visible (in case it was hidden earlier)
    canvas.style.display = '';
    // remove any existing "no data" message
    const parent = canvas.parentElement;
    if (parent) {
      const msg = parent.querySelector('.no-forecast-data') as HTMLElement | null;
      if (msg) parent.removeChild(msg);
      parent.style.background = '#F7F2FA';
      parent.style.padding = '8px';
      parent.style.borderRadius = '6px';
    }

    this.forecastChart = new Chart(canvas, {
      type: 'line' as ChartType,
      data: {
        labels,
        datasets: [
          {
            label: 'Historical',
            data: histDataset,
            borderColor: '#6750A4',
            backgroundColor: 'rgba(79,55,139,0.06)',
            borderWidth: 2,
            pointRadius: 3,
            spanGaps: true,
            tension: 0.2,
            fill: false
          },
          {
            label: 'Forecast',
            data: forecastDataset,
            borderColor: '#6750A4',
            backgroundColor: 'rgba(230,126,34,0.04)',
            borderWidth: 2,
            pointRadius: 3,
            spanGaps: true,
            tension: 0.2,
            borderDash: [6, 6],
            pointBackgroundColor: '#6750A4',
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          x: { ticks: { maxRotation: 90, autoSkip: true }, grid: { display: false } },
          y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.06)' } }
        },
        elements: { point: { hoverRadius: 6 } }
      }
    });

    this.isForecastLoading = false;
    this.cdr.detectChanges();
  }


  // Replenish button handler: save to localStorage and navigate
  confirmReplenishAndNavigate() {
    if (!this.currentDialogData) return;

    const storeId = Number(this.currentDialogData.store_id ?? this.currentDialogData.storeId ?? 0);
    const productName = String(this.currentDialogData.product_name ?? this.currentDialogData.name ?? '');
    const productId = String(this.currentDialogData.sku ?? this.currentDialogData.name ?? '');
    try {
      localStorage.setItem('replenish_store_id', String(storeId));
      localStorage.setItem('replenish_product_name', productName);
      localStorage.setItem('replenish_product_Id', productId);
    } catch (e) {
      // ignore localStorage errors
    }

    // close dialog then navigate
    this.currentDialogRef?.close();
    setTimeout(() => this.router.navigate(['/replenishment-recommendation']), 50);
  }

  // ===================== DESTROY =====================
  ngOnDestroy(): void {
    try { this.doughnutChart?.destroy(); } catch { }
    try { this.barChart?.destroy(); } catch { }
    try { this.forecastChart?.destroy(); } catch { }
  }

  refreshPage() {
    this.router.navigate(['/dashboard']);
  }



  softReload() {
    this.ngZone.runOutsideAngular(() => {
      setTimeout(() => this.ngZone.run(() => {
        this.activeCard = null;
        this.currentTabName = '';
        this.tabsDataSource.data = [];
        // re-init logic here
        this.ngOnInit();
      }));
    });
  }


}
