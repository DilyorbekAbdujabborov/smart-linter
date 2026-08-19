# Smart Litter Detection System - Claude Code Instructions

## Project Overview

Smart Litter Detection System — an MVP computer vision application that detects when a person throws trash on the ground from MP4 video or RTSP CCTV streams. Records 10-second clips of violations and exposes events via REST API + web dashboard.

**Language:** Python 3.12+
**Status:** MVP / Proof of Concept

## Recommended Reading Order

Read these files in order to understand the project quickly:

1. **`CLAUDE.md`** — this file (you are here)
2. **`main.py`** — CLI entry point: `process`, `serve`, `hash-password` subcommands
3. **`config.py`** — all settings in one place, pydantic-settings singleton
4. **`pipeline.py`** — orchestrator, shows how all components connect (incl. face-id + bin zones)
5. **`detector/types.py`** — domain types (ObjectClass, Detection, TrackedObject)
6. **`detector/rule_engine.py`** — the core logic: 6-rule state machine
7. **`auth/security.py`** — JWT access/refresh token issuance and verification
8. **`api/routes.py`** — REST API, SSE, WebSocket, dashboard, auth

After reading these 8 files you will understand the full system.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Object Detection | YOLO11 (ultralytics) |
| Multi-Object Tracking | ByteTrack (via ultralytics) |
| Face Detection/Recognition | OpenCV YuNet + SFace (built into opencv-python) |
| Video I/O | OpenCV (opencv-python) |
| Web Framework | FastAPI + Uvicorn |
| Database | SQLAlchemy 2.0 (SQLite w/ WAL, PostgreSQL-ready) |
| Auth | PyJWT (access + refresh tokens), PBKDF2 password hashing |
| Templates | Jinja2 + Tailwind (CDN) |
| Config | pydantic-settings + python-dotenv |
| Frontend | Vanilla JS, WebSocket, SSE, Canvas API |

## Architecture

```
Video/RTSP Source
  → camera/video_reader.py      (Frame yields)
  → detector/detector.py         (YOLO11 inference, shared model across WS connections)
  → detector/tracker.py          (ByteTrack tracking)
  → detector/rule_engine.py      (6-rule state machine, live-tunable ground line + bin zones)
  → face/face_id.py              (owner face match against enrolled Person roster)
  → recorder/recorder.py         (10s clip + JPEG)
  → database/database.py         (SQLAlchemy CRUD, WAL mode)
  → api/routes.py                (FastAPI REST + SSE + WebSocket + JWT auth)
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
│   ├── tracker.py     # ByteTrack wrapper with centroid history + stale-track pruning
│   └── rule_engine.py # 6-rule state machine, ground line + bin zones live-tunable
├── face/              # Face detection/recognition for owner identification
│   └── face_id.py     # YuNet detector + SFace recognizer wrapper (auto-downloads weights)
├── auth/              # JWT authentication
│   └── security.py    # Password hashing, access/refresh token issue + verify
├── recorder/          # Clip recording
│   ├── clip_buffer.py # Rolling deque ring buffer for pre-event frames
│   └── recorder.py    # MP4 (configurable codec) + JPEG writer
├── database/          # Persistence layer
│   ├── models.py      # Event, Person, BinZone SQLAlchemy models
│   └── database.py    # Engine (WAL), session factory, CRUD helpers, ALTER-TABLE migration
├── api/               # REST API + web dashboard
│   ├── schemas.py     # Pydantic response schemas
│   └── routes.py      # FastAPI app (REST, SSE, WebSocket, HTML, JWT auth)
├── templates/         # Jinja2 HTML templates (shared dark-*/brand-* Tailwind tokens)
│   ├── login.html     # Username/password login
│   ├── dashboard.html # Event dashboard: SSE live updates, face-match badge, delete
│   ├── process.html   # Real-time detection: WebSocket + canvas, draggable ground
│   │                   #   line, drawable/rememberable bin zones
│   └── roster.html    # Enroll/list/delete people for face matching
├── static/            # Static assets
│   └── auth.js         # Shared client-side token storage + refresh-on-401 fetch wrapper
├── events/            # Recorded violation clips
├── people/            # Enrolled people's reference photos
├── models/            # Auto-downloaded YOLO + face model weights (gitignored)
├── config.py          # pydantic-settings configuration (single source of truth)
├── logging_utils.py   # Project-wide logging setup
├── pipeline.py        # Orchestrates all components (CLI `process` path)
└── main.py            # CLI entry point (process / serve / hash-password)
```

