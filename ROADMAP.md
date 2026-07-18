# The Scenery — Build Roadmap

Companion to [DESIGN.md](DESIGN.md). The design doc says *what* to build; this says *in what
order and why*, broken into **single action items worked one at a time**.

## How to work this roadmap

- One action item per work session. Finish it (including its "done when"), check it off, stop.
- Items within a milestone are ordered by dependency — work top to bottom unless noted otherwise.
- Each spike in M0 is time-boxed to ≤1 day and ends with a written go/fallback outcome in
  `spikes/NOTES.md`.

Guiding principles:

1. **De-risk the young tech first.** A2UI v0.9.1, AG-UI, `ag-ui-langgraph`, and the community
   MySQL checkpointer are the four least-proven dependencies. Each gets a spike with a named
   fallback *before* anything is built on top of it.
2. **Tracer bullet before breadth.** One question flowing end-to-end (chat → agent → MCP tool →
   A2UI → map flyTo) beats three half-built layers.
3. **Stage the multi-agent split.** Single agent first; split into orchestrator + specialists once
   end-to-end works. The MCP tool contract is identical either way, so nothing is thrown away.
4. **Evals define "done" before the thing they test exists.**

---

## Milestone 0 — Spikes & decision gates (week 0)

- [x] **0.1 — Spike S1: A2UI Angular renderer hello-world.** ✅ **GO** — see `spikes/NOTES.md`
  (renderer works; findings: Angular 21 required, zod 3 required, mount surfaces after
  `createSurface`, `provideMarkdownRenderer()` needed).
  Verify the official Angular A2UI renderer works with one custom catalog component (a
  `SceneMapView` stub) reacting to `updateDataModel` messages on `/map/*` paths.
  *Done when:* a minimal Angular app renders the stub from a hand-written A2UI message stream,
  and a go/no-go verdict with fallback recommendation is written to `spikes/NOTES.md`.
  *Fallback if no-go:* keep the A2UI message format, hand-roll a thin renderer for our 3 catalog
  components; worst case, a bespoke JSON event union behind the same Angular service interface.

- [x] **0.2 — Spike S2: `ag-ui-langgraph` ↔ `@ag-ui/client` streaming hello-world.** ✅ **GO** —
  see `spikes/NOTES.md` (custom events carry A2UI payloads intact; checkpointer mandatory;
  bonus: official `get_a2ui_tools` A2UI-generation subagent found for M4).
  A trivial LangGraph graph exposed via `ag-ui-langgraph` on FastAPI, consumed by `@ag-ui/client`;
  confirm custom/activity events can carry A2UI payloads.
  *Done when:* tokens and one custom event round-trip to a bare TS client; verdict in `spikes/NOTES.md`.
  *Fallback:* hand-rolled SSE with typed Pydantic events mirroring AG-UI event names.

- [x] **0.3 — Spike S3: data feasibility (MusicBrainz → thrash ranking).** ✅ **GO** — Bay Area #1
  for thrash, Seattle #1 for grunge, Gothenburg top-3 for melodeath, zero tuning; scoring formula
  v1 drafted in `spikes/NOTES.md`.
  Pull artist↔area data for one genre (thrash) and compute a ranking where the Bay Area lands
  top-3 without hand-tuning. This drafts scoring formula v1.
  *Done when:* a script produces a city ranking from real data + scoring formula v1 is written up.
  *Fallback:* heavier manual curation of seed `scene_signals`.

- [x] **0.4 — Spike S4: MySQL checkpointer viability.** ✅ **GO** — v3.0.0 persists/resumes across
  processes (sync + async savers) against langgraph 1.2.9; single-maintainer package, fallbacks
  stay documented. See `spikes/NOTES.md`.

- [x] **0.5 — Decision gate: record locked decisions.** ✅ `DECISIONS.md` written — scoring
  formula v1, nightly batch, anonymous sessions, LangSmith in dev, A2UI v0.9 entry-point pin
  (+ spike-inherited constraints). **Milestone 0 complete.**
  Write `DECISIONS.md`: scoring formula v1 + weights (Q1), nightly batch freshness for MVP (Q2),
  anonymous sessions / defer auth (Q3), LangSmith for dev tracing (Q5), A2UI version pin (Q7).
  *Done when:* all five decisions recorded with a one-line rationale each.

---

## Milestone 1 — Data foundation (weeks 1–2)

