import { Injectable } from '@angular/core';
import { HttpClient ,HttpHeaders} from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { Observable } from 'rxjs';

export interface Message {
  id: string; from: 'user' | 'bot';
  text?: string;
  timestamp?: string;
  raw?: any; // full API response if needed
}
export interface ContentItem {
  id: string;
  title: string;
  description: string;
  imageUrl?: string;
  link?: string;
}
@Injectable({
  providedIn: 'root',
})


export class Chat {
  
   private readonly apiUrl = 'https://chatbot-mcp-client-service-888916268766.us-central1.run.app/chat';
   constructor(private http: HttpClient) { }
   /** * Send the chat payload to the external API. * The API expects JSON like: * { question: string, history: [{ role: 'user'|'assistant', content: string }] } */
   async postChat(payload: any): Promise<any> {
    const headers = new HttpHeaders({ 'Content-Type': 'application/json' });
    const obs = this.http.post(this.apiUrl, payload, { headers });
    return firstValueFrom(obs);
  }
}
