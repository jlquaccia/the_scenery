"""scene_service — the one place scene data is read from.

Shared by the REST routers (roadmap 1.7) and the scene-db MCP server (1.8), so
nothing here imports FastAPI: every function takes a SQLAlchemy `Session` and
returns Pydantic DTOs (`app.models.schemas`).

Two things are worth knowing about the data model before reading on:

1. `scene_score` is normalized 0–100 *within a (genre, level)* (DECISIONS.md D1),
   so scores are comparable across locations of the same level and genre, and NOT
   across levels or genres.
2. Rollup scenes (metro/state/country) are materialized rows with no signals of
   their own — their evidence lives in the descendant city scenes. `top_signals`
   therefore walks the location subtree rather than reading `scene_signals`
   directly, which is what makes "San Francisco Bay Area → Metallica, Exodus"
   work (DESIGN.md §4.3).
"""

import re
from collections import defaultdict

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Genre, Location, Scene, SceneSignal
from app.models.schemas import GenreOut, GeoLevel, SceneDetail, SceneSummary, SignalOut

TOP_SIGNALS = 3
MAX_DETAIL_SIGNALS = 25


# --------------------------------------------------------------------------- genres


def list_genres(session: Session) -> list[GenreOut]:
    """The full taxonomy, parents before children, for autocomplete (DESIGN.md §3.2)."""
    parent = Genre.__table__.alias("parent")
    rows = session.execute(
        select(Genre.id, Genre.name, Genre.parent_id, parent.c.name)
        .join(parent, Genre.parent_id == parent.c.id, isouter=True)
        .order_by(Genre.parent_id.is_not(None), Genre.name)
    )
    return [
        GenreOut(id=gid, name=name, parent_id=parent_id, parent_name=parent_name)
        for gid, name, parent_id, parent_name in rows
    ]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.casefold()).strip()


def resolve_genre(session: Session, query: str) -> GenreOut | None:
    """Best-effort name → taxonomy node.

    Deterministic and intentionally narrow: exact (case/punctuation-insensitive)
    match, then prefix ("thrash" → "thrash metal"), then substring. Fuzzy
    phrasings ("tallica-style stuff") are the job of the `genre-taxonomy` skill
    and eval A (roadmap 4.5) — this stays predictable enough to be a CI baseline.
    """
    normalized = _normalize(query)
    if not normalized:
        return None

    genres = list_genres(session)
    by_rank: list[tuple[int, int, GenreOut]] = []
    for genre in genres:
        name = _normalize(genre.name)
        if name == normalized:
            rank = 0
        elif name.startswith(normalized) or normalized.startswith(name):
            rank = 1
        elif normalized in name or name in normalized:
            rank = 2
        else:
            continue
        # Tie-break on the shorter name: "thrash" should land on "thrash metal",
        # not "melodic death metal"-style longer accidental containments.
        by_rank.append((rank, len(name), genre))

    if not by_rank:
        return None
    return min(by_rank, key=lambda item: (item[0], item[1]))[2]


def _genre_ids(session: Session, genre: GenreOut, include_subgenres: bool) -> list[int]:
    """The genre itself plus, optionally, everything under it in the taxonomy.

    Umbrella genres ("metal") carry no scenes of their own — every scene hangs off
    a leaf ("thrash metal") — so without the rollup a query for a parent genre
    would come back empty.
    """
    if not include_subgenres:
        return [genre.id]

    children: dict[int | None, list[int]] = defaultdict(list)
    for gid, parent_id in session.execute(select(Genre.id, Genre.parent_id)):
        children[parent_id].append(gid)

    ids: list[int] = []
    queue = [genre.id]
    while queue:
        current = queue.pop()
        ids.append(current)
        queue.extend(children.get(current, ()))
    return ids


# --------------------------------------------------------------------------- scenes


def _scene_query() -> Select[tuple[Scene, Location, Genre]]:
    return (
        select(Scene, Location, Genre)
        .join(Location, Scene.location_id == Location.id)
        .join(Genre, Scene.genre_id == Genre.id)
    )


def _summarize(scene: Scene, location: Location, genre: Genre) -> SceneSummary:
    return SceneSummary(
        scene_id=scene.id,
        genre=genre.name,
        genre_id=genre.id,
        location=location.name,
        location_id=location.id,
        level=_as_level(location.level),
        lat=float(location.lat) if location.lat is not None else None,
        lng=float(location.lng) if location.lng is not None else None,
        score=float(scene.scene_score),
    )


def _as_level(level: str) -> GeoLevel:
    # The column is an ENUM of exactly these values (changeset 002).
    assert level in ("city", "metro", "state", "country"), level
    return level  # type: ignore[return-value]


def query_scenes(
    session: Session,
    *,
    genre: GenreOut,
    level: GeoLevel | None = None,
    limit: int = 10,
    include_subgenres: bool = True,
) -> list[SceneSummary]:
    """Scenes for a genre, best first.

    `level` filters to one tier of the geo hierarchy (city/metro/state/country);
    omitting it mixes tiers, whose scores are not comparable — callers that rank
    should pass one.
    """
    genre_ids = _genre_ids(session, genre, include_subgenres)
    rows = session.execute(
        _scene_query()
        .where(Scene.genre_id.in_(genre_ids))
        .where(*([Location.level == level] if level else []))
        .order_by(Scene.scene_score.desc(), Location.name)
        .limit(limit)
    ).all()

    summaries = [_summarize(scene, location, g) for scene, location, g in rows]
    _attach_top_signals(session, summaries)
    return summaries


