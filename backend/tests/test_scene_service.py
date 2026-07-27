"""scene_service — the layer REST, MCP and every future agent share.

Assertions lean on the golden facts the project already committed to (DECISIONS.md D1,
roadmap 1.5/1.6): Bay Area #1 thrash at metro, Seattle #1 grunge at city, Sweden #1
melodeath at country. Scenes are looked up by (genre, location), never by hardcoded id —
rollup ids are assigned by the scoring job and change on a database rebuild.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.schemas import GenreOut
from app.services import scene_service


def genre_of(session: Session, name: str) -> GenreOut:
    resolved = scene_service.resolve_genre(session, name)
    assert resolved is not None, f"expected {name!r} to resolve"
    return resolved


def scene_id_for(session: Session, genre: str, location: str, level: str) -> int:
    matches = scene_service.query_scenes(
        session, genre=genre_of(session, genre), level=level, location=location, limit=1
    )
    assert matches, f"no {genre} scene at {location} ({level})"
    return matches[0].scene_id


# ------------------------------------------------------------------------ resolve_genre


@pytest.mark.parametrize(
    "query",
    ["thrash metal", "thrash", "Thrash Metal", "  THRASH METAL  ", "thrash-metal!"],
)
def test_resolve_genre_handles_loose_input(session: Session, query: str) -> None:
    assert genre_of(session, query).name == "thrash metal"


@pytest.mark.parametrize("query,expected", [("metal", "metal"), ("death metal", "death metal")])
def test_resolve_genre_prefers_the_exact_name(session: Session, query: str, expected: str) -> None:
    """An exact hit must win over a longer name that merely contains the query."""
    assert genre_of(session, query).name == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        # The query names a genre among other words: the specific name must win,
        # or the "metal" umbrella swallows every metal phrasing.
        ("i like death metal", "death metal"),
        ("into melodic death metal these days", "melodic death metal"),
        ("mostly thrash metal", "thrash metal"),
        # A prefix lands on the genre it starts.
        ("dea", "death metal"),
        # An interior fragment matches four names; the least specific is the safer
        # guess, since a fragment carries no evidence for the more specific ones.
        ("etal", "metal"),
    ],
)
def test_resolve_genre_picks_the_right_side_of_a_containment(
    session: Session, query: str, expected: str
) -> None:
    assert genre_of(session, query).name == expected


@pytest.mark.parametrize("query", ["polka", "", "   "])
def test_resolve_genre_returns_none_when_nothing_matches(session: Session, query: str) -> None:
    assert scene_service.resolve_genre(session, query) is None


def test_resolve_genre_reports_the_parent(session: Session) -> None:
    assert genre_of(session, "thrash metal").parent_name == "metal"


# ------------------------------------------------------------------------- query_scenes


@pytest.mark.parametrize(
    "genre,level,expected_top",
    [
        ("thrash metal", "metro", "San Francisco Bay Area"),
        ("grunge", "city", "Seattle"),
        ("melodic death metal", "country", "Sweden"),
    ],
)
def test_golden_rankings_hold(session: Session, genre: str, level: str, expected_top: str) -> None:
    results = scene_service.query_scenes(session, genre=genre_of(session, genre), level=level)
    assert results[0].location == expected_top


def test_results_are_ranked_and_carry_coordinates(session: Session) -> None:
    results = scene_service.query_scenes(
        session, genre=genre_of(session, "thrash metal"), level="city", limit=5
    )
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    assert all(r.lat is not None and r.lng is not None for r in results)
    assert all(r.level == "city" for r in results)


def test_limit_is_honoured(session: Session) -> None:
    results = scene_service.query_scenes(
        session, genre=genre_of(session, "thrash metal"), level="city", limit=3
    )
    assert len(results) == 3


def test_location_filter_narrows_to_one_place(session: Session) -> None:
    results = scene_service.query_scenes(
        session, genre=genre_of(session, "thrash metal"), level="country", location="Germany"
    )
    assert [r.location for r in results] == ["Germany"]


def test_umbrella_genre_answers_from_its_subgenres(session: Session) -> None:
    """ "metal" owns no scenes; without the rollup the query would come back empty."""
    metal = genre_of(session, "metal")
    with_rollup = scene_service.query_scenes(session, genre=metal, level="metro")
    without = scene_service.query_scenes(
        session, genre=metal, level="metro", include_subgenres=False
    )
    assert with_rollup
    assert {r.genre for r in with_rollup} <= {"thrash metal", "death metal", "melodic death metal"}
    assert without == []


def test_top_signals_roll_up_from_descendant_cities(session: Session) -> None:
    """A metro scene has no signals of its own — its evidence lives in its cities."""
    results = scene_service.query_scenes(
        session, genre=genre_of(session, "thrash metal"), level="metro", limit=1
    )
    assert results[0].top_signals, "rollup scene lost its evidence"


# ---------------------------------------------------------------------- get_scene_detail


def test_detail_includes_geo_path_and_evidence(session: Session) -> None:
    scene_id = scene_id_for(session, "thrash metal", "San Francisco Bay Area", "metro")
    detail = scene_service.get_scene_detail(session, scene_id)
    assert detail is not None
    assert detail.location_path[0] == "United States"
    assert detail.location_path[-1] == "San Francisco Bay Area"
    assert detail.signal_count > 0
    # Signals come from the cities below the metro, not from the metro row itself.
    assert any(s.location != "San Francisco Bay Area" for s in detail.signals)


def test_detail_is_none_for_an_unknown_id(session: Session) -> None:
    assert scene_service.get_scene_detail(session, 999_999) is None


# ----------------------------------------------------------------------- compare_scenes


def test_same_genre_and_level_is_comparable(session: Session) -> None:
    top_two = scene_service.query_scenes(
        session, genre=genre_of(session, "thrash metal"), level="metro", limit=2
    )
    result = scene_service.compare_scenes(session, [s.scene_id for s in top_two])
    assert result.comparable is True
    assert result.caveat is None


def test_different_levels_are_not_comparable(session: Session) -> None:
    """Scores are normalized per level — 100.0 @ metro vs 11.11 @ country is not 9x."""
    metro = scene_id_for(session, "thrash metal", "San Francisco Bay Area", "metro")
    country = scene_id_for(session, "thrash metal", "Germany", "country")
    result = scene_service.compare_scenes(session, [metro, country])
    assert result.comparable is False
    assert result.caveat is not None
    assert "geo levels" in result.caveat


def test_different_genres_are_not_comparable(session: Session) -> None:
    grunge = scene_id_for(session, "grunge", "New York", "city")
    thrash = scene_id_for(session, "thrash metal", "New York", "city")
    result = scene_service.compare_scenes(session, [grunge, thrash])
    assert result.comparable is False
    assert result.caveat is not None
    assert "genres" in result.caveat


def test_shared_signals_are_excluded_from_distinctive(session: Session) -> None:
    grunge = scene_id_for(session, "grunge", "New York", "city")
    thrash = scene_id_for(session, "thrash metal", "New York", "city")
    result = scene_service.compare_scenes(session, [grunge, thrash])
    assert "Anthrax" in result.shared_signals, "MusicBrainz tags Anthrax as both"
    for scene in result.scenes:
        assert not set(scene.distinctive_signals) & set(result.shared_signals)


def test_missing_ids_are_named_in_the_error(session: Session) -> None:
    good = scene_id_for(session, "thrash metal", "San Francisco Bay Area", "metro")
    with pytest.raises(LookupError, match="999999"):
        scene_service.compare_scenes(session, [good, 999_999])
