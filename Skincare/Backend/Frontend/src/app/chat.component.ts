import { OverlayModule } from '@angular/cdk/overlay';
import { CommonModule } from '@angular/common';
import {
  Component,
  computed,
  effect,
  EffectCleanupRegisterFn,
  ElementRef,
  inject,
  input,
  OnInit,
  SecurityContext,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import * as prism from 'prismjs';
import { take } from 'rxjs/operators';
import { ChatMessageComponent } from './chat-message.component';
import { ChatService } from './chat.service';
import { STATIC_FILE_PATH } from './constants';
import { ChatMessage, Profile, ViewCodeEvent } from './types';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    FormsModule,
    MatTooltipModule,
    ChatMessageComponent,
    MatProgressSpinnerModule,
    OverlayModule,
  ],
  templateUrl: './chat.ng.html',
  styleUrl: './chat.scss',
})
export class ChatComponent implements OnInit {
  // tslint:disable-next-line:no-ctor-only-private-properties
  private readonly chatMessages =
    viewChild<ElementRef<HTMLDivElement>>('chatMessages');

  private readonly sqlDialog =
    viewChild<ElementRef<HTMLDivElement>>('sqlDialog');

  sessionId: string | null = null;
  newMessage = '';
  messages = signal<ChatMessage[]>([]);
  isLoading = signal<boolean>(false);

  public readonly profile = input.required<Profile>();
  protected readonly userId = computed(() => this.profile().userId);

  protected readonly isChatOpen = signal(false);

  protected readonly viewCodeContent = signal<ViewCodeEvent | null>(null);

  protected readonly highlightedGeneratedQueryHtml = computed(() => {
    const sqlCode = this.viewCodeContent()?.generatedQuery;
    if (sqlCode) {
      return toHighlightedSqlHtml(this.sanitizer, sqlCode);
    }
    return '';
  });

  protected readonly highlightedNlaQueryHtml = computed(() => {
    const sqlCode = this.viewCodeContent()?.alloyDbNlaQuery;
    if (sqlCode) {
      return toHighlightedSqlHtml(this.sanitizer, sqlCode);
    }
    return '';
  });

  private readonly chatService = inject(ChatService);
  private readonly sanitizer = inject(DomSanitizer);

  constructor() {
    effect((cleanup: EffectCleanupRegisterFn) => {
      const messageContainer = this.isChatOpen()
        ? this.chatMessages()?.nativeElement
        : null;
      if (!messageContainer) return;
      const observer = new ResizeObserver(() => {
        scrollToBottom(messageContainer.parentElement);
      });
      cleanup(() => {
        observer.disconnect();
      });
      observer.observe(messageContainer);
      if (messageContainer.parentElement) {
        observer.observe(messageContainer.parentElement);
      }
      const currentProfile = this.profile();
      if (currentProfile) {
        this.chatService.setUserId(currentProfile.userId);
      }
    });
  }

  sqlDialogClicked(event: MouseEvent) {
    if (event.target === this.sqlDialog()?.nativeElement) {
      this.viewCodeContent.set(null);
    }
  }

  ngOnInit() {
    this.sessionId = Math.floor(Math.random() * 1000000000000000).toString();
    // Add welcome message
    this.messages.update((msgs) => [
      ...msgs,
      {
        sender: 'bot',
        senderAvatar: `${STATIC_FILE_PATH}assistant.svg`,
        text: `Hi there! Looking for the perfect skincare? I'm here to help! Feel free to ask me to find products based on your needs, get detailed information about any item, or even check your order history. Plus, if you've got a favorite product, I can help you discover similar gems.

        What can I do for you today?
        `,
        timestamp: new Date(),
      },
    ]);
  }
  toggleChat() {
    this.isChatOpen.update((open) => !open);
  }

  closeChat(event?: KeyboardEvent) {
    if (!event || event.key === 'Escape') {
      if (!this.viewCodeContent()) {
        this.isChatOpen.set(false);
      } else {
        this.viewCodeContent.set(null);
        if (event) {
          event.preventDefault();
          event.stopPropagation();
        }
      }
    }
  }

  orderConfirmed(details: ChatMessage['orderDetails']) {
    if (!details?.product) {
      this.messages.update((msgs) => [
        ...msgs,
        {
          sender: 'bot',
          senderAvatar: `${STATIC_FILE_PATH}assistant.svg`,
          text: "Sorry, I couldn't process your order. Please try again.",
          timestamp: new Date(),
        },
      ]);
    }
    this.messages.update((msgs) =>
      msgs.map((msg) => {
        if (
          msg.orderDetails?.product === details!.product &&
          msg.orderDetails?.nonce === details!.nonce
        ) {
          return {
            ...msg,
            orderDetails: {
              ...msg.orderDetails,
              status: 'CONFIRMING',
            },
          };
        }
        return msg;
      }),
    );
    this.chatService
      .processMessage(
        `I confirm the order with product name: ${details!.product}`,
        this.sessionId,
      )
      .pipe(take(1))
      .subscribe((response) => {
        const responseString = JSON.stringify(response);
        console.log('chat.component.ts response = ', responseString);
        this.messages.update((msgs) =>
          msgs.map((msg) => {
            if (
              msg.orderDetails?.product === details!.product &&
              msg.orderDetails?.nonce === details!.nonce
            ) {
              return {
                ...response,
                orderDetails: {
                  ...response.orderDetails,
                },
              };
            }
            return msg;
          }),
        );
      });
  }

  sendMessage() {
    if (!this.newMessage.trim()) return;

    this.isLoading.set(true);
    // Add user message
    this.messages.update((msgs) => [
      ...msgs,
      {
        sender: 'user',
        senderAvatar: this.profile().imageUrl,
        text: this.newMessage,
        timestamp: new Date(),
      },
    ]);

    const userQuery = this.newMessage;
    const sessionId = this.sessionId;
    this.newMessage = '';

    // Send to service and get response
    this.chatService
      .processMessage(userQuery, sessionId)
      .pipe(take(1))
      .subscribe((response) => {
        const responseString = JSON.stringify(response);
        console.log('chat.component.ts response = ', responseString);
        this.messages.update((msgs) => {
          return [...msgs, response];
        });
        this.isLoading.set(false);
      });
  }
}

function toHighlightedSqlHtml(
  sanitizer: DomSanitizer,
  sqlCode: string,
): SafeHtml {
  const highlightedCode = prism.highlight(
    sqlCode,
    prism.languages['sql'],
    'sql',
  );
  const sanitized =
    sanitizer.sanitize(SecurityContext.HTML, highlightedCode) ?? '';
  return sanitized;
}

function scrollToBottom(element: HTMLElement | null) {
  if (!element) return;
  element.scrollTop = element.scrollHeight;
}
