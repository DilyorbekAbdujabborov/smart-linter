"""SQLAlchemy ORM models.

A single ``Event`` table stores confirmed litter violations. The schema maps
directly onto the required event fields. Using the ORM (not raw SQL) means the
same models work unchanged against PostgreSQL later -- only the engine URL
changes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
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
