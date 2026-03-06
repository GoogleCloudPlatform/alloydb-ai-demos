import { Component, OnDestroy, OnInit, ViewChild, ElementRef, ChangeDetectorRef, NgZone, ApplicationRef } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ProductService } from '../../services/product';
import { Subscription } from 'rxjs';
import { finalize } from 'rxjs/operators';
import { Chart, ChartType, registerables } from 'chart.js';
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatSliderModule } from '@angular/material/slider';
import { MatButtonModule } from '@angular/material/button';

Chart.register(...registerables);

@Component({
  selector: 'app-quantity-forecast',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    FormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatSliderModule,
    MatButtonModule
  ],
  templateUrl: './quantity-forecast.html',
  styleUrls: ['./quantity-forecast.scss'],
})
export class QuantityForecast implements OnInit, OnDestroy {
  @ViewChild('forecastCanvas', { static: false }) forecastCanvasRef!: ElementRef<HTMLCanvasElement>;

  dateStoreProductForm: FormGroup;
  loading = false;
  private sub?: Subscription;
  private forecastChart?: Chart;
  private chartRenderTimeoutId?: any;

  modelname = '';
  chartRendered = false;
  private tempModelName = '';

  /** New flag used by the template overlay to show "No data available" */
  allZero = false;

  storeList = [
    { id: 1045, location: 'Web Store' },
    { id: 1050, location: 'Bangalore Store' },
    { id: 1055, location: 'New York Store' }
  ];

  skuList = ['22130', '21432', '21232', '37448', '37494A', '21700', '47556B', '22055', '37446', '84569D', '22209', '22210', '22208', '21428', '21430', '21884', '21882', '21880', '21883', '85049C', '85049F', '20862', '20864'];

  skuProductList = [
    { sku: 'POST', product_name: 'POSTAGE' },
    { sku: '22130', product_name: 'PARTY CONE CHRISTMAS DECORATION' },
    { sku: '21432', product_name: 'SET OF 3 CASES WOODLAND DESIGN' },
    { sku: '21232', product_name: 'STRAWBERRY CERAMIC TRINKET BOX' },
    { sku: '37448', product_name: 'CERAMIC CAKE DESIGN SPOTTED MUG' },
    { sku: '37494A', product_name: 'FAIRY CAKE CERAMIC BUTTER DISH' },
    { sku: '21700', product_name: 'BIG DOUGHNUT FRIDGE MAGNETS' },
    { sku: '47556B', product_name: 'TEA TIME TEA TOWELS' },
    { sku: '22055', product_name: 'MINI CAKE STAND  HANGING STRAWBERY' },
    { sku: '37446', product_name: 'MINI CAKE STAND WITH HANGING CAKES' },
    { sku: '84569D', product_name: 'PACK 6 HEART/ICE-CREAM PATCHES' },
    { sku: '22209', product_name: 'WOOD STAMP SET HAPPY BIRTHDAY' },
    { sku: '22210', product_name: 'WOOD STAMP SET BEST WISHES' },
    { sku: '22208', product_name: 'WOOD STAMP SET THANK YOU' },
    { sku: '21428', product_name: 'SET3 BOOK BOX GREEN GINGHAM FLOWER' },
    { sku: '21430', product_name: 'SET/3 RED GINGHAM ROSE STORAGE BOX' },
    { sku: '21884', product_name: 'CAKES AND BOWS GIFT  TAPE' }
  ];

  constructor(
    private fb: FormBuilder,
    private productService: ProductService,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone,
    private appRef: ApplicationRef
  ) {
    this.dateStoreProductForm = this.fb.group({
      storeId: ['', Validators.required],
      sku: ['', Validators.required],
      horizon: [0, [Validators.required, Validators.min(0), Validators.max(30)]]
    });
  }

  ngOnInit(): void {
    window.scrollTo(0, 0);
    console.debug('ChangeDetectionStrategy:', this.detectChangeDetectionStrategy());
    console.debug('initial loading:', this.loading);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    try { this.forecastChart?.destroy(); } catch { }
    if (this.chartRenderTimeoutId) {
      clearTimeout(this.chartRenderTimeoutId);
      this.chartRenderTimeoutId = undefined;
    }
  }

  /**
   * Detects compiled change detection strategy for this component.
   * Returns 'OnPush' | 'Default' | 'Unknown'
   */
  private detectChangeDetectionStrategy(): 'OnPush' | 'Default' | 'Unknown' {
    try {
      const cmp = (this as any).constructor?.ɵcmp;
      if (!cmp || typeof cmp.changeDetection === 'undefined') return 'Unknown';
      // Angular compiled constant: 0 === Default, 1 === OnPush
      return cmp.changeDetection === 1 ? 'OnPush' : 'Default';
    } catch {
      return 'Unknown';
    }
  }

