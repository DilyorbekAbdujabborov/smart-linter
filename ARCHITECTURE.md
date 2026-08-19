# Architecture

## System Overview

Smart Litter Detection System is a pipeline-based computer vision application. Each component is isolated behind clean interfaces, making them independently swappable.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Video / RTSP Source                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  camera/video_reader.py — Frame Iterator                           │
│  Wraps cv2.VideoCapture, yields Frame(index, timestamp, image)     │
│  Supports: MP4 files, RTSP streams, webcam indices                 │
│  Context manager for safe resource cleanup                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  detector/detector.py — YOLO11 Inference                           │
│  Runs ultralytics YOLO predict(), filters COCO→MVP class mapping   │
│  Returns List[Detection] (cls, confidence, bbox)                   │
│  Never imported directly by other layers (except tracker)           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  detector/tracker.py — ByteTrack Multi-Object Tracking             │
│  Wraps model.track(persist=True), assigns stable track_ids         │
│  Maintains centroid history per track (max 150 frames)             │
│  Returns List[TrackedObject] with full motion history               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  detector/rule_engine.py — 6-Rule State Machine                    │
│  Per-object state machine: CARRIED→RELEASED→ON_GROUND→REPORTED     │
│  Consumes List[TrackedObject], returns List[Violation]             │
│  Pure logic — no I/O, no video files, no database                  │
│  Configurable thresholds from settings                             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  recorder/recorder.py — Clip Recording                             │
│  Rolls ClipBuffer (pre-event) + collects post-event frames         │
│  Writes MP4 (OpenCV VideoWriter) + preview JPEG to events/         │
│  Returns List[ClipResult] with file paths                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  database/database.py — SQLAlchemy Persistence                     │
│  CRUD helpers: create_event, list_events, get_event, delete_event  │
│  Context-managed sessions with auto-commit/rollback                │
│  SQLite by default; PostgreSQL-ready via DATABASE_URL              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  api/routes.py — FastAPI Application                               │
│  REST: /health, /events, /events/{id}, /events/{id}/download       │
│  SSE: /events/stream (live event push)                             │
│  WebSocket: /ws/process (real-time annotated frames)               │
│  HTML: / (dashboard), /process (live detection)                    │
│  Swagger UI: /docs                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Camera Layer (`camera/`)

| File | Class | Purpose |
|------|-------|---------|
| `video_reader.py` | `VideoReader` | Iterable OpenCV capture wrapper |
| `video_reader.py` | `Frame` | Frozen dataclass: index, timestamp, image |
| `video_reader.py` | `VideoSourceError` | Raised when source cannot be opened |

**Design:** Context manager (`with VideoReader(src) as reader`). Supports MP4 paths, RTSP URLs, and numeric webcam indices. FPS fallback to 25.0 for streams reporting 0.

### Detector Layer (`detector/`)

| File | Class | Purpose |
|------|-------|---------|
| `types.py` | `ObjectClass` | Enum: PERSON, BOTTLE, PAPER, HANDBAG, BACKPACK, TRASH_BIN |
| `types.py` | `Detection` | Frozen dataclass: cls, confidence, bbox, computed properties |
| `types.py` | `TrackedObject` | Mutable dataclass: adds track_id + history |
| `detector.py` | `Detector` | YOLO11 adapter with COCO→MVP class mapping |
| `tracker.py` | `Tracker` | ByteTrack wrapper with centroid history |
| `rule_engine.py` | `RuleEngine` | Stateful evaluator (6-rule state machine) |
| `rule_engine.py` | `Violation` | Frozen dataclass: confirmed litter event |

**COCO Mapping:**
```
person       → PERSON
bottle       → BOTTLE
cup          → BOTTLE
wine glass   → BOTTLE
bowl         → BOTTLE
book         → PAPER
tie          → PAPER
box          → PAPER
handbag      → HANDBAG
umbrella     → HANDBAG
backpack     → BACKPACK
suitcase     → BACKPACK
```

