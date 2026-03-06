import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { ProductService, Product} from '../../services/product';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialogModule } from '@angular/material/dialog';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon'; // Import MatIconModule
import { ChangeDetectorRef } from '@angular/core';

export interface AddEditDialogData {
mode: 'add' | 'edit';
product?: Product;
}

@Component({
  selector: 'app-add-product',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MatDialogModule,
    MatSelectModule,
    MatIconModule
  ],
  templateUrl: './add-product.html',
  styleUrl: './add-product.css'
})

export class AddProductComponent {
addEditProductForm: FormGroup;
isEditMode= false;
saving = false;
title = 'Add Product';
loading = false;

locations = [{
    store_id: 1045,
    location: 'Web Store'
  },
  {
    store_id: 1050,
    location: 'Bangalore Store'
  },
  {
    store_id: 1055,
    location: 'New York Store'
  }];

constructor(
private fb: FormBuilder,
private dialogRef: MatDialogRef<AddProductComponent>,
private productService : ProductService,
private snack : MatSnackBar,
private cdr: ChangeDetectorRef,
@Inject(MAT_DIALOG_DATA) public data:AddEditDialogData
) {

this.isEditMode = data.mode === 'edit' ? true : false;

// Show form values as per mode. In edit mode values should pre populate.

this.addEditProductForm = this.fb.group({
sku: [{value: this.isEditMode? data.product?.sku : '', disabled: this.isEditMode? true: false}, Validators.required],
name: [{value:this.isEditMode? data.product?.product_name:'',disabled: this.isEditMode? true: false}, Validators.required],
category: [{value:this.isEditMode? data.product?.category:'',disabled: this.isEditMode? true: false}, Validators.required],
store_id: [this.isEditMode? data.product?.store_id:'', Validators.required],
on_hand: [this.isEditMode? data.product?.on_hand:'', Validators.required],
safety_stock: [this.isEditMode? data.product?.safety_stock:'', Validators.required],
reorder_point: [this.isEditMode? data.product?.reorder_point:'', Validators.required],
in_transit: [this.isEditMode? data.product?.in_transit : '', Validators.required],
location: [this.isEditMode? data.product?.location:'', Validators.required]
});


// Set respective store id on selecting location
this.addEditProductForm.get('location')?.valueChanges.subscribe(selectedLocation => {
  const found = this.locations.find(loc => loc.location === selectedLocation);
  if (found){
    this.addEditProductForm.get('store_id')?.setValue(found.store_id);
  }
  else{
    this.addEditProductForm.get('store_id')?.setValue('');
  }
})

}

// Save updated or added product
  save() {
    this.loading = true;
    this.cdr.detectChanges();
    if (this.addEditProductForm.invalid) {
      this.loading = false;
      this.addEditProductForm.markAllAsTouched();
      return;
    }
    const value: Product = {
      ...this.addEditProductForm.getRawValue()
    };
    this.saving = true;

    // Add new product
    if (this.data.mode === 'add') {
      this.productService.addProduct(value).subscribe({
        next: (created) => {
          this.loading = false;
          this.cdr.detectChanges();
          this.snack.open('Product added', 'Close', { duration: 2000 });
          this.dialogRef.close(created);
        },
        error: (err) => {
          this.loading = false;
          this.saving = false;
          this.cdr.detectChanges();
          this.snack.open(err.error.detail.length > 0 ? err.error.detail[0].msg : 'Failed to add product', 'Close', { duration: 3000 });
          this.dialogRef.close();
        }
      });
    } else {
      // Update existing product
      this.productService.updateProduct(value).subscribe({
        next: (updated) => {
          this.loading = false;
          this.snack.open('Product updated', 'Close', { duration: 2000 });
          this.dialogRef.close(updated);
        },
        error: (err) => {
          this.loading = false;
          this.snack.open('Failed to update product', 'Close', { duration: 3000 });
          this.saving = false;
        }
      });
    }
  }

// Close dialog
cancel() {
this.dialogRef.close();
}

}
