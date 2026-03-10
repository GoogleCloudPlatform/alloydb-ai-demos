import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { map, Observable } from 'rxjs';

export interface ProductModel {
  id: number;
  gender: string;
  masterCategory: string;
  subCategory: string;
  articleType: string;
  baseColour: string;
  season: string;
  year: number;
  usage: string;
  productDisplayName: string;
  link: string;
  unitPrice: number;
  discount: number;
  finalPrice: number;
  rating: number;
  stockCode: string;
  stockStatus: string;

  // UI helpers
  reviews?: number;
  roundedRate?: number;
}

@Injectable({ providedIn: 'root' })
export class ProductService {
  // single place for API endpoints
  private api = 'https://hybrid-search-service-888916268766.asia-south1.run.app/list-products';
  private multiSearchApi = 'https://hybrid-search-service-888916268766.asia-south1.run.app/search';

  // AI.IF endpoints
  private aiIfSearchApi = 'https://hybrid-search-service-888916268766.asia-south1.run.app/ai-if/search';
  private aiIfScenariosApi = 'https://hybrid-search-service-888916268766.asia-south1.run.app/ai-if/scenarios';

  // CloudSql endpoint
  private multiSearchSqlApi = "https://cloudsql-search-service-888916268766.asia-south1.run.app/cloudsql/multi";

  // New endpoints for categories and brands
  private listCategoriesApi = 'https://hybrid-search-service-888916268766.asia-south1.run.app/list-categories';
  private listBrandsApi = 'https://hybrid-search-service-888916268766.asia-south1.run.app/list-brands';

  constructor(private http: HttpClient) {}

  getAll(): Observable<ProductModel[]> {
    return this.http.get<{ products: ProductModel[] }>(this.api).pipe(map((res) => res.products));
  }

  getOne(id: number): Observable<ProductModel> {
    return this.http.get<ProductModel>(`${this.api}/${id}`);
  }

  // multi-search wrapper used by dashboard
  searchMulti(types: string[], question: string, filters?: any): Observable<any> {
    const body: any = {
      question: question || '',
      filters: filters
    };
    return this.http.post<any>(this.multiSearchApi, body);
  }

  searchMultiCloudSql(types: string[], question: string): Observable<any> {
    const body = {
      search_types: types,
      question: question || '',
    };
    return this.http.post<any>(this.multiSearchSqlApi, body);
  }

  // AI.IF search: sends natural language question to AI.IF search endpoint
  aiIfSearch(question: string): Observable<any> {
    const body = { question: question || '' };
    return this.http.post<any>(this.aiIfSearchApi, body);
  }

  // AI.IF scenario: sends scenario key (e.g., color_category or style_category)
  aiIfScenario(scenarioKey: string): Observable<any> {
    const body = { scenario: scenarioKey };
    return this.http.post<any>(this.aiIfScenariosApi, body);
  }

  // New: list categories
  listCategories(): Observable<string[]> {
    return this.http.get<{ categories: string[] }>(this.listCategoriesApi).pipe(map((res) => res?.categories ?? []));
  }

  // New: list brands
  listBrands(): Observable<string[]> {
    return this.http.get<{ brands: string[] }>(this.listBrandsApi).pipe(map((res) => res?.brands ?? []));
  }
}
