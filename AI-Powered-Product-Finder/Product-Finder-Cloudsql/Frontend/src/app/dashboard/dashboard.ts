import { Component, OnInit, OnDestroy, ChangeDetectorRef, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Product, ProductModel } from '../services/product';
import { finalize } from 'rxjs/operators';
import { Chatbot } from '../chatbot/chatbot';
import { NgxSliderModule, Options } from '@angular-slider/ngx-slider';
import { RouterOutlet, Router } from '@angular/router';

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
  imports: [CommonModule, HttpClientModule, FormsModule, NgxSliderModule, Chatbot, RouterOutlet],
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
    'Formal wear for men',
    'Kurta sets with dupatta'
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

  remoteClearedByUser = false;

  noResultsMessageVisible = false;

  constructor(private svc: Product, private cdr: ChangeDetectorRef, private router: Router) { }

  ngOnInit(): void {
    this.categories = [];
    this.brands = [];
    const cleared = localStorage.getItem('storageCleared');
    if (!cleared) {
      localStorage.clear();
      localStorage.setItem('storageCleared', 'true');
    }

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

            (copy as any).link =
              (p as any).link ??
              (p as any).image ??
              (p as any).imageUrl ??
              (p as any).thumbnail ??
              'assets/images/placeholder.png';

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

          if (!this.searchResultsVisible) {
            this.remoteProducts = [];
            this.page = 1;
            this.total = this.products.length;
            this.showPagination = true;
            if (this.showPagination) {
              const start = (this.page - 1) * this.perPage;
              this.displayed = this.products.slice(start, start + this.perPage);
            } else {
              this.displayed = [...this.products];
            }
            this.remoteClearedByUser = false;
            this.noResultsMessageVisible = false;
            this.error = '';
          } else {
            if (!this.remoteProducts || this.remoteProducts.length === 0) {
              this.page = 1;
              this.displayed = this.products.slice(0, this.perPage);
              this.total = this.products.length;
              this.searchResultsVisible = false;
              this.showPagination = true;
              this.remoteClearedByUser = false;
              this.noResultsMessageVisible = false;
              this.error = '';
            } else {
              this.total = this.remoteProducts.length;
              this.page = Math.min(this.page, Math.ceil(this.total / this.perPage) || 1);
              const start = (this.page - 1) * this.perPage;
              this.displayed = this.remoteProducts.slice(start, start + this.perPage);
              this.showPagination = true;
              this.remoteClearedByUser = false;
              this.noResultsMessageVisible = false;
              this.error = '';
            }
          }

          this.buildPages();
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error(err);
          this.clearListings();

          if (err instanceof HttpErrorResponse) {
            if (err.status === 500) {
              this.error = 'There is some issue from server end, Please try again after sometime';
            } else {
              this.error = err.error?.message || err.message || `Request failed with status ${err.status}`;
            }
          } else if (typeof err === 'string' && err.includes('Http failure response') && err.includes('500')) {
            this.error = 'There is some issue from server end, Please try again after sometime';
          } else {
            this.error = 'Failed to load products';
          }
          this.cdr.markForCheck();
        },
      });
  }

  applyFilter(): void {
    const term = (this.query || '').trim().toLowerCase();

    if (this.remoteClearedByUser) {
      this.displayed = [];
      this.total = 0;
      this.pages = [];
      this.showPagination = false;
      this.noResultsMessageVisible = true;
      this.cdr.markForCheck();
      return;
    }

    let filtered: ProductModel[] = [];
    const remoteActive = this.searchResultsVisible && Array.isArray(this.remoteProducts) && this.remoteProducts.length > 0;

    if (remoteActive) {
      filtered = [...this.remoteProducts];

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
    } else {
      filtered = [...this.products];

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
    }

    this.total = filtered.length;

    if (!this.showPagination) {
      this.page = 1;
      this.displayed = filtered;
    } else {
      this.page = Math.min(this.page, Math.ceil(this.total / this.perPage) || 1);
      if (this.page < 1) this.page = 1;
      const start = (this.page - 1) * this.perPage;
      this.displayed = filtered.slice(start, start + this.perPage);
    }

    if (remoteActive && (!this.remoteProducts || this.remoteProducts.length === 0)) {
      this.searchResultsVisible = false;
      this.displayed = [...this.products];
      this.total = this.products.length;
      this.showPagination = true;
    }

    if (!this.displayed.length && this.remoteClearedByUser) {
      this.noResultsMessageVisible = true;
      this.showPagination = false;
    } else {
      if (this.displayed.length) {
        this.noResultsMessageVisible = false;
        this.showPagination = true;
      }
    }

    this.buildPages();
    this.cdr.markForCheck();
  }

  private validateBeforeSearch(): boolean {
    this.validationMessage = '';
    return true;
  }

  onSearch(): void {
    this.page = 1;
    this.error = '';
    this.validationMessage = '';

    if (!this.validateBeforeSearch()) return;

    this.remoteProducts = [];
    this.rawRemoteResults = {};
    this.searchResponseMeta = {};
    this.searchResultsVisible = false;
    this.remoteClearedByUser = false;
    this.noResultsMessageVisible = false;

    this.showPagination = true;

    this.performMultiSearch();
  }

  onSearchInput(): void {
    if (this.searchResultsVisible) {
      this.searchResultsVisible = false;
      this.remoteProducts = [];
      this.rawRemoteResults = {};
      this.searchResponseMeta = {};
      this.infoModalSql = '';
      this.infoModalMode = '';
      this.infoModalOpen = false;

      this.showPagination = true;
      this.page = 1;

      this.clearListings();

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
            const detailMsg = (res && (res as any).detail) || (res && res.error && (res.error.detail || res.error?.message));
            if (typeof detailMsg === 'string' && detailMsg.toLowerCase().includes('unsupported search type')) {
              this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
              this.clearListings();
              this.rawRemoteResults = {};
              this.showPagination = true;
              this.searchResultsVisible = false;
              this.remoteProducts = [];
              this.cdr.markForCheck();
              return;
            }

            if (res && (res.search_type === 'reject' || res.answer?.search_type === 'reject')) {
              const reason = (res.reason || res.answer?.reason || '').toString().toLowerCase();
              if (reason.includes('no catalog attribute present')) {
                this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
                this.clearListings();
                this.rawRemoteResults = {};
                this.showPagination = false;
                this.searchResultsVisible = false;
                this.remoteProducts = [];

                this.cdr.markForCheck();
                return;
              }
            }

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

            if (Array.isArray(details) && details.length === 0) {
              this.error = 'No Products found';

              this.clearListings();
              this.rawRemoteResults = {};
              this.searchResultsVisible = false;
              this.remoteProducts = [];
              this.showPagination = false;
              this.displayed = [];
              this.total = 0;
              this.remoteClearedByUser = false;
              this.noResultsMessageVisible = true;
              this.buildPages();
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

            const normalizedDetails = this.normalizeResponseDetails(details);

            const remoteProducts: ProductModel[] = (normalizedDetails || []).map((nd: any, idx: number) => {
              const normalized = this.normalizeDetail(nd ?? {});
              const unit = Number(normalized.Unitprice ?? 0) || 0;
              const final = Number(normalized.Finalprice ?? unit) || unit;
              const rating = Number(normalized.Rating ?? 0) || 0;
              const discountPercent =
                Number(
                  normalized.discountPercent ??
                  normalized.Discount ??
                  (unit > 0 ? Math.round(((unit - final) / unit) * 100) : 0)
                ) || 0;

              const rawLink = (normalized.link ?? normalized.Link ?? normalized.link ?? '').toString().trim();
              let safeLink = 'assets/images/placeholder.png';

              if (rawLink) {
                if (rawLink.startsWith('//')) {
                  safeLink = `${location.protocol}${rawLink}`;
                } else if (/^https?:\/\//i.test(rawLink)) {
                  safeLink = rawLink;
                  if (location.protocol === 'https:' && safeLink.startsWith('http://')) {
                    safeLink = safeLink.replace(/^http:\/\//i, 'https://');
                  }
                } else if (rawLink.startsWith('/')) {
                  safeLink = `${location.origin}${rawLink}`;
                } else if (/^[^\/]+\.[^\/]+/.test(rawLink)) {
                  safeLink = `https://${rawLink}`;
                } else {
                  safeLink = rawLink;
                }
              }

              return {
                id: normalized.id ?? `r-${idx}`,
                productDisplayName: normalized.productDisplayName ?? normalized.name ?? normalized.Productdisplayname ?? 'Item',
                link: safeLink,
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

            if (remoteProducts && remoteProducts.length > 0) {
              this.error = '';

              this.remoteProducts = remoteProducts;
              this.searchResultsVisible = true;
              this.showPagination = true;
              this.page = 1;
              this.total = this.remoteProducts.length;
              const start = (this.page - 1) * this.perPage;
              this.displayed = this.remoteProducts.slice(start, start + this.perPage);

              if (!this.displayed || this.displayed.length === 0) {
                this.page = 1;
                this.displayed = this.remoteProducts.slice(0, this.perPage);
              }

              this.remoteClearedByUser = false;
              this.noResultsMessageVisible = false;
            } else {
              this.remoteProducts = [];
              this.searchResultsVisible = false;
              this.showPagination = true;
              this.page = 1;
              const start = (this.page - 1) * this.perPage;
              this.displayed = this.products.slice(start, start + this.perPage);
              this.total = this.products.length;
              this.remoteClearedByUser = false;
              this.noResultsMessageVisible = false;
              this.error = '';
            }

            this.buildPages();

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
            if (typeof errDetail === 'string' && errDetail.toLowerCase().includes('unsupported search type') && errDetail.toLowerCase().includes('No catalog attribute present')) {
              this.error = 'Enter a relevant search term, or choose from the suggested questions above.';
              this.clearListings();
            } else if (err instanceof HttpErrorResponse) {
              if (err.status === 500) {
                this.error = 'There is some issue from server end, Please try again after sometime';
              } else {
                this.error = err.error?.message || err.message || `Search failed with status ${err.status}`;
              }
              this.clearListings();
            } else if (typeof err === 'string' && err.includes('Http failure response') && err.includes('500')) {
              this.error = 'There is some issue from server end, Please try again after sometime';
              this.clearListings();
            } else {
              this.error = (err && err.message) ? err.message : 'Search failed. Please try again.';
              this.clearListings();
            }

            this.rawRemoteResults = {};
            this.showPagination = true;
            this.searchResultsVisible = false;
            this.remoteProducts = [];
            this.displayed = [...this.products].slice(0, this.perPage);
            this.total = this.products.length;
            this.buildPages();
            this.cdr.markForCheck();
          },
        });
    } else {
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

  clearSearchResults(): void {
    this.searchResultsVisible = false;
    this.remoteProducts = [];
    this.searchResponseMeta = {};
    this.showPagination = true;
    this.page = 1;
    this.perPage = 6;
    this.remoteClearedByUser = false;
    this.noResultsMessageVisible = false;
    this.applyFilter();
    this.cdr.markForCheck();
  }

  private clearRemoteResultsOnFilterChange(): void {
    this.remoteClearedByUser = true;

    this.searchResultsVisible = false;
    this.remoteProducts = [];
    this.rawRemoteResults = {};
    this.searchResponseMeta = {};
    this.infoModalSql = '';
    this.infoModalMode = '';
    this.infoModalOpen = false;

    this.error = '';

    this.displayed = [];
    this.total = 0;
    this.pages = [];
    this.showPagination = false;
    this.noResultsMessageVisible = false;

    this.cdr.markForCheck();
  }

  onCategoryChange(value: string): void {
    this.selectedCategory = value ?? '';
    this.clearRemoteResultsOnFilterChange();
  }

  onBrandChange(value: string): void {
    this.selectedBrand = value ?? '';
    this.clearRemoteResultsOnFilterChange();
  }

  onRatingChange(value: number | string | undefined): void {
    this.selectedRating = Number(value) || 0;
    this.clearRemoteResultsOnFilterChange();
  }

  openPricePopup(): void {
    this.pricePopupOpen = true;
    this.tempMin = this.priceRangeMin;
    this.tempMax = this.priceRangeMax;
    this.cdr.markForCheck();
  }

  closePricePopup(apply: boolean): void {
    this.pricePopupOpen = false;
    if (apply) {
      this.priceRangeMin = Math.max(this.priceLimitMin, Math.min(this.tempMin, this.priceLimitMax));
      this.priceRangeMax = Math.min(this.priceLimitMax, Math.max(this.tempMax, this.priceLimitMin));
      this.clearRemoteResultsOnFilterChange();
    } else {
      this.tempMin = this.priceRangeMin;
      this.tempMax = this.priceRangeMax;
    }
    this.cdr.markForCheck();
  }

  onMinInputChange(val: number | undefined): void {
    if (!Number.isFinite(val as number)) return;
    this.tempMin = Math.max(this.priceLimitMin, Math.min(val as number, this.priceLimitMax));
  }

  onMaxInputChange(val: number | undefined): void {
    if (!Number.isFinite(val as number)) return;
    this.tempMax = Math.min(this.priceLimitMax, Math.max(val as number, this.priceLimitMin));
  }

  buildPages(): void {
    const totalPages = Math.max(1, Math.ceil(this.total / this.perPage));
    const pages: number[] = [];
    for (let i = 1; i <= totalPages; i++) pages.push(i);
    this.pages = pages;
  }

  goToFirst(): void {
    this.goToPage(1);
  }

  goToLast(): void {
    this.goToPage(this.totalPages);
  }

  prevPage(): void {
    if (this.page > 1) this.goToPage(this.page - 1);
  }

  nextPage(): void {
    if (this.page < this.totalPages) this.goToPage(this.page + 1);
  }

  goToPage(p: number): void {
    this.page = p;
    this.applyFilter();
    this.cdr.markForCheck();
  }

  changePerPage(n: number | undefined): void {
    const newVal = Number(n) || 6;
    this.perPage = newVal;
    this.page = 1;
    this.applyFilter();
  }

  onPaginatorKeydown(ev: KeyboardEvent): void {
    if (ev.key === 'ArrowLeft') this.prevPage();
    if (ev.key === 'ArrowRight') this.nextPage();
  }

  normalizeResponseDetails(details: any[]): any[] {
    return details;
  }

  normalizeDetail(d: any): any {
    return d;
  }

  createSearchRecord(results: ProductModel[], filters: any, meta: any): any {
    return {
      id: Date.now(),
      query: this.query,
      filters,
      meta,
      results,
      createdAt: new Date().toISOString(),
    };
  }

  saveSearchRecord(record: any): void {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      arr.unshift(record);
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(arr.slice(0, 20)));
    } catch (e) {
      console.warn('Could not save search record', e);
    }
  }

  // Accept undefined and coerce to number to avoid template type errors
  createRange(n?: number): number[] {
    const count = Math.max(0, Math.round(Number(n || 0)));
    return Array.from({ length: count });
  }

  emptyStars(n?: number): number[] {
    const filled = Math.max(0, Math.round(Number(n || 0)));
    return Array.from({ length: Math.max(0, 5 - filled) });
  }

  onViewQuery(ev: Event): void {
    ev.preventDefault();
    const type = (this.searchResponseMeta.search_type || '').toString().toLowerCase();
    const map: Record<string, string> = {
      vector: 'Vector Search',
      hybrid: 'Hybrid Search',
      'nl_to_sql': 'SQL filter query powered by AlloyDB Data Agent',
      nltosql: 'SQL filter query powered by AlloyDB Data Agent',
      'ai.if': 'AI.IF',
    };

    if (!this.searchResultsVisible || this.total === 0) return;
    this.infoModalOpen = true;
    this.infoModalSql = this.searchResponseMeta.sql_command || '';
    this.infoModalSubtitle = this.searchResponseMeta.reason || '';
    this.infoModalMode = map[type] ?? (this.searchResponseMeta.search_type || 'Search Results');
    this.cdr.markForCheck();
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

  copySql(): void {
    try {
      if (!this.infoModalSql) return;
      navigator.clipboard?.writeText(this.infoModalSql);
    } catch (e) { }
  }

  closeInfoModal(): void {
    this.infoModalOpen = false;
    this.cdr.markForCheck();
  }

  applySuggestion(s: string): void {
    this.query = s;
  }

  goToHome(): void {
    this.router.navigate(['/']);
  }

  openDoc(): void {
    try {
      const url = '/assets/images/Al Powered Product Finder & MCP User Guide for CloudSQL.pdf';
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
}
