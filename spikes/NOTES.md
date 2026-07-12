# Spike Notes

## S1 — A2UI Angular renderer + custom catalog (roadmap 0.1)

**Date:** 2026-07-10 · **Verdict: GO** ✅

The official Angular renderer (`@a2ui/angular`) works for our architecture. A minimal app
(`spikes/s1-a2ui-angular/`) registers a custom `SceneMapView` catalog component and drives it
with hand-written A2UI v0.9 messages:

- `createSurface` → `updateComponents` (Column + Text + `SceneMapView` with props bound to
  `/map/viewport` and `/map/markers`) → `updateDataModel` renders the full tree with exact values.
- A follow-up `updateDataModel` on `/map/viewport` propagates reactively into the custom
  component's signals while other bindings stay untouched — exactly what the real MapLibre
  wrapper needs to trigger `flyTo` from an `effect()`.

**To reproduce:** `npx ng serve` in `spikes/s1-a2ui-angular/`, click button 1, then button 2.

### Findings (feed these into M2, task 2.3)

1. **Package/spec version split.** npm `@a2ui/angular@0.10.3` + `@a2ui/web_core@0.10.4`; the
   *spec* version is selected by entry point — import from `@a2ui/angular/v0_9`. "Pin v0.9.1"
   (DECISIONS.md-to-be) means: pin the `/v0_9` entry point; track package patch releases.
2. **Angular version constraint.** Renderer peers on Angular `^21.2.5`; Angular 22 (current CLI
   default) is rejected. The M2 frontend must scaffold on Angular 21 until upstream catches up.
3. **zod v3 required.** `web_core` and the renderer use zod `^3.25.76`; the Angular CLI hoists
   zod 4 to the root. Add an explicit app dependency `zod@^3.25.76` or custom catalog schemas
   fail type-checking against `ComponentApi`.
4. **Surface mount-order gotcha (the big one).** `ComponentHostComponent.setupComponent` runs in
   an effect that only tracks its *inputs*. If `<a2ui-v09-surface>` mounts before the
   `createSurface` message is processed, it logs "Surface X not found" and **never recovers**.
   Mount surfaces behind an `@if` that flips after the surface exists (in the real app: keyed off
   the AG-UI stream service). Also: replaying `createSurface` for an existing id throws
   `A2uiStateError` — the replay harness (2.6) must reset or delete surfaces between runs.
5. **`provideMarkdownRenderer()` is required** (undocumented) — the `Text` component injects
   `MarkdownRenderer` and crashes at render time without it.
6. **Custom component recipe** (worked first try once the above were fixed):
   `class SceneMapView extends CatalogComponent<typeof Api>` reading `props()['x'].value()`
   via `computed()`; register with `new AngularCatalog(id, [...BASIC_COMPONENTS, {name, schema, component}])`;
   reference the catalog id in `createSurface.catalogId`.
7. **Not exercised here:** `userAction` dispatch (surface has `dispatchAction`; the configured
   `actionHandler` is wired but untested) — cover in M2 task 2.5.

## S2 — ag-ui-langgraph ↔ @ag-ui/client (roadmap 0.2)

**Date:** 2026-07-11 · **Verdict: GO** ✅

A deterministic (LLM-free) LangGraph graph exposed via `add_langgraph_fastapi_endpoint`
(`spikes/s2-agui-langgraph/server/app.py`) streams to `@ag-ui/client`'s `HttpAgent`
(`client/verify.mjs`). All five checks pass: lifecycle events, token stream, CUSTOM event
carrying an A2UI payload byte-intact, and final message sync.

**To reproduce:** `server$ .venv/bin/uvicorn app:app --port 8020`, then `client$ node verify.mjs`.

### Findings (feed into M3, tasks 3.1–3.2)

1. **Custom events are the A2UI carrier, confirmed.** `adispatch_custom_event("a2ui_messages", [...])`
   in a node → AG-UI `CUSTOM` event with `name`/`value` intact at the client. No custom glue needed.
2. **A checkpointer is mandatory.** `LangGraphAgent` calls `graph.aget_state()`; a graph compiled
   without a checkpointer 500s (`ValueError: No checkpointer set`). `InMemorySaver` suffices until
   M5's MySQL saver.
