# Agent Instructions for Smart Litter Detection System

## Project Identity

Smart Litter Detection System — Python 3.12+ computer vision MVP that detects littering from video/RTSP, records 10s clips, matches the violator against an enrolled face roster, and serves events via a JWT-authenticated REST API + web dashboard.

## Quick Reference

### Run Commands

```bash
# Activate environment first
source .venv/bin/activate

# One-time: generate the admin password hash for .env
python main.py hash-password 'your-password'

# Process a video file
python main.py process --source video/sample.mp4 --camera-id cam-01

# Process RTSP stream
python main.py process --source "rtsp://user:pass@host:554/stream"

# Start API server
python main.py serve
python main.py serve --port 9000
python main.py serve --workers 4   # multi-process

# Direct uvicorn
uvicorn api.routes:app --reload
```

### Tech Stack

- Python 3.12+, YOLO11 (ultralytics), ByteTrack, OpenCV
- OpenCV YuNet + SFace for face detection/recognition (no extra dependency)
- FastAPI + Uvicorn, SQLAlchemy 2.0 (SQLite, WAL mode), Jinja2 + Tailwind (CDN)
- PyJWT for access/refresh tokens, PBKDF2 for password hashing
- pydantic-settings for configuration

### Code Conventions

- Type hints everywhere, `from __future__ import annotations`
- `get_logger(__name__)` for logging — never `print()`
- `from config import settings` for config — never `os.getenv()`
- Docstrings on every module, class, and public method
- `@dataclass(frozen=True)` for immutable value types
- Context managers for database sessions
- Delete buttons use a two-click inline confirm in the UI, never `window.confirm()` (blocks the page/automation)

### File Map

| Path | Purpose |
|------|---------|
| `main.py` | CLI entry point (process / serve / hash-password) |
| `pipeline.py` | Orchestrates all components incl. face-id + bin zones |
| `config.py` | pydantic-settings (single source of truth) |
| `logging_utils.py` | Project-wide logging |
| `camera/video_reader.py` | Frame iterator (MP4/RTSP/webcam) |
| `detector/types.py` | ObjectClass enum, Detection, TrackedObject |
| `detector/detector.py` | YOLO11 adapter with COCO mapping |
| `detector/tracker.py` | ByteTrack wrapper, centroid history, stale-track pruning |
| `detector/rule_engine.py` | 6-rule state machine (largest logic file); live-tunable ground line + bin zones |
| `face/face_id.py` | YuNet detector + SFace recognizer wrapper (auto-downloads weights) |
| `auth/security.py` | Password hashing, access/refresh JWT issue + verify |
| `recorder/clip_buffer.py` | Rolling deque ring buffer |
| `recorder/recorder.py` | MP4 (configurable codec) + JPEG writer |
| `database/models.py` | Event, Person, BinZone SQLAlchemy models |
| `database/database.py` | Engine (WAL), session factory, CRUD, ALTER-TABLE migration |
| `api/schemas.py` | Pydantic response models |
| `api/routes.py` | FastAPI app (REST, SSE, WS, HTML, JWT auth) |
| `static/auth.js` | Shared client token storage + refresh-on-401 fetch wrapper |
| `templates/login.html` | Login page |
| `templates/dashboard.html` | Event dashboard (SSE live, face-match badge, delete) |
| `templates/process.html` | Real-time detection (WS + canvas, draggable ground line, drawable bin zones) |
| `templates/roster.html` | Enroll/list/delete people for face matching (with camera capture) |

### Architecture Flow

```
Video/RTSP -> VideoReader -> Detector (YOLO11, shared across WS conns) -> Tracker (ByteTrack)
  -> RuleEngine (6 rules, live ground line + bin zones) -> face/face_id.py (owner match)
  -> Recorder (10s clip) -> Database (SQLAlchemy, WAL)
  -> API (FastAPI REST + SSE + WebSocket, JWT auth)
```

### Detection Rules (All Must Pass)

1. R1: Person and trash object are close (in-hand)
2. R2: Trash object separates from person
3. R3: Trash object moves toward ground (below live-adjustable `ground_y_ratio`)
4. R4: Trash object stays stationary >= N seconds
5. R5: Person leaves the area (no pickup)
6. R6: Trash object is NOT inside a trash bin — YOLO-detected `trash_bin` OR a manually-drawn, persisted bin zone

