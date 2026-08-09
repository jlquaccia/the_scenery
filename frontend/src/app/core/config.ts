import { InjectionToken } from '@angular/core';

export interface SceneryConfig {
  /** AG-UI endpoint the chat streams from. */
  aguiUrl: string;
}

/**
 * Injected so tests and later milestones can swap the endpoint without touching
 * components. Points at the spike S2 server until the real streaming endpoint
 * lands at 3.2 (`backend/app/api`), which speaks the same protocol.
 */
export const SCENERY_CONFIG = new InjectionToken<SceneryConfig>('SCENERY_CONFIG', {
  providedIn: 'root',
  factory: () => ({ aguiUrl: 'http://localhost:8020/agui' }),
});
