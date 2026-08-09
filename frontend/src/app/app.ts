import { Component } from '@angular/core';

import { ChatPane } from './features/chat/chat-pane';
import { MapPane } from './features/map/map-pane';

/**
 * App shell: map on the left, chat on the right (DESIGN.md §2.2).
 *
 * Both panes are static at 2.1 — this item exists to fix the layout and the
 * workspace structure everything else hangs off.
 */
@Component({
  selector: 'app-root',
  imports: [MapPane, ChatPane],
  template: `
    <main class="shell">
      <app-map-pane />
      <app-chat-pane />
    </main>
  `,
  styleUrl: './app.css',
})
export class App {}
