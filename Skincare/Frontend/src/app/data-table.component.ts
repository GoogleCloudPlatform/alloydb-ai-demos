// data-table.component.ts
import {CommonModule} from '@angular/common';
import {Component, Input, OnChanges} from '@angular/core';
import {MatTableModule} from '@angular/material/table';
// Removed MatPaginatorModule import

// Define interfaces for the table data
export interface TableColumn {
  key: string;
  header: string;
}

export interface TableData {
  columns: TableColumn[];
  rows: any[];
}

@Component({
  selector: 'app-data-table',
  standalone: true,
  imports: [CommonModule, MatTableModule],
  template: `
    <div class="table-container">
      <table mat-table [dataSource]="getRows()" class="mat-elevation-z0">
        <!-- Dynamic columns -->
        <ng-container *ngFor="let column of getColumns()" [matColumnDef]="column.key">
          <th mat-header-cell *matHeaderCellDef>{{ column.header }}</th>
          <td mat-cell *matCellDef="let element">{{ element[column.key] }}</td>
        </ng-container>

        <tr mat-header-row *matHeaderRowDef="getColumnKeys()"></tr>
        <tr mat-row *matRowDef="let row; columns: getColumnKeys();"></tr>
      </table>
    </div>
  `,
  styles: [
    `
    .table-container {
      overflow-x: auto;
      max-width: 100%;
    }

    table {
      width: 100%;
      border-radius: 8px;
      overflow: hidden;
      --mat-table-header-headline-color: var(--skin-care-primary);
      --mat-table-header-headline-font: "DM Sans";
      --mat-table-header-headline-line-height: normal;
      --mat-table-header-headline-size: 16px;
      --mat-table-header-headline-weight: 500;
      --mat-table-header-headline-tracking: normal;

      --mat-table-row-item-label-text-color: var(--skin-care-primary);
      --mat-table-row-item-label-text-font: "DM Sans";
      --mat-table-row-item-label-text-line-height: normal;
      --mat-table-row-item-label-text-size: 16px;
      --mat-table-row-item-label-text-weight: 400;
      --mat-table-row-item-label-text-tracking: normal;

      --mat-table-footer-supporting-text-color: var(--skin-care-primary);
      --mat-table-footer-supporting-text-font: "DM Sans";
      --mat-table-footer-supporting-text-line-height: normal;
      --mat-table-footer-supporting-text-size: 16px;
      --mat-table-footer-supporting-text-weight: 400;
      --mat-table-footer-supporting-text-tracking: normal;

      --mat-table-row-item-outline-color: var(--skin-care-search-outline);
      --mat-table-background-color: #FAFAFA;
    }

    th.mat-header-cell {
      font-weight: bold;
      background-color: #f5f5f5;
    }
  `,
  ],
})
export class DataTableComponent implements OnChanges {
  @Input() data: any[] | TableData = [];
  private columns: TableColumn[] = [];
  private rows: any[] = [];

  ngOnChanges() {
    this.processData();
  }

  private processData() {
    // Check if data is a TableData object
    if (!Array.isArray(this.data) && this.data && 'rows' in this.data) {
      console.log('DataTableComponent: Processing TableData object');
      this.rows = this.data.rows || [];
      this.columns = this.data.columns || [];

      // If no columns provided but we have rows, generate columns from first row
      if (this.columns.length === 0 && this.rows.length > 0) {
        this.columns = Object.keys(this.rows[0]).map((key) => ({
          key,
          header: this.formatColumnHeader(key),
        }));
      }
    }
    // If data is an array, treat it as rows and generate columns
    else if (Array.isArray(this.data)) {
      console.log('DataTableComponent: Processing array data');
      this.rows = this.data;

      if (this.rows.length > 0) {
        this.columns = Object.keys(this.rows[0]).map((key) => ({
          key,
          header: this.formatColumnHeader(key),
        }));
      } else {
        this.columns = [];
      }
    } else {
      console.log('DataTableComponent: No valid data format found');
      this.rows = [];
      this.columns = [];
    }

    console.log(
      'DataTableComponent: Rows =',
      this.rows.length,
      'Columns =',
      this.columns.length,
    );
  }

  // Helper methods to get data for the template
  getRows(): any[] {
    return this.rows;
  }

  getColumns(): TableColumn[] {
    return this.columns;
  }

  getColumnKeys(): string[] {
    return this.columns.map((col) => col.key);
  }

  formatColumnHeader(column: string): string {
    // Convert snake_case or camelCase to Title Case
    return column
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .replace(/^\w/, (c) => c.toUpperCase());
  }
}
