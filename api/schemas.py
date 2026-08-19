"""Pydantic response schemas for the REST API.

Kept separate from the ORM models so the wire format can evolve independently
of the database schema (a standard clean-architecture boundary).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EventOut(BaseModel):
    """API representation of a stored litter event."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    camera_id: str
    confidence: float
    object_type: str
    video_path: str
    preview_image: str
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    face_similarity: Optional[float] = None


class PersonOut(BaseModel):
    """API representation of an enrolled person (no embedding exposed)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    photo_path: str


class HealthOut(BaseModel):
    """Health-check payload."""

    status: str
    events: int


class TokenOut(BaseModel):
    """JWT issued on successful login."""

    access_token: str
    token_type: str = "bearer"
