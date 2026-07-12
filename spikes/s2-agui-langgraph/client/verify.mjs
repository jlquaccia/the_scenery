// Spike S2 client: consume the AG-UI stream with @ag-ui/client and assert
// that (a) text-message content and (b) the a2ui_messages CUSTOM event arrive.
import { HttpAgent } from '@ag-ui/client';

const agent = new HttpAgent({
  url: 'http://localhost:8020/agui',
  threadId: 'spike-thread-1',
});

agent.messages = [
  { id: 'm1', role: 'user', content: 'What city has the biggest thrash metal scene?' },
];

const received = { text: '', customEvents: [], lifecycle: [] };

const result = await agent.runAgent(undefined, {
  onRunStartedEvent: () => received.lifecycle.push('RUN_STARTED'),
  // Note: textMessageBuffer excludes the in-flight delta during the content
  // callback (it is complete only at END) — accumulate deltas instead.
  onTextMessageContentEvent: ({ event }) => {
    received.text += event.delta;
  },
  onEvent: ({ event }) => {
    // manually_emit_message leaks a duplicate CUSTOM event — filter it.
    if (event.type === 'CUSTOM' && event.name !== 'manually_emit_message') {
      received.customEvents.push({ name: event.name, value: event.value });
    }
  },
  onRunFinishedEvent: () => received.lifecycle.push('RUN_FINISHED'),
});

const a2ui = received.customEvents.find((e) => e.name === 'a2ui_messages');
const viewport = a2ui?.value?.[0]?.updateDataModel?.value;

const checks = {
  'lifecycle events received': received.lifecycle.join(' → ') === 'RUN_STARTED → RUN_FINISHED',
  'text message streamed': received.text.includes('Bay Area'),
  'a2ui_messages CUSTOM event received': !!a2ui,
  'A2UI payload intact (SF viewport)': viewport?.lat === 37.77 && viewport?.lng === -122.42,
  'final assistant message in agent.messages':
    agent.messages.at(-1)?.role === 'assistant' && agent.messages.at(-1)?.content.includes('Bay Area'),
};

console.log('--- Spike S2 verification ---');
for (const [name, ok] of Object.entries(checks)) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
}
console.log('\ntext:', JSON.stringify(received.text));
console.log('a2ui payload:', JSON.stringify(a2ui?.value));
console.log('runAgent result keys:', Object.keys(result ?? {}).join(', '));

process.exit(Object.values(checks).every(Boolean) ? 0 : 1);