- [x] **1.1 — Repo scaffold + docker-compose.** ✅ Skeleton per DESIGN.md §6; compose stack
  (MySQL 8.4 → Liquibase init → API) healthy end-to-end; Docker via colima.
  Project skeleton per DESIGN.md §6, docker-compose with MySQL + Liquibase init container,
  backend Python project bootstrapped (FastAPI app that boots, health endpoint).
  *Done when:* `docker compose up` gives a healthy MySQL and an empty-but-running API.

- [ ] **1.2 — Debugging & DX baseline.**
  Stand up the debugging toolkit so every later item is easier to diagnose:
  - **Backend:** `structlog` + rich tracebacks (pretty, correlated logs from day one); `debugpy`
    attach config for breakpoints inside graph nodes; **LangGraph Studio** config
    (`langgraph.json` + `langgraph dev`) for visual graph step-through — exercised for real at 3.1.
  - **MCP:** the official **MCP Inspector** (`npx @modelcontextprotocol/inspector`) as the
    interactive console for the scene-db server — used from 1.8 on.
  - **DB:** **Adminer** container in docker-compose (zero-install schema/data browser).
  - **Frontend (spec'd here, built with 2.2–2.3):** Angular DevTools extension, plus a dev-only
    **AG-UI/A2UI event inspector** — logs every event/A2UI message, keeps the last N streams
    replayable/exportable as fixtures (feeds the 2.6 replay harness), and exposes a
    `window.__scenery` debug handle to the renderer (spike S1 had to dig via `ng.getComponent`;
    this bakes the handle in).
  - **Linters/formatters:** backend **Ruff** (lint + format) + **mypy**; frontend
    **angular-eslint** + **Prettier** (added to the workspace at 2.1); config committed, wired
    into VS Code via `.vscode/settings.json` + `extensions.json` (format-on-save, fix-on-save).
  - **`DEBUGGING.md`** cheat sheet tying it together.
  *Done when:* Adminer reachable via compose; a forced backend error shows a rich, correlated
  traceback; debugpy attach documented and tested; Ruff/mypy run clean on the scaffold;
  `DEBUGGING.md` covers all of the above.

- [ ] **1.3 — Liquibase changesets: `genres` + `locations`.**
  SQL-formatted changesets with `--rollback` blocks; changelog-master wiring.
  *Done when:* `liquibase update` and `liquibase rollback` both work against the compose MySQL.

- [ ] **1.4 — Liquibase changesets: `scenes`, `scene_signals`, `conversations`, `messages`.**
  *Done when:* full DESIGN.md §3.3 schema migrates cleanly; SQLAlchemy models match
  (CI-checkable metadata validation).

- [ ] **1.5 — Seed data: ~5 genres × ~50 locations.**
  `context:seed` changesets (or seed scripts) from MusicBrainz/Wikipedia per spike S3 method.
  *Done when:* dev DB contains genres, locations, scenes, and signals for 5 genres.

- [ ] **1.6 — Scoring batch job.**
  Implements formula v1 from 0.5; writes `scene_score` + `score_updated_at`.
  *Done when:* running the job produces nonzero, plausible scores for all seeded scenes.

- [ ] **1.7 — `scene_service` + REST endpoints.**
  `/api/scenes`, `/api/scenes/{id}`, `/api/genres` on the shared service layer.
  *Done when:* `GET /api/scenes?genre=thrash+metal&level=city` returns a ranked list with coords.

- [ ] **1.8 — scene-db MCP server.**
  FastMCP server exposing `query_scenes`, `get_scene_detail`, `compare_scenes`, `resolve_genre`
  over streamable-HTTP, wrapping `scene_service`.
  *Done when:* an external MCP client (MCP Inspector or Claude Desktop) can query scenes.

- [ ] **1.9 — Eval C: golden rankings.**
  `golden_rankings.json` (Bay Area top-3 for thrash, Gothenburg for melodeath, Seattle for
  grunge, …) + Recall@3/NDCG runner wired into CI. Spike S3's `results/*.json` seed the dataset.
  *Done when:* eval C runs in CI and passes against the seeded data.

---

## Milestone 2 — Map UI on recorded messages (weeks 2–3)

No agent yet — the frontend is built against hand-written A2UI streams, which become permanent
fixtures: the frontend contract test *and* golden data for eval D later.

- [ ] **2.1 — Angular workspace scaffold.**
  Workspace per DESIGN.md §6 layout; app shell with map + chat panes (static).
  *Done when:* `ng serve` shows the empty two-pane shell.

- [ ] **2.2 — AG-UI client service.**
  Wrap `@ag-ui/client` in an Angular service exposing the event stream as Signals.
  *Done when:* the service consumes the spike S2 endpoint and Signals update live.

- [ ] **2.3 — A2UI renderer integration + custom catalog registration.**
  Per spike S1 outcome: official renderer or thin custom one; register `SceneMapView`,
  `SceneCard`, `SceneComparison` (stub).
  *Done when:* a hand-written `updateComponents` message renders a `SceneCard` in the chat surface.

- [ ] **2.4 — `SceneMapView` over MapLibre: viewport + markers.**
  React to `updateDataModel` on `/map/viewport` (flyTo) and `/map/markers` (pins).
  *Done when:* a recorded message stream flies the map to SF and drops Bay Area markers.

- [ ] **2.5 — Detail panel + marker click → `userAction`.**
  Slide-out `detail-panel` surface; marker click emits `{name: "explore_scene", context: {sceneId}}`.
  *Done when:* clicking a marker opens the panel and the `userAction` is visible on the wire.

- [ ] **2.6 — Replay harness + golden streams checked in.**
  Stream recorded A2UI sequences through the real transport; check fixtures into
  `backend/evals/datasets/a2ui_golden_messages/`.
  *Done when:* replaying a fixture produces a browsable genre map with working detail panel
  (M2 exit criteria).

---

## Milestone 3 — Tracer bullet: single-agent end-to-end (week 3)

- [ ] **3.1 — Single-agent LangGraph graph on scene-db MCP.**
  One agent (analyst + UI-composer behavior in one prompt) consuming the MCP server via
  `langchain-mcp-adapters`, emitting text + A2UI messages. LangSmith tracing on from first commit.
  *Done when:* invoking the graph in a test yields a chat answer + valid A2UI messages for the
  thrash question.

- [ ] **3.2 — AG-UI streaming endpoint.**
  Expose the graph per spike S2 outcome; A2UI messages ride custom/activity events.
  *Done when:* `curl` of the endpoint shows AG-UI event stream incl. A2UI payloads.

- [ ] **3.3 — Wire the frontend; thrash demo end-to-end.**
  Point the M2 frontend at the live endpoint.
  *Done when:* "What city has the biggest thrash metal scene?" streams a chat answer while the
  map flies to the Bay Area — live agent, real DB (M3 exit criteria).

- [ ] **3.4 — Geo hard-fail check.**
  CI check: every coordinate in `/map/*` updates matches a DB row returned by MCP tools.
  *Done when:* the check runs in CI against recorded agent runs and fails on a poisoned fixture.

---

## Milestone 4 — Agent MVP: the split (weeks 4–5)

- [ ] **4.1 — Orchestrator + Scene Analyst split.**
  Supervisor pattern with `TaskBrief`/`Findings` Pydantic schemas; intent classification
  (scene query / follow-up / chitchat / out-of-scope) on a cheap model.
  *Done when:* the thrash demo still passes, now via orchestrator → Scene Analyst handoff.

- [ ] **4.2 — UI Composer + `a2ui-authoring` skill.**
  UI Composer becomes the sole A2UI author; skill loader with progressive disclosure
  (`load_skill` tool); golden examples in the skill folder.
  *Done when:* all A2UI output flows through the UI Composer and the skill is loaded on demand.

- [ ] **4.3 — `userAction` round trip.**
  Marker click → orchestrator → detail-panel A2UI update.
  *Done when:* clicking a São Paulo marker populates the detail panel via the agent.

- [ ] **4.4 — Comparison queries.**
  "Compare Bay Area thrash to German thrash" → `compare_scenes` tool → `SceneComparison`
  component + dual map markers.
  *Done when:* the comparison demo works end to end.

- [ ] **4.5 — Evals A + B in CI.**
  A: ~200 genre-resolution phrasings (≥95% exact match). B: ~150 labeled intents
  (accuracy + confusion matrix).
  *Done when:* both run in CI and gate PRs touching prompts/graph/scoring (M4 exit criteria
  with 4.1–4.4: full DESIGN.md §2.4 flow incl. follow-ups).

---

## Milestone 5 — Memory & context engineering (weeks 5–6)

Starts only after M4's exit criteria pass — context engineering optimizes a *working* system.

- [ ] **5.1 — MySQL checkpointer.**
  Per spike S4 outcome; thread per conversation.
  *Done when:* refreshing the page mid-conversation resumes exactly where you were.

- [ ] **5.2 — Turn summarizer + scratchpad lifecycle.**
  End-of-turn node folds scratchpad notes into `turn_summary`, then clears; last K≈4 turns
  verbatim, older turns as summaries.
  *Done when:* turn 8 of a scripted conversation sees summaries, not verbatim turn 2.

- [ ] **5.3 — Fact extraction + `memory_store` + selection.**
  Async post-stream extraction node (DESIGN.md A.2), `memory_store` table + `MySQLStore`,
  relevance-filtered fact selection (A.4).
  *Done when:* "I'm from Oakland, mostly into death metal" in session 1 shapes "best scenes
  near me" in a fresh session 2.

- [ ] **5.4 — Cache-friendly assembly + token budget metric.**
  Static-front/dynamic-back context assembly; `context_tokens_used` per tier in trace metadata.
  *Done when:* LangSmith traces show per-tier token counts and prompt-cache hits.

- [ ] **5.5 — Eval E: context & memory regression.**
  10-turn replays assert per-tier budget + turn-10 accuracy; cross-session fact recall; selection
  precision (jazz query pulls no metal facts).
  *Done when:* eval E green (M5 exit criteria).

---

## Milestone 6 — Observability & feedback hardening (weeks 6–7)

- [ ] **6.1 — OTel + correlation ID.**
  FastAPI/SQLAlchemy auto-instrumentation; one `trace_id` per turn spanning OTel ↔ LangSmith ↔
  the SSE `done` event.
  *Done when:* a turn can be traced from browser console → FastAPI span → agent trace → SQL.

- [ ] **6.2 — 👍/👎 feedback loop.**
  Thumbs in the chat UI → LangSmith feedback attached to the turn's trace.
  *Done when:* a thumbs-down in the UI is visible on the exact trace in LangSmith.

- [ ] **6.3 — Dashboards + alerts.**
  p95 latency by node, tokens+cost per turn, tool error rate, cache hit rate, context-budget SLO
  alert (p95 > ~5k tokens).
  *Done when:* the minimum dashboard set from DESIGN.md §9.3 exists.

- [ ] **6.4 — LLM-as-judge nightly eval.**
  Eval D rubric (faithfulness, completeness, tone) on sampled traces + the ~50 scripted
  conversations; nightly schedule.
  *Done when:* a nightly run posts scores and the trend is dashboard-visible.

---

## Milestone 7 — Enrichment (ongoing)

- [ ] **7.1 — Music Research agent.** External MCP servers (MusicBrainz, web search);
  `provenance: "external"` badging in the UI.
- [ ] **7.2 — Agent-powered ingestion pipeline.** Writes `scene_signals`; fully decoupled from
  the chat agent.
- [ ] **7.3 — Coverage expansion.** More genres/regions; choropleth layer; more skills.
- [ ] **7.4 — Deferred decisions.** Auth + memory governance (DESIGN.md §11 Q3/Q10) before
  semantic memory ships to real users; LangSmith vs. Langfuse before production traffic.

---

## Critical path & cut lines

**Critical path:** 0.1/0.2 → 1.8 (scene-db MCP) → 2.3–2.4 (renderer + map) → 3.3 (tracer bullet)
→ M4 split. Data work (0.3 → 1.5/1.6) can run in parallel with frontend work (M2).

**If time-pressed, cut in this order (all restorable later):**
1. Music Research agent + external sources (M7)
2. Memory beyond the checkpointer (5.3) — M5 shrinks to persistence + summarizer
3. Comparison queries (4.4)
4. The multi-agent split itself (stay at M3's single agent longer) — a pure refactor whenever ready

**Do not cut:** eval C (1.9), the geo hard-fail check (3.4), LangSmith-from-day-one (3.1),
the recorded A2UI fixtures (2.6). Each costs hours now and saves days later.

## Top risks

| Risk | Mitigation |
|---|---|
| A2UI Angular renderer immature | Spike 0.1 + fallback renderer; spec-touching code isolated in `frontend/src/app/a2ui/` |
| Seed data can't support credible rankings | Spike 0.3 before schema hardens; eval C makes quality measurable |
| `ag-ui-langgraph` gaps for custom events | Spike 0.2; hand-rolled SSE fallback keeps the frontend contract |
| Memory system built before agent is good | Hard ordering: M5 starts only after M4 exit criteria |
| Community MySQL checkpointer abandoned | Spike 0.4; custom saver fallback sketched in DESIGN.md A.3 |
