import { Component, signal } from '@angular/core';
import { RouterOutlet, Router } from '@angular/router';
import { NgIf } from '@angular/common';
import { Chatbot } from './chatbot/chatbot';
import { NgxSliderModule } from '@angular-slider/ngx-slider';
@Component({
  selector: 'app-root',
  imports: [RouterOutlet,NgxSliderModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {

  constructor(private router: Router) {}

  protected readonly title = signal('search-app');
}
