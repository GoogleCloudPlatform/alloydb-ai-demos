import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ReplenishmentRecommendationComponent } from './replenishment-recommendation';

describe('ReplenishmentRecommendation', () => {
  let component: ReplenishmentRecommendationComponent;
  let fixture: ComponentFixture<ReplenishmentRecommendationComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReplenishmentRecommendationComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ReplenishmentRecommendationComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
