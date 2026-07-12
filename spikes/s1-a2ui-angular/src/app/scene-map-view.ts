import { ChangeDetectionStrategy, Component, computed } from '@angular/core';
import { JsonPipe } from '@angular/common';
import {
  AngularComponentImplementation,
  CatalogComponent,
} from '@a2ui/angular/v0_9';
import { z } from 'zod';

export const SceneMapViewApi = {
  name: 'SceneMapView',
  schema: z.object({
    viewport: z.any().optional(),
    markers: z.any().optional(),
  }),
};

interface Viewport {
  lat: number;
  lng: number;
  zoom: number;
  label?: string;
}

interface Marker {
  sceneId: number;
  location: string;
  lat: number;
  lng: number;
  score: number;
}

/**
 * Spike stand-in for the real MapLibre wrapper: renders the /map/* data-model
 * state as text so the renderer's data binding can be verified without a map.
 */
@Component({
  selector: 'scene-map-view',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [JsonPipe],
  template: `
    <div class="map-stub" data-testid="scene-map-view">
      <h2>SceneMapView (stub)</h2>
      <p data-testid="viewport">
        viewport → {{ viewport() | json }}
      </p>
      <ul data-testid="markers">
        @for (m of markers(); track m.sceneId) {
          <li>📍 {{ m.location }} ({{ m.lat }}, {{ m.lng }}) — score {{ m.score }}</li>
        } @empty {
          <li>(no markers)</li>
        }
      </ul>
    </div>
  `,
  styles: `
    .map-stub { border: 2px dashed #888; border-radius: 8px; padding: 1rem; font-family: monospace; }
  `,
})
export class SceneMapView extends CatalogComponent<typeof SceneMapViewApi> {
  readonly viewport = computed(
    () => (this.props()['viewport']?.value() ?? null) as Viewport | null,
  );
  readonly markers = computed(
    () => (this.props()['markers']?.value() ?? []) as Marker[],
  );
}

export const SceneMapViewImplementation: AngularComponentImplementation = {
  ...SceneMapViewApi,
  component: SceneMapView,
};
