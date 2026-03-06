import { Component, signal, OnInit, OnDestroy } from '@angular/core';
import { Router, NavigationEnd, RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { FormsModule } from '@angular/forms';
import { MatSliderModule } from '@angular/material/slider';
import { Subscription } from 'rxjs';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterModule, RouterModule, MatIconModule, FormsModule, MatSliderModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App implements OnInit, OnDestroy {
  protected readonly title = signal('inventory-management');
  isUserJourney = signal(false);
  private sub?: Subscription;

  constructor(private router: Router) {}

  ngOnInit() {
    this.checkUrl(this.router.url);
    this.sub = this.router.events
      .pipe(filter(e => e instanceof NavigationEnd))
      .subscribe((e: NavigationEnd) => this.checkUrl(e.urlAfterRedirects));
  }

  private checkUrl(url: string) {
    this.isUserJourney.set(url === '/user-journey' || url.startsWith('/user-journey/'));
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
  }

  openUserGuide() {
    window.open('/Inventory Managament User Guide for AlloyDB.pdf', '_blank');
  }
}
