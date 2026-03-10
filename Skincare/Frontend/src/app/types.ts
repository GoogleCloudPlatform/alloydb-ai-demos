import {TableData} from './data-table.component';

export interface Icon {
  readonly name: string;
  readonly tooltip: string;
}

export interface Preference {
  readonly typ:
    | 'prefvegan'
    | 'prefmineraloilfree'
    | 'prefparabenfree'
    | 'prefworksforoilyskin'
    | 'prefcrueltyfree';
  readonly icon?: Icon;
}

export interface SkinType {
  readonly typ: 'skincombination' | 'skindry' | 'skinnormal' | 'skinoily';
  readonly icon?: Icon;
}

export interface Profile {
  readonly imageUrl: string;
  readonly name: string;
  readonly preferences: Preference[];
  readonly skinTypes: SkinType[];
  readonly userId: string;
}

export interface ChatMessage {
  readonly text: string;
  readonly sender: 'user' | 'bot';
  readonly senderAvatar: string;
  readonly timestamp: Date;
  readonly tableData?: TableData;
  readonly sqlQuery?: string;
  readonly nlaQuery?: string;
  readonly orderDetails?: {
    user_id?: string;
    credit_card?: string;
    shipping_address?: string;
    order_id?: string;
    product?: string;
    price?: number;
    status?: string;
    nonce?: number;
  };
  isLoading?: boolean;
}

export interface ViewCodeEvent {
  readonly generatedQuery: string;
  readonly alloyDbNlaQuery: string;
  readonly target: HTMLElement;
}

export interface Filter {
  readonly key: string;
  readonly value: string;
}

export enum FilterKey {
  PREFERENCES = 'preferences',
  SKIN_TYPE = 'skinType',
  SECONDARY_CATEGORY = 'secondaryCategory',
  PRICE_RANGE = 'priceRange',
  RATING = 'rating',
}

export type WindowWithEnv = Window & {
  ENV: {
    baseUrl: string;
    userId: string;
    dataApiUrl: string;
    magicApiUrl: string;
  };
};

export interface Filters {
  readonly values: ReadonlyMap<string, FilterKey>;
  readonly personalized: boolean;
}

export declare interface AnalysisResult {
  original_query: string | null;
  rewritten_query: string | null;
  selected_api: string | null;
  response: string | null;
  order_status: string | null;
  order_details: string | null;
  nl2sql: string | null;
  params: string | null;
  result: string | null;
  a: string | null;
  status: string | null;
  analysis: string | null;
  priority: string | null;
  skinType: string | null;
  productSearch: string | null;
  image: string | null;
}
