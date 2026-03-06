import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AllSkuInventoryDetails } from './all-sku-inventory-details';

describe('AllSkuInventoryDetails', () => {
  let component: AllSkuInventoryDetails;
  let fixture: ComponentFixture<AllSkuInventoryDetails>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AllSkuInventoryDetails]
    })
    .compileComponents();

    fixture = TestBed.createComponent(AllSkuInventoryDetails);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
