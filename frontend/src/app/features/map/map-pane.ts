import { Component } from '@angular/core';

/**
 * The map half of the shell.
 *
 * Static at 2.1 — a MapLibre canvas replaces the placeholder at 2.4, driven by
 * `updateDataModel` messages on `/map/viewport` and `/map/markers`. This
 * component owns the pane; `SceneMapView` (the A2UI catalog component, 2.3)
 * will render into it.
 */
@Component({
  selector: 'app-map-pane',
  template: `
    <section class="pane map-pane" aria-label="Scene map">
      <div class="placeholder">
        <h2>Map</h2>
        <p>MapLibre canvas lands at 2.4.</p>
      </div>
    </section>
  `,
  styles: `
    /* See chat-pane: the host stays out of the layout so the <section> is the
       shell's grid item. */
    :host {
      display: contents;
    }
    .map-pane {
      background:
        radial-gradient(
          circle at 30% 30%,
          color-mix(in srgb, var(--accent) 12%, transparent),
          transparent 60%
        ),
        var(--surface-sunken);
      display: grid;
      place-items: center;
    }
  `,
})
export class MapPane {}
