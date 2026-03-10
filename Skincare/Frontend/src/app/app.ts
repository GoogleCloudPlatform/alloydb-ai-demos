import {OverlayModule} from '@angular/cdk/overlay';
import {HttpClient} from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MatButton, MatButtonModule} from '@angular/material/button';
import {MatFormFieldModule} from '@angular/material/form-field';
import {MatIconModule, MatIconRegistry} from '@angular/material/icon';
import {MatInputModule} from '@angular/material/input';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {MatSelectModule} from '@angular/material/select';
import {MatTooltipModule} from '@angular/material/tooltip';
import {RouterOutlet} from '@angular/router';
import {isEqual} from 'lodash';
import {Subscription} from 'rxjs';
import {ChatMessageComponent} from './chat-message.component';
import {ChatComponent} from './chat.component';
import {LABELS_BY_FILTER_VALUE, STATIC_FILE_PATH} from './constants';
import {FiltersComponent} from './filters';
import {
  AnalysisResult,
  FilterKey,
  Filters,
  Profile,
  WindowWithEnv,
} from './types';

/**
 * GENERATED VARIABLE. Do not edit manually. Use these instructions:
 * go/fix-hamburger?dir=experimental/alloydb-ai-demo/vector-ui/app
 */
const NG_COMPONENT_IMPORTS = [
  MatButton,
  MatButtonModule,
  FormsModule,
  MatIconModule,
  MatSelectModule,
  MatProgressSpinnerModule,
  MatFormFieldModule,
  MatTooltipModule,
  MatInputModule,
  OverlayModule,
  RouterOutlet,
  // Chat components below
  ChatMessageComponent,
  ChatComponent,
  FiltersComponent,
];

/**
 * The root component.
 */
