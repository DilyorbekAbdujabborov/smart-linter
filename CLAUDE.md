# Smart Litter Detection System - Claude Code Instructions

## Project Overview

Smart Litter Detection System — an MVP computer vision application that detects when a person throws trash on the ground from MP4 video or RTSP CCTV streams. Records 10-second clips of violations and exposes events via REST API + web dashboard.

**Language:** Python 3.12+
**Status:** MVP / Proof of Concept

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Object Detection | YOLO11 (ultralytics) |
| Multi-Object Tracking | ByteTrack (via ultralytics) |
| Video I/O | OpenCV (opencv-python) |
| Web Framework | FastAPI + Uvicorn |
| Database | SQLAlchemy 2.0 (SQLite, PostgreSQL-ready) |
| Templates | Jinja2 |
| Config | pydantic-settings + python-dotenv |
| Frontend | Vanilla JS, CSS, WebSocket, SSE, Canvas API |

## Architecture

```
Video/RTSP Source
  → camera/video_reader.py      (Frame yields)
  → detector/detector.py         (YOLO11 inference)
  → detector/tracker.py          (ByteTrack tracking)
  → detector/rule_engine.py      (6-rule state machine)
  → recorder/recorder.py         (10s clip + JPEG)
  → database/database.py         (SQLAlchemy CRUD)
  → api/routes.py                (FastAPI REST + SSE + WebSocket)
```

Each layer is injected and independently swappable.

## Project Structure

```
smart-linter/
├── camera/            # Video frame source (MP4/RTSP/webcam)
│   └── video_reader.py
├── detector/          # Detection, tracking, rule evaluation
│   ├── types.py       # ObjectClass enum, Detection, TrackedObject dataclasses
│   ├── detector.py    # YOLO11 adapter with COCO-to-MVP class mapping
│   ├── tracker.py     # ByteTrack wrapper with centroid history
│   └── rule_engine.py # 6-rule state machine (CARRIED→RELEASED→ON_GROUND→REPORTED)
├── recorder/          # Clip recording
│   ├── clip_buffer.py # Rolling deque ring buffer for pre-event frames
│   └── recorder.py    # MP4 + JPEG writer
├── database/          # Persistence layer
│   ├── models.py      # SQLAlchemy Event model
│   └── database.py    # Engine, session factory, CRUD helpers
├── api/               # REST API + web dashboard
│   ├── schemas.py     # Pydantic response schemas
│   └── routes.py      # FastAPI app (REST, SSE, WebSocket, HTML dashboard)
├── templates/         # Jinja2 HTML templates
│   ├── dashboard.html # Dark-themed event dashboard with SSE live updates
│   └── process.html   # Real-time detection page with WebSocket + canvas
├── static/            # Static assets
├── events/            # Recorded violation clips
├── config.py          # pydantic-settings configuration (single source of truth)
├── logging_utils.py   # Project-wide logging setup
├── pipeline.py        # Orchestrates all components
└── main.py            # CLI entry point (process / serve subcommands)
```

## Key Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run detection pipeline on a video
python main.py process --source path/to/video.mp4 --camera-id cam-01

# Run detection on RTSP stream
python main.py process --source "rtsp://user:pass@host:554/stream"

# Start API server + dashboard
python main.py serve              # http://localhost:8000
python main.py serve --port 9000  # custom port

# Direct uvicorn
uvicorn api.routes:app --reload
```

## Configuration

All tunables are in `.env` (loaded via pydantic-settings). Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VIDEO_SOURCE` | `sample.mp4` | MP4 path or RTSP URL |
| `CAMERA_ID` | `cam-01` | Camera identifier |
| `YOLO_MODEL` | `yolo11n.pt` | YOLO11 weights |
| `DEVICE` | `cpu` | Inference device (cpu/0/cuda) |
| `CONF_THRESHOLD` | `0.30` | Min detection confidence |
| `STATIONARY_SECONDS` | `5.0` | Seconds on ground before violation |
| `PROXIMITY_PX` | `120` | Person-object "close" distance in px |
| `GROUND_Y_RATIO` | `0.55` | Frame height fraction for ground line |
| `PRE_EVENT_SECONDS` | `5.0` | Clip pre-event window |
| `POST_EVENT_SECONDS` | `5.0` | Clip post-event window |
| `DATABASE_URL` | `sqlite:///./smart_litter.db` | Database connection |
| `LOG_LEVEL` | `INFO` | Logging level |