3. **LLM-free text streaming exists**: `adispatch_custom_event("manually_emit_message",
   {"message_id", "message"})` → TEXT_MESSAGE_START/CONTENT/END. Useful for canned responses and
   tests. Quirk: it *also* leaks a duplicate `CUSTOM` event named `manually_emit_message` — the
   client must filter that name.
4. **Client buffer semantics:** in `onTextMessageContentEvent`, `textMessageBuffer` does NOT yet
   include the current delta (complete only at END) — accumulate `event.delta` in the Angular
   stream service.
5. **The wire is noisy:** every LangGraph event is mirrored as an AG-UI `RAW` event (~half the
   stream). Check for a raw-event opt-out flag in M3; otherwise it's wasted bandwidth in prod.
6. **Bonus discovery:** `ag-ui-langgraph` now ships `get_a2ui_tools` (via its `ag-ui-a2ui-toolkit`
   dependency) — an official LLM subagent that generates *schema-validated* A2UI surfaces with a
   retry/recovery loop, streaming progressively as tool-call arg deltas. Evaluate it as the core
   of the UI Composer in M4 (task 4.2) instead of hand-rolling A2UI generation. It defaults to the
   basic catalog; check custom-catalog support (`catalog` param in `A2UIToolParams`).
7. Versions: `ag-ui-langgraph 0.0.42`, `ag-ui-protocol 0.1.19`, `langgraph 1.2.9`,
   `@ag-ui/client` latest (client dir `package.json`). Python 3.13 works.

## S3 — MusicBrainz data feasibility (roadmap 0.3)

**Date:** 2026-07-11 · **Verdict: GO** ✅

`spikes/s3-musicbrainz/fetch_and_rank.py` pulls artists by tag from the MusicBrainz search API
(1 req/sec, bands only, located via `begin-area`) and ranks cities by band count — the simplest
possible scoring core. Results (`results/*.json`), zero tuning:

- **thrash metal** (500 of 2,705 tagged artists): **SF Bay Area #1** (22 bands) after metro
  rollup; Greater LA #2 among metros; Belo Horizonte, Tokyo, Melbourne all surface. Raw cities:
  LA 13, SF 9, Oakland 7.
- **grunge** (300 artists): **Seattle #1 raw** (23 bands, +53% over #2 LA). Textbook.
- **melodic death metal** (300 artists): Helsinki 9, **Gothenburg 7 (top-3 ✓)**, Stockholm 6.

All three eval-C golden cases pass already — these runs ARE the seed of the golden dataset (1.9).

### Scoring formula v1 (input to decision gate 0.5)

- **Signal:** one MusicBrainz artist of type Group tagged with the genre, located via
  `begin-area` = one `band` signal, weight 1.0, keyed by MBID.
- **Score:** `scene_score(genre, location) = Σ signal weights`, rolled up through OUR locations
  hierarchy (city → metro/region → country), normalized 0–100 per (genre, level):
  `100 * count / max_count`.
- **Deferred refinements** (iterate against eval C, not now): historic-era multiplier from band
  begin dates, active-status weighting, venue/festival/label signals, popularity via release counts.

### Findings (feed into M1, tasks 1.5–1.6, and the ingestion pipeline)

1. **Coverage is excellent:** 494/497 thrash bands have a usable location; 2,705 artists carry
   the tag (we fetched the top 500 by search relevance).
2. **Area levels are mixed:** `begin-area` may be a city, subdivision, or country — "United
   States" (16) and "Germany" (13) polluted the raw city ranking. Ingestion must resolve each MB
   area's type/parent chain (`/ws/2/area/{id}?inc=area-rels`) and attribute the signal at the
   right `locations.level`. Country-level attributions feed country scenes, not cities.
3. **Metro regions are ours to define.** MusicBrainz has no metro concept (SF chains to
   California, not "Bay Area"). The spike's metro city lists are a stand-in for `locations`
   parent rows — geography curation, not score tuning. Seed the handful of metros that matter
   per genre in 1.5.
4. **Identity by MBID**, not name — same-named bands exist (a non-Swedish "Bloodbath" landed in
   the Bay Area count).
5. **Rate limit is a non-issue for nightly batch:** ~5 genres × 5 pages + ~100 area lookups ≈
   minutes at 1 req/sec. Cache area resolutions locally.

## S4 — MySQL checkpointer viability (roadmap 0.4)

_Not started._
