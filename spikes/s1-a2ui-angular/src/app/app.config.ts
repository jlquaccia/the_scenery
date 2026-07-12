import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import {
  A2UI_RENDERER_CONFIG,
  A2uiRendererService,
  provideMarkdownRenderer,
} from '@a2ui/angular/v0_9';

import { routes } from './app.routes';
import { sceneCatalog } from './scene-catalog';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    {
      provide: A2UI_RENDERER_CONFIG,
      useValue: {
        catalogs: [sceneCatalog],
        actionHandler: (action: unknown) => {
          console.log('[spike] userAction dispatched:', action);
        },
      },
    },
    A2uiRendererService,
    provideMarkdownRenderer(),
  ],
};
