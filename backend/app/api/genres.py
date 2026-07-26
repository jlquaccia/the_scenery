"""Genre taxonomy for autocomplete (DESIGN.md §3.2)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.schemas import GenreOut
from app.services import scene_service

router = APIRouter(prefix="/api", tags=["genres"])


@router.get("/genres", response_model=list[GenreOut])
def list_genres(session: Annotated[Session, Depends(get_session)]) -> list[GenreOut]:
    return scene_service.list_genres(session)
