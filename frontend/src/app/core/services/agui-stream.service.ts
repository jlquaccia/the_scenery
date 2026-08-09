import { Injectable, computed, isDevMode, signal } from '@angular/core';
import { HttpAgent } from '@ag-ui/client';

/** A chat turn as the transcript renders it. */
export interface TranscriptMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

/** An A2UI message lifted off a CUSTOM event — opaque here, parsed at 2.3. */
export type A2uiMessage = Record<string, unknown>;

/** Named for the wire events it mirrors (DESIGN.md §2.5). */
export type RunStatus = 'idle' | 'running' | 'error';

const A2UI_EVENT = 'a2ui_messages';

/**
 * The AG-UI stream, as Angular Signals.
 *
 * `@ag-ui/client` is framework-agnostic and callback-driven; this is the thin
 * adapter DESIGN.md §2.5 calls for — everything downstream (chat transcript,
 * map, context chips, the A2UI renderer at 2.3) reads Signals and never touches
 * the transport.
 *
 * Two behaviours here are spike S2 findings, not preferences:
 *  - accumulate `event.delta` during streaming. `textMessageBuffer` excludes the
 *    in-flight delta and is only complete at TEXT_MESSAGE_END.
 *  - ignore the CUSTOM event named `manually_emit_message`. The backend uses it
 *    to emit an assistant message, and it arrives a second time as a raw CUSTOM
 *    event; taking it as A2UI would duplicate every turn.
 */
@Injectable({ providedIn: 'root' })
export class AguiStreamService {
  private readonly _messages = signal<TranscriptMessage[]>([]);
  private readonly _streamingText = signal('');
  private readonly _status = signal<RunStatus>('idle');
  private readonly _error = signal<string | null>(null);
  private readonly _a2uiMessages = signal<A2uiMessage[]>([]);

  /** Completed turns, oldest first. */
  readonly messages = this._messages.asReadonly();
  /** Text of the answer currently streaming in ('' when nothing is). */
  readonly streamingText = this._streamingText.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  /** Every A2UI message seen this session, in arrival order (2.3 consumes it). */
  readonly a2uiMessages = this._a2uiMessages.asReadonly();

  readonly isRunning = computed(() => this._status() === 'running');
  /** What the transcript renders: settled turns plus the in-flight one. */
  readonly transcript = computed<TranscriptMessage[]>(() => {
    const streaming = this._streamingText();
    return streaming
      ? [...this._messages(), { id: 'streaming', role: 'assistant', content: streaming }]
      : this._messages();
  });

  private agent?: HttpAgent;

  constructor() {
    this.threadId = crypto.randomUUID();
    if (isDevMode()) {
      // Dev-only console handle, specified at roadmap 1.2: spike S1 had to dig
      // through `ng.getComponent` to inspect anything, so bake the handle in.
      // Every AG-UI event and A2UI message is reachable from here.
      (globalThis as Record<string, unknown>)['__scenery'] = {
        stream: this,
        threadId: this.threadId,
        events: this.eventLog,
        dump: () => ({
          status: this._status(),
          messages: this._messages(),
          streamingText: this._streamingText(),
          a2uiMessages: this._a2uiMessages(),
          events: this.eventLog,
        }),
      };
    }
  }

  /** Dev-only ring of raw AG-UI events; feeds the 2.6 replay fixtures. */
  private readonly eventLog: { type: string; name?: string }[] = [];

  /** One conversation per browser session — anonymous, per DECISIONS.md D3. */
  private threadId: string;

  private connect(url: string): HttpAgent {
    if (!this.agent) {
      this.agent = new HttpAgent({ url, threadId: this.threadId });
    }
    return this.agent;
  }

  /** Send a user turn and stream the answer back into the Signals. */
  async send(text: string, url: string): Promise<void> {
    const content = text.trim();
    if (!content || this.isRunning()) {
      return;
    }

    const agent = this.connect(url);
    const userMessage: TranscriptMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    };
    this._messages.update((messages) => [...messages, userMessage]);
    this._streamingText.set('');
    this._error.set(null);
    this._status.set('running');

    // The agent owns the message history the backend sees.
    agent.messages = this._messages().map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
    }));

    try {
      await agent.runAgent(undefined, {
        onTextMessageContentEvent: ({ event }) => {
          this._streamingText.update((text) => text + event.delta);
        },
        onEvent: ({ event }) => {
          if (isDevMode()) {
            const named = event as unknown as { name?: string };
            this.eventLog.push({ type: event.type, name: named.name });
          }
          if (event.type === 'CUSTOM') {
            const custom = event as unknown as { name: string; value: unknown };
            if (custom.name === A2UI_EVENT && Array.isArray(custom.value)) {
              this._a2uiMessages.update((all) => [...all, ...(custom.value as A2uiMessage[])]);
            }
          }
        },
      });
      this.settleStreamedTurn();
      this._status.set('idle');
    } catch (cause) {
      this._streamingText.set('');
      this._status.set('error');
      this._error.set(cause instanceof Error ? cause.message : String(cause));
    }
  }

  /** Move the streamed text into the transcript as a settled turn. */
  private settleStreamedTurn(): void {
    const content = this._streamingText();
    this._streamingText.set('');
    if (!content) {
      return;
    }
    this._messages.update((messages) => [
      ...messages,
      { id: crypto.randomUUID(), role: 'assistant', content },
    ]);
  }
}