## Key Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Generate the admin password hash for .env's ADMIN_PASSWORD_HASH
python main.py hash-password 'your-password'

# Run detection pipeline on a video
python main.py process --source path/to/video.mp4 --camera-id cam-01

# Run detection on RTSP stream
python main.py process --source "rtsp://user:pass@host:554/stream"

# Start API server + dashboard
python main.py serve                # http://localhost:8000
python main.py serve --port 9000    # custom port
python main.py serve --workers 4    # multi-process (concurrent REST/dashboard clients)

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
| `GROUND_Y_RATIO` | `0.55` | Frame height fraction for ground line (draggable live in the UI) |
| `TRACK_TTL_SECONDS` | `30.0` | Drop a track's rule/history state after this long unseen |
| `PRE_EVENT_SECONDS` | `5.0` | Clip pre-event window |
| `POST_EVENT_SECONDS` | `5.0` | Clip post-event window |
| `VIDEO_CODEC` | `mp4v` | Clip FourCC codec (`avc1` if your OpenCV build supports H264) |
| `WS_DETECT_EVERY_N_FRAMES` | `1` | Run detection every Nth frame in `/ws/process` (raise on slow CPUs) |
| `FACE_MODELS_DIR` | `models` | Where YuNet/SFace ONNX weights auto-download |
| `FACE_MATCH_THRESHOLD` | `0.363` | Cosine-similarity threshold for a face match |
| `PEOPLE_DIR` | `people` | Enrolled people's reference photos |
| `ADMIN_USERNAME` | `admin` | Single admin login |
| `ADMIN_PASSWORD_HASH` | _(empty)_ | From `python main.py hash-password <pw>` |
| `JWT_SECRET` | _(change me)_ | Signs access + refresh tokens |
| `JWT_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `JWT_REFRESH_EXPIRE_MINUTES` | `10080` | Refresh token lifetime (7 days) |
| `DATABASE_URL` | `sqlite:///./smart_litter.db` | Database connection (WAL mode when SQLite) |
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
6. **R6:** Trash object is NOT inside a trash bin — checked against both YOLO-detected `trash_bin` objects *and* manually-drawn, persisted bin zones (see below)

State machine: `CARRIED → RELEASED → ON_GROUND → REPORTED`

`RuleEngine.set_ground_y_ratio()` and `RuleEngine.add_bin_zone()`/`remove_bin_zone()` let the live `/ws/process` session and the UI adjust R3/R6 without restarting the stream.

## Face Identification

When a violation fires, `Pipeline` looks up the owning person's last-seen face crop (cached every frame from tracked `PERSON` boxes) and matches it against the enrolled `Person` roster (`face/face_id.py`: OpenCV YuNet detector + SFace recognizer, no extra ML dependency). A match attaches `person_id` / `person_name` / `face_similarity` to the stored `Event`. Enroll people at `/roster` (`POST /people`, name + one clear photo). Costs nothing when the roster is empty — the crop/detect/match path is skipped entirely.

## Bin Zones (R6)

Since the stock YOLO11/COCO model only approximates a trash bin via `toilet`, detection alone is unreliable. On `/process`, click **+ Bin Zone** and drag a rectangle over a real bin; it's persisted (`BinZone` table, `/bin-zones` CRUD) and mirrored live into the running `RuleEngine`. Remembered zones auto-load into every future WS session and the CLI `process` pipeline. Double-click a drawn zone to remove it.

## Supported Object Classes

| Class | COCO Mappings | Is Trash |
|-------|--------------|----------|
| `person` | person | No |
| `bottle` | bottle, cup, wine glass, bowl | Yes |
| `paper` | book, tie, box | Yes |
| `handbag` | handbag, umbrella | Yes |
| `backpack` | backpack, suitcase | Yes |
| `trash_bin` | toilet (approx) | No (reference) |