### Rule Engine State Machine

```
                 ┌──────────┐
                 │ CARRIED  │ ◄──── initial state
                 └────┬─────┘
                      │ R2: separates from person
                      ▼
                 ┌──────────┐
                 │ RELEASED │
                 └────┬─────┘
                      │ R3: below ground_y_ratio
                      ▼
                 ┌──────────┐
                 │ON_GROUND │
                 └────┬─────┘
                      │ R4: stationary >= N seconds
                      │ R5: person left vicinity
                      ▼
                 ┌──────────┐
                 │ REPORTED │ ──► emits Violation
                 └──────────┘

Cancellations:
  - RELEASED → CARRIED (person picks back up)
  - ON_GROUND → CARRIED (person picks back up)
  - R6: object inside trash_bin → reset to CARRIED
```

### Recorder Layer (`recorder/`)

| File | Class | Purpose |
|------|-------|---------|
| `clip_buffer.py` | `ClipBuffer` | Rolling deque ring buffer (pre-event frames) |
| `recorder.py` | `Recorder` | Manages buffer + pending clips |
| `recorder.py` | `ClipResult` | Paths + metadata for completed clip |
| `recorder.py` | `_PendingClip` | Clip collecting post-event frames |

**Clip lifecycle:**
1. `feed()` called every frame → updates rolling buffer + pending clips
2. `trigger(violation)` on violation → snapshots pre-buffer, starts pending clip
3. Post-event frames accumulate via subsequent `feed()` calls
4. When post-window full → `_flush()` writes MP4 + JPEG to disk
5. `flush_pending()` at stream end → force-writes incomplete clips

### Database Layer (`database/`)

| File | Class/Function | Purpose |
|------|---------------|---------|
| `models.py` | `Event` | SQLAlchemy ORM model (events table) |
| `database.py` | `init_db()` | Creates tables if not exist |
| `database.py` | `session_scope()` | Context-managed transactional sessions |
| `database.py` | `create_event()` | Insert new violation event |
| `database.py` | `list_events()` | All events, newest first |
| `database.py` | `get_event()` | Single event by ID |
| `database.py` | `delete_event()` | Remove event by ID |

**Event schema:**
```sql
CREATE TABLE events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     DATETIME NOT NULL,
    camera_id     VARCHAR(64) NOT NULL,
    confidence    FLOAT NOT NULL,
    object_type   VARCHAR(32) NOT NULL,
    video_path    VARCHAR(255) NOT NULL,
    preview_image VARCHAR(255) NOT NULL
);
```

### API Layer (`api/`)

| File | Class | Purpose |
|------|-------|---------|
| `schemas.py` | `EventOut` | Pydantic response model for events |
| `schemas.py` | `HealthOut` | Pydantic response model for health check |
| `routes.py` | `create_app()` | FastAPI app factory |
| `routes.py` | `app` | Module-level app for uvicorn |

**Communication modes:**
- **REST:** Standard request/response for CRUD operations
- **SSE:** `/events/stream` pushes new events as they arrive (2s poll interval)
- **WebSocket:** `/ws/process` streams annotated frames as base64 JPEG in JSON payloads

## Configuration Architecture

All configuration flows through a single source:

```
.env file
  → pydantic-settings (Settings class in config.py)
    → settings singleton (importable everywhere)
```

No `os.getenv()` calls exist anywhere in the codebase. Every tunable is typed and validated.

## Design Principles

1. **Dependency Injection:** Components receive dependencies via constructor, never import singletons directly (except `settings`)
2. **Interface Isolation:** Each layer only knows the layer directly below it
3. **No Circular Imports:** Domain types in `detector/types.py` have zero heavy imports
4. **Configuration-Driven:** All thresholds and paths in `.env`, validated by pydantic
5. **Fail-Safe:** Context managers ensure resources are released; DB sessions auto-rollback on error
6. **Thread Safety:** SQLite `check_same_thread=False` for multi-threaded API+pipeline access
