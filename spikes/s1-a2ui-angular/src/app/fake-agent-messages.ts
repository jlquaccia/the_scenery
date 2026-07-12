import type { A2uiMessage } from '@a2ui/web_core/v0_9';
import { SCENE_CATALOG_ID } from './scene-catalog';

/**
 * Hand-written A2UI v0.9 message stream simulating what the UI Composer agent
 * will emit for: "What city has the biggest thrash metal scene?"
 */
export const THRASH_QUERY_MESSAGES: A2uiMessage[] = [
  {
    version: 'v0.9',
    createSurface: {
      surfaceId: 'map',
      catalogId: SCENE_CATALOG_ID,
    },
  },
  {
    version: 'v0.9',
    updateComponents: {
      surfaceId: 'map',
      components: [
        {
          id: 'root',
          component: 'Column',
          children: ['headline', 'the-map'],
        },
        {
          id: 'headline',
          component: 'Text',
          text: { path: '/map/headline' },
        },
        {
          id: 'the-map',
          component: 'SceneMapView',
          viewport: { path: '/map/viewport' },
          markers: { path: '/map/markers' },
        },
      ],
    },
  },
  {
    version: 'v0.9',
    updateDataModel: {
      surfaceId: 'map',
      path: '/map',
      value: {
        headline: 'Thrash Metal — top city scenes',
        viewport: { lat: 37.77, lng: -122.42, zoom: 8, label: 'San Francisco Bay Area' },
        markers: [
          { sceneId: 17, location: 'San Francisco Bay Area', lat: 37.77, lng: -122.42, score: 94.2 },
          { sceneId: 43, location: 'São Paulo', lat: -23.55, lng: -46.63, score: 81.0 },
          { sceneId: 51, location: 'Ruhr Region', lat: 51.45, lng: 7.01, score: 76.4 },
        ],
      },
    },
  },
] as A2uiMessage[];

/** Simulated follow-up turn: "tell me more about São Paulo" → viewport flies south. */
export const FOLLOW_UP_MESSAGES: A2uiMessage[] = [
  {
    version: 'v0.9',
    updateDataModel: {
      surfaceId: 'map',
      path: '/map/viewport',
      value: { lat: -23.55, lng: -46.63, zoom: 10, label: 'São Paulo' },
    },
  },
  {
    version: 'v0.9',
    updateDataModel: {
      surfaceId: 'map',
      path: '/map/headline',
      value: 'São Paulo thrash — Sepultura, Korzus…',
    },
  },
] as A2uiMessage[];
