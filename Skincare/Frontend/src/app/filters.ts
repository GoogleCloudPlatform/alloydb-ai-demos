import {CommonModule} from '@angular/common';
import {
  Component,
  computed,
  effect,
  input,
  output,
  signal,
} from '@angular/core';
import {toSignal} from '@angular/core/rxjs-interop';
import {FormControl, ReactiveFormsModule} from '@angular/forms';
import {MatButton, MatButtonModule} from '@angular/material/button';
import {MatOption, MatOptionModule} from '@angular/material/core';
import {
  MatFormField,
  MatFormFieldModule,
  MatLabel,
} from '@angular/material/form-field';
import {MatIcon, MatIconModule} from '@angular/material/icon';
import {MatSelect, MatSelectModule} from '@angular/material/select';
import {
  MatSlideToggleChange,
  MatSlideToggleModule,
} from '@angular/material/slide-toggle';
import {MatTooltip} from '@angular/material/tooltip';
import {FilterKey, Filters} from './types';

/**
 * GENERATED VARIABLE. Do not edit manually. Use these instructions:
 * go/fix-hamburger?dir=experimental/alloydb-ai-demo/vector-ui/app
 */
const NG_COMPONENT_IMPORTS = [
  CommonModule,
  MatButton,
  MatButtonModule,
  MatFormField,
  MatFormFieldModule,
  MatIcon,
  MatIconModule,
  MatLabel,
  MatOption,
  MatOptionModule,
  MatSelect,
  MatTooltip,
  MatSelectModule,
  ReactiveFormsModule,
  MatSlideToggleModule,
];

@Component({
  selector: 'app-filters',
  templateUrl: './filters.ng.html',
  styleUrls: ['./filters.scss'],
  imports: [NG_COMPONENT_IMPORTS],
})
export class FiltersComponent {
  public readonly profilePresets = input<Map<string, FilterKey>>(
    new Map<string, FilterKey>(),
  );
  protected readonly filtersChanged = output<Filters>();
  protected readonly preferencesControl = new FormControl<string[]>([], {
    nonNullable: true,
  });
  protected readonly skinTypeControl = new FormControl<string[]>([], {
    nonNullable: true,
  });
  protected readonly secondaryCategoryControl = new FormControl<string[]>([], {
    nonNullable: true,
  });
  protected readonly priceRangeControl = new FormControl<string[]>([], {
    nonNullable: true,
  });
  protected readonly ratingControl = new FormControl<string[]>([], {
    nonNullable: true,
  });

  protected readonly preferences = toSignal<string[]>(
    this.preferencesControl.valueChanges,
  );
  protected readonly skinType = toSignal<string[]>(
    this.skinTypeControl.valueChanges,
  );
  protected readonly secondaryCategory = toSignal<string[]>(
    this.secondaryCategoryControl.valueChanges,
  );
  protected readonly priceRange = toSignal<string[]>(
    this.priceRangeControl.valueChanges,
  );
  protected readonly rating = toSignal<string[]>(
    this.ratingControl.valueChanges,
  );
  protected readonly isPersonalized = signal(false);

  protected hasFilters = computed(() => {
    return this.buildFiltersMap().size > 0;
  });

  constructor() {
    this.setupFilterEffect();
  }

  private setupFilterEffect() {
    effect(() => {
      const isPersonalized = this.isPersonalized();
      if (!isPersonalized) return;

      const filters = this.buildFiltersMap();
      const personalizedFilters = this.profilePresets();
      for (const [key] of personalizedFilters) {
        if (!filters.has(key)) {
          this.isPersonalized.set(false);
          return;
        }
      }
    });

    effect(() => {
      this.filtersChanged.emit({
        values: this.buildFiltersMap(),
        personalized: this.isPersonalized(),
      });
    });
  }

  protected clearFilters() {
    this.preferencesControl.reset();
    this.skinTypeControl.reset();
    this.secondaryCategoryControl.reset();
    this.priceRangeControl.reset();
    this.ratingControl.reset();
  }

  setFilters(filters: Map<string, FilterKey>) {
    this.setFilterValues(
      this.preferencesControl,
      filters,
      FilterKey.PREFERENCES,
    );
    this.setFilterValues(this.skinTypeControl, filters, FilterKey.SKIN_TYPE);
    this.setFilterValues(
      this.secondaryCategoryControl,
      filters,
      FilterKey.SECONDARY_CATEGORY,
    );
    this.setFilterValues(this.priceRangeControl,
      filters,
      FilterKey.PRICE_RANGE,
    );
    this.setFilterValues(this.ratingControl, filters, FilterKey.RATING);
  }

  unsetFilters(filters: Map<string, FilterKey>) {
    this.unsetFilterValues(
      this.preferencesControl,
      filters,
      FilterKey.PREFERENCES,
    );
    this.unsetFilterValues(this.skinTypeControl, filters, FilterKey.SKIN_TYPE);
    this.unsetFilterValues(
      this.secondaryCategoryControl,
      filters,
      FilterKey.SECONDARY_CATEGORY,
    );
    this.unsetFilterValues(
      this.priceRangeControl,
      filters,
      FilterKey.PRICE_RANGE,
    );
    this.unsetFilterValues(this.ratingControl, filters, FilterKey.RATING);
  }

  private unsetFilterValues(
    control: FormControl<string[]>,
    filters: Map<string, FilterKey>,
    key: FilterKey,
  ) {
    const currentValues = new Set<string>(control.value);
    for (const [value, filterKey] of filters) {
      if (filterKey === key) {
        currentValues.delete(value);
      }
    }
    control.setValue([...currentValues]);
  }

  private setFilterValues(
    control: FormControl<string[]>,
    filters: Map<string, FilterKey>,
    key: FilterKey,
  ) {
    const result = new Set<string>();
    for (const [value, filterKey] of filters) {
      if (filterKey === key) {
        result.add(value);
      }
    }
    if (result.size > 0) {
      control.setValue([...new Set([...control.value, ...result])]);
    }
  }

  protected onPersonalizedChange(event: MatSlideToggleChange) {
    this.isPersonalized.set(event.checked);
    if (event.checked) {
      this.setFiltersFromProfile();
    }
  }

  setSkinTypes(skinTypes: string[]) {
    const filters = new Map<string, FilterKey>();
    for (const skinType of skinTypes) {
      filters.set('skin' + skinType.toLowerCase(), FilterKey.SKIN_TYPE);
    }
    this.setFilters(filters);
  }

  unsetSkinTypes(skinTypes: string[]) {
    const filters = new Map<string, FilterKey>();
    for (const skinType of skinTypes) {
      filters.set('skin' + skinType.toLowerCase(), FilterKey.SKIN_TYPE);
    }
    this.unsetFilters(filters);
  }

  private setFiltersFromProfile() {
    this.setFilters(this.profilePresets());
  }

  private buildFiltersMap() {
    const result = new Map<string, FilterKey>();
    this.addValuesToResult(this.preferences(), FilterKey.PREFERENCES, result);
    this.addValuesToResult(this.skinType(), FilterKey.SKIN_TYPE, result);
    this.addValuesToResult(
      this.secondaryCategory(),
      FilterKey.SECONDARY_CATEGORY,
      result,
    );
    this.addValuesToResult(this.priceRange(), FilterKey.PRICE_RANGE, result);
    this.addValuesToResult(this.rating(), FilterKey.RATING, result);
    return result;
  }

  private addValuesToResult(
    values: string[] | undefined,
    key: FilterKey,
    result: Map<string, FilterKey>,
  ) {
    if (!values) return;
    for (const value of values) {
      result.set(value, key);
    }
  }
}

