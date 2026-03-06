import { Routes } from '@angular/router';
import { DashboardComponent } from './components/inventory-dashboard/inventory-dashboard';
import { ReplenishmentRecommendationComponent } from './components/replenishment-recommendation/replenishment-recommendation';
import { AllSkuInventoryDetails } from './components/all-sku-inventory-details/all-sku-inventory-details';
import { JourneyPage } from './components/journey-page/journey-page';
import { PublicLayout } from './layout/public-layout/public-layout';
import { MainLayoutComponent } from './layout/main-layout/main-layout';
import { QuantityForecast } from './components/quantity-forecast/quantity-forecast';

export const routes: Routes = [

  // PUBLIC LAYOUT — NO SIDEBAR (JOURNEY PAGE)
  {
    path: '',
    component: PublicLayout,
    children: [
      { path: '', redirectTo: '/user-journey', pathMatch: 'full' },
      { path: 'user-journey', component: JourneyPage }
    ]
  },

  // MAIN LAYOUT — WITH SIDEBAR
  {
    path: '',
    component: MainLayoutComponent,
    children: [
      { path: 'dashboard', component: DashboardComponent },
      { path: 'replenishment-recommendation', component: ReplenishmentRecommendationComponent },
      { path: 'all-sku-inventory-details', component: AllSkuInventoryDetails },
       { path: 'quantity-forecast', component: QuantityForecast },
    ]
  },

  { path: '**', redirectTo: 'journey' }
];
