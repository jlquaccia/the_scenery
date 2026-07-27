"""Pydantic DTOs returned by `scene_service` — the shared contract.

These are what REST responses (1.7), the scene-db MCP tools (1.8) and the agent's
`scene_results` state slot all speak, so the shape is deliberately compact and
LLM-friendly: no ORM objects, no nested rows, coordinates always present when the
location has them (DESIGN.md §4.3).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

GeoLevel = Literal["city", "metro", "state", "country"]
SignalType = Literal["band", "venue", "festival", "label", "release", "historic"]


class GenreOut(BaseModel):
    """A node of the genre taxonomy."""

    id: int
    name: str
    parent_id: int | None = None
    parent_name: str | None = None


class SignalOut(BaseModel):
    """One piece of evidence behind a scene's score."""

    name: str
    signal_type: SignalType | None = None
    weight: float = 1.0
    location: str | None = Field(
        default=None,
        description="City the signal came from — differs from the scene's location on rollups.",
    )


class SceneSummary(BaseModel):
    """A ranked scene row (DESIGN.md §4.3)."""

    scene_id: int
    genre: str
    genre_id: int
    location: str
    location_id: int
    level: GeoLevel
    lat: float | None = None
    lng: float | None = None
    score: float
    top_signals: list[str] = Field(
        default_factory=list, description='Formatted as "Metallica (band)".'
    )


class SceneDetail(SceneSummary):
    """Everything the marker-click detail panel needs."""

    description: str | None = None
    score_updated_at: datetime | None = None
    location_path: list[str] = Field(
        default_factory=list, description="Ancestors first: ['United States', 'California', …]."
    )
    signal_count: int = 0
    signals: list[SignalOut] = Field(default_factory=list)


class ComparedScene(SceneSummary):
    """One side of a comparison."""

    signal_count: int = 0
    distinctive_signals: list[str] = Field(
        default_factory=list, description="Signals this scene has and the others do not."
    )


class SceneComparison(BaseModel):
    """Side-by-side scenes, with an explicit verdict on whether scores can be compared.

    Scores are normalized per (genre, level), so two 100.0s from different genres or
    different geo tiers mean "top of its own tier", not "equal". `comparable` says
    whether a score comparison is meaningful; `caveat` explains it in words the agent
    can pass through to the user rather than inventing a conclusion.
    """

    scenes: list[ComparedScene]
    comparable: bool
    caveat: str | None = None
    shared_signals: list[str] = Field(
        default_factory=list, description="Signals present in every compared scene."
    )