@Component({
  selector: 'app-root',
  templateUrl: './app.html',
  standalone: true,
  styleUrl: './app.scss',
  imports: [NG_COMPONENT_IMPORTS],

  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  private readonly http = inject(HttpClient);
  private readonly filtersComponent =
    viewChild<FiltersComponent>('filtersTemplate');
  protected readonly logoUrl = `${STATIC_FILE_PATH}logo.svg`;

  // Search filters & cards.
  protected query = '';
  protected readonly response = signal<Row[] | undefined>([]);
  protected readonly appliedQuery = signal<string>('');
  protected readonly isLoading = signal<boolean>(false);
  protected readonly filters = signal<Filters>({
    values: new Map(),
    personalized: false,
  });
  protected readonly distinctFilters = computed(() => this.filters(), {
    equal: isEqual,
  });

  // Menu specific.
  protected readonly menuOpen = signal(false);
  protected readonly menuProfileUserId = signal(
    (window as unknown as WindowWithEnv).ENV.userId,
  );
  protected readonly sessionId = Math.floor(
    Math.random() * 1000000000000000,
  ).toString();

  // Analyze my skin.
  protected readonly isAnalyzing = signal(false);
  protected readonly webcamError = signal<string>('');
  protected readonly streamPromise = signal<null | Promise<MediaStream | null>>(
    null,
  );
  protected readonly webshotUrl = signal<string>(PHOTO_1X1_TRANSPARENT);
  private readonly analyzeBackdrop =
    viewChild<ElementRef<HTMLDivElement>>('analyzeBackdrop');
  private readonly analyzeVideo =
    viewChild<ElementRef<HTMLVideoElement>>('analyzeVideo');
  protected readonly waitingForAnalysis = signal(false);
  protected readonly analysisResult = signal<AnalysisResult | null>(null);
  protected analysisSubscription: Subscription | null = null;

  private readonly selectedSampleIndex = signal<number>(-1);
  protected readonly skinSamples = computed<
    Array<{src: string; isSelected: boolean}>
  >(() => {
    return SKIN_SAMPLES.map((src, index) => {
      return {src, isSelected: index === this.selectedSampleIndex() - 1};
    });
  });
  protected readonly isCameraOpen = computed<boolean>(() => {
    return this.selectedSampleIndex() === -1;
  });
  protected readonly isWebshotOpen = computed<boolean>(() => {
    return this.selectedSampleIndex() === 0;
  });
  protected readonly selectedPhoto = computed<string>(() => {
    if (this.isCameraOpen()) return PHOTO_1X1_TRANSPARENT;
    if (this.isWebshotOpen()) return this.webshotUrl();
    return this.skinSamples()[this.selectedSampleIndex() - 1].src;
  });
  protected selectSamplePhoto(index: number) {
    this.selectedSampleIndex.set(index + 1);
  }

  protected readonly menuProfile = computed(
    () =>
      PROFILES.find((profile) => profile.userId === this.menuProfileUserId()) ??
      PROFILES[0],
  );
  protected readonly profilePresets = computed<Map<string, FilterKey>>(() => {
    const profile = this.menuProfile();
    if (!profile) return new Map<string, FilterKey>();
    const preferences: Array<[string, FilterKey]> = profile.preferences.map(
      (pref) => [pref.typ, FilterKey.PREFERENCES],
    );
    const skinType: Array<[string, FilterKey]> = profile.skinTypes.map(
      (skinType) => [skinType.typ, FilterKey.SKIN_TYPE],
    );
    return new Map<string, FilterKey>([...preferences, ...skinType]);
  });

  protected readonly skinTypeFilters = computed<string[]>(() => {
    const filters = this.filters();
    return Array.from(filters.values.entries())
      .filter(([_, filterKey]) => filterKey === FilterKey.SKIN_TYPE)
      .map(([key, _]) => key);
  });

  protected readonly preferenceFilters = computed<string[]>(() => {
    const filters = this.filters();
    return Array.from(filters.values.entries())
      .filter(([_, filterKey]) => filterKey === FilterKey.PREFERENCES)
      .map(([key, _]) => key);
  });

  protected readonly displaySkinTypeFilterBanner = computed<boolean>(() => {
    return this.skinTypeFilters().length > 0;
  });

  protected readonly displayPreferenceFilterBanner = computed<boolean>(() => {
    return this.preferenceFilters().length > 0;
  });

  // Returns the base64 encoded image of the selected photo or null if the
  // photo is not available. The promise always resolves without throwing.
  protected readonly base64SelectedPhoto = computed<Promise<string | null>>(
    async () => {
      const webshotUrl = this.webshotUrl();
      if (this.isWebshotOpen() && webshotUrl) {
        return toBase64(webshotUrl);
      }
      const selectedPhoto = this.selectedPhoto();
      if (selectedPhoto === PHOTO_1X1_TRANSPARENT) return null;
      try {
        return toBase64(await toDataUrl(selectedPhoto));
      } catch (e) {
        return null;
      }
    },
  );

  toggleMenu() {
    this.menuOpen.update((menuOpen) => !menuOpen);
  }
  switchProfile() {
    this.closeMenu();
  }
  closeMenu(event?: KeyboardEvent) {
    if (!event || event.key === 'Escape') {
      this.menuOpen.set(false);
    }
  }

  constructor() {
    const iconRegistry = inject(MatIconRegistry);
    iconRegistry.setDefaultFontSetClass('google-symbols');
    effect(() => {
      this.search(this.distinctFilters());
    });

    effect(() => {
      const videoEl = this.analyzeVideo()?.nativeElement ?? null;
      const isOpen = this.isCameraOpen() && this.isAnalyzing();
      const streamPromise = this.streamPromise();
      if (!streamPromise && isOpen) {
        if (videoEl) {
          const streamPromise = startWebcam(videoEl);
          this.streamPromise.set(streamPromise);
          this.onWebcamRequested(streamPromise);
        }
      } else if (streamPromise && !isOpen) {
        stopWebcam(streamPromise, videoEl);
        this.streamPromise.set(null);
      }
    });
  }

  protected analyzeMySkin() {
    this.isAnalyzing.set(true);
  }

  protected onFiltersChanged(filters: Filters) {
    this.filters.set(filters);
  }

  protected analyzeBackdropClicked(event: MouseEvent) {
    if (event.target === this.analyzeBackdrop()?.nativeElement) {
      this.isAnalyzing.set(false);
    }
  }

  private async onWebcamRequested(request: Promise<MediaStream | null>) {
    this.webcamError.set('');
    let stream: MediaStream | null = null;
    try {
      stream = await request;
    } catch {}
    if (!stream) {
      this.webcamError.set('Failed to access webcam');
      return;
    }
  }

  protected cancel() {
    this.analysisSubscription?.unsubscribe();
    this.webshotUrl.set(PHOTO_1X1_TRANSPARENT);
    this.selectedSampleIndex.set(-1);
    this.waitingForAnalysis.set(false);
    this.isAnalyzing.set(false);
  }

  protected openCamera(force?: boolean) {
    if (force) {
      this.selectedSampleIndex.set(0);
      setTimeout(() => {
        this.selectedSampleIndex.set(-1);
      }, 0);
      return;
    }
    this.selectedSampleIndex.set(-1);
  }

  protected takeScreenshot() {
    const videoEl = this.analyzeVideo()?.nativeElement;
    if (!videoEl) return;
    const imageDataURL = takeScreenshot(
      videoEl,
      document.createElement('canvas'),
    );
    this.webshotUrl.set(imageDataURL);
    this.selectedSampleIndex.set(0);
  }

  protected async uploadPhoto() {
    this.waitingForAnalysis.set(true);
    const b64 = await this.base64SelectedPhoto();
    if (!b64) {
      this.waitingForAnalysis.set(false);
      return;
    }
    this.analysisSubscription = this.http
      .post(`${(window as unknown as WindowWithEnv).ENV.magicApiUrl}`, {
        query: b64,
        sessionId: this.sessionId,
        userId: this.menuProfileUserId(),
      })
      .subscribe(
        (result: any) => {
          const analysisResult: AnalysisResult = {
            ...result,
            image: `data:image/png;base64,${b64}`,
          };
          if (analysisResult.status === 'success') {
            this.isAnalyzing.set(false);
            this.webshotUrl.set(PHOTO_1X1_TRANSPARENT);
            this.selectedSampleIndex.set(-1);
          }
          this.waitingForAnalysis.set(false);
          if (analysisResult.status !== 'success') {
            this.analysisResult.set(null);
            return;
          }
          // Set the analysis result and update the filters with the skin type.
          this.analysisResult.set(analysisResult);
          if (analysisResult.skinType) {
            this.filtersComponent()?.setSkinTypes([analysisResult.skinType]);
          }
          if (analysisResult.productSearch) {
            this.query = analysisResult.productSearch;
            this.search(this.filters());
          }
        },
        () => {
          this.waitingForAnalysis.set(false);
          // TODO: handle errors.
        },
      );
  }
  protected closeAnalysis() {
    const analysisResult = this.analysisResult();
    this.analysisResult.set(null);
    if (!analysisResult) return;
    if (analysisResult.skinType) {
      this.filtersComponent()?.unsetSkinTypes([analysisResult.skinType]);
    }
    if (analysisResult.productSearch) {
      this.query = '';
      this.search(this.filters());
    }
  }

  protected search(filters: Filters) {
    const appliedQuery = this.query;
    this.response.set(undefined);
    this.isLoading.set(true);
    const query = appliedQuery || DEFAULT_QUERY;
    const filterParams = Array.from(
      filters.values.entries(),
      ([key, value]) => `${value}=${key}`,
    ).join('&');
    this.http
      .get(
        `${(window as unknown as WindowWithEnv).ENV.dataApiUrl}?query=${query}&personalized=${filters.personalized}&${filterParams}`,
      )
      .subscribe((response) => {
        if (response) {
          this.appliedQuery.set(appliedQuery);
          const a = (response as HttpResponse).a;
          if (a && a.rows) {
            this.response.set(
              a.rows.map((row) => ({
                ...row,
                price_usd: Math.round(row.price_usd),
              })),
            );
          } else {
            this.response.set([]);
          }
        }
        this.isLoading.set(false);
      });
  }

  protected starIcons(
    rating: number,
  ): Array<{name: string; className: string}> {
    if (rating > 5) rating = 5;
    if (rating < 0) rating = 0;
    const margin = 0.2;
    return Array.from({length: 5}, (_, i) =>{
      if (rating > i + margin && rating <= i + 1 - margin) {
        return {name: 'star_half', className: 'product-star-half'};
      } else if (rating > i + margin) {
        return {name: 'star', className: 'product-star-full'};
      } else {
        return {name: 'star', className: 'product-star-empty'};
      }
    });
  }

  protected filterLabel(filter: string) {
    return LABELS_BY_FILTER_VALUE.get(filter) ?? filter;
  }
}

interface HttpResponse {
  a: Response;
}

interface Response {
  rows: Row[];
}

interface Row {
  // tslint:disable:enforce-name-casing
  product_id: string;
  product_name: string;
  skin_type: string;
  review_text: string;
  price_usd: number;
  works_for_oily_skin: boolean;
  cruelty_free: boolean;
  is_vegan: boolean;
  reviews: number;
  rating: number;
  // tslint:enable:enforce-name-casing
}

const DEFAULT_QUERY = 'skincare products';

const PROFILES: readonly Profile[] = Object.freeze([
  {
    imageUrl:
      // SkipFileAnalysisHardcodedUrl: Throwaway code in experimental.
      'https://lh3.googleusercontent.com/a-/ALV-UjUObywRl3wcRXwsiODO5tJ9HQVSU71H1djHkJTdyd_3vh02B-61=s600-p',
    name: 'Tabatha (Tabby) Lewis-Simó',
    preferences: [
      {typ: 'prefvegan', icon: {name: 'psychiatry', tooltip: 'Vegan friendly'}},
    ],
    skinTypes: [
      {
        typ: 'skinoily',
        icon: {name: 'water_drop', tooltip: 'Works for oily skin'},
      },
    ],
    userId: '123',
  },
  {
    imageUrl:
      // SkipFileAnalysisHardcodedUrl: Throwaway code in experimental.
      'https://lh3.googleusercontent.com/a-/ALV-UjX1gA32xCT-WvliQZtS7C_oSBdsIXKvPy9mXEp0LDug35xr0vnt=s600-p',
    name: 'Gabe Weiss',
    preferences: [
      {typ: 'prefvegan', icon: {name: 'psychiatry', tooltip: 'Vegan friendly'}},
    ],
    skinTypes: [
      {
        typ: 'skinoily',
        icon: {name: 'water_drop', tooltip: 'Works for oily skin'},
      },
    ],
    userId: '124',
  },
]);

const PHOTO_1X1_TRANSPARENT =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

async function startWebcam(
  videoEl: HTMLVideoElement,
): Promise<MediaStream | null> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: {ideal: 1600},
        height: {ideal: 900},
      },
    });
    videoEl.srcObject = stream;
    await videoEl.play();
    return stream;
  } catch (err) {
    console.error('Error accessing webcam:', err);
  }
  return null;
}

