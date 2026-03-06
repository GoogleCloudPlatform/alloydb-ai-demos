import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';

export interface Product {
  product_name: string;
  sku: string;
  category: string;
  store_id: number;
  location: string;
  on_hand: number;
  in_transit: number;
  safety_stock: number;
  reorder_point: number;
  status: string;
}

@Injectable({ providedIn: 'root' })
export class ProductService {

  private socket$: WebSocketSubject<any> | undefined;
  private baseUrl = "https://inventory-management-alloydb-service-888916268766.asia-south1.run.app/";
  constructor(private http: HttpClient) { }

  connectToWebSocket(): Observable<any> {
    const url = this.baseUrl + "ws/status";

    if (!this.socket$ || this.socket$.closed) {
      this.socket$ = webSocket(url);
    }
    return this.socket$.asObservable();
  }

  disconnectFromWebSocket() {
    if (this.socket$ && !this.socket$.closed) {
      this.socket$.complete();
    }
    this.socket$ = undefined;
  }

  addProduct(product: Product): Observable<Product> {
    const apiUrl = this.baseUrl + "dashboard/inventory/po_recommendation/add_product";
    return this.http.post<Product>(apiUrl, product);
  }

  updateProduct(updatedProduct: Product): Observable<Product> {
    const apiUrl = this.baseUrl + "dashboard/inventory/po_recommendation/edit_product";
    return this.http.put<Product>(apiUrl, updatedProduct);
  }

  getBarChartData(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/by_location";
    return this.http.get(apiUrl);
  }

  getDoughnutChartData(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/status_distribution";
    return this.http.get(apiUrl);
  }

  getAllSkuDetailsData(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/all_sku_inventory";
    return this.http.get(apiUrl);
  }

  getInventoryOverviewData(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/overview";
    return this.http.get(apiUrl);
  }

  getRecentPurchaseOrders(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/replrecommendation/recent_po";
    return this.http.get(apiUrl);
  }

  getRecommendations(requestBody: any): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/replrecommendation/create_recommendations";
    return this.http.post<any>(apiUrl, requestBody);
  }

  getLowStockItems(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/overview/low_stock";
    return this.http.get(apiUrl);
  }

  getOverStockItems(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/overview/over_stock";
    return this.http.get(apiUrl);
  }

  getCriticalStockItems(): Observable<any> {
    const apiUrl = this.baseUrl + "dashboard/inventory/overview/critical_stock";
    return this.http.get(apiUrl);
  }

  updatePurchaseOrder(payload: any): Observable<any> {
    let apiUrl = this.baseUrl + "dashboard/replrecommendation/editpo";
    return this.http.post(apiUrl, payload);
  }

  approvePurchaseOrder(payload: any): Observable<any> {
    let apiUrl = this.baseUrl + "dashboard/replrecommendation/approvepo";
    return this.http.post(apiUrl, payload);
  }

  getReplenishForecast(payload: {
    sku: string;
    store_id: number;
    horizon_days: number
  }): Observable<any> {
    // adjust endpoint to match your backend
    let apiUrl = this.baseUrl + "dashboard/inventory/overview/quantity_forecast";
    return this.http.post(apiUrl, payload);
  }
  predictQuantity(payload: any): Observable<any> {
    // replace with your real endpoint
    return this.http.post('/api/forecast/predict', payload);
  }

}
