import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewInit,
  HostListener,
  ChangeDetectorRef,
  Renderer2,
  Inject,
  PLATFORM_ID
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { Chat } from '../services/chat';
import { RouterOutlet, Router } from '@angular/router';

type Product = {
  productDisplayName: string;
  rating?: number;
  unitPrice: number;
  originalPrice?: number;
  finalPrice?: number;
  discount?: number;
  unitPriceNote?: string;
  link: string;
  description?: string;
  mcpConfidence?: number;
  mcpTag?: string;
  hasImage?: boolean;
};

type Message = {
  id: string;
  from: 'user' | 'bot';
  text: string;
  time: number;
  typing?: boolean;
  products?: Product[];
  _accordionOpen?: boolean;
};

@Component({
  selector: 'app-chatbot',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './chatbot.html',
  styleUrls: ['./chatbot.scss'],
})
export class Chatbot implements AfterViewInit {
  messages: Message[] = [];
  inputText = '';

  isOpen = false;
  isMinimized = false;
  showHelpBubble = true;

  // convenience: current products (most recent bot message products)
  products: Product[] = [];

  usdPerUnit = 0.012;
  isLoading = false;
  sampleQuestions: string[] = [
    "Suggest a gift for my friend’s birthday",
    "Recommend a wedding gift for a colleague",
  ];
  unreadCount = 0;
  currency: 'USD' | 'INR' = 'USD';

  showMcpNote = false;
  private mcpNoteTimer: any = null;
  private lastProductsQuery?: string;

  /** ID of the assistant message that produced the most recent products */
  lastProductsMessageId?: string;

  // persistence key (versioned)
  private STORAGE_KEY = 'mcp_chat_state_v1';

  @ViewChild('messagesContainer', { static: false }) messagesContainer!: ElementRef<HTMLElement>;
  @ViewChild('inputEl', { static: false }) inputEl!: ElementRef<HTMLInputElement>;
  @ViewChild('hostRoot', { static: false }) hostRoot!: ElementRef<HTMLElement>;

  private isBrowser: boolean;

  // --- Modal state for product details ---
  selectedProduct?: Product;
  showProductModal = false;

  constructor(
    private cdr: ChangeDetectorRef,
    private service: Chat,
    private router: Router,
    private renderer: Renderer2,
    @Inject(PLATFORM_ID) private platformId: Object
  ) {
    this.isBrowser = isPlatformBrowser(this.platformId);
  }

  ngOnInit(): void {
    this.resetChat();
    // this.open();
  }

  ngAfterViewInit(): void {
    // Only run DOM-related initialization in the browser
    if (!this.isBrowser) return;

    setTimeout(() => {
      this.restoreState();
      if (!this.messages || this.messages.length === 0) {
        const welcomeId = this.genId();
        const secondId = this.genId();
        this.messages = [{
          id: welcomeId,
          from: 'bot',
          text: `Hi—I'm your MCP ShopBot. Looking for a gift or  something special? Tell me what you have in mind and I’ll find the best options. `,
          time: Date.now()
        },
        {
          id: secondId,
          from: 'bot',
          text: `I’ve just powered up my specialized search tools. Your agent is now fully synced with the MCP server and ready to query our catalog for the perfect find!`,
          time: Date.now() + 1
        }];
        this.persistState();
      } else {
        if (this.lastProductsMessageId) {
          const m = this.messages.find(x => x.id === this.lastProductsMessageId);
          this.products = m?.products ? m.products : [];
        } else {
          this.products = [];
        }
      }

      this.cdr.markForCheck();
      this.scrollToBottom();
    });
  }

