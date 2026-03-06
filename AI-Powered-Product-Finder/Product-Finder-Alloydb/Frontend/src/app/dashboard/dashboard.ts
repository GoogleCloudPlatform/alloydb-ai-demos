import { Component, OnInit, OnDestroy, ChangeDetectorRef, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ProductService, ProductModel } from '../services/product';
import { finalize } from 'rxjs/operators';
import { Chatbot } from '../chatbot/chatbot';
import { NgxSliderModule, Options } from '@angular-slider/ngx-slider';
import { Router } from '@angular/router';

type PriceSort = 'none' | 'low' | 'high';

interface RemoteResultSet {
  summary?: string;
  total?: number;
  count?: number;
  details: any[];
  sql_command?: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, HttpClientModule, FormsModule, NgxSliderModule, Chatbot],
  templateUrl: './dashboard.html',
  styleUrls: ['./dashboard.scss'],
})
export class Dashboard implements OnInit, OnDestroy {
  @ViewChild('searchInput') searchInput!: ElementRef<HTMLInputElement>;

  products: ProductModel[] = [];
  displayed: ProductModel[] = [];
  categories: string[] = [];
  brands: string[] = [];

  loading = false;
  error = '';
  query = '';

  validationMessage = '';

  selectedCategory = '';
  selectedBrand = '';
  priceSort: PriceSort = 'none';
  selectedRating = 0;

  // legacy pagination (kept for compatibility)
  perPage = 6;
  page = 1;
  total = 0;
  pages: number[] = [];
  itemsPerOptions = [6, 9, 12, 24];

  rawRemoteResults: Record<string, RemoteResultSet> = {};

  showPagination = false;

  remoteProducts: ProductModel[] = [];
  searchResultsVisible = false;

  suggestions: string[] = [
    'Black purses',
    'Nike Air Max sports shoes',
    'Shirts for men with ratings above 3',
    'Indian brand shirts, avoid solid pattern',
  ];

  infoModalOpen = false;
  infoModalMode: string | '' = '';
  infoModalTitle = '';
  infoModalSubtitle = '';
  infoModalSql = '';

  filterMessage = '';
  private _filterMsgTimer: any = null;

  showHelpBubble = true;

  pricePopupOpen = false;

  priceLimitMin = 3;
  priceLimitMax = 50;

  priceRangeMin = 3;
  priceRangeMax = 50;

  tempMin = 3;
  tempMax = 50;

  sliderOptions: Options = {
    floor: 3,
    ceil: 50,
    step: 1,
    draggableRange: true,
    translate: (value: number): string => {
      return '$' + value;
    },
  };

  searchResponseMeta: { search_type?: string; reason?: string; sql_command?: string } = {};

  private readonly STORAGE_KEY = 'dashboard_searches';

  // ---------- New independent pagination state (public so template can access) ----------
  useNewPagination = true;
  newPerPage = 6;
  newPage = 1;
  newTotal = 0;
  newPages: number[] = [];
  newPerPageOptions = [6, 9, 12, 24];

  // **NEW**: store the last filtered results so pagination always slices from the same array
  private lastFiltered: ProductModel[] = [];

  constructor(private svc: ProductService, private cdr: ChangeDetectorRef, private router: Router) { }

  ngOnInit(): void {
    this.categories = [];
    this.brands = [];

    this.svc.listCategories().pipe(finalize(() => { })).subscribe({
      next: (cats) => {
        this.categories = (cats || []).slice().sort();
        this.cdr.markForCheck();
      },
      error: (err) => {
        console.error('Failed to load categories', err);
      },
    });

    this.svc.listBrands().pipe(finalize(() => { })).subscribe({
      next: (b) => {
        this.brands = (b || []).slice().sort();
        this.cdr.markForCheck();
      },
      error: (err) => {
        console.error('Failed to load brands', err);
      },
    });

    // ensure defaults and clamp to limits
    this.priceRangeMin = Math.max(this.priceLimitMin, Math.min(this.priceRangeMin, this.priceLimitMax));
    this.priceRangeMax = Math.min(this.priceLimitMax, Math.max(this.priceRangeMax, this.priceLimitMin));
    this.tempMin = this.priceRangeMin;
    this.tempMax = this.priceRangeMax;
    this.selectedRating = 0;

    this.fetch();
  }

