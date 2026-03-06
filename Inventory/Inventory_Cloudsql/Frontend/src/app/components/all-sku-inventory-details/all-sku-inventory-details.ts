import { Component, OnInit } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { AddProductComponent } from '../add-product/add-product';
import { MatTableModule , MatTableDataSource} from '@angular/material/table';
import { ProductService } from '../../services/product';
import { MatDialog } from '@angular/material/dialog';
import { ChangeDetectorRef } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { CommonModule } from '@angular/common';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

interface Product {
  image_data: string;
  name: string;
  sku: string;
  category: string;
  store_id:number;
  location: string;
  on_hand: number;
  inTransit: number;
  safety_stock: number;
  reorder_point: number;
}

@Component({
  selector: 'app-all-sku-inventory-details',
  standalone: true,
  imports: [MatIconModule, MatTableModule, CommonModule, MatProgressSpinnerModule],
  templateUrl: './all-sku-inventory-details.html',
  styleUrl: './all-sku-inventory-details.css'
})
export class AllSkuInventoryDetails implements OnInit {
dataSource:any = [];
loading = false;

displayedPOColumns: string[] = ['image','name', 'sku', 'category', 'store_id','location', 'on_hand', 'in_transit','safety_stock', 'reorder_point', 'actions'];
datasource=new MatTableDataSource<Product>();
constructor(private snack: MatSnackBar, private productService:ProductService, private dialog: MatDialog, private cdr: ChangeDetectorRef){}

 loadInventoryOverviewPurchaseOrderData(): void{
    this.loading = true;
    this.cdr.detectChanges();
    this.productService.getAllSkuDetailsData().subscribe({
    next: (response) => {
      //assign data to table
      this.datasource.data = response.map((item : any) => ({
          ...item,
          image:`data:image_data/jpeg;base64,${item.image_data}`
      }));
      //update loader
      this.loading = false;
      this.cdr.detectChanges();
    },
      error: (err) => {
        this.loading = false;
        this.cdr.detectChanges();
        this.snack.open('Failed to load SKU inventory details.', 'Close', {
          duration: 2000,
        });
      }
  });
  }

  ngOnInit(): void {
    setTimeout(() => this.loadInventoryOverviewPurchaseOrderData());
  }

 /** ADD PRODUCT */
  openAddProductDialog() {
    const ref = this.dialog.open(AddProductComponent, {
      width: '720px',
      data: { mode: 'add' as const }
    });

    ref.afterClosed().subscribe((result: Product | undefined) => {
      if (result) {
        // const data = this.datasource.data;
        // data.unshift(result);
        // this.datasource.data = [...data];
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

}
