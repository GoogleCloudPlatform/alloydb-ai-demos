import { Routes } from '@angular/router';
import { Home } from './home/home';
import { Dashboard } from './dashboard/dashboard';
import { Chatbot } from './chatbot/chatbot';


export const routes: Routes = [
{ path: 'dashboard', component: Dashboard },
{ path: 'home', component: Home },
  {path:'chat', component: Chatbot},
 {path: '', redirectTo: 'home', pathMatch: 'full' }
];
