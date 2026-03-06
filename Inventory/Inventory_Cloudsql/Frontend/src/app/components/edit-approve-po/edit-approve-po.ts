import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ProductService } from '../../services/product';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { ReactiveFormsModule } from '@angular/forms';
import { CommonModule} from '@angular/common';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';
import { MatIconModule } from '@angular/material/icon';
import { ChangeDetectorRef } from '@angular/core';


@Component({
  selector: 'app-edit-approve-po',
  standalone: true,
  imports: [MatProgressSpinnerModule, MatIconModule,MatDialogModule, MatFormFieldModule, ReactiveFormsModule, CommonModule, MatInputModule, MatSelectModule, MatOptionModule],
  templateUrl: './edit-approve-po.html',
  styleUrl: './edit-approve-po.css'
})
export class EditApprovePo {
editForm: FormGroup;
loading = false;
suppliers = [{
    id: 1,
    name: 'FreshMart Distributors'
  },
  {
    id: 34,
    name: 'Global Foods Ltd'
  }];

constructor(
private fb: FormBuilder,
private dialogRef: MatDialogRef<EditApprovePo>,
@Inject(MAT_DIALOG_DATA) public data: any,
private productService: ProductService,
private snackBar: MatSnackBar,
private cdr: ChangeDetectorRef
) {
this.editForm = this.fb.group({
recommendedQuantity: [data.recommendedQuantity, [Validators.required]],
supplier: [data.supplier, [Validators.required]],
});
}

// Save edited/updated PO
onSave(): void {
if (this.editForm.invalid) return;

this.loading = true;
let payload=
{
  "po_id": this.data.poId,
  "sku": this.data.sku,
  "new_supplier_id": this.editForm.value.supplier,
  "new_quantity": this.editForm.value.recommendedQuantity
}

  this.productService.updatePurchaseOrder(payload).subscribe({
    next: (res) => {
      this.loading = false;
      this.snackBar.open('Purchase Order updated successfully!', 'Close', {
        duration: 3000,
      });
      this.dialogRef.close({ ...this.data, ...payload });
      this.cdr.detectChanges();

    },
    error: (err) => {
      this.loading = false;
      this.cdr.detectChanges();
      this.snackBar.open('Failed to update PO. Try again.', 'Close', {
        duration: 3000,
      });
    }
  });
}
// CLose dialog
onCancel(): void {
this.dialogRef.close();
}
}