def get_scene_detail(session: Session, scene_id: int) -> SceneDetail | None:
    """One scene with its evidence and geo path — the marker-click payload (2.5)."""
    row = session.execute(_scene_query().where(Scene.id == scene_id)).first()
    if row is None:
        return None
    scene, location, genre = row

    signals = _signals_for(session, genre_id=genre.id, location_id=location.id)
    detail = SceneDetail(
        **_summarize(scene, location, genre).model_dump(),
        description=scene.description,
        score_updated_at=scene.score_updated_at,
        location_path=_location_path(session, location.id),
        signal_count=len(signals),
        signals=signals[:MAX_DETAIL_SIGNALS],
    )
    detail.top_signals = [_format_signal(s) for s in signals[:TOP_SIGNALS]]
    return detail


# --------------------------------------------------------------------------- signals


def _format_signal(signal: SignalOut) -> str:
    return f"{signal.name} ({signal.signal_type})" if signal.signal_type else signal.name


def _location_tree(session: Session) -> tuple[dict[int, int | None], dict[int, str]]:
    parents: dict[int, int | None] = {}
    names: dict[int, str] = {}
    for loc_id, parent_id, name in session.execute(
        select(Location.id, Location.parent_id, Location.name)
    ):
        parents[loc_id] = parent_id
        names[loc_id] = name
    return parents, names


def _descendants(parents: dict[int, int | None], root_id: int) -> set[int]:
    """Every location at or below `root_id`, walking child → parent edges."""
    children: dict[int | None, list[int]] = defaultdict(list)
    for loc_id, parent_id in parents.items():
        children[parent_id].append(loc_id)

    found: set[int] = set()
    queue = [root_id]
    while queue:
        current = queue.pop()
        if current in found:
            continue
        found.add(current)
        queue.extend(children.get(current, ()))
    return found


def _location_path(session: Session, location_id: int) -> list[str]:
    parents, names = _location_tree(session)
    path: list[str] = []
    seen: set[int] = set()  # a cyclic parent chain would be bad data, not a hang
    node: int | None = location_id
    while node is not None and node not in seen:
        seen.add(node)
        path.append(names[node])
        node = parents.get(node)
    return list(reversed(path))


def _signals_for(session: Session, *, genre_id: int, location_id: int) -> list[SignalOut]:
    """Signals backing one (genre, location), including its descendant cities."""
    parents, names = _location_tree(session)
    subtree = _descendants(parents, location_id)
    rows = session.execute(
        select(SceneSignal.name, SceneSignal.signal_type, SceneSignal.weight, Scene.location_id)
        .join(Scene, SceneSignal.scene_id == Scene.id)
        .where(Scene.genre_id == genre_id, Scene.location_id.in_(subtree))
        .order_by(SceneSignal.weight.desc(), SceneSignal.name)
    ).all()
    return [
        SignalOut(
            name=name or "unknown",
            signal_type=signal_type,
            weight=float(weight) if weight is not None else 1.0,
            location=names.get(loc_id),
        )
        for name, signal_type, weight, loc_id in rows
    ]


def _attach_top_signals(session: Session, summaries: list[SceneSummary]) -> None:
    """Fill `top_signals` for a page of results in one query.

    Rollup scenes have no signals of their own, so each summary claims the
    signals of its own location subtree.
    """
    if not summaries:
        return

    parents, names = _location_tree(session)
    subtrees = {s.scene_id: _descendants(parents, s.location_id) for s in summaries}
    wanted_locations = {loc for subtree in subtrees.values() for loc in subtree}
    wanted_genres = {s.genre_id for s in summaries}

    by_key: dict[tuple[int, int], list[SignalOut]] = defaultdict(list)
    for genre_id, loc_id, name, signal_type, weight in session.execute(
        select(
            Scene.genre_id,
            Scene.location_id,
            SceneSignal.name,
            SceneSignal.signal_type,
            SceneSignal.weight,
        )
        .join(SceneSignal, SceneSignal.scene_id == Scene.id)
        .where(Scene.genre_id.in_(wanted_genres), Scene.location_id.in_(wanted_locations))
        .order_by(SceneSignal.weight.desc(), SceneSignal.name)
    ):
        by_key[(genre_id, loc_id)].append(
            SignalOut(
                name=name or "unknown",
                signal_type=signal_type,
                weight=float(weight) if weight is not None else 1.0,
                location=names.get(loc_id),
            )
        )

    for summary in summaries:
        candidates = [
            signal
            for loc_id in subtrees[summary.scene_id]
            for signal in by_key.get((summary.genre_id, loc_id), ())
        ]
        candidates.sort(key=lambda s: (-s.weight, s.name))
        summary.top_signals = [_format_signal(s) for s in candidates[:TOP_SIGNALS]]
