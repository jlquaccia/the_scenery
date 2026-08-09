import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { AguiStreamService } from './agui-stream.service';

/**
 * The two behaviours pinned here are spike S2 findings — both were wrong in the
 * obvious implementation, and neither shows up as an error, just as subtly wrong
 * output. See spikes/NOTES.md S2.
 */

interface Callbacks {
  onTextMessageContentEvent?: (arg: { event: { delta: string } }) => void;
  onEvent?: (arg: { event: { type: string; name?: string; value?: unknown } }) => void;
}

const runAgent = vi.fn();

vi.mock('@ag-ui/client', () => ({
  HttpAgent: class {
    messages: unknown[] = [];
    runAgent = (_: unknown, callbacks: Callbacks) => runAgent(callbacks);
  },
}));

describe('AguiStreamService', () => {
  let service: AguiStreamService;

  beforeEach(() => {
    runAgent.mockReset();
    TestBed.configureTestingModule({});
    service = TestBed.inject(AguiStreamService);
  });

  it('accumulates deltas into one assistant turn', async () => {
    runAgent.mockImplementation((cb: Callbacks) => {
      cb.onTextMessageContentEvent?.({ event: { delta: 'The Bay Area ' } });
      cb.onTextMessageContentEvent?.({ event: { delta: 'remains the heart of thrash.' } });
      return Promise.resolve();
    });

    await service.send('where is thrash?', 'http://test/agui');

    expect(service.messages().map((m) => `${m.role}: ${m.content}`)).toEqual([
      'user: where is thrash?',
      'assistant: The Bay Area remains the heart of thrash.',
    ]);
    // Streaming buffer is handed to the transcript, then cleared.
    expect(service.streamingText()).toBe('');
    expect(service.status()).toBe('idle');
  });

  it('takes a2ui_messages but ignores the duplicate manually_emit_message', async () => {
    const a2ui = { version: 'v0.9', updateDataModel: { path: '/map/viewport' } };
    runAgent.mockImplementation((cb: Callbacks) => {
      cb.onEvent?.({ event: { type: 'CUSTOM', name: 'manually_emit_message', value: ['nope'] } });
      cb.onEvent?.({ event: { type: 'CUSTOM', name: 'a2ui_messages', value: [a2ui] } });
      return Promise.resolve();
    });

    await service.send('hi', 'http://test/agui');

    expect(service.a2uiMessages()).toEqual([a2ui]);
  });

  it('surfaces transport failures instead of hanging', async () => {
    runAgent.mockImplementation(() => Promise.reject(new Error('connection refused')));

    await service.send('hi', 'http://test/agui');

    expect(service.status()).toBe('error');
    expect(service.error()).toContain('connection refused');
    expect(service.isRunning()).toBe(false);
  });

  it('ignores empty input and re-entrant sends', async () => {
    await service.send('   ', 'http://test/agui');
    expect(runAgent).not.toHaveBeenCalled();
    expect(service.messages()).toEqual([]);
  });

  it('shows the in-flight turn in the transcript while streaming', async () => {
    runAgent.mockImplementation((cb: Callbacks) => {
      cb.onTextMessageContentEvent?.({ event: { delta: 'partial…' } });
      // Assert mid-run: the transcript must already include the streamed text.
      expect(service.transcript().at(-1)).toMatchObject({
        role: 'assistant',
        content: 'partial…',
      });
      return Promise.resolve();
    });

    await service.send('hi', 'http://test/agui');
    expect(service.transcript().at(-1)?.id).not.toBe('streaming');
  });
});
