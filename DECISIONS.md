# The Scenery — Locked Decisions

Decisions from the M0 gate (roadmap 0.5), resolving DESIGN.md §11 open questions.
Each entry: the decision, one-line rationale, and revisit trigger. Spike evidence in
[spikes/NOTES.md](spikes/NOTES.md).

## D1 — Scoring formula v1 (§11 Q1)

**Decision:** One MusicBrainz artist of type *Group*, tagged with the genre, located via
`begin-area`, keyed by MBID = one `band` signal of weight 1.0. Scene score = Σ signal weights,
rolled up through our `locations` hierarchy (city → metro/region → country), normalized 0–100
per (genre, level): `100 * count / max_count`.

**Rationale:** spike S3 showed this zero-tuning core already passes all three golden cases
(Bay Area #1 thrash, Seattle #1 grunge, Gothenburg top-3 melodeath).

**Revisit when:** eval C (1.9) fails on a new golden case — then iterate weights (historic-era
multiplier, activity status, venue/festival/label signals), never before there's a failing eval.

## D2 — Data freshness (§11 Q2)

**Decision:** Nightly batch recompute is sufficient for MVP. "Emerging scene" recency questions
are out of scope until the Music Research agent (M7, task 7.1).

**Rationale:** curated-DB questions dominate the core demo; freshness adds an external-API
dependency with no MVP payoff.

**Revisit when:** M7 starts, or users demonstrably ask recency questions the DB can't answer.

## D3 — Auth & persistence (§11 Q3)

**Decision:** Anonymous sessions for MVP. `conversations` are keyed by generated UUID; no
accounts. Auth + memory governance (§11 Q10) must be decided **before** semantic user-fact
memory (5.3) ships to real users — fine to build 5.3 against an anonymous per-browser id in dev.

**Rationale:** auth is pure drag on every milestone before memory matters.

**Revisit when:** starting M5 task 5.3 (check), and hard-stop before any public deploy.

## D4 — Tracing platform (§11 Q5)

**Decision:** LangSmith for development, enabled from the first agent commit (3.1).
LangSmith-vs-Langfuse gets decided before production traffic (7.4), on data-residency grounds.

**Rationale:** one env var to turn on; native LangGraph tracing; eval datasets live there too.

**Revisit when:** production deploy planning begins.

## D5 — A2UI version pin (§11 Q7)

**Decision:** Pin the **A2UI v0.9 spec** via versioned entry points (`@a2ui/angular/v0_9`,
catalog `createSurface` messages declaring v0.9), while tracking npm package patch/minor
releases (`@a2ui/angular` 0.10.x, `@a2ui/web_core` 0.10.x). All spec-touching code stays in
`frontend/src/app/a2ui/`. v1.0 migration gets its own roadmap item when v1.0 goes final.

**Rationale:** spike S1 showed package version ≠ spec version; the entry point is the real pin.

**Constraints inherited from spikes (S1/S2):** Angular 21 (renderer peer), `zod@^3.25.76`
explicit dep, `provideMarkdownRenderer()` in providers, surfaces mount only after
`createSurface`, graphs always compile with a checkpointer.

**Revisit when:** A2UI v1.0 final ships, or the renderer adds Angular 22+ support.
