"""FastAPI application: REST API + HTML dashboard.

Exposes the required endpoints (``/events``, ``/events/{id}``, ``/health``)
plus a Jinja2 dashboard at ``/``. Event media (clips + previews) is served
statically from the events directory.

``create_app`` is a factory so the app can be configured/instantiated in tests
or embedded elsewhere without import-time side effects.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.schemas import EventOut, HealthOut
from config import settings
from database import database
from logging_utils import get_logger

logger = get_logger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Smart Litter Detection System",
        description="MVP: detect people littering from CCTV / video.",
        version="0.1.0",
    )

    database.init_db()

    # cache_size=0 disables Jinja2's LRUCache, which is incompatible with
    # Python 3.14 (raises inside the cache on lookup). Templates are tiny, so
    # recompiling per request is negligible for this MVP.
    jinja_env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        cache_size=0,
    )
    templates = Jinja2Templates(env=jinja_env)

    # Serve recorded clips/previews and any static assets.
    events_dir = Path(settings.events_dir)
    events_dir.mkdir(parents=True, exist_ok=True)
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(events_dir)), name="media")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # -- REST API -----------------------------------------------------------

    @app.get("/health", response_model=HealthOut, tags=["system"])
    def health() -> HealthOut:
        """Liveness probe + event count."""
        return HealthOut(status="ok", events=len(database.list_events()))

    @app.get("/events", response_model=List[EventOut], tags=["events"])
    def get_events() -> List[EventOut]:
        """List all violation events, newest first."""
        return [EventOut.model_validate(e) for e in database.list_events()]

    @app.get("/events/{event_id}", response_model=EventOut, tags=["events"])
    def get_event(event_id: int) -> EventOut:
        """Fetch a single event by id."""
        event = database.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return EventOut.model_validate(event)

    @app.delete("/events/{event_id}", tags=["events"])
    def delete_event(event_id: int) -> dict:
        """Delete an event and its media files."""
        event = database.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        # Best-effort media cleanup; DB row removal is the source of truth.
        for path in (event.video_path, event.preview_image):
            try:
                os.remove(path)
            except OSError:
                logger.warning("Could not remove media file %s", path)
        database.delete_event(event_id)
        return {"deleted": event_id}

    @app.get(
        "/events/{event_id}/download", tags=["events"], response_class=FileResponse
    )
    def download_event(event_id: int) -> FileResponse:
        """Download the 10-second MP4 clip for an event."""
        event = database.get_event(event_id)
        if event is None or not os.path.exists(event.video_path):
            raise HTTPException(status_code=404, detail="Clip not found")
        return FileResponse(
            event.video_path,
            media_type="video/mp4",
            filename=os.path.basename(event.video_path),
        )

    # -- Dashboard ----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, tags=["dashboard"])
    def dashboard(request: Request) -> HTMLResponse:
        """Render the HTML dashboard of events."""
        events = database.list_events()
        # Build view models: media is served from /media/<basename>.
        view = [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "camera_id": e.camera_id,
                "confidence": e.confidence,
                "object_type": e.object_type,
                "preview_url": f"/media/{os.path.basename(e.preview_image)}",
                "video_url": f"/media/{os.path.basename(e.video_path)}",
                "download_url": f"/events/{e.id}/download",
            }
            for e in events
        ]
        return templates.TemplateResponse(
            request, "dashboard.html", {"events": view}
        )

    logger.info("FastAPI app created")
    return app


# Module-level app for ``uvicorn api.routes:app``.
app = create_app()