  ngOnDestroy(): void {
    if (this._filterMsgTimer) {
      clearTimeout(this._filterMsgTimer);
      this._filterMsgTimer = null;
    }
  }

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.total / this.perPage));
  }

  get newTotalPages(): number {
    return Math.max(1, Math.ceil(this.newTotal / this.newPerPage));
  }

  get pageRangeLabel(): string {
    if (this.total === 0) return '0-0';
    if (this.searchResultsVisible && !this.showPagination) return `1-${this.total}`;
    const start = (this.page - 1) * this.perPage + 1;
    const end = Math.min(this.total, this.page * this.perPage);
    return `${start}-${end}`;
  }

  private clearListings(): void {
    this.displayed = [];
    this.total = 0;
    this.newTotal = 0;
    this.lastFiltered = [];
    this.cdr.markForCheck();
  }

  fetch(): void {
    this.loading = true;
    this.error = '';
    this.svc
      .getAll()
      .pipe(finalize(() => (this.loading = false)))
      .subscribe({
        next: (list) => {
          this.products = (list || []).map((p) => {
            const copy: ProductModel = { ...p } as any;
            copy.reviews = Math.floor(Math.random() * 300) + 10;
            copy.roundedRate = Math.round((p as any).rating ?? 4);
            copy.unitPrice = Number((p as any).unitPrice ?? (p as any).unitprice ?? 0);
            copy.finalPrice = Number((p as any).finalPrice ?? (p as any).finalprice ?? copy.unitPrice ?? 0);
            (copy as any).brand = (p as any).brand ?? (p as any).Brand ?? '';
            const unit = Number((copy as any).unitPrice ?? 0);
            const final = Number((copy as any).finalPrice ?? unit);
            (copy as any).discountPercent = unit > 0 ? Math.round(((unit - final) / unit) * 100) : 0;
            return copy;
          });

          const brandSet = new Set<string>();
          for (const p of this.products) {
            const b = ((p as any).brand || '').toString().trim();
            if (b) brandSet.add(b);
          }

          if (!this.brands || this.brands.length === 0) {
            this.brands = Array.from(brandSet).sort();
          }

          this.total = this.products.length;
          this.buildPages();
          this.applyFilter();
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error(err);
          this.clearListings();

          if (err instanceof HttpErrorResponse) {
            if (err.status === 500) {
              this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
            } else {
              this.error = err.error?.message || err.message || `Request failed with status ${err.status}`;
            }
          } else if (typeof err === 'string' && err.includes('Http failure response') && err.includes('500')) {
            this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
          } else {
            this.error = 'Failed to load products';
          }
          this.cdr.markForCheck();
        },
      });
  }

  /**
   * applyFilter
   * - computes filtered results and stores them in lastFiltered
   * - resets newPage to 1 (so user sees first page of new filter)
   * - updates displayed slice from lastFiltered
   */
  applyFilter(): void {
    const term = (this.query || '').trim().toLowerCase();
    const source = this.searchResultsVisible ? [...this.remoteProducts] : [...this.products];

    let filtered = source;

    if (term) {
      filtered = filtered.filter(
        (p) =>
          (p.productDisplayName || '').toString().toLowerCase().includes(term) ||
          (p.masterCategory || '').toString().toLowerCase().includes(term) ||
          (p.subCategory || '').toString().toLowerCase().includes(term) ||
          (p.articleType || '').toString().toLowerCase().includes(term) ||
          (p.baseColour || '').toString().toLowerCase().includes(term)
      );
    }

    if (this.selectedCategory) {
      const catNorm = this.selectedCategory.trim().toLowerCase();
      filtered = filtered.filter((p) => (p.subCategory || '').toString().trim().toLowerCase() === catNorm);
    }

    if (this.selectedBrand) {
      const brandNorm = (this.selectedBrand || '').toString().trim().toLowerCase();
      filtered = filtered.filter((p) => ((p as any).brand || '').toString().trim().toLowerCase() === brandNorm);
    }

    if (this.selectedRating > 0) {
      filtered = filtered.filter((p) => (p.roundedRate ?? 0) >= this.selectedRating);
    }

    filtered = filtered.filter((p) => {
      const price = Number(p.finalPrice ?? p.unitPrice ?? 0);
      return price >= this.priceRangeMin && price <= this.priceRangeMax;
    });

    if (this.priceSort !== 'none') {
      const priceOf = (p: ProductModel) => Number(p.finalPrice ?? p.unitPrice ?? 0);
      filtered.sort((a, b) => {
        const pa = priceOf(a);
        const pb = priceOf(b);
        return this.priceSort === 'low' ? pa - pb : pb - pa;
      });
    }

    // Save filtered results for pagination slicing
    this.lastFiltered = filtered;
    // Reset newPage to 1 whenever filters change
    this.newPage = 1;
    // Update totals and displayed slice
    this.newTotal = this.lastFiltered.length;
    this.total = this.lastFiltered.length; // keep legacy total in sync
    this.updateDisplayedFromLastFiltered();
    this.buildNewPages();
    this.cdr.markForCheck();
  }

  // Use this to slice displayed from lastFiltered (so clicking page numbers won't re-filter)
  private updateDisplayedFromLastFiltered(): void {
    if (!this.useNewPagination) {
      // fallback to legacy behavior
      if (!this.showPagination) {
        this.page = 1;
        this.displayed = [...this.lastFiltered];
      } else {
        this.page = Math.min(this.page, Math.ceil(this.total / this.perPage) || 1);
        const start = (this.page - 1) * this.perPage;
        this.displayed = this.lastFiltered.slice(start, start + this.perPage);
      }
      this.buildPages();
      return;
    }

    // new pagination: slice from lastFiltered
    this.newPage = Math.max(1, Math.min(this.newPage, Math.ceil(this.newTotal / this.newPerPage) || 1));
    const start = (this.newPage - 1) * this.newPerPage;
    this.displayed = this.lastFiltered.slice(start, start + this.newPerPage);
  }

  private validateBeforeSearch(): boolean {
    this.validationMessage = '';
    return true;
  }

  onSearch(): void {
    this.showPagination = false;
    this.page = 1;

    if (!this.validateBeforeSearch()) return;
    this.performMultiSearch();
  }

  onSearchInput(): void {
    if (this.searchResultsVisible) {
      this.searchResultsVisible = false;
      this.remoteProducts = [];
      this.searchResponseMeta = {};
      this.showPagination = true;
      this.page = 1;
      this.applyFilter();
      this.cdr.markForCheck();
    }
  }

  performMultiSearch(): void {
    const modes = ['vector', 'hybrid', 'nltosql'];
    this.loading = true;
    this.error = '';
    this.cdr.markForCheck();

    const priceMin = Number.isFinite(this.priceRangeMin) ? this.priceRangeMin : this.priceLimitMin;
    const priceMax = Number.isFinite(this.priceRangeMax) ? this.priceRangeMax : this.priceLimitMax;

    const hasCategory = (this.selectedCategory || '').toString().trim().length > 0;
    const hasBrand = (this.selectedBrand || '').toString().trim().length > 0;
    const hasRating = (Number(this.selectedRating) || 0) > 0;
    const hasPriceRange = priceMin !== this.priceLimitMin || priceMax !== this.priceLimitMax;

    const filtersForSearch: any = {};
    if (hasCategory) filtersForSearch.category = this.selectedCategory;
    if (hasBrand) filtersForSearch.brand = this.selectedBrand;
    if (hasRating) filtersForSearch.rating = this.selectedRating;
    if (hasPriceRange) filtersForSearch.price = { min: priceMin, max: priceMax };

    const filtersForSave = Object.keys(filtersForSearch).length ? filtersForSearch : {};

    if (typeof (this.svc as any).searchMulti === 'function') {
      this.svc
        .searchMulti(modes, this.query || '', filtersForSearch)
        .pipe(finalize(() => (this.loading = false)))
        .subscribe({
          next: (res) => {
            const extractArray = (v: any): any[] | null => {
              if (!v) return null;
              if (Array.isArray(v)) return v;
              if (typeof v === 'string') {
                try {
                  const parsed = JSON.parse(v);
                  if (Array.isArray(parsed)) return parsed;
                  if (parsed && Array.isArray(parsed.details)) return parsed.details;
                } catch (e) {
                  return null;
                }
              }
              if (typeof v === 'object') {
                if (Array.isArray(v.details)) return v.details;
                if (Array.isArray(v.data?.details)) return v.data.details;
                if (Array.isArray(v.payload?.details)) return v.payload.details;
              }
              return null;
            };

            const details =
              extractArray(res.answer) ??
              extractArray(res.answer?.details) ??
              extractArray(res.details) ??
              extractArray(res.data) ??
              extractArray(res.payload) ??
              [];

            if (!res) {
              this.error = 'Empty response from search service';
              this.clearListings();
              this.rawRemoteResults = {};
              this.showPagination = true;
              this.searchResultsVisible = false;
              this.remoteProducts = [];
              this.cdr.markForCheck();
              return;
            }

            if ((res as any).error) {
              const errDetail = (res as any).error?.detail || (res as any).error?.message || '';
              if (typeof errDetail === 'string' && errDetail.toLowerCase().includes('unsupported search type')) {
                this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
              } else {
                this.error = (res as any).error?.message || (res as any).error || 'Search failed';
              }
              this.clearListings();
              this.rawRemoteResults = {};
              this.showPagination = true;
              this.searchResultsVisible = false;
              this.remoteProducts = [];
              this.cdr.markForCheck();
              return;
            }

            this.searchResponseMeta = {
              search_type: res.search_type ?? (res.answer?.search_type ?? ''),
              reason: res.reason ?? (res.answer?.reason ?? ''),
              sql_command: res.answer?.sql_command ?? '',
            };

            const remoteProducts: ProductModel[] = (details || []).map((nd: any, idx: number) => {
              const normalized = this.normalizeDetail(nd ?? {});
              const unit = Number(normalized.unitPrice ?? 0) || 0;
              const final = Number(normalized.finalPrice ?? unit) || unit;
              const rating = Number(normalized.rating ?? 0) || 0;
              const discountPercent =
                Number(
                  normalized.discountPercent ??
                  normalized.discount ??
                  (unit > 0 ? Math.round(((unit - final) / unit) * 100) : 0)
                ) || 0;

              return {
                id: normalized.id ?? `r-${idx}`,
                productDisplayName: normalized.productDisplayName ?? normalized.name ?? 'Item',
                link: normalized.link || '/assets/images/placeholder.png',
                unitPrice: unit,
                finalPrice: final,
                rating: rating,
                roundedRate: Math.round(rating),
                reviews: Math.floor(Math.random() * 300) + 10,
                brand: (normalized.brand ?? '') + '',
                discount: Number(normalized.discount ?? 0),
                discountPercent: discountPercent,
                masterCategory: normalized.masterCategory ?? '',
                subCategory: normalized.subCategory ?? '',
                articleType: normalized.articleType ?? '',
                stockCode: normalized.stockCode ?? '',
                stockStatus: normalized.stockStatus ?? '',
              } as any as ProductModel;
            });

            // set remote products and use them as source for filtering/pagination
            this.remoteProducts = remoteProducts;
            this.searchResultsVisible = true;
            this.showPagination = false;
            this.page = 1;

            // store filtered results and update pagination state
            this.lastFiltered = [...this.remoteProducts];
            this.newTotal = this.lastFiltered.length;
            this.total = this.lastFiltered.length;
            this.newPage = 1;
            this.updateDisplayedFromLastFiltered();
            this.buildNewPages();

            // persist search
            try {
              const record = this.createSearchRecord(this.remoteProducts, filtersForSave, this.searchResponseMeta);
              this.saveSearchRecord(record);
            } catch (e) {
              console.warn('Could not persist search', e);
            }

            this.cdr.markForCheck();
          },
          error: (err) => {
            console.error('searchMulti error', err);

            const errDetail = err?.error?.detail || err?.detail || err?.message || '';
            if (typeof errDetail === 'string' && errDetail.toLowerCase().includes('unsupported search type')) {
              this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
              this.clearListings();
            } else if (err instanceof HttpErrorResponse) {
              if (err.status === 500) {
                this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
              } else {
                this.error = err.error?.message || err.message || `Search failed with status ${err.status}`;
              }
              this.clearListings();
            } else if (typeof err === 'string' && err.includes('Http failure response') && err.includes('500')) {
              this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
              this.clearListings();
            } else {
              this.error = (err && err.message) ? err.message : 'Search failed. Please try again.';
              this.clearListings();
            }

            this.rawRemoteResults = {};
            this.showPagination = true;
            this.searchResultsVisible = false;
            this.remoteProducts = [];
            this.cdr.markForCheck();
          },
        });
    } else {
      // fallback: local filtering
      this.loading = false;
      this.applyFilter();
      this.showPagination = true;
      this.searchResultsVisible = false;
      this.remoteProducts = [];

      try {
        const record = this.createSearchRecord([...this.displayed], filtersForSave, { search_type: 'local' });
        this.saveSearchRecord(record);
      } catch (e) {
        console.warn('Could not persist local search', e);
      }

      this.cdr.markForCheck();
    }
  }

  // Restore to local products and clear remote results
  clearSearchResults(): void {
    this.searchResultsVisible = false;
    this.remoteProducts = [];
    this.searchResponseMeta = {};
    this.showPagination = true;
    this.page = 1;
    this.perPage = 6;
    this.applyFilter();
    this.cdr.markForCheck();
  }

  // template-required handlers
  onBrandChange(value: string): void {
    this.selectedBrand = value || '';
    this.page = 1;
    this.applyFilter();
  }

  onCategoryChange(value: string): void {
    this.selectedCategory = value || '';
    this.page = 1;
    this.applyFilter();
  }

  onRatingChange(value: string | number): void {
    const v = Number(value) || 0;
    this.selectedRating = v;
    this.page = 1;
    this.applyFilter();
  }

  onPriceSortChange(value: string): void {
    const v = (value || 'none') as PriceSort;
    this.priceSort = v;
    this.page = 1;
    this.applyFilter();
  }

  openPricePopup(): void {
    this.pricePopupOpen = true;
    this.tempMin = Math.max(this.priceLimitMin, Math.min(this.priceRangeMin, this.priceLimitMax));
    this.tempMax = Math.min(this.priceLimitMax, Math.max(this.priceRangeMax, this.priceLimitMin));
    this.cdr.markForCheck();
  }

  onMinInputChange(v: number | null | undefined): void {
    const n = Number.isFinite(Number(v)) ? Math.round(Number(v)) : NaN;
    if (!Number.isFinite(n)) return;
    this.tempMin = Math.max(this.priceLimitMin, Math.min(n, this.tempMax));
    this.cdr.markForCheck();
  }

  onMaxInputChange(v: number | null | undefined): void {
    const n = Number.isFinite(Number(v)) ? Math.round(Number(v)) : NaN;
    if (!Number.isFinite(n)) return;
    this.tempMax = Math.min(this.priceLimitMax, Math.max(n, this.tempMin));
    this.cdr.markForCheck();
  }

  closePricePopup(apply = true): void {
    if (apply) {
      this.priceRangeMin = Math.round(Math.max(this.priceLimitMin, Math.min(this.tempMin, this.tempMax)));
      this.priceRangeMax = Math.round(Math.min(this.priceLimitMax, Math.max(this.tempMax, this.tempMin)));
      this.applyFilter();
    } else {
      this.tempMin = this.priceRangeMin;
      this.tempMax = this.priceRangeMax;
    }
    this.pricePopupOpen = false;
    this.cdr.markForCheck();
  }

  pointerLeftPct(value: number): string {
    const pct = ((value - this.priceLimitMin) / (this.priceLimitMax - this.priceLimitMin)) * 100;
    return `${Math.max(0, Math.min(100, pct))}%`;
  }

  // legacy pagination (kept)
  prevPage(): void {
    if (this.page > 1) {
      this.page--;
      this.applyFilter();
    }
  }

  nextPage(): void {
    if (this.page < this.totalPages) {
      this.page++;
      this.applyFilter();
    }
  }

  goToPage(n: number): void {
    if (n >= 1 && n <= this.totalPages) {
      this.page = n;
      this.applyFilter();
    }
  }

  changePerPage(n: number): void {
    if (!n || n <= 0) return;
    this.perPage = n;
    this.page = Math.min(this.page, Math.ceil(this.total / this.perPage) || 1);
    this.applyFilter();
  }

  buildPages(): void {
    const totalPages = this.totalPages;
    const maxButtons = 2;
    let start = Math.max(1, this.page - Math.floor(maxButtons / 2));
    let end = start + maxButtons - 1;
    if (end > totalPages) {
      end = totalPages;
      start = Math.max(1, end - maxButtons + 1);
    }
    this.pages = [];
    for (let i = start; i <= end; i++) this.pages.push(i);
  }

  // ---------- New pagination helpers ----------
  private buildNewPages(): void {
    const totalPages = this.newTotalPages;
    const maxButtons = 5;
    let start = Math.max(1, this.newPage - Math.floor(maxButtons / 2));
    let end = start + maxButtons - 1;
    if (end > totalPages) {
      end = totalPages;
      start = Math.max(1, end - maxButtons + 1);
    }
    this.newPages = [];
    for (let i = start; i <= end; i++) this.newPages.push(i);
  }

  // IMPORTANT: these now only update page index and slice from lastFiltered
  newPrev(): void {
    if (this.newPage > 1) {
      this.newPage--;
      this.updateDisplayedFromLastFiltered();
      this.buildNewPages();
      this.cdr.markForCheck();
    }
  }

  newNext(): void {
    if (this.newPage < this.newTotalPages) {
      this.newPage++;
      this.updateDisplayedFromLastFiltered();
      this.buildNewPages();
      this.cdr.markForCheck();
    }
  }

  newGoToPage(n: number): void {
    if (n >= 1 && n <= this.newTotalPages) {
      this.newPage = n;
      this.updateDisplayedFromLastFiltered();
      this.buildNewPages();
      this.cdr.markForCheck();
    }
  }

  newChangePerPage(n: any): void {
    const parsed = Number(n) || this.newPerPage;
    if (!parsed || parsed <= 0) return;
    this.newPerPage = parsed;
    this.newPage = Math.min(this.newPage, Math.ceil(this.newTotal / this.newPerPage) || 1);
    this.updateDisplayedFromLastFiltered();
    this.buildNewPages();
    this.cdr.markForCheck();
  }

  // Helper methods used by template to avoid referencing global Math
  getDisplayStart(): number {
    if (this.newTotal === 0) return 0;
    return (this.newPage - 1) * this.newPerPage + 1;
  }

  getDisplayEnd(): number {
    const end = this.newPage * this.newPerPage;
    return end < this.newTotal ? end : this.newTotal;
  }

  createRange(n: number | undefined): any[] {
    const count = Math.max(0, Math.floor(n ?? 0));
    return Array.from({ length: count });
  }

  emptyStars(n: number | undefined): any[] {
    const filled = Math.max(0, Math.floor(n ?? 0));
    return Array.from({ length: Math.max(0, 5 - filled) });
  }

  roundValue(n: number | undefined): number {
    return Math.round(n ?? 0);
  }

  formatRating(n: number | undefined, digits = 1): number {
    const v = Number(n ?? 0);
    const factor = Math.pow(10, digits);
    return Math.round(v * factor) / factor;
  }

  applySuggestion(text: string): void {
    this.query = text;
    this.validationMessage = '';
    try {
      this.searchInput?.nativeElement?.focus();
    } catch { }
  }

  openInfoModal(mode: string | ''): void {
    const m = (mode || '').toString();
    this.infoModalMode = m;
    this.infoModalOpen = true;
    this.infoModalTitle = `${m ? m.toString().toUpperCase() : 'Info'} Search`;
    this.infoModalSubtitle = '';
    this.infoModalSql = '';
    this.cdr.markForCheck();
    setTimeout(() => {
      const el = document.querySelector('.info-modal') as HTMLElement | null;
      if (el) el.focus();
    }, 0);
  }

  closeInfoModal(): void {
    this.infoModalOpen = false;
    this.infoModalMode = '';
    this.infoModalSql = '';
    this.cdr.markForCheck();
  }

  copySql(): void {
    try {
      if (!this.infoModalSql) return;
      navigator.clipboard?.writeText(this.infoModalSql);
    } catch (e) { }
  }

  downloadSql(): void {
    try {
      if (!this.infoModalSql) return;
      const blob = new Blob([this.infoModalSql], { type: 'text/sql' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'query.sql';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { }
  }

  refresh(): void {
    this.router.navigateByUrl('/home');
  }

  goToChatbot() {
    this.router.navigateByUrl('/chat');
  }

  openDoc(): void {
    try {
      const url = '/assets/images/Al Powered Product Finder & MCP User Guide for AlloyDB.pdf';
      const a = document.createElement('a');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      console.error('Failed to open user guide in new tab', e);
    }
  }

  onHelpBubbleClick(event: Event): void {
    this.showHelpBubble = false;
  }

  private normalizeDetail(d: any): any {
    if (!d || typeof d !== 'object') return {};
    if ((d as any).__normalized) return d;
    const normalized: any = { ...d };

    normalized.id = d.id ?? d.ID ?? d.productId ?? d.product_id ?? normalized.id ?? 0;
    normalized.productDisplayName =
      d.productDisplayName ?? d.productdisplayname ?? d.name ?? d.title ?? normalized.productDisplayName ?? '';
    normalized.masterCategory = d.masterCategory ?? d.mastercategory ?? d.category ?? '';
    normalized.subCategory = d.subCategory ?? d.subcategory ?? d.sub_category ?? '';

    normalized.unitPrice = Number(d.unitPrice ?? d.unitprice ?? d.price ?? 0) || 0;
    normalized.finalPrice = Number(d.finalPrice ?? d.finalprice ?? normalized.unitPrice ?? 0) || normalized.unitPrice || 0;
    normalized.discount = Number(d.discount ?? 0) || 0;
    normalized.rating = Number(d.rating ?? d.score ?? 0) || 0;

    normalized.link = d.link ?? d.image ?? d.imageUrl ?? '/assets/images/placeholder.png';
    normalized.brand = (d.brand ?? d.Brand ?? '') + '';

    normalized.discountPercent = Number(
      d.discountPercent ??
      (normalized.unitPrice > 0 ? Math.round(((normalized.unitPrice - normalized.finalPrice) / normalized.unitPrice) * 100) : 0)
    ) || 0;

    (normalized as any).__normalized = true;
    return normalized;
  }

  private showTransientFilterMessage(msg: string): void {
    if (this._filterMsgTimer) {
      clearTimeout(this._filterMsgTimer);
      this._filterMsgTimer = null;
    }
    this.filterMessage = msg;
    this.cdr.markForCheck();
    this._filterMsgTimer = setTimeout(() => {
      this.filterMessage = '';
      this._filterMsgTimer = null;
      this.cdr.markForCheck();
    }, 5000);
  }

  openSearchMetaPopup(): void {
    const type = (this.searchResponseMeta.search_type || '').toString().toLowerCase();
    const map: Record<string, string> = {
      vector: 'Vector Search',
      hybrid: 'Hybrid Search',
      'nl_to_sql': 'SQL filter query powered by AlloyDB Data Agent',
      nltosql: 'SQL filter query powered by AlloyDB Data Agent',
      'ai.if': 'AI.IF',
      aiif: 'AI.IF',
    };

    this.infoModalMode = map[type] ?? (this.searchResponseMeta.search_type || 'Search Results');
    this.infoModalTitle = '';
    this.infoModalSubtitle = this.searchResponseMeta.reason || '';
    this.infoModalSql = this.searchResponseMeta.sql_command || '';
    this.infoModalOpen = true;
    this.cdr.markForCheck();
  }

  onViewQuery(event: Event): void {
    event.preventDefault();
    if (this.total > 0) {
      this.openSearchMetaPopup();
    }
  }

  // ---------- Local storage helpers ----------
  private loadSavedSearches(): any[] {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      if (!raw) return [];
      return JSON.parse(raw) || [];
    } catch (e) {
      console.warn('Failed to read saved searches', e);
      return [];
    }
  }

  private saveSearchRecord(record: any): void {
    try {
      const list = this.loadSavedSearches();
      list.unshift(record);
      const trimmed = list.slice(0, 25);
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(trimmed));
    } catch (e) {
      console.warn('Failed to save search', e);
    }
  }

  private createSearchRecord(results: ProductModel[], filters: any, meta: any): any {
    const shallow = (results || []).map((r) => {
      return {
        id: (r as any).id ?? '',
        name: r.productDisplayName ?? '',
        link: (r as any).link ?? '',
        unitPrice: Number((r as any).unitPrice ?? 0),
        finalPrice: Number((r as any).finalPrice ?? 0),
        brand: (r as any).brand ?? '',
        rating: Number((r as any).rating ?? 0),
      };
    });

    return {
      timestamp: new Date().toISOString(),
      query: this.query || '',
      filters: filters || {},
      meta: meta || {},
      results: shallow,
    };
  }

  private tryApplySavedResults(): boolean {
    // Not implemented in this iteration; return false to always apply live filters.
    return false;
  }
}