async function stopWebcam(
  streamPromise: Promise<MediaStream | null>,
  videoEl: HTMLVideoElement | null,
) {
  const stream = await streamPromise;
  if (!stream) return;
  const tracks = stream.getTracks();
  for (const track of tracks) {
    track.stop();
  }
  if (videoEl) {
    videoEl.srcObject = null;
  }
}

function takeScreenshot(
  videoEl: HTMLVideoElement,
  canvasEl: HTMLCanvasElement,
): string {
  if (videoEl.readyState !== videoEl.HAVE_ENOUGH_DATA) {
    return PHOTO_1X1_TRANSPARENT;
  }
  // Set canvas dimensions to match the video dimensions
  canvasEl.width = videoEl.videoWidth;
  canvasEl.height = videoEl.videoHeight;
  const context = canvasEl.getContext('2d');
  if (!context) return PHOTO_1X1_TRANSPARENT;
  // Draw the current frame of the video onto the canvas
  context.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
  // Get the image data from the canvas as a data URL (PNG format by default)
  const imageDataURL = canvasEl.toDataURL('image/png');
  return imageDataURL;
}

function toBase64(url: string): string {
  return url.split('data:image/png;base64,')[1];
}

async function toDataUrl(url: string): Promise<string> {
  const image = new Image();
  await new Promise((resolve) => {
    image.onload = () => {
      resolve(image.src);
    };
    image.onerror = () => {
      resolve(PHOTO_1X1_TRANSPARENT);
    };
    image.crossOrigin = 'anonymous';
    image.src = url;
  });
  const canvas = document.createElement('canvas');
  canvas.width = image.width;
  canvas.height = image.height;
  const context = canvas.getContext('2d');
  if (!context) return PHOTO_1X1_TRANSPARENT;
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/png');
}

const SKIN_SAMPLES = [
  'https://storage.googleapis.com/alloydb-ai-demo/ac1482625702b403bc3a7976fcdb2d1e2d4c3e24.png',
  'https://storage.googleapis.com/alloydb-ai-demo/4aadff4011d60288a6674702411eb18d3c689b20.png',
  'https://storage.googleapis.com/alloydb-ai-demo/59c944f031113cbe6244ba81de5c86ca19bda1fd.png',
  'https://storage.googleapis.com/alloydb-ai-demo/4a2a4bd6bec597c34898f27c4eaabdd8264bb0a8.png',
  'https://storage.googleapis.com/alloydb-ai-demo/a0cf2aa61303cedebcf5cbea40c18135516fae84.png',
];
