import { Component } from '@angular/core';
import { RouterOutlet, Router } from '@angular/router';
@Component({
  selector: 'app-home',
  imports: [],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
    constructor(private router: Router) {}
  navigateDemo() {
  debugger;
  this.router.navigateByUrl('/dashboard');
  }
}
