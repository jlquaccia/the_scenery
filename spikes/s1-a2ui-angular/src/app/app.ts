import { Component, inject, signal } from '@angular/core';
import { A2uiRendererService, SurfaceComponent } from '@a2ui/angular/v0_9';

import { THRASH_QUERY_MESSAGES, FOLLOW_UP_MESSAGES } from './fake-agent-messages';

@Component({
  selector: 'app-root',
  imports: [SurfaceComponent],
  template: `
    <h1>Spike S1 — A2UI Angular renderer + custom catalog</h1>
    <p>
      <button (click)="simulateThrashQuery()">1. Simulate thrash query</button>
      <button (click)="simulateFollowUp()" [disabled]="!surfaceReady()">
        2. Simulate follow-up (fly to São Paulo)
      </button>
    </p>
    @if (surfaceReady()) {
      <!-- Finding: mount the surface only after createSurface has been processed.
           A host that initializes before its surface exists never recovers. -->
      <a2ui-v09-surface surfaceId="map" />
    }
  `,
  styles: [`button { margin-right: .5rem; }`],
})
export class App {
  private readonly renderer = inject(A2uiRendererService);
  readonly surfaceReady = signal(false);

  simulateThrashQuery(): void {
    if (this.surfaceReady()) {
      return; // surface already created; replay only the data updates
    }
    this.renderer.processMessages(THRASH_QUERY_MESSAGES);
    this.surfaceReady.set(true);
  }

  simulateFollowUp(): void {
    this.renderer.processMessages(FOLLOW_UP_MESSAGES);
  }
}