  onToggleClick(event?: MouseEvent): void {
    event?.stopPropagation();
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  onHelpBubbleClick(event?: MouseEvent): void {
    event?.stopPropagation();
    this.showHelpBubble = true;
    // this.open();
  }

  open(event?: MouseEvent): void {
    event?.stopPropagation?.();
    this.isOpen = true;
    this.isMinimized = false;
    this.cdr.markForCheck();
    if (!this.isBrowser) return;
    setTimeout(() => {
      this.focusInput(120);
      this.scrollToBottom();
    }, 120);
    this.unreadCount = 0;
  }

  close(event?: MouseEvent): void {
    event?.stopPropagation?.();
    this.isOpen = false;
    this.isMinimized = false;
    this.cdr.markForCheck();
    if (!this.isBrowser) return;
    setTimeout(() => {
      const toggle = document.querySelector<HTMLButtonElement>('#copilot-toggle');
      toggle?.focus();
    }, 0);
  }

  toggleMinimize(event?: MouseEvent): void {
    event?.stopPropagation?.();
    this.isOpen = true;
    this.isMinimized = !this.isMinimized;
    this.cdr.markForCheck();

    if (!this.isMinimized) {
      if (!this.isBrowser) return;
      setTimeout(() => {
        this.focusInput(120);
        this.scrollToBottom();
      }, 120);
    }
  }

  async send(event?: Event): Promise<void> {
    event?.stopPropagation();
    event?.preventDefault?.();
    const text = (this.inputText || '').trim();
    if (!text || this.isLoading) return;

    const userMsg: Message = { id: this.genId(), from: 'user', text, time: Date.now() };
    this.appendMessage(userMsg);

    this.inputText = '';
    this.cdr.markForCheck();
    this.scrollToBottom();

    const typingMsgId = this.genId();
    const typingMsg: Message = { id: typingMsgId, from: 'bot', text: '', time: Date.now(), typing: true };
    this.appendMessage(typingMsg);

    const history = this.messages
      .filter(m => m.from === 'user' || m.from === 'bot')
      .map(m => ({ role: m.from === 'user' ? 'user' : 'assistant', content: m.text }));

    // build previous-products summary including finalPrice and discount
    const previousProductsSummary = this.messages
      .filter(m => m.products && m.products.length)
      .map(m => ({
        messageId: m.id,
        products: m.products!.map(p => ({
          name: p.productDisplayName,
          price: p.unitPrice,
          finalPrice: p.finalPrice ?? p.unitPrice,
          discount: p.discount ?? 0,
          rating: p.rating ?? 0,
          link: p.link
        }))
      }));

    // push the summary into the assistant history so followups see finalPrice and discount
    if (previousProductsSummary.length) {
      history.push({
        role: 'assistant',
        content: `previous_products_by_message:${JSON.stringify(previousProductsSummary)}`
      });
    }

    const payload: any = {
      question: text,
      history,
      tool: 'mcp',
      mcpOptions: {
        ranker: 'mcp-default',
        maxResults: 8,
        includeConfidence: true
      }
    };

    // flatten and attach to payload.previousProducts so the tool receives the extra fields
    const flattenedPrev = previousProductsSummary.flatMap(x => x.products);
    if (flattenedPrev.length > 0) {
      payload.previousProducts = flattenedPrev.map((p: any) => ({
        productDisplayName: p.name,
        unitPrice: p.price,
        finalPrice: p.finalPrice,
        discount: p.discount,
        rating: p.rating,
        link: p.link
      }));
    }

    this.isLoading = true;
    this.cdr.markForCheck();
    this.scrollToBottom();

    try {
      const response = await this.service.postChat(payload);

      // Update typing placeholder in-place to preserve attached products
      const idx = this.messages.findIndex(m => m.id === typingMsgId);
      const botText = response?.answer || '';
      if (idx !== -1) {
        const existing = this.messages[idx];
        existing.text = botText;
        existing.typing = false;
        existing.time = Date.now();
        this.messages = [...this.messages];
        this.persistState();
      } else {
        this.appendMessage({ id: typingMsgId, from: 'bot', text: botText, time: Date.now() });
      }

      if (response && Array.isArray(response.products) && response.products.length > 0) {
        const mapped: Product[] = response.products.map((p: any) => ({
          productDisplayName: p.productDisplayName || 'Unnamed product',
          rating: typeof p.rating === 'number' ? p.rating : (p.rating ? parseFloat(p.rating) : undefined),
          unitPrice: typeof p.unitPrice === 'number' ? p.unitPrice : (p.unitPrice ? parseFloat(p.unitPrice) : 0),
          originalPrice: typeof p.originalPrice === 'number' ? p.originalPrice
            : (p.listPrice ? parseFloat(p.listPrice) : undefined),
          finalPrice: typeof p.finalPrice === 'number' ? p.finalPrice : (p.finalPrice ? parseFloat(p.finalPrice) : undefined),
          discount: typeof p.discount === 'number' ? p.discount : (p.discount ? parseFloat(p.discount) : undefined),
          unitPriceNote: p.unitPriceNote || p.currency || undefined,
          link: p.link || '',
          description: p.description || '',
          mcpConfidence: typeof p.mcpConfidence === 'number' ? p.mcp?.mcpConfidence ?? p.mcpConfidence : (p.mcp?.confidence ?? undefined),
          mcpTag: p.mcpTag || p.mcp?.tag || undefined,
          hasImage: !!p.link
        }));

        const msg = this.messages.find(m => m.id === typingMsgId);
        if (msg) {
          msg.products = mapped;
          // initialize accordion closed by default
          msg._accordionOpen = false;
          this.messages = [...this.messages]; // trigger change detection
        } else {
          this.messages.push({ id: typingMsgId, from: 'bot', text: botText, time: Date.now(), products: mapped, _accordionOpen: false });
        }

        this.products = mapped;
        this.lastProductsMessageId = typingMsgId;
        this.lastProductsQuery = text;

        this.persistState();
        this.showTransientMcpNote();
      } else {
        const msg = this.messages.find(m => m.id === typingMsgId);
        if (msg && msg.products) {
          delete msg.products;
        }
        this.products = [];
        this.lastProductsMessageId = undefined;
        this.clearTransientMcpNote();
        this.persistState();

        const reply = await this.sendMessageMock(text);
        if (reply) {
          this.appendMessage({ id: this.genId(), from: 'bot', text: reply, time: Date.now() });
        }
      }

      this.cdr.markForCheck();
    } catch (err) {
      console.error('Chat API error', err);
      const idxErr = this.messages.findIndex(m => m.id === typingMsgId);
      if (idxErr !== -1) {
        const existing = this.messages[idxErr];
        existing.text = 'Sorry, something went wrong contacting product service.';
        existing.typing = false;
        existing.time = Date.now();
        this.messages = [...this.messages];
        this.persistState();
      } else {
        this.appendMessage({ id: this.genId(), from: 'bot', text: 'Sorry, something went wrong contacting product service.', time: Date.now() });
      }
      const msg = this.messages.find(m => m.id === typingMsgId);
      if (msg && msg.products) delete msg.products;
      this.products = [];
      this.lastProductsMessageId = undefined;
      this.clearTransientMcpNote();
      this.persistState();
      this.cdr.markForCheck();
    } finally {
      this.isLoading = false;
      this.cdr.markForCheck();
      this.scrollToBottom();
    }
  }

  private showTransientMcpNote(): void {
    if (this.mcpNoteTimer) {
      clearTimeout(this.mcpNoteTimer);
      this.mcpNoteTimer = null;
    }

    this.showMcpNote = true;
    this.cdr.markForCheck();

    this.mcpNoteTimer = setTimeout(() => {
      this.showMcpNote = false;
      this.mcpNoteTimer = null;
      this.cdr.markForCheck();
    }, 5000);
  }

  private clearTransientMcpNote(): void {
    if (this.mcpNoteTimer) {
      clearTimeout(this.mcpNoteTimer);
      this.mcpNoteTimer = null;
    }
    if (this.showMcpNote) {
      this.showMcpNote = false;
      this.cdr.markForCheck();
    }
  }

  private appendMessage(msg: Message): void {
    this.messages = [...this.messages, msg];
    if (!this.isOpen) this.unreadCount++;
    this.cdr.markForCheck();
    this.persistState();
    // safe: scrollToBottom checks for messagesContainer
    setTimeout(() => this.scrollToBottom(), 40);
  }

  private scrollToBottom(): void {
    try {
      if (!this.isBrowser) return;
      const el = this.messagesContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch { }
  }

  private genId(): string { return Math.random().toString(36).slice(2, 9); }

  private async sendMessageMock(userText: string): Promise<string> {
    await this.delay(600 + Math.random() * 700);
    const lower = userText.toLowerCase();
    if (lower.includes('hello') || lower.includes('hi')) return 'Hello! How can I help you today?';
    if (lower.includes('help')) return 'I use MCP to find and rank products. Try asking for a gift or a category.';
    if (lower.includes('time')) return `Current time is ${new Date().toLocaleTimeString()}.`;
    return '';
  }

  private delay(ms: number): Promise<void> { return new Promise((res) => setTimeout(res, ms)); }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.isOpen) return;
    const target = event.target as Node | null;
    const hostEl = this.hostRoot?.nativeElement;
    if (hostEl && target && !hostEl.contains(target)) {
      this.close();
    }
  }

