"""FastAPI application: REST API + HTML dashboard.

Exposes the required endpoints (``/events``, ``/events/{id}``, ``/health``)
plus a Jinja2 dashboard at ``/``. Event media (clips + previews) is served
statically from the events directory.

``create_app`` is a factory so the app can be configured/instantiated in tests
or embedded elsewhere without import-time side effects.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.schemas import BinZoneIn, BinZoneOut, CameraEnrollIn, EventOut, FaceIdentifyIn, FaceIdentifyOut, HealthOut, PersonOut, RefreshIn, TokenOut
from auth.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    verify_password,
)
from config import settings
from database import database
from logging_utils import get_logger

logger = get_logger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"

# ``auto_error=False``: SSE (EventSource) and the dashboard's initial page
# load can't attach an Authorization header, so ``get_current_username``
# also accepts the token as a ``?token=`` query param and raises itself.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_username(
    header_token: str | None = Depends(_oauth2_scheme),
    query_token: str | None = Query(default=None, alias="token"),
) -> str:
    """Resolve + validate the JWT from the Authorization header or ``?token=``."""
    raw = header_token or query_token
    if raw is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = decode_access_token(raw)
    if username is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


# Loaded lazily (only when a WebSocket connects) and shared across all
# connections in this process: YOLO weight loading takes real time, and
# reloading it per connection was both slow and a memory multiplier under
# concurrent viewers.
#
# ultralytics' ``model.track(persist=True)`` -- which the tracker calls --
# keeps its ByteTrack state ON THE MODEL OBJECT ITSELF (``model.predictor``),
# not on our ``Tracker`` wrapper. So sharing the model is only safe if calls
# to it are serialized (``_detector_lock``) and each new connection resets
# that state before it starts (below) -- otherwise concurrent viewers would
# corrupt each other's track ids.
_shared_detector = None
_detector_lock = threading.Lock()


def _get_shared_detector():
    global _shared_detector
    if _shared_detector is None:
        from detector.detector import Detector

        _shared_detector = Detector()
    return _shared_detector


# Same lazy-singleton pattern for face enrollment: loaded on first POST
# /people call, not at server startup, so the API stays lightweight when
# face id is never used.
_shared_face_identifier = None


def _get_face_identifier():
    global _shared_face_identifier
    if _shared_face_identifier is None:
        from face.face_id import FaceIdentifier

        _shared_face_identifier = FaceIdentifier()
    return _shared_face_identifier


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
    people_dir = Path(settings.people_dir)
    people_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(events_dir)), name="media")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.mount("/people-media", StaticFiles(directory=str(people_dir)), name="people-media")

    # -- Auth -----------------------------------------------------------------

    @app.post("/auth/login", response_model=TokenOut, tags=["auth"])
    def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenOut:
        """Exchange the admin username/password for an access + refresh token pair."""
        valid = form.username == settings.admin_username and verify_password(
            form.password, settings.admin_password_hash
        )
        if not valid:
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        return TokenOut(
            access_token=create_access_token(subject=form.username),
            refresh_token=create_refresh_token(subject=form.username),
        )

    @app.post("/auth/refresh", response_model=TokenOut, tags=["auth"])
    def refresh(body: RefreshIn) -> TokenOut:
        """Exchange a still-valid refresh token for a new access + refresh pair.

        Rotates the refresh token too (issues a new one each call) so a
        leaked refresh token has a shrinking window of usefulness instead of
        working for its full lifetime regardless of how often it's used.
        """
        username = decode_refresh_token(body.refresh_token)
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        return TokenOut(
            access_token=create_access_token(subject=username),
            refresh_token=create_refresh_token(subject=username),
        )

    # -- REST API -----------------------------------------------------------

    @app.get("/health", response_model=HealthOut, tags=["system"])
    def health() -> HealthOut:
        """Liveness probe + event count."""
        return HealthOut(status="ok", events=database.count_events())

    @app.get("/events", response_model=List[EventOut], tags=["events"])
    def get_events(
        username: str = Depends(get_current_username),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        camera_id: str | None = Query(default=None),
        object_type: str | None = Query(default=None),
    ) -> List[EventOut]:
        """List violation events, newest first, paginated and filterable."""
        events = database.list_events(
            limit=limit, offset=offset, camera_id=camera_id, object_type=object_type
        )
        return [EventOut.model_validate(e) for e in events]

    # -- People (face-id roster) ----------------------------------------------

    @app.post("/people", response_model=PersonOut, tags=["people"])
    async def enroll_person(
        username: str = Depends(get_current_username),
        name: str = Form(...),
        file: UploadFile = File(...),
    ) -> PersonOut:
        """Enroll a person for face matching from one reference photo."""
        import uuid

        import cv2
        import numpy as np

        from face.face_id import embedding_to_json

        raw = await file.read()
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Could not decode image")

        detected = _get_face_identifier().detect_and_embed(image)
        if detected is None:
            raise HTTPException(status_code=400, detail="No face detected in photo")
        embedding, _bbox = detected

        photo_path = people_dir / f"{uuid.uuid4().hex[:12]}.jpg"
        cv2.imwrite(str(photo_path), image)

        person = database.create_person(
            name=name,
            embedding_json=embedding_to_json(embedding),
            photo_path=str(photo_path),
        )
        return PersonOut.model_validate(person)

    @app.post("/people/camera", response_model=PersonOut, tags=["people"])
    async def enroll_person_from_camera(
        body: CameraEnrollIn,
        username: str = Depends(get_current_username),
    ) -> PersonOut:
        """Enroll a person from a base64-encoded camera frame (JPEG)."""
        import base64
        import uuid

        import cv2
        import numpy as np

        from face.face_id import embedding_to_json

        raw = base64.b64decode(body.frame)
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Could not decode image")

        detected = _get_face_identifier().detect_and_embed(image)
        if detected is None:
            raise HTTPException(status_code=400, detail="No face detected in photo")
        embedding, _bbox = detected

        photo_path = people_dir / f"{uuid.uuid4().hex[:12]}.jpg"
        cv2.imwrite(str(photo_path), image)

        person = database.create_person(
            name=body.name,
            embedding_json=embedding_to_json(embedding),
            photo_path=str(photo_path),
        )
        return PersonOut.model_validate(person)

    @app.get("/people", response_model=List[PersonOut], tags=["people"])
    def list_people(username: str = Depends(get_current_username)) -> List[PersonOut]:
        """List enrolled people."""
        return [PersonOut.model_validate(p) for p in database.list_people()]

    @app.delete("/people/{person_id}", tags=["people"])
    def delete_person(person_id: int, username: str = Depends(get_current_username)) -> dict:
        """Remove an enrolled person."""
        person = database.get_person(person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found")
        try:
            os.remove(person.photo_path)
        except OSError:
            logger.warning("Could not remove person photo %s", person.photo_path)
        database.delete_person(person_id)
        return {"deleted": person_id}

    # -- Face identification -------------------------------------------------

    @app.post("/face/identify", response_model=FaceIdentifyOut, tags=["face"])
    async def identify_face(
        body: FaceIdentifyIn,
        username: str = Depends(get_current_username),
    ) -> FaceIdentifyOut:
        """Identify a face from a base64 JPEG frame against the enrolled roster."""
        import base64

        import cv2
        import numpy as np

        from face.face_id import embedding_from_json

        raw = base64.b64decode(body.frame)
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Could not decode image")

        fi = _get_face_identifier()
        detected = fi.detect_and_embed(image)
        if detected is None:
            return FaceIdentifyOut(matched=False)

        embedding, _bbox = detected
        roster = [
            (p.id, p.name, embedding_from_json(p.embedding))
            for p in database.list_people()
        ]
        if not roster:
            return FaceIdentifyOut(matched=False)

        match = fi.best_match(embedding, roster)
        if match is None:
            return FaceIdentifyOut(matched=False)

        person_id, name, similarity = match
        return FaceIdentifyOut(
            matched=True,
            person_id=person_id,
            name=name,
            similarity=round(similarity, 4),
        )

    # -- Bin zones (R6) ---------------------------------------------------------

    @app.post("/bin-zones", response_model=BinZoneOut, tags=["bin-zones"])
    def create_bin_zone(
        body: BinZoneIn, username: str = Depends(get_current_username)
    ) -> BinZoneOut:
        """Remember a manually-drawn trash-bin zone."""
        zone = database.create_bin_zone(x1=body.x1, y1=body.y1, x2=body.x2, y2=body.y2)
        return BinZoneOut.model_validate(zone)

    @app.get("/bin-zones", response_model=List[BinZoneOut], tags=["bin-zones"])
    def list_bin_zones(username: str = Depends(get_current_username)) -> List[BinZoneOut]:
        """List remembered bin zones."""
        return [BinZoneOut.model_validate(z) for z in database.list_bin_zones()]

    @app.delete("/bin-zones/{zone_id}", tags=["bin-zones"])
    def delete_bin_zone(zone_id: int, username: str = Depends(get_current_username)) -> dict:
        """Forget a bin zone."""
        if not database.delete_bin_zone(zone_id):
            raise HTTPException(status_code=404, detail="Bin zone not found")
        return {"deleted": zone_id}

    # -- Real-time SSE (must be before /events/{event_id}) -------------------

    @app.get("/events/stream", tags=["events"])
    async def events_stream(request: Request, username: str = Depends(get_current_username)):
        """Server-Sent Events stream: pushes new events to the client."""
        async def generate():
            latest = database.list_events(limit=1)
            last_id = latest[0].id if latest else 0
            while True:
                if await request.is_disconnected():
                    break
                # Indexed id-range query instead of re-fetching every event
                # each poll -- cheap even with a large event history.
                for e in database.list_events_since(last_id):
                    payload = json.dumps({
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "camera_id": e.camera_id,
                        "confidence": e.confidence,
                        "object_type": e.object_type,
                        "preview_url": f"/media/{os.path.basename(e.preview_image)}",
                        "video_url": f"/media/{os.path.basename(e.video_path)}",
                        "download_url": f"/events/{e.id}/download",
                        "person_id": e.person_id,
                        "person_name": e.person_name,
                        "face_similarity": e.face_similarity,
                    })
                    yield f"data: {payload}\n\n"
                    last_id = e.id
                await asyncio.sleep(2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/events/{event_id}", response_model=EventOut, tags=["events"])
    def get_event(event_id: int, username: str = Depends(get_current_username)) -> EventOut:
        """Fetch a single event by id."""
        event = database.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return EventOut.model_validate(event)

    @app.delete("/events/{event_id}", tags=["events"])
    def delete_event(event_id: int, username: str = Depends(get_current_username)) -> dict:
        """Delete an event and its media files."""
        event = database.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        # Best-effort media cleanup; DB row removal is the source of truth.
        paths = [event.video_path, event.preview_image]
        paths.extend(p for p in (event.object_crop_path, event.face_crop_path) if p)
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                logger.warning("Could not remove media file %s", path)
        database.delete_event(event_id)
        return {"deleted": event_id}

    @app.get(
        "/events/{event_id}/download", tags=["events"], response_class=FileResponse
    )
    def download_event(event_id: int, username: str = Depends(get_current_username)) -> FileResponse:
        """Download the 10-second MP4 clip for an event."""
        event = database.get_event(event_id)
        if event is None or not os.path.exists(event.video_path):
            raise HTTPException(status_code=404, detail="Clip not found")
        return FileResponse(
            event.video_path,
            media_type="video/mp4",
            filename=os.path.basename(event.video_path),
        )

    # -- Real-time WebSocket processing ------------------------------------

    @app.websocket("/ws/process")
    async def ws_process(websocket: WebSocket, source: str = Query(...), token: str = Query(...)):
        """WebSocket endpoint: streams annotated frames from a video source.

        Each message sent to the client is a JSON object:
        {
            "frame": "<base64 JPEG>",
            "frame_index": int,
            "timestamp": float,
            "detections": [{"cls": str, "conf": float, "bbox": [x1,y1,x2,y2], "track_id": int}],
            "violation": {"track_id": int, "object_type": str, "confidence": float, "timestamp": float} | null
        }
        """
        # Browsers can't set a WebSocket Authorization header, so the JWT
        # travels as a query param instead. Validated before accept() so an
        # unauthenticated client never gets a connection.
        if decode_access_token(token) is None:
            await websocket.close(code=1008)  # policy violation
            return
        await websocket.accept()
        import base64
        import cv2
        from detector.motion_gate import MotionGate
        from detector.tracker import Tracker
        from detector.rule_engine import RuleEngine
        from camera.video_reader import VideoReader

        colors = {
            "person": (0, 255, 0),
            "bottle": (255, 0, 0),
            "paper": (255, 255, 0),
            "handbag": (0, 165, 255),
            "backpack": (128, 0, 128),
            "trash_bin": (128, 128, 128),
        }

        # Detection/tracking runs every Nth frame; skipped frames redraw the
        # last known boxes so the video stays smooth without paying full
        # inference cost every frame (tune via WS_DETECT_EVERY_N_FRAMES).
        detect_every = max(1, settings.ws_detect_every_n_frames)
        last_result = {"tracked": [], "violations": []}

        def process_next(frame_iter, tracker, rule_engine, motion_gate):
            """Read + detect + annotate one frame (blocking CPU work).

            Runs in a thread executor so a live camera never blocks the
            server's event loop (SSE, dashboard, other clients).
            Returns the JSON payload dict, or None at end of stream.
            """
            frame = next(frame_iter, None)
            if frame is None:
                return None

            due = frame.index % detect_every == 0
            # Motion gate stacks on top of the N-th-frame schedule: even on a
            # scheduled frame, skip the detect pass if nothing moved (its own
            # heartbeat still forces one periodically).
            moved = motion_gate is None or motion_gate.should_detect(
                frame.timestamp, frame.image
            )
            if due and moved:
                # Serialize access: the underlying YOLO model (and its
                # persisted ByteTrack state) is shared across connections.
                with _detector_lock:
                    last_result["tracked"] = tracker.update(frame.image)
                last_result["violations"] = rule_engine.process(
                    frame.timestamp, last_result["tracked"]
                )
                violations = last_result["violations"]
            else:
                violations = []
            tracked = last_result["tracked"]

            annotated = frame.image.copy()
            for obj in tracked:
                x1, y1, x2, y2 = [int(v) for v in obj.bbox]
                color = colors.get(obj.cls.value, (255, 255, 255))
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                label = f"{obj.cls.value} {obj.confidence:.2f} #{obj.track_id}"
                cv2.putText(annotated, label, (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # The ground line is drawn client-side (so dragging it is instant
            # and doesn't need a round trip) -- just report its current
            # pixel position, which set_ground_y_ratio can move mid-stream.
            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buf).decode("utf-8")

            dets = [
                {
                    "cls": obj.cls.value,
                    "conf": round(obj.confidence, 3),
                    "bbox": [round(v, 1) for v in obj.bbox],
                    "track_id": obj.track_id,
                }
                for obj in tracked
            ]

            viol = None
            if violations:
                v = violations[0]
                viol = {
                    "track_id": v.track_id,
                    "object_type": v.object_type.value,
                    "confidence": round(v.confidence, 3),
                    "timestamp": round(v.timestamp, 2),
                }

            return {
                "frame": frame_b64,
                "frame_index": frame.index,
                "timestamp": round(frame.timestamp, 2),
                "detections": dets,
                "violation": viol,
                "ground_y": round(rule_engine.ground_y, 1),
            }

        try:
            loop = asyncio.get_event_loop()
            detector = _get_shared_detector()
            with _detector_lock:
                # Drop any ByteTrack state left over from a previous
                # connection so this stream starts with a clean slate.
                detector.model.predictor = None
            tracker = Tracker(detector)
            motion_gate = MotionGate() if settings.motion_gate_enabled else None

            with VideoReader(source) as reader:
                rule_engine = RuleEngine(reader.height, reader.width)
                zones = database.list_bin_zones()
                for zone in zones:
                    rule_engine.add_bin_zone(zone.id, zone.x1, zone.y1, zone.x2, zone.y2)
                # Sent once, separately from per-frame payloads (which have
                # no "bin_zones" key), so the client can draw the remembered
                # zones before/alongside the first frame arriving.
                await websocket.send_json(
                    {
                        "bin_zones": [
                            {"id": z.id, "x1": z.x1, "y1": z.y1, "x2": z.x2, "y2": z.y2}
                            for z in zones
                        ]
                    }
                )
                frame_iter = reader.frames()

                async def receive_control_messages() -> None:
                    """Apply live UI adjustments (dragging the ground line,
                    drawing/removing a bin zone) sent by the client,
                    concurrently with the frame send loop below. Bin zones
                    are persisted separately over REST (POST/DELETE
                    /bin-zones); this only mirrors that into the *running*
                    RuleEngine so the change takes effect without a
                    reconnect."""
                    try:
                        while True:
                            msg = await websocket.receive_json()
                            msg_type = msg.get("type")
                            if msg_type == "set_ground_y_ratio":
                                rule_engine.set_ground_y_ratio(float(msg["value"]))
                            elif msg_type == "add_bin_zone":
                                rule_engine.add_bin_zone(
                                    int(msg["id"]),
                                    float(msg["x1"]),
                                    float(msg["y1"]),
                                    float(msg["x2"]),
                                    float(msg["y2"]),
                                )
                            elif msg_type == "remove_bin_zone":
                                rule_engine.remove_bin_zone(int(msg["id"]))
                    except (WebSocketDisconnect, RuntimeError, ValueError, TypeError, KeyError):
                        return

                receiver_task = asyncio.create_task(receive_control_messages())
                try:
                    while True:
                        payload = await loop.run_in_executor(
                            None, process_next, frame_iter, tracker, rule_engine, motion_gate
                        )
                        if payload is None:
                            break  # end of file / stream
                        await websocket.send_json(payload)
                        # Yield to the event loop so other clients get serviced.
                        await asyncio.sleep(0.01)
                finally:
                    receiver_task.cancel()

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            try:
                await websocket.close()
            except Exception:
                pass

    # -- Dashboard ----------------------------------------------------------
    #
    # These pages are unauthenticated shells: the JWT lives in the browser's
    # localStorage (not a cookie), so the server can't gate the HTML response
    # itself. Each page's JS checks for a token on load, redirects to /login
    # if missing, and attaches it to every /events, /events/stream and
    # /ws/process call it makes.

    @app.get("/login", response_class=HTMLResponse, tags=["dashboard"])
    def login_page(request: Request) -> HTMLResponse:
        """Render the login page."""
        return templates.TemplateResponse(request, "login.html", {})

    @app.get("/", response_class=HTMLResponse, tags=["dashboard"])
    def dashboard(request: Request) -> HTMLResponse:
        """Render the HTML dashboard shell; events load client-side via JWT."""
        return templates.TemplateResponse(request, "dashboard.html", {})

    @app.get("/process", response_class=HTMLResponse, tags=["dashboard"])
    def process_page(request: Request) -> HTMLResponse:
        """Render the real-time detection processing page."""
        import glob as globmod
        videos = [Path(p).name for p in sorted(globmod.glob("video/*.mp4"))]
        return templates.TemplateResponse(
            request, "process.html", {"videos": videos}
        )

    @app.get("/roster", response_class=HTMLResponse, tags=["dashboard"])
    def roster_page(request: Request) -> HTMLResponse:
        """Render the enrolled-people (face-id roster) management page."""
        return templates.TemplateResponse(request, "roster.html", {})

    logger.info("FastAPI app created")
    return app


# Module-level app for ``uvicorn api.routes:app``.
app = create_app()
