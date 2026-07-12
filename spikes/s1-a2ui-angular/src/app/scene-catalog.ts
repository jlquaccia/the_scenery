import { AngularCatalog, BASIC_COMPONENTS } from '@a2ui/angular/v0_9';
import { SceneMapViewImplementation } from './scene-map-view';

/** Catalog id referenced by createSurface messages. */
export const SCENE_CATALOG_ID = 'https://thescenery.example/catalogs/scene/catalog.json';

/** The basic catalog extended with The Scenery's custom components. */
export const sceneCatalog = new AngularCatalog(SCENE_CATALOG_ID, [
  ...BASIC_COMPONENTS,
  SceneMapViewImplementation,
]);
