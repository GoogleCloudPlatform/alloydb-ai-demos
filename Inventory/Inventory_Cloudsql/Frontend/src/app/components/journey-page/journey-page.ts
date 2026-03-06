import { Component } from '@angular/core';
import { CommonModule } from '@angular/common'
import { RouterModule } from '@angular/router';
@Component({
  selector: 'app-journey-page',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './journey-page.html',
  styleUrl: './journey-page.scss'
})
export class JourneyPage {
}
