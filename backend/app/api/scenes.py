"""REST access to scene data — the map stays browsable without chatting (DESIGN.md §3.2)."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.schemas import GeoLevel, SceneDetail, SceneSummary
from app.services import scene_service

log = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["scenes"])


@router.get("/scenes", response_model=list[SceneSummary])
def list_scenes(
    session: Annotated[Session, Depends(get_session)],
    genre: Annotated[str, Query(description="Genre name; resolved loosely, e.g. 'thrash'.")],
    level: Annotated[GeoLevel | None, Query(description="Geo tier to rank within.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    include_subgenres: Annotated[
        bool, Query(description="Roll umbrella genres ('metal') up from their subgenres.")
    ] = True,
) -> list[SceneSummary]:
    resolved = scene_service.resolve_genre(session, genre)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"unknown genre: {genre!r}")
    log.info("scenes.query", genre=resolved.name, level=level, limit=limit)
    return scene_service.query_scenes(
        session,
        genre=resolved,
        level=level,
        limit=limit,
        include_subgenres=include_subgenres,
    )


@router.get("/scenes/{scene_id}", response_model=SceneDetail)
def scene_detail(
    session: Annotated[Session, Depends(get_session)],
    scene_id: Annotated[int, Path(ge=1)],
) -> SceneDetail:
    detail = scene_service.get_scene_detail(session, scene_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no scene with id {scene_id}")
    return detail
