# The Scenery — Frontend

Angular **21** workspace (the A2UI renderer's peer range — DECISIONS.md D5, spikes/NOTES.md S1).

```bash
cd frontend
npm install
npm start          # ng serve → http://localhost:4200
npm run lint       # angular-eslint
npm run build
npx ng test --watch=false
npx prettier --write "src/**/*.{ts,html,css}"
```

## Layout (DESIGN.md §6)

```
src/app/
├── core/services/     # AG-UI stream service, surface registry     (2.2)
├── a2ui/              # A2UI renderer integration + custom catalog (2.3)
│   └── components/    #   SceneMapView, SceneCard, SceneComparison
├── features/map/      # MapLibre wrapper used by SceneMapView      (2.4)
├── features/chat/     # transcript + composer                      (2.2)
└── shared/models/     # catalog + data-model TypeScript types
```

`app.ts` is the shell: a CSS grid with the map pane left and the chat pane right, stacking to
map-over-chat under 720px. Both panes are static until 2.2–2.4.

**Pane hosts use `:host { display: contents }`** so the `<section>` inside each component
becomes the shell grid's item directly. Without it the host stretches but the section keeps its
content height, and the chat composer floats mid-pane instead of sitting at the bottom.

## Constraints inherited from the spikes

Applied when the renderer lands at 2.3, not before:

- `zod@^3.25.76` as an explicit dependency
- `provideMarkdownRenderer()` in the app providers
- import from the versioned entry point `@a2ui/angular/v0_9` — the spec version is the pin, not
  the package version
- surfaces only mount after `createSurface`
- all spec-touching code stays under `src/app/a2ui/`

The working A2UI reference is `spikes/s1-a2ui-angular/`.
