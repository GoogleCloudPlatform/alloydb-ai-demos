import { ComponentFixture, TestBed } from '@angular/core/testing';

import { EditApprovePo } from './edit-approve-po';

describe('EditApprovePo', () => {
  let component: EditApprovePo;
  let fixture: ComponentFixture<EditApprovePo>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EditApprovePo]
    })
    .compileComponents();

    fixture = TestBed.createComponent(EditApprovePo);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
