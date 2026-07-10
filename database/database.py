"""Database engine, session factory, and event-persistence helpers.

Centralises all DB access. Everything else (pipeline, API) goes through the
``SessionLocal`` factory or the small repository functions here, so switching
from SQLite to PostgreSQL is a one-line ``DATABASE_URL`` change with no query
rewrites.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from database.models import Base, Event
from logging_utils import get_logger

logger = get_logger(__name__)

# ``check_same_thread`` is a SQLite-only concern: the API (FastAPI) and the
# pipeline may touch the DB from different threads. Harmless for other engines
# because we only pass it when the URL is SQLite.
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they do not yet exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialised at %s", settings.database_url)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context: commit on success, rollback on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_event(
    *,
    camera_id: str,
    confidence: float,
    object_type: str,
    video_path: str,
    preview_image: str,
    timestamp: Optional[datetime] = None,
) -> Event:
    """Persist a new violation event and return it."""
    with session_scope() as session:
        event = Event(
            timestamp=timestamp or datetime.now(timezone.utc),
            camera_id=camera_id,
            confidence=confidence,
            object_type=object_type,
            video_path=video_path,
            preview_image=preview_image,
        )
        session.add(event)
        session.flush()  # populate event.id before the session closes
        logger.info("Stored event id=%s (%s)", event.id, object_type)
        # Detach a fully-loaded copy so callers can use it after commit.
        session.expunge(event)
        return event


def list_events() -> List[Event]:
    """Return all events, newest first."""
    with session_scope() as session:
        events = session.query(Event).order_by(Event.timestamp.desc()).all()
        for e in events:
            session.expunge(e)
        return events


def get_event(event_id: int) -> Optional[Event]:
    """Return one event by id, or None."""
    with session_scope() as session:
        event = session.get(Event, event_id)
        if event is not None:
            session.expunge(event)
        return event


def delete_event(event_id: int) -> bool:
    """Delete an event by id. Returns True if a row was removed."""
    with session_scope() as session:
        event = session.get(Event, event_id)
        if event is None:
            return False
        session.delete(event)
        logger.info("Deleted event id=%s", event_id)
        return True
