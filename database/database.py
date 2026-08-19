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

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from database.models import Base, Event, Person
from logging_utils import get_logger

logger = get_logger(__name__)

_is_sqlite = settings.database_url.startswith("sqlite")

# ``check_same_thread`` is a SQLite-only concern: the API (FastAPI) and the
# pipeline may touch the DB from different threads. Harmless for other engines
# because we only pass it when the URL is SQLite.
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

if _is_sqlite:
    # WAL lets readers (API) and the writer (pipeline) hit the DB concurrently
    # without lock contention -- the default rollback-journal mode serializes
    # all access and stalls one side under concurrent read+write.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def init_db() -> None:
    """Create tables if they do not yet exist, and add any missing columns."""
    Base.metadata.create_all(bind=engine)
    _migrate_missing_columns()
    logger.info("Database initialised at %s", settings.database_url)


def _migrate_missing_columns() -> None:
    """Add columns introduced after a database already existed.

    No Alembic in this MVP: ``create_all`` only creates missing *tables*, so
    a lightweight ``ALTER TABLE ADD COLUMN`` here keeps older on-disk
    databases (with existing event rows) working after a schema change,
    instead of requiring the file to be deleted.
    """
    inspector = inspect(engine)
    if "events" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("events")}
    additions = {
        "person_id": "INTEGER",
        "person_name": "VARCHAR(128)",
        "face_similarity": "FLOAT",
    }
    with engine.begin() as conn:
        for column, coltype in additions.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE events ADD COLUMN {column} {coltype}"))
                logger.info("Migrated: added events.%s", column)


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
    person_id: Optional[int] = None,
    person_name: Optional[str] = None,
    face_similarity: Optional[float] = None,
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
            person_id=person_id,
            person_name=person_name,
            face_similarity=face_similarity,
        )
        session.add(event)
        session.flush()  # populate event.id before the session closes
        logger.info("Stored event id=%s (%s)", event.id, object_type)
        # Detach a fully-loaded copy so callers can use it after commit.
        session.expunge(event)
        return event


def list_events(
    *,
    limit: int = 100,
    offset: int = 0,
    camera_id: Optional[str] = None,
    object_type: Optional[str] = None,
) -> List[Event]:
    """Return events newest-first, paginated and optionally filtered."""
    with session_scope() as session:
        query = session.query(Event)
        if camera_id is not None:
            query = query.filter(Event.camera_id == camera_id)
        if object_type is not None:
            query = query.filter(Event.object_type == object_type)
        events = (
            query.order_by(Event.timestamp.desc()).offset(offset).limit(limit).all()
        )
        for e in events:
            session.expunge(e)
        return events


def list_events_since(last_id: int) -> List[Event]:
    """Return events with id > ``last_id``, oldest first (for SSE polling).

    Filters in SQL on the indexed primary key instead of fetching the whole
    table every poll.
    """
    with session_scope() as session:
        events = (
            session.query(Event)
            .filter(Event.id > last_id)
            .order_by(Event.id.asc())
            .all()
        )
        for e in events:
            session.expunge(e)
        return events


def count_events() -> int:
    """Return the total number of stored events."""
    with session_scope() as session:
        return session.query(Event).count()


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


def create_person(*, name: str, embedding_json: str, photo_path: str) -> Person:
    """Enroll a new person for face matching."""
    with session_scope() as session:
        person = Person(name=name, embedding=embedding_json, photo_path=photo_path)
        session.add(person)
        session.flush()
        logger.info("Enrolled person id=%s (%s)", person.id, name)
        session.expunge(person)
        return person


def list_people() -> List[Person]:
    """Return all enrolled people."""
    with session_scope() as session:
        people = session.query(Person).order_by(Person.created_at.desc()).all()
        for p in people:
            session.expunge(p)
        return people


def get_person(person_id: int) -> Optional[Person]:
    """Return one enrolled person by id, or None."""
    with session_scope() as session:
        person = session.get(Person, person_id)
        if person is not None:
            session.expunge(person)
        return person


def delete_person(person_id: int) -> bool:
    """Delete an enrolled person by id. Returns True if a row was removed."""
    with session_scope() as session:
        person = session.get(Person, person_id)
        if person is None:
            return False
        session.delete(person)
        logger.info("Deleted person id=%s", person_id)
        return True
