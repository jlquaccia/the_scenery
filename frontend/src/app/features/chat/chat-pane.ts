import { Component, inject, signal } from '@angular/core';

import { SCENERY_CONFIG } from '../../core/config';
import { AguiStreamService } from '../../core/services/agui-stream.service';

/**
 * The chat half of the shell.
 *
 * Reads the AG-UI stream through Signals (2.2). At 2.3 A2UI surfaces mount
 * inside the transcript; today assistant turns render as plain text.
 */
@Component({
  selector: 'app-chat-pane',
  template: `
    <section class="pane chat-pane" aria-label="Chat">
      <header class="chat-header">
        <h1>The Scenery</h1>
        <p class="tagline">Find the places a genre actually comes from.</p>
      </header>

      <div class="transcript" role="log" aria-live="polite">
        @for (message of stream.transcript(); track message.id) {
          <article class="turn" [class.user]="message.role === 'user'">
            <span class="who">{{ message.role === 'user' ? 'You' : 'Scenery' }}</span>
            <p>{{ message.content }}</p>
          </article>
        } @empty {
          <p class="placeholder-msg">
            Ask about a scene — “What city has the biggest thrash metal scene?”
          </p>
        }

        @if (stream.isRunning() && !stream.streamingText()) {
          <p class="thinking">Thinking…</p>
        }
        @if (stream.error(); as message) {
          <p class="error" role="alert">Couldn’t reach the agent: {{ message }}</p>
        }
      </div>

      <form class="composer" (submit)="send($event)">
        <input
          type="text"
          [value]="draft()"
          (input)="draft.set($any($event.target).value)"
          placeholder="Ask about a scene…"
          aria-label="Message"
          [disabled]="stream.isRunning()"
        />
        <button type="submit" [disabled]="stream.isRunning() || !draft().trim()">Send</button>
      </form>
    </section>
  `,
  styles: `
    /* The host is a layout no-op: the <section> becomes the shell's grid item
       directly, so it stretches to the full pane height instead of collapsing
       to its content. */
    :host {
      display: contents;
    }
    .chat-pane {
      display: grid;
      grid-template-rows: auto 1fr auto;
      border-inline-start: 1px solid var(--border);
      background: var(--surface);
      min-height: 0;
    }
    .chat-header {
      padding: 1.25rem 1.25rem 0.75rem;
      border-block-end: 1px solid var(--border);
    }
    h1 {
      margin: 0;
      font-size: 1.125rem;
      letter-spacing: 0.01em;
    }
    .tagline {
      margin: 0.25rem 0 0;
      font-size: 0.8125rem;
      color: var(--text-muted);
    }
    .transcript {
      overflow-y: auto;
      padding: 1.25rem;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .turn {
      display: grid;
      gap: 0.25rem;
      font-size: 0.875rem;
      line-height: 1.5;
    }
    .who {
      font-size: 0.6875rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
    }
    .turn p {
      margin: 0;
    }
    .turn.user p {
      padding: 0.5rem 0.75rem;
      border-radius: 8px;
      background: var(--surface-sunken);
    }
    .placeholder-msg,
    .thinking {
      margin: 0;
      color: var(--text-muted);
      font-size: 0.875rem;
      line-height: 1.5;
    }
    .thinking {
      font-style: italic;
    }
    .error {
      margin: 0;
      font-size: 0.8125rem;
      color: var(--accent);
    }
    .composer {
      display: flex;
      gap: 0.5rem;
      padding: 0.875rem 1.25rem;
      border-block-start: 1px solid var(--border);
    }
    input {
      flex: 1;
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface-sunken);
      color: inherit;
      font: inherit;
    }
    button {
      padding: 0.5rem 1rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--accent);
      color: var(--accent-contrast);
      font: inherit;
      cursor: pointer;
    }
    input:disabled,
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
  `,
})
export class ChatPane {
  protected readonly stream = inject(AguiStreamService);
  private readonly config = inject(SCENERY_CONFIG);
  protected readonly draft = signal('');

  protected async send(event: Event): Promise<void> {
    event.preventDefault();
    const text = this.draft();
    this.draft.set('');
    await this.stream.send(text, this.config.aguiUrl);
  }
}
