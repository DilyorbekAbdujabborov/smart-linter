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
│  In /ws/process: one shared, lock-serialized model per process     │
│  (avoids per-connection reload; ByteTrack persist=True state lives │
│  on the model object itself, so access must be serialized)         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  detector/tracker.py — ByteTrack Multi-Object Tracking             │
│  Wraps model.track(persist=True), assigns stable track_ids         │
│  Centroid history per track (max 150 frames), pruned after a track │
│  goes unseen for _MAX_MISSING_FRAMES (bounds memory)                │
│  Returns List[TrackedObject] with full motion history               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  detector/rule_engine.py — 6-Rule State Machine                    │
│  Per-object state machine: CARRIED→RELEASED→ON_GROUND→REPORTED     │
│  Consumes List[TrackedObject], returns List[Violation]             │
│  Pure logic — no I/O, no video files, no database                  │
│  Ground line (R3) and bin zones (R6) are live-tunable at runtime   │
│  (set_ground_y_ratio / add_bin_zone / remove_bin_zone), driven by  │
│  WS control messages from the UI                                   │
│  Per-track state pruned after TRACK_TTL_SECONDS unseen (bounds     │
│  memory on long-running / RTSP streams)                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  face/face_id.py — Face Identification                             │
│  OpenCV YuNet (detect) + SFace (128-d embedding), auto-downloaded  │
│  Pipeline caches each tracked person's latest crop; on a violation │
│  it's matched against the enrolled Person roster by cosine         │
│  similarity. Skipped entirely when the roster is empty.            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  recorder/recorder.py — Clip Recording                             │
│  Rolls ClipBuffer (pre-event) + collects post-event frames         │
│  Writes MP4 (OpenCV VideoWriter, configurable codec) + preview     │
│  JPEG to events/. Returns List[ClipResult] with file paths         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  database/database.py — SQLAlchemy Persistence                     │
│  CRUD for Event, Person (face roster), BinZone                     │
│  Context-managed sessions with auto-commit/rollback                │
│  SQLite in WAL mode by default; PostgreSQL-ready via DATABASE_URL  │
│  No Alembic: init_db() ALTER TABLEs in columns missing from an     │
│  existing on-disk database                                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  api/routes.py — FastAPI Application                               │
│  Auth: /auth/login, /auth/refresh (JWT access + refresh, rotated)  │
│  REST: /events*, /people*, /bin-zones* (all JWT-protected)         │
│  SSE: /events/stream (indexed id>last_id polling)                  │
│  WebSocket: /ws/process (annotated frames + live control messages) │
│  HTML: /login, / (dashboard), /process (live detection), /roster   │
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
| `tracker.py` | `Tracker` | ByteTrack wrapper with centroid history, stale-track pruning |
| `rule_engine.py` | `RuleEngine` | Stateful evaluator (6-rule state machine), live-tunable ground line + bin zones |
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
toilet       → TRASH_BIN   (closest COCO approximation)
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
  - R6: object inside trash_bin (detected OR a manually-drawn bin zone) → reset to CARRIED
