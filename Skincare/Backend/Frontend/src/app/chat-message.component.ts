import { OverlayModule } from '@angular/cdk/overlay';

// chat-message.component.ts
import { CommonModule } from '@angular/common';
import { Component, computed, input, output, viewChild } from '@angular/core';
import { MatButtonModule, MatIconButton } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { format } from 'sql-formatter';

import { DataTableComponent } from './data-table.component';
import { ChatMessage, ViewCodeEvent } from './types';

@Component({
  selector: 'app-chat-message',
  standalone: true,
  imports: [
    MatButtonModule,
    CommonModule,
    MatIconModule,
    MatTooltipModule,
    DataTableComponent,
    MatProgressSpinnerModule,
    OverlayModule,
  ],
  templateUrl: './chat-message.component.html',
  styleUrls: ['./chat-message.component.scss'],
})
export class ChatMessageComponent {
  public readonly message = input.required<ChatMessage>();
  protected readonly viewSqlQueryButton = viewChild<MatIconButton>('viewSql');
  protected readonly viewCode = output<ViewCodeEvent>();
  protected readonly orderConfirmed = output<ChatMessage['orderDetails']>();

  // Using sql-formatter (browser-friendly) instead of internal QueryFormatter.
  // You can change the language option to 'sql', 'postgresql', 'mysql', 'bigquery', etc.
  private readonly sqlFormatterOptions = { language: 'postgresql' as const };

  showSqlTooltip = false;
  showSqlDialog = false;

  protected readonly generatedSql = computed(() => {
    const sqlQuery = this.message().sqlQuery;
    if (sqlQuery) {
      return removeNewlinesFromKnownOperators(
        format(sqlQuery, this.sqlFormatterOptions),
      );
    }
    return '';
  });

  protected readonly alloyDbNlaSql = computed(() => {
    const { nlaQuery } = this.message();
    if (nlaQuery) {
      const sqlStringLiteral = toPgStringLiteral(nlaQuery);
      return removeNewlinesFromKnownOperators(
        format(
          `SELECT alloydb_ai_nl.get_sql('google_io', ${sqlStringLiteral})->>'sql';`,
          this.sqlFormatterOptions,
        ),
      );
    }
    return '';
  });

  protected readonly messageLines = computed(() => {
    const { text } = this.message();
    return text.split('\n');
  });

  openSqlDialog() {
    const component = this.viewSqlQueryButton();

    const button = component?._elementRef?.nativeElement;
    if (!button) return;

    const generated = this.generatedSql();
    if (!generated) return;

    const nla = this.alloyDbNlaSql();
    if (!nla) return;

    this.viewCode.emit({
      generatedQuery: generated,
      alloyDbNlaQuery: nla,
      target: button,
    });
  }
}

function toPgStringLiteral(str: string): string {
  const quoteEscaped = str.replaceAll(/'/g, "''");
  if (str.includes('\\')) {
    return ` E'${quoteEscaped.replaceAll(/\\/g, '\\\\')}'`;
  }
  return `'${quoteEscaped}'`;
}

function removeNewlinesFromKnownOperators(str: string): string {
  str = str.replaceAll(/distinct\s+from\s+/gm, 'distinct from ');
  str = str.replaceAll(/DISTINCT\s+FROM\s+/gm, 'DISTINCT FROM ');
  return str;
}
