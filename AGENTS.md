# Agent Instructions for Smart Litter Detection System

## Project Identity

Smart Litter Detection System — Python 3.12+ computer vision MVP that detects littering from video/RTSP, records 10s clips, and serves events via REST API + web dashboard.

## Quick Reference

### Run Commands

```bash
# Activate environment first
source .venv/bin/activate

# Process a video file
python main.py process --source video/sample.mp4 --camera-id cam-01

# Process RTSP stream
python main.py process --source "rtsp://user:pass@host:554/stream"

# Start API server
python main.py serve
python main.py serve --port 9000

# Direct uvicorn
uvicorn api.routes:app --reload
```

### Tech Stack

- Python 3.12+, YOLO11 (ultralytics), ByteTrack, OpenCV
- FastAPI + Uvicorn, SQLAlchemy 2.0 (SQLite), Jinja2
- pydantic-settings for configuration

### Code Conventions

- Type hints everywhere, `from __future__ import annotations`
- `get_logger(__name__)` for logging — never `print()`
- `from config import settings` for config — never `os.getenv()`
- Docstrings on every module, class, and public method
- `@dataclass(frozen=True)` for immutable value types
- Context managers for database sessions

### File Map

| Path | Purpose |
|------|---------|
| `main.py` | CLI entry point (process / serve) |
| `pipeline.py` | Orchestrates all components |
| `config.py` | pydantic-settings (single source of truth) |
| `logging_utils.py` | Project-wide logging |
| `camera/video_reader.py` | Frame iterator (MP4/RTSP/webcam) |
| `detector/types.py` | ObjectClass enum, Detection, TrackedObject |
| `detector/detector.py` | YOLO11 adapter with COCO mapping |
| `detector/tracker.py` | ByteTrack wrapper with centroid history |
| `detector/rule_engine.py` | 6-rule state machine (largest logic file) |
| `recorder/clip_buffer.py` | Rolling deque ring buffer |
| `recorder/recorder.py` | MP4 + JPEG writer |
| `database/models.py` | SQLAlchemy Event model |
| `database/database.py` | Engine, session factory, CRUD |
| `api/schemas.py` | Pydantic response models |
| `api/routes.py` | FastAPI app (REST, SSE, WS, HTML) |
| `templates/dashboard.html` | Event dashboard (SSE live) |
| `templates/process.html` | Real-time detection (WS + canvas) |

### Architecture Flow

```
Video/RTSP -> VideoReader -> Detector (YOLO11) -> Tracker (ByteTrack)
  -> RuleEngine (6 rules) -> Recorder (10s clip) -> Database (SQLAlchemy)
  -> API (FastAPI REST + SSE + WebSocket)
```

### Detection Rules (All Must Pass)

1. R1: Person and trash object are close (in-hand)
2. R2: Trash object separates from person
3. R3: Trash object moves toward ground
4. R4: Trash object stays stationary >= N seconds
5. R5: Person leaves the area (no pickup)
6. R6: Trash object is NOT inside a trash bin

State machine: CARRIED -> RELEASED -> ON_GROUND -> REPORTED

### Configuration

All settings in `.env`, accessed via `settings` singleton:
- `VIDEO_SOURCE`, `CAMERA_ID`, `YOLO_MODEL`, `DEVICE`
- `CONF_THRESHOLD`, `STATIONARY_SECONDS`, `PROXIMITY_PX`, `GROUND_Y_RATIO`
- `PRE_EVENT_SECONDS`, `POST_EVENT_SECONDS`, `EVENTS_DIR`
- `DATABASE_URL`, `API_HOST`, `API_PORT`, `LOG_LEVEL`

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | HTML dashboard |
| GET | `/process` | Real-time detection page |
| GET | `/health` | Liveness + event count |
| GET | `/events` | List all events |
| GET | `/events/stream` | SSE live stream |
| GET | `/events/{id}` | Get one event |
| DELETE | `/events/{id}` | Delete event + media |
| GET | `/events/{id}/download` | Download MP4 clip |
| WS | `/ws/process?source=...` | Real-time annotated frames |

### Testing

No test suite yet. When adding tests use pytest:

```bash
pip install pytest
pytest
pytest --cov=. --cov-report=term-missing
```

### Common Tasks

**Add new object class:**
1. `detector/types.py` — add to `ObjectClass` enum + `is_trash`
2. `detector/detector.py` — add COCO mapping in `_COCO_TO_CLASS`

**Add new rule:**
1. `detector/rule_engine.py` — add check + update state machine
2. `config.py` + `.env.example` — add threshold

**Add new API endpoint:**
1. `api/routes.py` — add route in `create_app()`
2. `api/schemas.py` — add Pydantic model
3. `database/database.py` — add CRUD helper if needed

**Add new database field:**
1. `database/models.py` — update ORM model
2. `database/database.py` — update CRUD
3. `api/schemas.py` — update response model