  @HostListener('window:keydown', ['$event'])
  onWindowKeydown(event: KeyboardEvent): void {
    if (!this.isBrowser) return;

    // Close modal on Escape if open
    if (this.showProductModal && event.key === 'Escape') {
      event.preventDefault();
      this.closeProductModal();
      return;
    }

    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.open();
      setTimeout(() => this.inputEl?.nativeElement?.focus(), 120);
      return;
    }

    if (!this.isOpen) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
      return;
    }

    if (event.key === 'Enter') {
      const active = document.activeElement;
      const inputNative = this.inputEl?.nativeElement;
      if (active === inputNative) {
        event.preventDefault();
        void this.send();
      } else {
        inputNative?.focus();
      }
    }
  }

  // Open modal instead of navigating directly
  productClick(p: Product): void {
    if (!p) { this.pulseCard(); return; }
    this.openProductModal(p);
  }

  openProductModal(p: Product): void {
    this.selectedProduct = p;
    this.showProductModal = true;
    this.cdr.markForCheck();
    if (!this.isBrowser) return;
    setTimeout(() => {
      // header close button removed; no focus target here
    }, 40);
  }

  closeProductModal(): void {
    this.showProductModal = false;
    this.selectedProduct = undefined;
    this.cdr.markForCheck();
    if (!this.isBrowser) return;
    setTimeout(() => this.focusInput(40), 40);
  }

  productClickOpenLinkFromModal(p?: Product): void {
    if (!p || !p.link) { this.pulseCard(); return; }
    try {
      window.open(p.link, '_blank', 'noopener');
      this.launchConfetti();
    } catch {
      window.location.href = p.link;
      this.launchConfetti();
    }
  }

  clearMessages(): void {
    this.messages = [];
    this.products = [];
    this.clearTransientMcpNote();
    this.lastProductsMessageId = undefined;
    this.cdr.markForCheck();
    this.persistState();
  }

  setUsdPerUnit(factor: number): void { if (typeof factor !== 'number' || isNaN(factor) || factor <= 0) return; this.usdPerUnit = factor; this.cdr.markForCheck(); this.persistState(); }

  refresh() { this.router.navigateByUrl('/home'); }

  selectSample(question: string): void {
    this.inputText = question;
    this.cdr.markForCheck();
    setTimeout(() => {
      this.focusInput(40);
      this.scrollToBottom();
    }, 40);
  }

  resetInput(): void {
    this.inputText = '';
    this.cdr.markForCheck();
    if (!this.isBrowser) return;
    setTimeout(() => this.inputEl?.nativeElement?.focus(), 20);
  }

  resetChat(): void {
    try {
      localStorage.removeItem(this.STORAGE_KEY);
    } catch { }
    this.clearMessages();
    const welcomeId = this.genId();
    const secondId = this.genId();
    this.messages = [{
      id: welcomeId,
      from: 'bot',
      text: `Hi—I'm your MCP ShopBot. Looking for a gift or  something special? Tell me what you have in mind and I’ll find the best options. `,
      time: Date.now()
    },
    {
      id: secondId,
      from: 'bot',
      text: `I’ve just powered up my specialized search tools. Your agent is now fully synced with the MCP server and ready to query our catalog for the perfect find!`,
      time: Date.now() + 1
    }];
    this.products = [];
    this.lastProductsMessageId = undefined;
    this.lastProductsQuery = undefined;
    this.persistState();
    this.cdr.markForCheck();
    this.focusInput(40);
  }

  onImageError(event: Event, p?: Product): void {
    const img = event.target as HTMLImageElement;
    if (img) {
      img.style.display = 'none';
      if (p) p.hasImage = false;
      this.cdr.markForCheck();
      this.persistState();
    }
  }

  initials(name?: string): string { if (!name) return 'P'; return name.split(' ').slice(0, 2).map(s => s[0]).join('').toUpperCase(); }

  private pulseCard(): void {
    if (!this.isBrowser) return;
    const el = document.querySelector('.products-inline-item');
    if (!el) return;
    el.classList.add('pulse');
    setTimeout(() => el.classList.remove('pulse'), 420);
  }

  private launchConfetti(): void {
    if (!this.isBrowser) return;
    try {
      const layer = document.querySelector('.confetti-layer');
      if (!layer) return;
      const colors = ['#FF6B6B', '#FFD93D', '#6BCB77', '#4D96FF', '#9B6BFF'];
      const count = 18;
      for (let i = 0; i < count; i++) {
        const el = document.createElement('div');
        el.className = 'confetti';
        const size = 6 + Math.random() * 12;
        el.style.width = `${size}px`;
        el.style.height = `${size * 1.2}px`;
        el.style.left = `${20 + Math.random() * 60}vw`;
        el.style.top = `${-10 - Math.random() * 10}vh`;
        el.style.background = colors[Math.floor(Math.random() * colors.length)];
        el.style.transform = `rotate(${Math.random() * 360}deg)`;
        (layer as HTMLElement).appendChild(el);
        setTimeout(() => el.remove(), 1400 + Math.random() * 400);
      }
    } catch { }
  }

  /**
   * Accepts number | undefined to avoid template type errors.
   * Returns '-' for missing/invalid values.
   */
  formatDisplayedPrice(unitPrice?: number): string {
    if (unitPrice === null || unitPrice === undefined) return '-';
    if (typeof unitPrice !== 'number' || isNaN(unitPrice)) return '-';
    const currencyCode = this.currency === 'INR' ? 'INR' : 'USD';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currencyCode }).format(unitPrice);
  }

  // helper used by template instead of Math.round
  round(value: any): number {
    if (value === null || value === undefined || value === '') return 0;
    const n = typeof value === 'number' ? value : Number(value);
    return isNaN(n) ? 0 : Math.round(n);
  }

  /**
   * Accepts rating as number | undefined so template can pass selectedProduct?.rating safely.
   * Returns an array of 'full' | 'half' | 'empty' for 5-star rendering.
   */
  starArray(rating?: number): Array<'full' | 'half' | 'empty'> {
    const out: Array<'full' | 'half' | 'empty'> = [];
    if (rating === null || rating === undefined || isNaN(rating)) {
      for (let i = 0; i < 5; i++) out.push('empty');
      return out;
    }
    let r = Math.round(rating * 2) / 2;
    for (let i = 0; i < 5; i++) {
      if (r >= 1) { out.push('full'); r -= 1; }
      else if (r === 0.5) { out.push('half'); r -= 0.5; }
      else out.push('empty');
    }
    return out;
  }

  // -------------------------
  // Persistence helpers
  // -------------------------

  private persistState(): void {
    try {
      const maxMessages = 400;
      const messagesToSave = this.messages ? this.messages.slice(-maxMessages) : [];

      const state = {
        messages: messagesToSave,
        lastProductsMessageId: this.lastProductsMessageId,
        lastProductsQuery: this.lastProductsQuery,
        usdPerUnit: this.usdPerUnit,
        currency: this.currency
      };
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(state));
    } catch {
      // ignore storage errors
    }
  }

  private restoreState(): void {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      if (!raw) return;
      const s = JSON.parse(raw);

      // clone messages so Angular sees new object identities
      if (Array.isArray(s?.messages)) {
        this.messages = s.messages.map((m: any) => ({ ...m }));
      }

      // restore lastProductsMessageId explicitly
      this.lastProductsMessageId = s?.lastProductsMessageId ?? undefined;
      this.lastProductsQuery = s?.lastProductsQuery ?? undefined;
      if (typeof s?.usdPerUnit === 'number') this.usdPerUnit = s.usdPerUnit;
      if (s?.currency) this.currency = s.currency;

      // Normalize: ensure messages that have products are bot messages; if not, synthesize a bot message after the original
      this.messages.forEach((m, idx) => {
        if (m.products && m.products.length && m.from !== 'bot') {
          const syntheticId = this.genId();
          const synthetic: Message = {
            id: syntheticId,
            from: 'bot',
            text: 'Previously suggested products',
            time: m.time + 1,
            products: m.products
          };
          delete m.products;
          this.messages.splice(idx + 1, 0, synthetic);
        }
      });

      // ensure change detection picks up restored products
      this.messages = this.messages.map(m => ({ ...m }));

      // set convenience current products to the most recent message's products if present
      if (this.lastProductsMessageId) {
        const m = this.messages.find(x => x.id === this.lastProductsMessageId);
        this.products = m?.products ? m.products : [];
      } else {
        this.products = [];
      }

      this.cdr.markForCheck();
      setTimeout(() => this.scrollToBottom(), 40);
    } catch {
      // ignore parse errors
    }
  }

  // trackBy for stable DOM and to preserve per-message DOM state
  trackByMessageId(index: number, m: Message) {
    return m.id;
  }

  private focusInput(delay = 120) {
    if (!this.isBrowser) return;
    setTimeout(() => {
      const el = this.inputEl?.nativeElement ?? document.querySelector<HTMLInputElement>('#copilot-input');
      el?.focus();
    }, delay);
  }

  /** Return true when the first two messages exist and are bot messages */
  get hasWelcomePair(): boolean {
    return Array.isArray(this.messages) && this.messages.length >= 2
      && this.messages[0]?.from === 'bot'
      && this.messages[1]?.from === 'bot';
  }

  /** Return the first two messages (safe slice) */
  get welcomePair(): { id: string; from: 'user' | 'bot'; text: string; time: number }[] {
    if (!Array.isArray(this.messages) || this.messages.length < 2) return [];
    return this.messages.slice(0, 2).map(m => ({ id: m.id, from: m.from, text: m.text, time: m.time }));
  }

}
