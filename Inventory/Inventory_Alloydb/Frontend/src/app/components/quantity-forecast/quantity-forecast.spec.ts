import { ComponentFixture, TestBed } from '@angular/core/testing';

import { QuantityForecast } from './quantity-forecast';

describe('QuantityForecast', () => {
  let component: QuantityForecast;
  let fixture: ComponentFixture<QuantityForecast>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuantityForecast]
    })
    .compileComponents();

    fixture = TestBed.createComponent(QuantityForecast);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