```

### Face Identification (`face/`)

| File | Class | Purpose |
|------|-------|---------|
| `face_id.py` | `FaceIdentifier` | YuNet detector + SFace recognizer; detects the primary face in an image, extracts a 128-d embedding, matches by cosine similarity |
| `face_id.py` | `embedding_to_json` / `embedding_from_json` | Serialize an embedding for `Person.embedding` |

Both ONNX models are OpenCV's own (Apache-2.0) and auto-download into `FACE_MODELS_DIR` on first use — no ML dependency beyond `opencv-python`, which the project already requires.

**Owner lookup (`pipeline.py`):** every frame, `Pipeline` caches each tracked `PERSON`'s latest bbox crop. `RuleEngine.Violation.owner_track_id` (the person who was last seen carrying the object) is used to fetch that cached crop when a violation fires, run it through `FaceIdentifier`, and match it against the enrolled roster. All of this is skipped when no one is enrolled.

### Auth Layer (`auth/`)

| File | Function | Purpose |
|------|----------|---------|
| `security.py` | `hash_password` / `verify_password` | PBKDF2-HMAC-SHA256, random salt |
| `security.py` | `create_access_token` / `create_refresh_token` | Short/long-lived JWTs, `type` claim (`access`/`refresh`) and random `jti` |
| `security.py` | `decode_access_token` / `decode_refresh_token` | Verify signature, expiry, and `type` |

Single-admin (no user table). `POST /auth/login` returns both tokens; `POST /auth/refresh` rotates them. `api/routes.py`'s `get_current_username` dependency accepts the token via the `Authorization` header or a `?token=` query param (needed for SSE/WebSocket, which can't set custom headers).

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
| `models.py` | `Event` | Violation events, incl. face-match columns |
| `models.py` | `Person` | Enrolled face-id roster entry |
| `models.py` | `BinZone` | A remembered R6 rectangle (normalized [0,1] coords) |
| `database.py` | `init_db()` | Creates tables if not exist, `ALTER TABLE`s in missing columns |
| `database.py` | `session_scope()` | Context-managed transactional sessions |
| `database.py` | `create_event()` / `list_events()` / `list_events_since()` / `count_events()` / `get_event()` / `delete_event()` | Event CRUD; `list_events` is paginated + filterable, `list_events_since` powers SSE |
| `database.py` | `create_person()` / `list_people()` / `get_person()` / `delete_person()` | Face-roster CRUD |
| `database.py` | `create_bin_zone()` / `list_bin_zones()` / `delete_bin_zone()` | Bin-zone CRUD |

Engine runs SQLite in **WAL mode** (`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`) so the API (reader) and the pipeline (writer) don't lock each other out — the default rollback-journal mode serializes all access.

**Event schema:**
```sql
CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       DATETIME NOT NULL,
    camera_id       VARCHAR(64) NOT NULL,
    confidence      FLOAT NOT NULL,
    object_type     VARCHAR(32) NOT NULL,
    video_path      VARCHAR(255) NOT NULL,
    preview_image   VARCHAR(255) NOT NULL,
    person_id       INTEGER,          -- nullable: face match, if any
    person_name     VARCHAR(128),
    face_similarity FLOAT
);

CREATE TABLE people (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL,
    embedding  TEXT NOT NULL,         -- JSON-encoded 128-float SFace embedding
    photo_path VARCHAR(255) NOT NULL
);

CREATE TABLE bin_zones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    x1 FLOAT NOT NULL, y1 FLOAT NOT NULL,
    x2 FLOAT NOT NULL, y2 FLOAT NOT NULL,   -- normalized [0,1]
    created_at DATETIME NOT NULL
);
```

### API Layer (`api/`)

| File | Class | Purpose |
|------|-------|---------|
| `schemas.py` | `EventOut`, `PersonOut`, `BinZoneOut`/`BinZoneIn`, `TokenOut`/`RefreshIn`, `HealthOut` | Pydantic request/response models |
| `routes.py` | `create_app()` | FastAPI app factory |
| `routes.py` | `get_current_username` | Auth dependency: JWT from header or `?token=` |
| `routes.py` | `_get_shared_detector` / `_get_face_identifier` | Lazy, process-wide singletons (avoid reload cost per request/connection) |
| `routes.py` | `app` | Module-level app for uvicorn |

**Communication modes:**
- **REST:** Standard request/response for CRUD operations (`/events*`, `/people*`, `/bin-zones*`, `/auth/*`), all JWT-protected except `/health` and `/auth/*`
- **SSE:** `/events/stream` pushes new events as they arrive (2s poll, indexed `id > last_id` query)
- **WebSocket:** `/ws/process` streams annotated frames as base64 JPEG in JSON payloads, and accepts `set_ground_y_ratio` / `add_bin_zone` / `remove_bin_zone` control messages from the client via a concurrent receive task

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
6. **Thread Safety:** SQLite `check_same_thread=False` + WAL mode for multi-threaded API+pipeline access
7. **Bounded Memory:** Per-track state (rule engine, tracker history) is pruned after a configurable unseen duration — required for long-running/RTSP streams
8. **Auth at the Boundary:** JWT verification lives entirely in `api/routes.py`'s dependency; `RuleEngine`, `Pipeline`, and the detector/face layers have no auth awareness
