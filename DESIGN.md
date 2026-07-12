# Design Plan: Music Scene Locator ("The Scenery")
A web application that answers questions like *"What city has the biggest thrash metal scene?"* through a conversational AI agent, with an interactive map that updates in real time based on the conversation.
---
## 1. High-Level Architecture
```
┌─────────────────────────────────────────────┐
│                Angular Frontend             │
│  ┌───────────────┐      ┌────────────────┐  │
│  │   Chat UI     │◄────►│    Map UI      │  │
│  │  (streaming)  │      │ (Leaflet/      │  │
│  │               │      │  MapLibre GL)  │  │
│  └──────┬────────┘      └───────▲────────┘  │
│         │   Shared State Service │          │
│         │   (Signals / RxJS)     │          │
└─────────┼────────────────────────┼──────────┘
          │ WebSocket / SSE        │ map commands
┌─────────▼────────────────────────┴──────────┐
│           Python Backend (FastAPI)          │
│  ┌────────────────────────────────────────┐ │
│  │        LangGraph Agent Runtime         │ │
│  │  Router → Tools → Response Synthesizer │ │
│  └──────┬─────────────────┬───────────────┘ │
│         │                 │                 │
│   ┌─────▼─────┐    ┌──────▼──────┐          │
│   │  MySQL    │    │ External    │          │
│   │  (scene   │    │ APIs (opt.) │          │
│   │   data)   │    │ MusicBrainz,│          │
│   └───────────┘    │ Bandcamp... │          │
│                    └─────────────┘          │
└─────────────────────────────────────────────┘
```
**Core interaction loop:**
1. User asks a question in the chat ("Where's the biggest thrash scene?")
2. LangGraph agent interprets it, queries MySQL (and optionally external sources)
3. Agent streams back two things simultaneously:
   - **Natural language answer** → rendered in chat
   - **Structured map commands** (JSON) → consumed by the map component