## Code Conventions

- **Python style:** PEP 8, type hints everywhere, `from __future__ import annotations`
- **Docstrings:** Every module, class, and public method has docstrings
- **Logging:** Use `get_logger(__name__)` from `logging_utils.py` — never `print()`
- **Configuration:** Always use `from config import settings` — never `os.getenv()`
- **Error handling:** Raise specific exceptions, use context managers for DB sessions
- **Dataclasses:** Use `@dataclass(frozen=True)` for immutable value types
- **No circular imports:** Domain types live in `detector/types.py` with zero heavy imports
- **Testing:** No test suite yet (MVP). When adding tests, use `pytest`.

## Detection Rules (6-Rule State Machine)

All six must pass for a violation:

1. **R1:** Person and trash object are close (in-hand)
2. **R2:** Trash object separates from the person
3. **R3:** Trash object moves toward the ground (below `ground_y_ratio`)
4. **R4:** Trash object stays stationary for >= N seconds
5. **R5:** Person leaves the object's vicinity (no pickup)
6. **R6:** Trash object is NOT inside a trash bin

State machine: `CARRIED → RELEASED → ON_GROUND → REPORTED`

## Supported Object Classes

| Class | COCO Mappings | Is Trash |
|-------|--------------|----------|
| `person` | person | No |
| `bottle` | bottle, cup, wine glass, bowl | Yes |
| `paper` | book, tie, box | Yes |
| `handbag` | handbag, umbrella | Yes |
| `backpack` | backpack, suitcase | Yes |
| `trash_bin` | toilet (approx) | No (reference) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | HTML dashboard |
| GET | `/process` | Real-time detection page |
| GET | `/health` | Liveness + event count |
| GET | `/events` | List all events (newest first) |
| GET | `/events/stream` | SSE live event stream |
| GET | `/events/{id}` | Get one event |
| DELETE | `/events/{id}` | Delete event + media |
| GET | `/events/{id}/download` | Download 10s MP4 clip |
| WS | `/ws/process?source=...` | Real-time annotated frames |

Interactive docs at `/docs` (Swagger UI).

## Important Notes

- YOLO11 weights (`yolo11n.pt`) auto-download on first run
- Stock COCO model lacks native `paper`/`trash_bin` classes — approximated via mapping
- SQLite uses `check_same_thread=False` for multi-threaded API+pipeline access
- Jinja2 `cache_size=0` to avoid Python 3.14 compatibility issue
- WebSocket processing runs in thread executor to avoid blocking the event loop
- Events directory (`events/`) stores MP4 clips and JPEG previews
- `.env` is gitignored — never commit secrets

## Extensibility Points (Not Yet Implemented)

- Multiple cameras (one Pipeline per source)
- PostgreSQL (swap `DATABASE_URL`)
- Redis/RabbitMQ queues (between recorder and DB)
- GPU inference (`DEVICE=0`)
- Custom YOLO models (edit mapping in `detector/detector.py`)
- Docker/Kubernetes deployment
- Action/pose/face/plate recognition (new detectors behind same interface)

## Git Workflow

### Commit Rules

**Every change must be committed individually.** When Claude Code makes a change:

1. Make the change to one file (or a logically related group of files)
2. Stage the changed file(s) with `git add`
3. Commit with a descriptive message following the convention below
4. Move to the next change

### Commit Message Convention

```
type(scope): short description

Types:
  feat     New feature or functionality
  fix      Bug fix
  docs     Documentation only (README, CLAUDE.md, ARCHITECTURE.md, etc.)
  style    Code style changes (formatting, no logic change)
  refactor Code restructuring (no feature change, no bug fix)
  test     Adding or updating tests
  chore    Build, CI, tooling, config changes
  perf     Performance improvement

Examples:
  docs: add CLAUDE.md - main project instructions
  feat: add handbag as trash class in ObjectClass enum
  fix: correct ground_y_ratio threshold in rule_engine
  refactor: extract session_scope into database module
```

### Commit Workflow for Claude Code

```bash
# 1. Make the change
# 2. Stage
git add <changed-file>

# 3. Commit
git commit -m "type(scope): description"

# 4. Repeat for next change
```

**Never batch unrelated changes into one commit.** Each logical change gets its own commit with a clear message.
