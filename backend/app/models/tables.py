"""SQLAlchemy models mirroring the Liquibase changelog.

The changelog (backend/db/changelog) is the source of truth — these models are
written to MATCH it, never the other way around. `python -m app.models.validate`
diffs this metadata against a migrated database and fails on drift (CI check).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    DECIMAL,
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import ENUM, JSON, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("genres.id"), nullable=True)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (Index("idx_level", "level"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    level: Mapped[str] = mapped_column(ENUM("city", "metro", "state", "country"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(DECIMAL(9, 6), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(DECIMAL(9, 6), nullable=True)
    mb_area_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True, unique=True)


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("genre_id", "location_id", name="uq_scene"),
        Index("idx_genre_score", "genre_id", "scene_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genres.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    scene_score: Mapped[Decimal] = mapped_column(
        DECIMAL(6, 2), nullable=False, server_default=text("0")
    )
    score_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class SceneSignal(Base):
    __tablename__ = "scene_signals"
    __table_args__ = (UniqueConstraint("scene_id", "mb_id", name="uq_signal_mb"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False)
    signal_type: Mapped[str | None] = mapped_column(
        ENUM("band", "artist", "venue", "festival", "label", "release", "historic"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(
        DECIMAL(5, 2), nullable=True, server_default=text("1.0")
    )
    mb_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    metadata_: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, nullable=True, server_default=text("CURRENT_TIMESTAMP")
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(ENUM("user", "assistant", "tool"), nullable=False)
    content: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, nullable=True, server_default=text("CURRENT_TIMESTAMP")
    )
