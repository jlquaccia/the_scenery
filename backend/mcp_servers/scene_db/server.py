"""scene-db MCP server — the scene database as tools (roadmap 1.8, DESIGN.md §4.5).

A thin FastMCP wrapper over `app.services.scene_service`: no query logic lives here,
so the REST API (1.7), the agents (M3+) and the ingestion pipeline all see identical
data. Tools return the same Pydantic DTOs the REST endpoints do, which is what makes
the contract testable independently of any LLM.

Docstrings below are the tool descriptions the model actually reads — they carry the
one non-obvious rule of this dataset (scores are normalized per genre *and* per geo
level, so they don't compare across either) at the point of use.

Run it:
    MYSQL_DSN=mysql://scenery_app:...@localhost:3306/scenery \
        .venv/bin/python -m mcp_servers.scene_db.server     # http://localhost:8001/mcp
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models.schemas import GenreOut, GeoLevel, SceneComparison, SceneDetail, SceneSummary
from app.services import scene_service

mcp: FastMCP = FastMCP(
    name="scene-db",
    instructions=(
        "Music scene rankings by genre and place. Resolve a genre name first, then query "
        "scenes at one geo level (city/metro/state/country). Scores are 0-100 normalized "
        "within a (genre, level) pair — never compare scores across genres or levels. "
        "Coordinates come from this database; never invent them."
    ),
)


@contextmanager
def _session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


@mcp.tool
def resolve_genre(name: str) -> GenreOut:
    """Resolve a genre name or nickname to its taxonomy node.

    Handles loose input ("thrash" → "thrash metal"). Call this before query_scenes so
    the rest of the turn works with a real genre id. Errors when nothing matches —
    say so rather than guessing a neighbouring genre.
    """
    with _session() as session:
        resolved = scene_service.resolve_genre(session, name)
        if resolved is None:
            known = ", ".join(g.name for g in scene_service.list_genres(session))
            raise ToolError(f"no genre matches {name!r}. Known genres: {known}")
        return resolved


@mcp.tool
def list_genres() -> list[GenreOut]:
    """The full genre taxonomy, each node with its parent (thrash metal → metal → rock)."""
    with _session() as session:
        return scene_service.list_genres(session)


@mcp.tool
def query_scenes(
    genre: str,
    level: GeoLevel | None = None,
    location: str | None = None,
    limit: int = 10,
    include_subgenres: bool = True,
) -> list[SceneSummary]:
    """Rank the places with the strongest scene for a genre, best first.

    Pass `level` to rank within one tier of the geo hierarchy — that is the only way
    the scores are comparable to each other. `location` narrows to places whose name
    contains that text, which is how you reach a specific scene ("Germany") that a
    top-N ranking wouldn't surface. `include_subgenres` lets an umbrella genre
    ("metal") answer from its subgenres, which carry the actual scenes.

    Each result carries `scene_id` (for get_scene_detail / compare_scenes), real
    `lat`/`lng` for map display, and the top signals behind the score.
    """
    with _session() as session:
        resolved = scene_service.resolve_genre(session, genre)
        if resolved is None:
            known = ", ".join(g.name for g in scene_service.list_genres(session))
            raise ToolError(f"no genre matches {genre!r}. Known genres: {known}")
        return scene_service.query_scenes(
            session,
            genre=resolved,
            level=level,
            location=location,
            limit=limit,
            include_subgenres=include_subgenres,
        )


@mcp.tool
def get_scene_detail(scene_id: int) -> SceneDetail:
    """Everything known about one scene: full signal list, geo path, when it was scored.

    Use it to answer "why is this ranked here?" — the signals are the evidence.
    """
    with _session() as session:
        detail = scene_service.get_scene_detail(session, scene_id)
        if detail is None:
            raise ToolError(f"no scene with id {scene_id}")
        return detail


@mcp.tool
def compare_scenes(scene_ids: list[int]) -> SceneComparison:
    """Compare two or more scenes side by side (ids from query_scenes).

    Returns each scene, the signals they share, and what is distinctive to each. Check
    `comparable` before making a claim about the scores: when it is false the scenes
    span different genres or geo levels, `caveat` explains why their scores can't be
    ranked against each other, and the honest comparison is signals, not numbers.
    """
    if len(scene_ids) < 2:
        raise ToolError("compare_scenes needs at least two scene ids")
    with _session() as session:
        try:
            return scene_service.compare_scenes(session, scene_ids)
        except LookupError as exc:
            raise ToolError(str(exc)) from exc


def main() -> None:
    """Serve over streamable-HTTP (the compose default), or stdio on request.

    `MCP_TRANSPORT=stdio` exists for desktop MCP clients that only accept https
    URLs and so can't reach a local http server: they launch this process instead
    and talk to it over the pipe. Same tools either way.
    """
    if os.environ.get("MCP_TRANSPORT", "http") == "stdio":
        mcp.run(transport="stdio", show_banner=False)
        return
    mcp.run(
        transport="http",
        host=os.environ.get("MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MCP_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
