import { Component } from '@angular/core';

/**
 * The chat half of the shell.
 *
 * Static at 2.1. At 2.2 the composer sends through the AG-UI client service and
 * the transcript renders streamed `TEXT_MESSAGE_CONTENT`; at 2.3 A2UI surfaces
 * (SceneCard and friends) mount inside the transcript. The input is disabled
 * until there is something to send.
 */
@Component({
  selector: 'app-chat-pane',
  template: `
    <section class="pane chat-pane" aria-label="Chat">
      <header class="chat-header">
        <h1>The Scenery</h1>
        <p class="tagline">Find the places a genre actually comes from.</p>
      </header>

      <div class="transcript">
        <p class="placeholder-msg">
          Ask about a scene once the agent is wired up — “What city has the biggest thrash metal
          scene?”
        </p>
      </div>

      <form class="composer" (submit)="$event.preventDefault()">
        <input
          type="text"
          placeholder="Streaming chat arrives at 2.2"
          aria-label="Message"
          disabled
        />
        <button type="submit" disabled>Send</button>
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
    }
    .placeholder-msg {
      margin: 0;
      color: var(--text-muted);
      font-size: 0.875rem;
      line-height: 1.5;
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
export class ChatPane {}
