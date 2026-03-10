import {STATIC_FILE_PATH} from './constants';
import {ChatMessage, WindowWithEnv} from './types';

// chat.service.ts
import {HttpClient} from '@angular/common/http';
import {inject, Injectable} from '@angular/core';
import {Observable, of} from 'rxjs';
import {catchError, map} from 'rxjs/operators';

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  private readonly http = inject(HttpClient);
  private userId: string | null = null;
  private orderNonce = 0;
  private promptText = '';
  setUserId(userId: string) {
    this.userId = userId;
  }
  processMessage(
    message: string,
    sessionId: string | null,
  ): Observable<ChatMessage | any> {
    console.log('userId = ', this.userId);
    this.orderNonce++;
    return this.http
      .post(`${(window as unknown as WindowWithEnv).ENV.magicApiUrl}`, {
        query: message,
        sessionId,
        userId: this.userId,
      })
      .pipe(
        map((response: any) => {
          console.log('Magic API Response:', JSON.stringify(response));

          if (
            response.selected_api === 'orderInsert' ||
            response.selected_api === 'orderCheckout'
          ) {
            return {
              text: response.response,
              sender: 'bot',
              senderAvatar: `${STATIC_FILE_PATH}assistant.svg`,
              orderDetails: {
                credit_card: response.order_details.credit_card,
                shipping_address: response.order_details.shipping_address,
                order_id: response.order_details.order_id,
                product:
                  response.order_details.product ??
                  response.order_details.product_name,
                price: response.order_details.price,
                status: response.order_status,
                nonce: this.orderNonce,
              },
            };
          }

          // Handle different API response types
          else if (response.selected_api === 'getResultsOnly') {
            // SQL results only
            return {
              ...toChatMessage(response.response || 'Here are the results:'),
              sqlQuery: response.nl2sql,
              nlaQuery: message,
              tableData: this.parseDataToTableFormat(response.result),
            };
          } else if (response.selected_api === 'getSummaryOnly') {
            // Text summary only
            return toChatMessage(response.response);
          } else if (response.selected_api === 'getSummaryAndResults') {
            // Both summary and results
            return {
              ...toChatMessage(response.response),
              sqlQuery: response.nl2sql,
              nlaQuery: message,
              tableData: this.parseDataToTableFormat(response.result),
            };
          } else {
            // Fallback
            return toChatMessage(
              response.response ||
                "I'm unable to answer that question. Try again.",
            );
          }
        }),
        catchError((error) => {
          console.error('Error in processMessage:', error);
          return of(
            toChatMessage("I'm unable to answer that question. Try again."),
          );
        }),
      );
  }

  // Utility methods moved from previous implementation
  private parseDataToTableFormat(data: any): any {
    if (!data || typeof data !== 'object') {
      return {columns: [], rows: []};
    }

    if (Array.isArray(data)) {
      if (data.length === 0) {
        return {columns: [], rows: []};
      }

      // Extract column information from the first row
      const columns = Object.keys(data[0]).map((key) => ({
        key,
        header: this.formatColumnName(key),
      }));

      return {
        columns,
        rows: data,
      };
    }

    // Handle single object (not an array)
    const columns = Object.keys(data).map((key) => ({
      key,
      header: this.formatColumnName(key),
    }));

    return {
      columns,
      rows: [data],
    };
  }
  private formatColumnName(column: string): string {
    return column
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .split(' ')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }
}

function toChatMessage(text?: string): ChatMessage {
  return {
    text: text ?? "I'm unable to answer that question. Try again.",
    sender: 'bot',
    timestamp: new Date(),
    senderAvatar: `${STATIC_FILE_PATH}assistant.svg`,
  };
}