  /**
   * Centralized change detection helper.
   * Uses markForCheck for OnPush, detectChanges for Default, falls back to appRef.tick if needed.
   */
  private applyChangeDetection(): void {
    const strategy = this.detectChangeDetectionStrategy();
    try {
      if (strategy === 'OnPush') {
        this.cdr.markForCheck();
      } else if (strategy === 'Default') {
        this.cdr.detectChanges();
      } else {
        try { this.cdr.detectChanges(); } catch { /* noop */ }
        try { this.cdr.markForCheck(); } catch { /* noop */ }
        try { this.appRef.tick(); } catch { /* noop */ }
      }
    } catch (err) {
      try { this.appRef.tick(); } catch { /* noop */ }
    }
  }

  /**
   * Single setter for loading to centralize logging and CD calls.
   */
  private setLoading(value: boolean): void {
    this.loading = value;
    console.debug('loading ->', value, 'at', new Date().toISOString());
    this.applyChangeDetection();
  }

  private stopLoadingDeferred(): void {
    if (this.chartRenderTimeoutId) {
      clearTimeout(this.chartRenderTimeoutId);
      this.chartRenderTimeoutId = undefined;
    }

    this.ngZone.run(() => {
      if (!this.loading) return;
      this.setLoading(false);
    });
  }

  predictQuantity(): void {
    if (this.dateStoreProductForm.invalid) {
      this.dateStoreProductForm.markAllAsTouched();
      return;
    }

    // reset UI state
    this.chartRendered = false;
    this.modelname = '';
    this.tempModelName = '';
    this.allZero = false;
    this.applyChangeDetection();

    const form = this.dateStoreProductForm.value;
    const payload = {
      sku: form.sku,
      store_id: Number(form.storeId),
      horizon_days: Number(form.horizon)
    };

    this.setLoading(true);

    if (this.chartRenderTimeoutId) {
      clearTimeout(this.chartRenderTimeoutId);
    }
    this.chartRenderTimeoutId = setTimeout(() => {
      if (this.loading) {
        console.error('Chart render timed out.');
        this.stopLoadingDeferred();
      }
      this.chartRenderTimeoutId = undefined;
    }, 8000);

    this.sub = this.productService.getReplenishForecast(payload)
      .pipe(finalize(() => {
        // Always stop loader when the HTTP observable completes or errors
        try {
          this.ngZone.run(() => {
            this.setLoading(false);
          });
        } catch (e) {
          try { this.cdr.markForCheck(); } catch { /* noop */ }
          try { this.appRef.tick(); } catch { /* noop */ }
        }

        if (this.chartRenderTimeoutId) {
          clearTimeout(this.chartRenderTimeoutId);
          this.chartRenderTimeoutId = undefined;
        }

        console.log('[finalize] request completed, loader stopped');
      }))
      .subscribe({
        next: async (res: any) => {
          const qf = res?.result?.quantity_forecast;
          this.tempModelName = res?.result?.model_name ?? '';

          if (qf) {
            const historical = qf.historical_data ?? qf.historical ?? [];
            const forecast = qf.forecast_data ?? qf.forecast_output ?? qf.forecast ?? [];
            try {
              // render chart (resolves back inside Angular zone)
              await this.renderForecastChart(historical, forecast);

              const sanitized = String(this.tempModelName ?? '').replace(/[\u0000-\u001F\u007F-\u009F]/g, '');

              // Consolidated UI update inside Angular zone so change detection runs immediately
              this.ngZone.run(() => {
                // If allZero is true, we intentionally do not set chartRendered true
                if (!this.allZero) {
                  this.modelname = sanitized;
                  this.chartRendered = true;
                } else {
                  this.modelname = '';
                  this.chartRendered = false;
                }
                console.debug('UI updated: modelname set, chartRendered', this.chartRendered);
                // do not rely solely on this to stop loader; finalize will ensure loader is stopped
                this.applyChangeDetection();
              });

              // ensure any pending timeout is cleared (defensive)
              if (this.chartRenderTimeoutId) {
                clearTimeout(this.chartRenderTimeoutId);
                this.chartRenderTimeoutId = undefined;
              }
            } catch (e) {
              console.error('renderForecastChart failed', e);
              this.ngZone.run(() => {
                this.chartRendered = false;
                this.modelname = '';
                this.applyChangeDetection();
              });
              if (this.chartRenderTimeoutId) {
                clearTimeout(this.chartRenderTimeoutId);
                this.chartRenderTimeoutId = undefined;
              }
            }
          } else {
            console.error('Unexpected response shape', res);
            this.ngZone.run(() => {
              this.chartRendered = false;
              this.modelname = '';
              this.applyChangeDetection();
            });
            if (this.chartRenderTimeoutId) {
              clearTimeout(this.chartRenderTimeoutId);
              this.chartRenderTimeoutId = undefined;
            }
          }
        },
        error: (err) => {
          console.error('API error', err);
          this.ngZone.run(() => {
            this.chartRendered = false;
            this.modelname = '';
            this.applyChangeDetection();
          });
          if (this.chartRenderTimeoutId) {
            clearTimeout(this.chartRenderTimeoutId);
            this.chartRenderTimeoutId = undefined;
          }
        }
      });
  }