## Authentication

Single-admin JWT auth (no user table — not multi-tenant). `POST /auth/login` (username/password) returns an access token (short-lived, `JWT_EXPIRE_MINUTES`) and a refresh token (long-lived, `JWT_REFRESH_EXPIRE_MINUTES`). `POST /auth/refresh` exchanges a valid refresh token for a new pair, rotating the refresh token each time. Tokens carry a `type` claim (`access`/`refresh`) so one can't be used as the other, and a random `jti` so tokens issued in the same second still differ.

All data endpoints require a JWT (`Authorization: Bearer` header, or `?token=` query param for SSE/WebSocket, which can't set custom headers). `static/auth.js` is the shared client-side helper: stores both tokens in `localStorage`, and its `authFetch()` wrapper auto-refreshes on a 401 and retries once before redirecting to `/login`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Exchange username/password for access + refresh tokens |
| POST | `/auth/refresh` | Exchange a refresh token for a new pair (rotates it) |
| GET | `/` | HTML dashboard |
| GET | `/login` | Login page |
| GET | `/process` | Real-time detection page |
| GET | `/roster` | People (face-id) management page |
| GET | `/health` | Liveness + event count |
| GET | `/events` | List events, newest first — paginated (`limit`/`offset`) + filterable (`camera_id`/`object_type`) |
| GET | `/events/stream` | SSE live event stream (indexed `id > last_id` polling) |
| GET | `/events/{id}` | Get one event |
| DELETE | `/events/{id}` | Delete event + media |
| GET | `/events/{id}/download` | Download 10s MP4 clip |
| POST | `/people` | Enroll a person (multipart: `name` + `file`) |
| GET | `/people` | List enrolled people |
| DELETE | `/people/{id}` | Remove an enrolled person |
| POST | `/bin-zones` | Remember a trash-bin rectangle (normalized `x1,y1,x2,y2`) |
| GET | `/bin-zones` | List remembered bin zones |
| DELETE | `/bin-zones/{id}` | Forget a bin zone |
| WS | `/ws/process?source=...&token=...` | Real-time annotated frames; accepts `set_ground_y_ratio` / `add_bin_zone` / `remove_bin_zone` control messages from the client |

Interactive docs at `/docs` (Swagger UI). Every endpoint above except `/health`, `/auth/*`, and the HTML page shells requires a valid access token.

## Important Notes

- YOLO11 weights (`yolo11n.pt`) and the face models (`models/*.onnx`) auto-download on first run
- Stock COCO model lacks native `paper`/`trash_bin` classes — approximated via mapping
- SQLite runs in WAL mode (`journal_mode=WAL`) so the API and pipeline don't lock each other out; `check_same_thread=False` for multi-threaded API+pipeline access
- No Alembic: `database.init_db()` `ALTER TABLE`s in any columns missing from an existing on-disk database, so schema changes don't require deleting it
- Jinja2 `cache_size=0` to avoid Python 3.14 compatibility issue
- WebSocket processing runs in a thread executor; the YOLO model is a **shared, lock-serialized** singleton across all `/ws/process` connections in a process (ByteTrack's `persist=True` state lives on the model object itself, not per-caller)
- Events directory (`events/`) stores MP4 clips and JPEG previews; `people/` stores enrolled reference photos
- `.env` is gitignored — never commit secrets
- Delete buttons in the UI use a two-click inline confirm, not `window.confirm()` — a native confirm dialog blocks the page (and breaks browser automation)

## Extensibility Points (Not Yet Implemented)

- Multiple cameras (one Pipeline per source)
- PostgreSQL (swap `DATABASE_URL`)
- Redis/RabbitMQ queues (between recorder and DB)
- GPU inference (`DEVICE=0`) — supported by config, not the default
- Custom YOLO models trained on real litter/bin classes (edit mapping in `detector/detector.py`)
- Docker/Kubernetes deployment
- Action/pose/plate recognition (new detectors behind same interface)
- Per-camera calibration UI for `proximity_px`/`stationary_seconds` (ground line + bin zones already have one)

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
