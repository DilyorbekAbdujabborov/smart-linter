"""SQLAlchemy ORM models.

A single ``Event`` table stores confirmed litter violations. The schema maps
directly onto the required event fields. Using the ORM (not raw SQL) means the
same models work unchanged against PostgreSQL later -- only the engine URL
changes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Event(Base):
    """A recorded litter-violation event."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    video_path: Mapped[str] = mapped_column(String(255), nullable=False)
    preview_image: Mapped[str] = mapped_column(String(255), nullable=False)
    # Face-match against the enrolled Person roster, if any. Nullable: most
    # events have no confident match (person turned away, not enrolled, ...).
    person_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    person_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    face_similarity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Person(Base):
    """An enrolled person, identifiable by face for future violation events."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # SFace embedding (128 floats), JSON-encoded -- SQLite/Postgres both take
    # TEXT, and 128 floats is small enough that no vector column type is
    # worth the extra dependency at this scale.
    embedding: Mapped[str] = mapped_column(Text, nullable=False)
    photo_path: Mapped[str] = mapped_column(String(255), nullable=False)


class BinZone(Base):
    """A manually-drawn trash-bin region (R6), remembered across sessions.

    Coordinates are normalized [0,1] ratios of frame width/height -- like
    ``settings.ground_y_ratio`` -- so the same zone still lines up correctly
    on any stream resolution.
    """

    __tablename__ = "bin_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