  private renderForecastChart(historical: any, forecastData: any, retry = 0): Promise<void> {
    const MAX_RETRY = 10;
    const RETRY_DELAY_MS = 50;

    const mapDateMapToArray = (mapObj: Record<string, any> | undefined) => {
      if (!mapObj) return [];
      return Object.entries(mapObj)
        .map(([date, value]) => ({ date, value: Number(value ?? 0) }))
        .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    };

    const histArr = Array.isArray(historical)
      ? historical.map(h => ({ date: h.date, value: Number(h.quantity ?? h.value ?? 0) }))
      : mapDateMapToArray(historical);

    const fcArr = Array.isArray(forecastData)
      ? forecastData.map(f => ({ date: f.date, value: Number(f.predicted_quantity ?? f.predictedQuantity ?? f.value ?? 0) }))
      : mapDateMapToArray(forecastData);

    const histDates = histArr.map(h => h.date);
    const histValues = histArr.map(h => h.value);

    const fcDates = fcArr.map(f => f.date);
    const fcValues = fcArr.map(f => f.value);

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

    const canvas = this.forecastCanvasRef?.nativeElement;
    if (!canvas) {
      if (retry >= MAX_RETRY) {
        console.error('Canvas not available after retries; aborting chart render.');
        return Promise.resolve();
      }
      return new Promise((resolve) => {
        setTimeout(() => {
          this.renderForecastChart(historical, forecastData, retry + 1).then(resolve);
        }, RETRY_DELAY_MS);
      });
    }

    // --- NEW: determine if all numeric values are zero and handle overlay ---
    const combinedValues = [...histValues, ...fcValues].filter(v => v !== null && typeof v !== 'undefined');
    const hasNumeric = combinedValues.some(v => Number.isFinite(Number(v)));
    this.allZero = hasNumeric && combinedValues.every(v => Number(v) === 0);

    if (this.allZero) {
      try { this.forecastChart?.destroy(); } catch { /* noop */ }

      // optional: style parent container consistently
      const parent = canvas.parentElement;
      if (parent) {
        parent.style.background = '#F7F2FA';
        parent.style.padding = '8px';
        parent.style.borderRadius = '6px';
      }

      // ensure Angular sees the change and we do not create a heavy chart instance
      this.ngZone.run(() => {
        this.chartRendered = false;
        this.modelname = '';
        this.applyChangeDetection();
      });

      return Promise.resolve();
    }

    // If not all zeros, ensure overlay hidden and proceed to create chart
    this.allZero = false;

    return new Promise<void>((resolve) => {
      try {
        try { this.forecastChart?.destroy(); } catch { }

        const parent = canvas.parentElement;
        if (parent) {
          parent.style.background = '#F7F2FA';
          parent.style.padding = '8px';
          parent.style.borderRadius = '6px';
        }

        // create chart outside Angular for performance, but resolve back inside Angular
        this.ngZone.runOutsideAngular(() => {
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
                  borderWidth: 3,
                  pointRadius: 4,
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
              plugins: {
                legend: { position: 'top' },
                tooltip: { enabled: true }
              },
              scales: {
                x: {
                  ticks: { maxRotation: 90, autoSkip: true },
                  grid: { display: false }
                },
                y: {
                  beginAtZero: true,
                  grid: { color: 'rgba(0,0,0,0.06)' }
                }
              },
              elements: {
                point: { hoverRadius: 6 }
              }
            }
          });

          try {
            this.forecastChart.update();
          } catch (e) {
            console.warn('Chart update threw', e);
          }

          // Wait two animation frames to ensure canvas layout is stable, then resolve back in Angular zone
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              this.ngZone.run(() => resolve());
            });
          });
        });
      } catch (err) {
        console.error('Chart creation error', err);
        resolve();
      }
    });
  }

  getSelectedProductName(): string | null {
    const sku = this.dateStoreProductForm.get('sku')?.value;
    const product = this.skuProductList.find(p => p.sku === sku);
    return product ? product.product_name : null;
  }
}
