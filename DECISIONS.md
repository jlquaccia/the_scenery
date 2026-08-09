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

### D1a — Amendment (roadmap 1.11): what counts, and where it attaches

The revisit trigger above fired: eval C's `techno-city` and
`melodic-death-metal-country-sweden-first` both failed for reasons that were about the
*definition* of a signal, not about weights. Three changes, all inclusion — **no weight
changes; every signal is still 1.0**:

1. **Solo artists count.** "Artist of type *Group*" made techno structurally unrankable —
   Juan Atkins, Derrick May, Kevin Saunderson and Jeff Mills are all typed Person, so the
   Belleville lineage was invisible and London led Detroit. Person artists now seed signals
   with `signal_type = 'artist'`, kept distinct from `'band'` so the two can be weighted
   separately later without another reseed.
2. **A signal is never discarded, only re-attached.** `MIN_BANDS` decides whether a *city
   scene* exists; it must not decide whether an artist exists. An artist in a sub-threshold
   city now attaches to the nearest ancestor that has a scene.
3. **Artists with no city attach to their state or country** (spike S3 finding #2, specified
   but never implemented). MusicBrainz `begin-area` is frequently just "Germany".

**Rationale:** measured on the 1.10 fetch, the pipeline was discarding ~40% of located,
correctly-tagged artists (thrash 473 kept / 314 dropped; grunge 299 / 174). Because they were
dropped rather than re-attached, they counted at *no* level, so every state and country
ranking was computed from a partial set — which made the volume-vs-influence question
unanswerable until fixed. The most vivid case: Nirvana carries a `grunge` tag with 64 votes
but was discarded because Aberdeen has one grunge band, while a 1960s London band of the same
name (grunge tag: 1 vote) survived because London cleared the threshold.

### D1b — What the score means in time (2026-08-02)

`scene_score` is **all-time cumulative**: every artist ever tagged with the genre whose
`begin-area` is that place, regardless of whether they are still active. It is "everything
this place has contributed to the genre", not "what is happening there now".

**Rationale:** the two are very different, and cumulative is the one that answers the
product's question. Seattle is the grunge city because of 1988–1994 — filter to currently
active bands and that claim mostly disappears, taking eval C's `grunge-city` case with it
(303 of 472 thrash signals and 126 of 330 grunge signals began pre-2000). "Still active" is
also not reliably knowable from what we store: MusicBrainz marks `ended` on only ~15% of
signals (51 of 330 grunge, 65 of 472 thrash), so an active-only filter would mostly be
measuring metadata completeness rather than scenes.

**Future (deferred, roadmap 1.12 note):** an **era filter** — "the 80s", "1985", "active
now" — as a view on top of this default, not a replacement for it. `scene_signals.metadata`
already carries `begin`/`ended` for 86% of signals, so the data supports it today.

**Still deferred (roadmap 1.12):** whether scoring stays pure volume. Counting more signals
does not make Sweden outrank Finland or Detroit outrank London — those need an influence
signal, and that is a weighting decision to be made against the whole eval C suite at once.

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
