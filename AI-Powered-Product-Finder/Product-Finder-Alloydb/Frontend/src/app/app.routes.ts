import { Routes } from '@angular/router';
import { Dashboard } from './dashboard/dashboard';
import { Home } from './home/home';


export const routes: Routes = [

  { path: 'dashboard', component: Dashboard },
  { path: 'home', component: Home },
  { path: '', redirectTo: 'home', pathMatch: 'full' },
];
