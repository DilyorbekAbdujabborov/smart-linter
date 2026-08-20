"""Pydantic response schemas for the REST API.

Kept separate from the ORM models so the wire format can evolve independently
of the database schema (a standard clean-architecture boundary).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class BinZoneOut(BaseModel):
    """API representation of a remembered trash-bin zone."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    x1: float
    y1: float
    x2: float
    y2: float
    created_at: datetime


class BinZoneIn(BaseModel):
    """Body for POST /bin-zones: a rectangle in normalized [0,1] coordinates."""

    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_ordering(self) -> "BinZoneIn":
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("x2 must be > x1 and y2 must be > y1")
        return self


class HealthOut(BaseModel):
    """Health-check payload."""

    status: str
    events: int


class TokenOut(BaseModel):
    """JWT pair issued on login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    """Body for POST /auth/refresh."""

    refresh_token: str


class CameraEnrollIn(BaseModel):
    """Body for POST /people/camera: enroll a person from a captured frame."""

    name: str = Field(min_length=1, max_length=200)
    frame: str  # base64-encoded JPEG


class FaceIdentifyIn(BaseModel):
    """Body for POST /face/identify: identify a face from a camera frame."""

    frame: str  # base64-encoded JPEG


class FaceIdentifyOut(BaseModel):
    """Response from POST /face/identify."""

    matched: bool
    person_id: Optional[int] = None
    name: Optional[str] = None
    similarity: Optional[float] = None