4. Map flies to the location, drops markers, renders heat/choropleth layers
---
## 2. Frontend (Angular + TypeScript)
### 2.1 Component Structure
```
AppComponent
├── MapComponent          (MapLibre GL JS or Leaflet)
├── ChatComponent
│   ├── MessageListComponent
│   ├── MessageInputComponent
│   └── ThinkingIndicatorComponent
└── SceneDetailPanelComponent  (slide-out on marker click)
```
### 2.2 Key Technology Choices
| Concern | Choice | Rationale |
|---|---|---|
| Map rendering | **MapLibre GL JS** | Free, vector tiles, smooth flyTo animations, heatmap + choropleth support. Leaflet is a simpler fallback. |
| State management | **Angular Signals** + a `SceneStateService` | Signals are the modern Angular idiom; ideal for chat→map reactivity |
| Streaming | **SSE (Server-Sent Events)** for agent responses; WebSocket if you later want bidirectional (e.g., map clicks informing the agent) | SSE is simpler and pairs perfectly with LangGraph's streaming |
| HTTP | Angular `HttpClient` + typed DTO interfaces | Type safety across the API boundary |
### 2.3 The Chat↔UI Contract: A2UI (the most important design decision)
Instead of inventing a bespoke event protocol, adopt **A2UI** — the open, declarative, streaming UI protocol for agent-driven interfaces (target v0.9.1, the current spec; v1.0 is in candidate stage). Agents emit a stream of JSON messages — `createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface` — and the client renders them using **pre-approved native components only**. No code execution, no UI injection surface.
**Surfaces** (independently controllable UI regions, all driven by one agent stream):
| Surface | Contents |
|---|---|
| `chat` | Conversation; agents respond with rich components (scene cards, comparison tables, genre-picker forms) — not just text |
| `map` | The MapLibre view |
| `detail-panel` | Slide-out scene details |
**The map becomes a custom catalog component.** A2UI is component-agnostic — you define a custom catalog extending the basic one:
```
Custom catalog:
  SceneMapView    → binds to /map/viewport, /map/markers, /map/choropleth
  SceneCard       → scene name, score, top bands, "Explore" action
  SceneComparison → scenes[], comparison dimensions[]
```
The Angular renderer maps `SceneMapView` to a component wrapping MapLibre that reacts to `updateDataModel` messages on `/map/*` paths — a viewport update triggers `flyTo`, a markers update re-renders pins. Crucially, **the agent only updates the data model with values sourced from the database**, so the zero-hallucinated-geography invariant survives intact.
**Interactions flow back as A2UI `userAction` events** — a marker click sends `{name: "explore_scene", context: {sceneId: 17}}` to the agent. This gives you the map→agent channel (user clicks informing the conversation) essentially for free.
**Transport: AG-UI over SSE** — the standard transport binding for A2UI, with existing LangGraph integrations. Build the frontend on the official Angular A2UI renderer, registering your custom catalog components as ordinary Angular components.
### 2.4 UX Flow Example
> **User:** "What city has the biggest thrash metal scene?"
>
> 1. Chat shows a thinking indicator with agent status ("Searching scene database…")
> 2. Map dims slightly (loading state)
> 3. Agent streams: *"The Bay Area remains the historical heart of thrash…"*
> 4. Simultaneously: `updateDataModel` messages on `/map/*` — the viewport flies to San Francisco, Bay Area markers render, plus smaller markers for runner-ups (São Paulo, Ruhr region); a `SceneCard` component streams into the chat surface
> 5. User clicks a marker → detail panel shows bands, venues, festivals, and a "why this score?" breakdown
### 2.5 AG-UI: The Interaction Layer
The full protocol stack, and each layer's job:
```
┌────────────────────────────────────────────────────┐
│  A2UI      →  WHAT the user sees                   │
│               (declarative component/data messages)│
├────────────────────────────────────────────────────┤
│  AG-UI     →  HOW frontend and agent interact      │
│               (event stream: lifecycle, text,      │
│                tool calls, shared state, actions)  │
├────────────────────────────────────────────────────┤
│  LangGraph →  WHAT runs                            │
│               (orchestrator + specialist agents)   │
└────────────────────────────────────────────────────┘
```
**AG-UI** is an open, event-based protocol standardizing the live stream between an agentic backend and a frontend. It's not just transport — three of its features do real work in this design:
**1. Standardized event stream.** Instead of hand-rolling SSE payloads, the backend emits typed AG-UI events. Frontend mapping:
| AG-UI event | Frontend behavior |
|---|---|
| `RUN_STARTED` / `RUN_FINISHED` | Thinking indicator on/off; map loading dim |
| `TEXT_MESSAGE_CONTENT` (streamed) | Token-by-token chat rendering |
| `TOOL_CALL_START` / `_END` | Agent status line ("Searching scene database…") |
| `STATE_SNAPSHOT` / `STATE_DELTA` | Sync shared state (see below) |
| Custom/activity events | Carry the A2UI messages (§2.3) |
**2. Shared state sync — the sleeper feature.** Mirror the presentation-relevant slice of `AgentState` (`resolved_genre`, `geo_scope`) to the frontend via `STATE_DELTA` events. The UI can render persistent context chips — *"Exploring: Thrash Metal · City level"* — that update live as the conversation shifts, and stay correct across follow-ups because they reflect the agent's actual state, not a frontend guess. This also makes the context-engineering state slots (§5) *visible and debuggable* in the browser.
**3. Bidirectional by design.** A2UI `userAction` events (marker clicks, card buttons) travel client→server on AG-UI's return channel, alongside ordinary chat input — one channel, one session model.
**Backend integration:** the `ag-ui-langgraph` package exposes a LangGraph graph as an AG-UI endpoint on FastAPI, translating `astream_events` into AG-UI events with state-sync support — this replaces hand-written streaming glue.
**Angular note:** AG-UI's TypeScript client SDK (`@ag-ui/client`) is framework-agnostic — the prebuilt UI component ecosystem around AG-UI (CopilotKit) is React-centric, so don't plan on those. Wrap the client SDK in an Angular service that exposes the event stream as Signals; your chat, map, and context chips subscribe to it. This is a thin, well-bounded piece of code.
---
## 3. Backend (Python + FastAPI + MySQL)
### 3.1 Why FastAPI
Native async (needed for streaming agent output), Pydantic models mirror your TypeScript DTOs, first-class SSE/WebSocket support, and it's the de facto pairing with LangGraph.
### 3.2 API Surface
```
POST /api/chat                → starts/continues a conversation, returns SSE stream
GET  /api/scenes?genre=&level= → direct REST access for non-chat map browsing
GET  /api/scenes/{id}          → scene detail (marker click)
GET  /api/genres               → genre taxonomy for autocomplete
```
Keep the REST endpoints even though the agent exists — the map should be browsable without chatting, and the agent's tools can reuse the same service layer.
### 3.3 MySQL Schema
```sql
-- Genre taxonomy (thrash metal → metal → rock)
CREATE TABLE genres (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  parent_id INT NULL,
  FOREIGN KEY (parent_id) REFERENCES genres(id)
);
-- Geographic hierarchy: country → state/region → city
CREATE TABLE locations (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  level ENUM('city','state','country') NOT NULL,
  parent_id INT NULL,
  lat DECIMAL(9,6),
  lng DECIMAL(9,6),
  FOREIGN KEY (parent_id) REFERENCES locations(id),
  INDEX idx_level (level)
);
-- The core entity: a scene = genre × location
CREATE TABLE scenes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  genre_id INT NOT NULL,
  location_id INT NOT NULL,
  scene_score DECIMAL(6,2) NOT NULL DEFAULT 0,  -- precomputed ranking
  score_updated_at TIMESTAMP,
  description TEXT,
  UNIQUE KEY uq_scene (genre_id, location_id),
  FOREIGN KEY (genre_id) REFERENCES genres(id),
  FOREIGN KEY (location_id) REFERENCES locations(id),
  INDEX idx_genre_score (genre_id, scene_score DESC)
);
-- Evidence that feeds the score (keeps rankings explainable)
CREATE TABLE scene_signals (
  id INT PRIMARY KEY AUTO_INCREMENT,
  scene_id INT NOT NULL,
  signal_type ENUM('band','venue','festival','label','release','historic'),
  name VARCHAR(200),
  weight DECIMAL(5,2) DEFAULT 1.0,
  metadata JSON,          -- e.g. {"formed": 1983, "status": "active"}
  FOREIGN KEY (scene_id) REFERENCES scenes(id)
);
CREATE TABLE conversations (
  id CHAR(36) PRIMARY KEY,           -- UUID
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE messages (
  id INT PRIMARY KEY AUTO_INCREMENT,
  conversation_id CHAR(36) NOT NULL,
  role ENUM('user','assistant','tool') NOT NULL,
  content MEDIUMTEXT,
  summary VARCHAR(500),              -- for context compression (see §5)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
```
**Scene scoring:** `scene_score` is precomputed (batch job) from weighted signals — number of active bands, notable venues, festivals, historic significance. Precomputing means the agent's "biggest scene" queries are a single indexed lookup instead of expensive aggregation at chat time, and the `scene_signals` table lets the agent *explain* rankings.
### 3.4 Data Sourcing Strategy
- **Seed data:** MusicBrainz (open, has artist→area relations), Wikipedia scene articles, RateYourMusic-style genre metadata
- **Enrichment job:** periodic batch that recomputes scores; optionally an agent-powered pipeline that researches scenes via web search and writes structured signals
- Keep sourcing decoupled from the chat agent — the chat agent *reads* curated data; a separate ingestion pipeline *writes* it
### 3.5 Schema Migrations with Liquibase
Liquibase (not Alembic) manages the MySQL schema:
```
backend/db/
├── liquibase.properties          # MySQL JDBC URL, credentials via env
└── changelog/
    ├── changelog-master.yaml     # includes changesets in order
    └── changesets/
        ├── 001-genres.sql
        ├── 002-locations.sql
        ├── 003-scenes-and-signals.sql
        └── 004-conversations.sql
```
Conventions:
- **SQL-formatted changesets** (`--liquibase formatted sql`) — you keep the exact MySQL DDL from §3.3, reviewable in PRs, no ORM-generated surprises
- **Every changeset includes a `--rollback` block** — non-negotiable for the scoring-related tables you'll iterate on
- **Contexts** separate concerns: `context:seed` changesets load reference genre/location data in dev/test but not prod (prod data comes from the ingestion pipeline)
- **`liquibase tag`** per release; deploys run `liquibase update` as an init step (dedicated container in docker-compose, init job in k8s) *before* the app starts
- SQLAlchemy models are written to match the changelog (the changelog is the source of truth); add a CI check that boots the migrated schema and validates SQLAlchemy metadata against it
---
## 4. Agentic Layer (LangGraph Multi-Agent Orchestrator)
### 4.1 Orchestrator + Specialist Agents
A supervisor/orchestrator pattern with three specialist agents, each with its own isolated context window:
```
                        ┌──────────────────────────┐
   user message ───────►│      ORCHESTRATOR        │
   A2UI userActions ───►│  (LangGraph supervisor)  │
                        │  intent · planning ·     │
                        │  handoffs · shared state │
                        └───┬─────────┬─────────┬──┘
              handoff briefs│         │         │
             ┌──────────────┘         │         └──────────────┐
             ▼                        ▼                        ▼
   ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
   │   SCENE ANALYST   │   │  MUSIC RESEARCH   │   │   UI COMPOSER     │
   │  rankings, detail,│   │  live/external:   │   │  the ONLY agent   │
   │  comparisons from │   │  emerging scenes, │   │  that emits A2UI  │
   │  curated DB       │   │  recency checks   │   │  messages         │
   └─────────┬─────────┘   └─────────┬─────────┘   └─────────┬─────────┘
             │ MCP                   │ MCP                   │
             ▼                       ▼                       ▼
      scene-db MCP           musicbrainz MCP,        chat / map /
      server (§4.5)          web-search MCP          detail-panel surfaces
```
**Agent roles:**
- **Orchestrator** — a cheap, fast model. Classifies intent (scene query / follow-up / chitchat / out-of-scope), decomposes multi-part questions ("compare Bay Area thrash to German thrash *and show me both*"), routes to specialists, and merges results. Owns the shared `AgentState`. Chitchat never leaves the orchestrator.
- **Scene Analyst** — answers ranking/comparison/detail questions using scene-db MCP tools. Deterministic domain: curated data only.
- **Music Research** — handles recency and coverage gaps ("any emerging hyperpop scenes?") via external MCP servers (MusicBrainz, web search). Its findings are marked `provenance: "external"` so the UI can badge unverified claims.
- **UI Composer** — receives structured findings and authors the A2UI messages (chat components + `/map/*` data-model updates). Centralizing UI generation in one agent keeps the presentation consistent, gives you a single point to eval (§10), and means only one prompt needs deep A2UI/catalog knowledge (via a skill, §4.6).
**Handoffs carry compact structured briefs, not transcripts.** The orchestrator passes a Pydantic `TaskBrief` (goal, resolved genre, geo scope, constraints) down and receives a typed `Findings` object back. This is context isolation — each specialist sees only what it needs, which is the biggest single win for the context budget in §5. Implement with LangGraph's supervisor pattern (`langgraph-supervisor` or hand-rolled `Command`-based handoffs).
### 4.2 LangGraph State
```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    scratchpad: Annotated[list[ScratchNote], operator.add]  # in-turn working notes (§5.2, Appendix A.1)
    # Structured slots — the backbone of context engineering
    resolved_genre: GenreRef | None       # {"id": 42, "name": "thrash metal"}
    geo_scope: GeoScope | None            # {"level": "city", "region": None}
    scene_results: list[SceneResult]      # compact tool output, not raw rows
    findings: list[Findings]              # typed briefs returned by specialists
    ui_messages: list[dict]               # A2UI messages staged by UI Composer
    turn_summary: str | None              # written at end of turn
```
### 4.3 Tools Return Structured Data, Not Prose
`query_scenes("thrash metal", level="city", limit=5)` returns:
```json
[
  {"scene_id": 17, "location": "San Francisco Bay Area", "lat": 37.77,
   "lng": -122.42, "score": 94.2,
   "top_signals": ["Metallica (band)", "Exodus (band)", "Ruthie's Inn (venue)"]},
  {"scene_id": 43, "location": "São Paulo", "lat": -23.55, "lng": -46.63,
   "score": 81.0, "top_signals": ["Sepultura (band)", "Korzus (band)"]}
]
```
The UI Composer converts this into the chat narrative and A2UI `updateDataModel` messages — the LLM never has to invent coordinates, which eliminates hallucinated geography.
### 4.4 Streaming
Expose the orchestrator graph via `ag-ui-langgraph` on FastAPI: LLM tokens stream as `TEXT_MESSAGE_CONTENT` events into the chat surface, tool activity surfaces as `TOOL_CALL_*` events, state slots sync via `STATE_DELTA`, and the UI Composer's A2UI messages (`updateComponents`, `updateDataModel`) ride the same stream as activity events (see the event mapping in §2.5). `userAction` events return on AG-UI's client→server channel and enter the orchestrator like user messages.
### 4.5 MCP Support
All tools are exposed as **MCP servers** rather than in-process functions:
- **scene-db MCP server** (FastMCP, Python) — wraps `scene_service` and exposes `query_scenes`, `get_scene_detail`, `compare_scenes`, `resolve_genre` with typed schemas. Runs co-located with the backend (streamable-HTTP transport).
- **External MCP servers** — MusicBrainz, web search, and future data sources plug in without touching agent code.
Agents consume MCP tools via `langchain-mcp-adapters`, which converts them into LangGraph-compatible tools.
**Why MCP here (and the trade-off):**
- One tool implementation shared by all three agents *and* the ingestion pipeline
- The tool contract becomes a stable, documented interface — exactly what component evals (§10.1) test against
- Free bonus: your scene database becomes queryable from any MCP client (Claude Desktop, IDEs), which is genuinely useful for data curation and debugging
- Cost: a network hop per tool call. Keep the scene-db server on the same host/pod; latency impact is negligible relative to LLM calls.
### 4.6 Agent Skills
Package domain expertise as **skills**: folders containing a `SKILL.md` (instructions + methodology) plus optional reference files, loaded via **progressive disclosure** — only each skill's name and one-line description sit in an agent's system prompt; the full content enters context only when the task needs it.
```
skills/
├── genre-taxonomy/
│   └── SKILL.md            # subgenre relations, disambiguation ("melodeath" → melodic death metal)
├── scene-scoring/
│   └── SKILL.md            # scoring methodology, how to explain/caveat rankings
├── a2ui-authoring/
│   ├── SKILL.md            # catalog usage rules: when SceneCard vs SceneComparison, map conventions
│   └── examples/           # golden A2UI message sequences
└── map-presentation/
    └── SKILL.md            # zoom levels per geo level, choropleth thresholds, marker scaling
```
**Wire-up:** each agent's prompt lists its available skills (metadata only) plus a `load_skill(name)` tool. The UI Composer always loads `a2ui-authoring`; the Scene Analyst pulls `scene-scoring` only when someone asks *"why is X ranked above Y?"*.
**Why this matters:** it's context engineering (§5) applied to instructions — expertise on demand instead of a bloated static prompt (which would also wreck prompt caching). And because skills are plain files versioned in git, they're testable: change `scene-scoring/SKILL.md`, run the eval suite, see if ranking explanations improved.
---
## 5. Context Engineering Strategy
This is where the design earns the "efficient" requirement. The architecture is organized along two dimensions: **four memory tiers** (what kinds of information exist and where they live) and **four strategies** — *write, select, compress, isolate* — (what we do with that information relative to the context window).
### 5.1 Memory Tiers
| Tier | What it holds in The Scenery | Storage | Lifetime |
|---|---|---|---|
| **Working** (short-term) | The active `AgentState`: recent messages, a **scratchpad** of in-turn notes, `resolved_genre`, `geo_scope`, current `scene_results`, `findings`, staged `ui_messages` | LangGraph **checkpointer** (MySQL saver) — one checkpoint thread per conversation | Single conversation |
| **Episodic** | What happened: per-turn summaries; notable past episodes (e.g., a query→A2UI sequence that got a 👍, reusable as a few-shot exemplar) | `messages.summary` + LangGraph **Store**, namespace `(user_id, "episodes")` | Across sessions |
| **Semantic** | Facts. Two kinds: (a) **domain knowledge** — the entire scene database *is* externalized semantic memory, accessed via MCP tools, never bulk-loaded into context; (b) **user facts** — "favorite genre: death metal", "home city: Oakland" | (a) MySQL via scene-db MCP; (b) LangGraph Store, namespace `(user_id, "facts")` | Permanent (DB) / across sessions (user facts) |
| **Procedural** | How to behave: system prompts, skills (§4.6), golden A2UI exemplars, TaskBrief/Findings schemas | Git-versioned files; skills loaded progressively | Deployed with releases |
User-facing memory store (semantic user facts + episodes) in MySQL:
```sql
CREATE TABLE memory_store (
  user_id CHAR(36) NOT NULL,
  namespace ENUM('facts','episodes') NOT NULL,
  memory_key VARCHAR(200) NOT NULL,
  value JSON NOT NULL,               -- {"fact": "...", "confidence": ..., "source_turn": ...}
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, namespace, memory_key)
);
```
### 5.2 The Four Strategies
**WRITE — persist context outside the window so it survives.**
- Agents **write to a scratchpad** during a turn: the orchestrator jots its plan ("2-part query: rank thrash cities, then compare top-2"), specialists jot intermediate observations ("SF score driven 60% by historic signals — caveat this"). Notes survive across graph steps without being re-derived, and via the checkpointer, across process restarts mid-turn
- The MySQL **checkpointer** writes working memory after every graph step: refresh the page mid-conversation, resume exactly where you were
- An **end-of-turn summarizer node** writes the episodic `turn_summary` ("Explored thrash scenes; Bay Area #1, São Paulo #2") — generated once, reused forever
- A lightweight **memory-extraction node** (runs async, after the response streams) mines the turn for semantic user facts: *"I'm from Oakland and mostly into death metal"* → two facts written to `(user_id, "facts")`
- 👍-rated turns get their `(TaskBrief, Findings, A2UI messages)` triple written as an episodic exemplar
- Procedural memory is "written" by developers — and improved through the eval loop (§10): a failing eval → edit a SKILL.md → re-run
**SELECT — pull only what's relevant into the window, per turn.**
- State slots (`resolved_genre`, `geo_scope`): always included — tiny and load-bearing
- Working memory: last K≈4 message pairs verbatim; older turns appear only as episodic summaries
- Semantic user facts: retrieved by relevance to the current query (genre/geo match), not dumped wholesale — asking about jazz doesn't need the user's metal preferences
- Episodic exemplars: the UI Composer retrieves 1–2 past golden episodes matching the current query *type* (ranking vs. comparison) as few-shots
- Procedural: skills loaded on demand via `load_skill` (§4.6); domain facts fetched via MCP tools only when needed
- The orchestrator's routing is itself selection: only the relevant specialist's toolset ever enters a context
**COMPRESS — shrink what must be in the window.**
- Progressive summarization: verbatim → `turn_summary` → (for very long histories) a rolling conversation-level summary
- **Scratchpad lifecycle:** at turn end, the summarizer folds notable notes into `turn_summary`, then the scratchpad is cleared — notes are working memory, not an archive
- Compact tool outputs: top-N with top-3 signals, never raw SQL rows; drill-down costs extra only when requested
- Eviction: after a turn completes, bulky tool payloads are dropped from working memory — the distilled facts live on in `turn_summary` and the current `scene_results`
- The `TaskBrief`/`Findings` schemas are compression at agent boundaries: a specialist's entire investigation returns as one typed object
**ISOLATE — keep contexts separate so no single window carries everything.**
- Multi-agent handoffs (§4.1): each specialist has its own context; the Scene Analyst never sees pleasantries, the UI Composer never sees raw SQL — only `Findings`
- Scratchpad notes are **namespaced by agent**: a specialist selects only its own notes plus the orchestrator's plan — never another specialist's musings
- The scene database is isolated behind MCP tools — thousands of scenes never touch a prompt
- Skills sit on disk until loaded; unloaded expertise costs zero tokens
- Cache isolation: static procedural content (system prompt + tool defs) stays byte-identical at the *front* of the context; all dynamic content (state, summaries, facts) goes at the *end* — maximizing prompt-cache reuse
### 5.3 Strategy × Tier Matrix
| | Write | Select | Compress | Isolate |
|---|---|---|---|---|
| **Working** | Checkpointer per step; scratchpad notes | Slots + last K turns + own notes | Distill scratchpad → summary, evict payloads | Per-agent state & notes |
| **Episodic** | Turn summarizer; 👍 exemplars | Summaries + matched few-shots | Rolling summary | Namespaced per user |
| **Semantic** | Async fact extraction | Relevance-filtered facts; MCP on demand | Facts, not transcripts | DB behind MCP |
| **Procedural** | Devs + eval loop | `load_skill` on demand | Skill metadata only in prompt | On disk until needed |
### 5.4 Context Assembly Order & Budget
Assembled front-to-back for cache friendliness (static → dynamic):
| Segment (tier) | Budget |
|---|---|
| System prompt + tool defs (procedural, static) | ~1.5k tokens (cached) |
| Loaded skill content (procedural, on demand) | 0–800 tokens |
| Episodic: summaries + retrieved exemplars | ~500 tokens |
| Semantic: retrieved user facts | ~150 tokens |
| Working: recent verbatim turns | ~1k tokens |
| Working: state slots | ~200 tokens |
| Working: scratchpad (agent's own notes) | ~200 tokens |
| Fresh tool output | ~500 tokens |
| **Total** | **~4–4.7k tokens/turn** |
The `context_tokens_used` trace metric (§9.2) monitors this budget per tier, turning it into an SLO.
---
## 6. Project Structure
```
the_scenery/
├── frontend/                     # Angular workspace
│   └── src/app/
│       ├── core/services/        # AG-UI stream service, surface registry
│       ├── a2ui/                 # A2UI renderer integration + custom catalog
│       │   └── components/       # SceneMapView, SceneCard, SceneComparison
│       ├── features/map/         # MapLibre wrapper used by SceneMapView
│       ├── features/chat/
│       └── shared/models/        # catalog + data-model TypeScript types
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI routers + AG-UI stream endpoint
│   │   ├── orchestrator/         # supervisor graph, TaskBrief/Findings schemas
│   │   ├── agents/               # scene_analyst/, music_research/, ui_composer/
│   │   ├── services/             # scene_service.py (shared by REST + MCP)
│   │   ├── models/               # SQLAlchemy models + Pydantic schemas
│   │   └── context/              # summarizer, state compaction, skill loader
│   ├── mcp_servers/
│   │   └── scene_db/             # FastMCP server wrapping scene_service
│   ├── skills/                   # SKILL.md folders (§4.6)
│   ├── ingestion/                # seed scripts, score computation batch job
│   ├── evals/
│   │   ├── datasets/             # genre_resolution.json, router.json,
│   │   │                         #   golden_rankings.json, conversations/,
│   │   │                         #   a2ui_golden_messages/
│   │   ├── runners/              # CI eval scripts, judge rubric prompts
│   │   └── checks.py             # hard-fail assertions (geo + A2UI schema)
│   ├── observability/            # OTel setup, correlation-ID middleware
│   └── db/
│       ├── changelog/            # Liquibase changelog-master.yaml + changesets
│       └── liquibase.properties
└── docker-compose.yml            # mysql, liquibase init, backend, mcp, frontend
```
---
## 7. Phased Build Plan
> **Note:** superseded by [ROADMAP.md](ROADMAP.md), which breaks these phases into single
> action items with de-risking spikes. This section is kept as the original phase intent.

**Phase 1 — Data foundation (week 1–2)**
Liquibase changelogs + migrated MySQL schema, seed ~5 genres × ~50 locations from MusicBrainz/Wikipedia (seed context), scoring batch job, REST endpoints, **scene-db MCP server**. *Exit criteria: `query_scenes` returns sensible rankings via both REST and an MCP client.*
**Phase 2 — Map UI (week 2–3)**
Angular shell, A2UI renderer with the custom catalog stub, `SceneMapView` wrapping MapLibre driven by hand-written A2UI messages, detail panel. No agent yet. *Exit criteria: replaying a recorded A2UI message stream produces a browsable genre map.*
**Phase 3 — Agent MVP (week 3–5)**
Orchestrator + Scene Analyst (consuming scene-db MCP) + UI Composer with the `a2ui-authoring` skill, AG-UI streaming endpoint, chat UI. *Exit criteria: the thrash-metal demo flow in §2.4 works end to end.*
**Phase 4 — Context engineering & memory (week 5–6)**
MySQL checkpointer (working memory persistence/resume), turn summarizer + async fact-extraction nodes (episodic + semantic writes), relevance-based memory selection, TaskBrief/Findings handoffs, cache-friendly assembly order, skill loading, comparison queries, `userAction` round-trips. *Exit criteria: 10-turn conversation stays under the §5.4 budget with correct follow-ups, and user facts persist into a new session.*
**Phase 5 — Enrichment (ongoing)**
Music Research agent with MusicBrainz/web-search MCP servers ("any new scenes emerging?"), agent-powered ingestion pipeline, more genres/regions, more skills.
---
## 8. Key Design Decisions & Trade-offs
| Decision | Alternative | Why this choice |
|---|---|---|
| Precomputed scene scores | Live aggregation per query | Fast agent tools, explainable via signals table; recompute nightly |
| A2UI standard protocol | Bespoke event union | Interop, official Angular renderer, declarative = no UI injection risk, free map→agent channel via `userAction`; cost: learning a young spec |
| AG-UI event protocol + `ag-ui-langgraph` | Hand-rolled SSE glue | Typed lifecycle/tool/state events for free, shared-state sync powers live context chips; cost: React-centric component ecosystem means a thin custom Angular client wrapper |
| UI Composer is the sole A2UI author | Every agent emits UI | Consistent presentation, one prompt needs catalog knowledge, one place to eval |
| Tools via MCP servers | In-process functions | Shared across agents + ingestion; stable contract for evals; queryable from external MCP clients; cost: a (co-located) network hop |
| Skills with progressive disclosure | Everything in system prompts | Small cache-stable prompts; expertise versioned in git and testable |
| Orchestrator + 3 specialists | Single agent / large swarm | Context isolation per agent; specialists stay simple; still debuggable |
| Liquibase (SQL changesets) | Alembic | Reviewable raw MySQL DDL, rollback blocks, contexts for seed data, tag-based release management |
| MySQL adjacency-list geo hierarchy | PostGIS | You specified MySQL; city/state/country lookups don't need spatial ops (lat/lng stored for map only) |
---
## 9. Observability & Tracing
### 9.1 Two Layers of Telemetry
**Layer 1 — LLM/Agent tracing (the interesting layer).**
Instrument the LangGraph runtime so every conversation turn produces a full trace: router decision → tool calls (with inputs/outputs) → synthesizer output → emitted MapCommands.
Recommended options, in order of fit:
| Tool | Fit | Notes |
|---|---|---|
| **LangSmith** | Best out-of-the-box | Native LangGraph integration — set `LANGSMITH_TRACING=true` and every node/tool/LLM call is traced automatically, with graph-aware visualization. Hosted SaaS; also the natural home for your eval datasets (§10). |
| **Langfuse** | Best self-hosted | Open source, OTel-compatible, first-class LangGraph support via callback handler. Choose this if data residency matters. |
| **Raw OpenTelemetry** | Most portable | Vendor-neutral; more assembly required for LLM-specific views (token costs, prompt diffs). |
Pragmatic choice: **LangSmith in development, decide between LangSmith and Langfuse before production** based on data-privacy needs. Both share the same conceptual model, so switching is cheap early.
**Layer 2 — Application telemetry (OpenTelemetry).**
Standard OTel instrumentation for FastAPI (auto-instrumentation package), SQLAlchemy/MySQL query spans, and SSE stream lifecycle. Export to whatever you already use (Grafana Tempo, Jaeger, Datadog).
**Crucial: propagate one correlation ID across both layers.** Generate a `trace_id` per chat turn, attach it as LangSmith/Langfuse metadata *and* as an OTel span attribute *and* return it in the SSE `done` event. Then a user-reported bad answer can be traced from the Angular console → FastAPI span → exact agent trace → exact SQL queries.
### 9.2 What to Capture Per Turn
```python
trace_metadata = {
    "conversation_id": ...,
    "turn_number": ...,
    "resolved_genre": ...,        # from AgentState
    "geo_scope": ...,
    "context_tokens_used": ...,   # validates the §5 budget!
    "cache_hit": ...,             # prompt cache effectiveness
    "a2ui_messages_emitted": [...],
    "agents_invoked": ["scene_analyst", "ui_composer"],
    "skills_loaded": ["a2ui-authoring"],
    "latency_ms": {"orchestrator": ..., "specialists": ..., "mcp_tools": ..., "total": ...}
}
```
The `context_tokens_used` metric matters especially: it turns your context-engineering budget (§5) from an aspiration into a monitored SLO. Alert if p95 exceeds ~5k tokens.
### 9.3 Dashboards & Alerts (minimum set)
- p50/p95 end-to-end latency, broken down by graph node
- Token usage + cost per turn (trend over time)
- Tool error rate (SQL failures, genre-resolution misses)
- Router misclassification proxy: % of turns where chitchat path was followed by an immediate rephrase
- Prompt cache hit rate
---
## 10. Evaluation Strategy
Evals for this app split into four distinct targets — each needs its own dataset and metric. Run them with **LangSmith Evaluations** (or Langfuse's equivalent) so results attach directly to traces.
### 10.1 Component Evals
**A. Genre resolution (`resolve_genre`)** — *deterministic, cheap, run in CI*
Dataset: ~200 phrasings → expected genre ID. ("thrash", "thrash metal", "bay area thrash", "tallica-style stuff", misspellings.)
Metric: exact-match accuracy. Target ≥95%.
**B. Router intent classification** — *deterministic, run in CI*
Dataset: ~150 labeled user messages (scene query / follow-up / chitchat / out-of-scope).
Metric: accuracy + confusion matrix. Watch the follow-up↔new-query boundary — it's where structured state (§5) breaks if misrouted.
**C. Ranking quality (the data layer, no LLM involved)**
Dataset: golden rankings for well-documented scenes — e.g., Bay Area must appear in top-3 city results for thrash; Gothenburg for melodic death metal; Seattle for grunge.
Metric: Recall@3 / NDCG against golden sets. This eval tests your *scoring methodology*, and will be the eval you iterate on most.
### 10.2 End-to-End Evals
**D. Full conversation eval** — *LLM-as-judge + programmatic checks*
Dataset: ~50 multi-turn scripted conversations, including follow-ups ("what about at the state level?", "compare that to Germany").
Programmatic assertions (strict, no judge needed):
- Every A2UI message validates against the protocol + custom catalog schemas (**hard-fail**)
- Every coordinate in `/map/*` `updateDataModel` messages matches DB rows returned by MCP tools (zero hallucinated geography — **hard-fail**)
- The `/map/viewport` target corresponds to the #1 result mentioned in the chat text
- Follow-up turns reuse `resolved_genre` without re-asking
- Externally sourced claims (Music Research agent) carry `provenance: "external"`
LLM-as-judge rubric (scored 1–5):
- Faithfulness: does the chat text only claim what tool outputs support?
- Answer completeness: mentions runner-ups, not just #1?
- Tone/format appropriateness
**E. Context-engineering & memory regression eval**
Replay the 10-turn scripted conversations and assert: tokens/turn stays under the §5.4 budget (per tier), and turn-10 answers are as accurate as turn-2 answers (compression didn't lose critical state). Add cross-session memory cases: end a conversation after "I'm mostly into death metal", start a *new* conversation, ask "show me the best scenes near me" — assert the semantic facts were extracted, retrieved, and applied. Also assert selection precision: a jazz query must *not* pull metal-preference facts into context.
### 10.3 Eval Lifecycle
```
   ┌────────────┐     nightly / on PR      ┌─────────────┐
   │  Datasets  │─────────────────────────►│  CI Evals   │──► block merge on
   │ (LangSmith │                          │ (A,B,C + D  │    hard-fail checks
   │  datasets) │                          │ programmatic)│
   └─────▲──────┘                          └─────────────┘
         │ promote interesting traces
   ┌─────┴──────────┐    weekly            ┌─────────────┐
   │ Production     │─────────────────────►│ Judge Evals │──► dashboard trend
   │ traces + 👍/👎 │   sampled            │ (D rubric)  │
   └────────────────┘                      └─────────────┘
```
- **Feedback loop:** add a 👍/👎 on chat answers in the Angular UI; send it to LangSmith as feedback attached to the turn's trace via the correlation ID. Thumbs-down traces are your best source of new eval cases — triage weekly and promote to datasets.
- **CI gating:** deterministic evals (A, B, C, D-programmatic) run on every PR that touches prompts, graph code, or scoring. Judge-based evals run nightly (they're slower and cost money).
- **Prompt versioning:** every system-prompt or tool-description change gets an eval run before merge; store prompt versions in the repo, not in a dashboard.
### 10.4 Additions to the Phased Plan
- **Phase 1:** stand up eval C (golden rankings) alongside the scoring job — it defines "correct" before you build the agent
- **Phase 3:** enable LangSmith tracing on day one of agent work (it's one env var); build evals A, B, and the D hard-fail geography check
- **Phase 4:** add eval E (context regression) and the judge rubric; wire the 👍/👎 feedback loop
- **New Phase 4.5:** OTel instrumentation for FastAPI/MySQL + correlation-ID plumbing + dashboards
---
## 11. Open Questions to Resolve Early
1. **Scoring methodology** — what makes a scene "big"? Active bands vs. historical significance vs. current venue activity? This defines your data model's soul. (Recommendation: weighted composite, with the weights visible to users.)
2. **Data freshness** — is a nightly batch acceptable, or do "emerging scene" questions need live web search from day one?
3. **Auth/persistence** — anonymous sessions or user accounts with saved conversations?
4. **Genre taxonomy depth** — how granular? (thrash → crossover thrash → …) Affects the `resolve_genre` tool design.
5. **Tracing platform** — LangSmith (hosted, easiest) vs. Langfuse (self-hosted, OSS)? Depends on data-residency requirements; decide before production traffic.
6. **Judge model budget** — nightly LLM-as-judge runs have real cost; pick a sampling rate for production trace evaluation (e.g., 5–10%).
7. **A2UI version pinning** — v0.9.1 is current, v1.0 is a release candidate; pin one, isolate spec-touching code in the `a2ui/` module, and plan a migration checkpoint.
8. **MCP transport & auth** — local streamable-HTTP with no auth is fine for dev; decide on auth (OAuth/token) before exposing the scene-db MCP server beyond the pod, especially if you want external MCP clients to use it.
9. **Model tiering per agent** — orchestrator on a small/fast model, specialists on a mid-tier, UI Composer possibly smallest of all (structured generation against a schema); benchmark cost vs. eval scores.
10. **Memory governance** — user facts require user identity (ties into the auth question), a way for users to view/delete what's remembered, and a retention policy. Decide before shipping semantic memory.
11. **Fact extraction quality bar** — extracted facts should carry confidence and be conservative (explicit statements only, no inferred preferences) to avoid the agent confidently misremembering users.
---
## Appendix A — Implementation Sketches: Memory & Context Machinery
### A.1 Scratchpad
```python
# app/orchestrator/state.py
import operator
from typing import Annotated, Literal
from pydantic import BaseModel
class ScratchNote(BaseModel):
    agent: Literal["orchestrator", "scene_analyst", "music_research", "ui_composer"]
    note: str                      # keep short; one thought per note
    kind: Literal["plan", "observation", "caveat"] = "observation"
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    scratchpad: Annotated[list[ScratchNote], operator.add]   # append-only reducer
    resolved_genre: GenreRef | None
    geo_scope: GeoScope | None
    scene_results: list[SceneResult]
    findings: list[Findings]
    ui_messages: list[dict]
    turn_summary: str | None
```
Usage conventions (enforced in each agent's prompt + a `write_note` tool):
```python
# Selection: an agent sees only its own notes + the orchestrator's plan
def scratchpad_view(state: AgentState, agent: str) -> str:
    visible = [n for n in state["scratchpad"]
               if n.agent == agent or (n.agent == "orchestrator" and n.kind == "plan")]
    return "\n".join(f"[{n.kind}] {n.note}" for n in visible[-10:])  # cap it
# Compression: turn-end node folds notes into the summary, then clears
def end_of_turn(state: AgentState) -> dict:
    summary = summarize_turn(state["messages"][-6:], state["scratchpad"])
    return {"turn_summary": summary, "scratchpad": "__clear__"}  # custom reducer sentinel
```
(The append-only reducer needs a small tweak to honor a clear sentinel — or model the scratchpad as a dict keyed by turn and drop old keys.)
### A.2 Fact-Extraction Node (semantic memory writes)
**Output schema:**
```python
# app/context/fact_extraction.py
from pydantic import BaseModel, Field
from typing import Literal
class UserFact(BaseModel):
    key: str = Field(description="canonical snake_case key, e.g. 'favorite_genre', 'home_city'")
    value: str
    kind: Literal["preference", "biographical", "context"]
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(description="short verbatim quote from the user's message")
class FactExtraction(BaseModel):
    facts: list[UserFact] = Field(default_factory=list)  # empty is the expected common case
```
**System prompt (verbatim, versioned in git):**
```text
You extract durable facts about the user from one conversation turn.
Rules:
1. Extract ONLY facts the user explicitly stated about themselves.
2. Never infer preferences from questions. A user asking about polka
   scenes is NOT evidence they like polka. "I love polka" is.
3. Durable facts only. Skip ephemeral states ("I'm bored tonight").
4. Every fact requires a short verbatim quote as evidence.
5. Reuse an existing key when the user contradicts or updates a prior
   fact (upsert semantics). Existing facts are provided below.
6. If nothing qualifies, return {"facts": []}. This is the common case.
   An empty result is a success, not a failure.
Existing facts:
{existing_facts}
```
**The node — runs async after the response has streamed, so it adds zero latency:**
```python
from langgraph.store.base import BaseStore
CONFIDENCE_FLOOR = 0.8
async def extract_facts(state: AgentState, config: RunnableConfig, *, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    existing = await store.asearch((user_id, "facts"), limit=50)
    existing_str = "\n".join(f"- {m.key}: {m.value['value']}" for m in existing) or "(none)"
    last_user_msgs = [m for m in state["messages"][-4:] if m.type == "human"]
    if not last_user_msgs:
        return {}
    extractor = small_fast_llm.with_structured_output(FactExtraction)
    result = await extractor.ainvoke([
        SystemMessage(EXTRACTION_PROMPT.format(existing_facts=existing_str)),
        HumanMessage("\n".join(m.content for m in last_user_msgs)),
    ])
    for fact in result.facts:
        if fact.confidence >= CONFIDENCE_FLOOR:
            await store.aput(
                (user_id, "facts"), fact.key,
                fact.model_dump() | {"source_turn": state.get("turn_number")},
            )
    return {}
# Wiring: response path ends the visible turn; extraction hangs off it
# and does NOT block the stream:
builder.add_node("extract_facts", extract_facts)
builder.add_edge("end_of_turn", "extract_facts")   # after summary; stream already flushed
builder.add_edge("extract_facts", END)
```
### A.3 Checkpointer + Store Wiring
Note: LangGraph's officially maintained checkpointers are Postgres/SQLite; MySQL support comes from the community `langgraph-checkpoint-mysql` package — vet its current maintenance status at implementation time. The Store interface is small enough that a custom implementation over the `memory_store` table (§5.1) is a reasonable fallback.
```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver     # community package
from app.context.mysql_store import MySQLStore                # thin BaseStore impl
from app.orchestrator.graph import build_graph
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AIOMySQLSaver.from_conn_string(settings.MYSQL_DSN) as checkpointer:
        await checkpointer.setup()                            # creates checkpoint tables
        store = MySQLStore(pool=create_pool(settings.MYSQL_DSN))   # memory_store table
        app.state.graph = build_graph().compile(
            checkpointer=checkpointer,                        # working memory (per thread)
            store=store,                                      # semantic + episodic (per user)
        )
        yield
# Invocation — thread_id binds working memory, user_id binds long-term memory
config = {
    "configurable": {
        "thread_id": conversation_id,    # checkpointer namespace
        "user_id": user_id,              # store namespace
    }
}
async for event in app.state.graph.astream_events(input_state, config):
    ...  # translated to AG-UI events (§4.4)
```
```python
# app/context/mysql_store.py — custom BaseStore over memory_store (§5.1)
# Interface to implement: put/get/search/delete (+ async variants).
class MySQLStore(BaseStore):
    async def aput(self, namespace: tuple, key: str, value: dict):
        # INSERT ... ON DUPLICATE KEY UPDATE against memory_store
        ...
    async def asearch(self, namespace: tuple, *, query: str | None = None, limit: int = 10):
        # v1: SELECT by namespace + LIKE/keyword filter
        # v2: add an embedding column for semantic retrieval if needed
        ...
```
### A.4 Selection Helper (semantic memory reads)
```python
async def select_relevant_facts(store: BaseStore, user_id: str,
                                genre: GenreRef | None, geo: GeoScope | None) -> str:
    """Relevance-filtered facts for prompt assembly (§5.4). Never dump all facts."""
    facts = await store.asearch((user_id, "facts"), limit=50)
    relevant = [
        f for f in facts
        if f.value["kind"] == "biographical"                        # home city etc: usually relevant
        or (genre and genre.family in f.value.get("value", ""))     # genre-adjacent prefs
    ]
    return "\n".join(f"- {f.key}: {f.value['value']}" for f in relevant[:5])
```
Start with this keyword/kind heuristic; add embeddings to `memory_store` only if eval E's selection-precision cases start failing.
---
## Appendix B — References
### Protocols: A2UI & AG-UI
- A2UI project home & concepts — https://a2ui.org/ and https://a2ui.org/introduction/what-is-a2ui/
- A2UI specification v0.9.1 (current) — https://a2ui.org/specification/v0.9-a2ui/ · v1.0 candidate — https://a2ui.org/specification/v1.0-a2ui/
- Google's A2UI announcement (positioning vs. MCP Apps, AG-UI, ChatKit) — https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/
- AG-UI protocol docs (events, state sync, transports) — https://docs.ag-ui.com/
- AG-UI GitHub (TypeScript client SDK, framework integrations incl. LangGraph) — https://github.com/ag-ui-protocol/ag-ui
- Tutorial: full-stack A2UI over A2A/AG-UI — https://www.copilotkit.ai/blog/build-with-googles-new-a2ui-spec-agent-user-interfaces-with-a2ui-ag-ui
### LangGraph: Orchestration, Memory, Streaming
- LangGraph docs — https://langchain-ai.github.io/langgraph/
- Multi-agent concepts & supervisor pattern — https://langchain-ai.github.io/langgraph/concepts/multi_agent/ · https://github.com/langchain-ai/langgraph-supervisor-py
- Persistence (checkpointers, threads) — https://langchain-ai.github.io/langgraph/concepts/persistence/
- Memory concepts (short-term vs. long-term, the Store) — https://langchain-ai.github.io/langgraph/concepts/memory/
- Streaming (`astream_events`) — https://langchain-ai.github.io/langgraph/concepts/streaming/
- Community MySQL checkpointer — https://pypi.org/project/langgraph-checkpoint-mysql/ (verify maintenance status; official savers are Postgres/SQLite)
### Context Engineering & Memory Theory
- LangChain: "Context Engineering for Agents" — the write/select/compress/isolate framework — https://blog.langchain.com/context-engineering-for-agents/
- Anthropic: "Effective context engineering for AI agents" — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- CoALA paper — cognitive architecture framing of working/episodic/semantic/procedural memory for language agents — https://arxiv.org/abs/2309.02427
- Anthropic prompt caching (why cache-stable prompt layout matters) — https://docs.claude.com/en/docs/build-with-claude/prompt-caching
### MCP & Agent Skills
- Model Context Protocol specification — https://modelcontextprotocol.io/
- FastMCP (Python MCP server framework) — https://gofastmcp.com/
- `langchain-mcp-adapters` (MCP tools → LangGraph tools) — https://github.com/langchain-ai/langchain-mcp-adapters
- Anthropic: "Equipping agents for the real world with Agent Skills" (SKILL.md, progressive disclosure) — https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
### Observability & Evals
- LangSmith (tracing + evaluations) — https://docs.smith.langchain.com/
- Langfuse (open-source alternative, LangGraph integration) — https://langfuse.com/docs
- OpenTelemetry Python / FastAPI instrumentation — https://opentelemetry.io/docs/languages/python/ · https://opentelemetry-python-contrib.readthedocs.io/
### Data Layer
- Liquibase docs (changelogs, contexts, rollback) — https://docs.liquibase.com/ · MySQL specifics — https://docs.liquibase.com/start/tutorials/mysql.html
- MusicBrainz API (seed data: artist↔area relations) — https://musicbrainz.org/doc/MusicBrainz_API
### Frontend
- MapLibre GL JS — https://maplibre.org/maplibre-gl-js/docs/
- Angular Signals — https://angular.dev/guide/signals
- FastAPI — https://fastapi.tiangolo.com/
*Note: A2UI and AG-UI are young, fast-moving specs — treat their docs as canonical over this document if they diverge, and re-verify the community MySQL checkpointer and the Anthropic/LangChain blog URLs at implementation time.*