State machine: CARRIED -> RELEASED -> ON_GROUND -> REPORTED

### Configuration

All settings in `.env`, accessed via `settings` singleton:
- `VIDEO_SOURCE`, `CAMERA_ID`, `YOLO_MODEL`, `DEVICE`
- `CONF_THRESHOLD`, `IMGSZ`, `TORCH_NUM_THREADS`
- `STATIONARY_SECONDS`, `PROXIMITY_PX`, `GROUND_Y_RATIO`, `TRACK_TTL_SECONDS`
- `PRE_EVENT_SECONDS`, `POST_EVENT_SECONDS`, `EVENTS_DIR`, `VIDEO_CODEC`
- `WS_DETECT_EVERY_N_FRAMES` — run detection every Nth WS frame, raise on slow CPUs
- `FACE_MODELS_DIR`, `FACE_MATCH_THRESHOLD`, `PEOPLE_DIR`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `JWT_REFRESH_EXPIRE_MINUTES`
- `DATABASE_URL`, `API_HOST`, `API_PORT`, `LOG_LEVEL`

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Username/password -> access + refresh tokens |
| POST | `/auth/refresh` | Refresh token -> new pair (rotates it) |
| GET | `/` | HTML dashboard |
| GET | `/login` | Login page |
| GET | `/process` | Real-time detection page |
| GET | `/roster` | People management page |
| GET | `/health` | Liveness + event count |
| GET | `/events` | List events (paginated, filterable) |
| GET | `/events/stream` | SSE live stream |
| GET | `/events/{id}` | Get one event |
| DELETE | `/events/{id}` | Delete event + media |
| GET | `/events/{id}/download` | Download MP4 clip |
| POST/GET | `/people` | Enroll / list people |
| POST | `/people/camera` | Enroll person from camera frame (base64 JPEG) |
| DELETE | `/people/{id}` | Remove person |
| POST/GET | `/bin-zones` | Add / list remembered bin zones |
| DELETE | `/bin-zones/{id}` | Forget a bin zone |
| WS | `/ws/process?source=...&token=...` | Real-time annotated frames + live control messages |

Everything above requires a JWT except `/health`, `/auth/*`, and the HTML page shells.

### Performance Tuning

| Setting | Default | Effect |
|---------|---------|--------|
| `IMGSZ` | `480` | Inference resolution (px). 640=accurate, 480=balanced, 320=max FPS |
| `TORCH_NUM_THREADS` | `0` | PyTorch threads (0=auto). Set to CPU core count if needed |
| `WS_DETECT_EVERY_N_FRAMES` | `1` | Skip N frames between detections in WS. Raise on slow CPUs |

Both `Detector` and `Tracker` use the same `IMGSZ` value for consistent inference.

### Client-Side Auth

- `process.html` skips `/auth/refresh` if the current access token is still valid
- WebSocket code 1008 (bad token) triggers automatic refresh + reconnect
- `auth.js` validates refresh responses before writing to `localStorage`

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
1. `api/routes.py` — add route in `create_app()`, add `username: str = Depends(get_current_username)` unless it's meant to be public
2. `api/schemas.py` — add Pydantic model
3. `database/database.py` — add CRUD helper if needed

**Add new database field:**
1. `database/models.py` — update ORM model
2. `database/database.py` — update CRUD; add to `_migrate_missing_columns()` if it's a new column on an existing table
3. `api/schemas.py` — update response model

## Git Workflow

### Commit Rules

**Every change must be committed individually.** When making a change:

1. Make the change to one file (or logically related group)
2. Stage with `git add <file>`
3. Commit with descriptive message
4. Move to next change

### Commit Message Convention

```
type(scope): description

Types:
  feat     New feature
  fix      Bug fix
  docs     Documentation only
  style    Code style (no logic change)
  refactor Code restructuring
  test     Adding or updating tests
  chore    Build, CI, tooling
```

### Example Workflow

```bash
# Change 1
git add detector/types.py
git commit -m "feat: add handbag as trash class"

# Change 2
git add detector/detector.py
git commit -m "feat: add COCO mapping for handbag"

# Each change gets its own commit
```

**Never batch unrelated changes into one commit.**
