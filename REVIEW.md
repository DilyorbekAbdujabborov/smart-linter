# Smart Litter Detection System — Project Review

## 1. Project Summary

A Python 3.12+ computer vision MVP that detects littering from video files or RTSP CCTV streams. When a person throws trash on the ground, the system records a 10-second clip, optionally matches the violator against an enrolled face roster, and exposes events through a JWT-authenticated REST API + web dashboard.

**Tech Stack:** YOLO11 (ultralytics), ByteTrack, OpenCV YuNet/SFace, FastAPI + Uvicorn, SQLAlchemy 2.0 (SQLite/WAL), PyJWT, Jinja2 + Tailwind (CDN), pydantic-settings.

**Status:** MVP / Proof of Concept. 49 commits on `main`, clean working tree.

---

## 2. Architecture Assessment

### Pipeline Flow
```
Video/RTSP → VideoReader → Detector(YOLO11) → Tracker(ByteTrack)
  → RuleEngine(6-rule state machine) → FaceIdentifier → Recorder → Database
  → FastAPI (REST + SSE + WebSocket, JWT auth)
```

### State Machine: CARRIED → RELEASED → ON_GROUND → REPORTED

Each layer is behind a clean interface, independently swappable. Dependency injection throughout. No circular imports. Domain types in `detector/types.py` have zero heavy imports. This is well-architected for an MVP.

### Component Quality

| Component | File(s) | Verdict |
|-----------|---------|---------|
| Video Reader | `camera/video_reader.py` | Clean context manager, FPS fallback, webcam support |
| Detector | `detector/detector.py` | Thin YOLO adapter, COCO→MVP class mapping |
| Tracker | `detector/tracker.py` | ByteTrack wrapper, bounded history (max 150), stale-track pruning |
| Rule Engine | `detector/rule_engine.py` | Pure logic, 6 rules, live-tunable ground line + bin zones, bounded state |
| Face ID | `face/face_id.py` | YuNet+SFace, auto-download, opt-in at zero cost |
| Auth | `auth/security.py` | PBKDF2, JWT access+refresh with rotation, `jti` for uniqueness |
| Recorder | `recorder/recorder.py` + `clip_buffer.py` | Rolling ring buffer, streaming-friendly clip lifecycle |
| Database | `database/database.py` + `models.py` | WAL mode, context-managed sessions, ALTER-TABLE migration |
| API | `api/routes.py` + `schemas.py` | REST + SSE + WebSocket, shared lock-serialized detector, lazy singletons |
| Frontend | `templates/*.html` + `static/auth.js` | Dark theme, SSE live updates, WS canvas, draggable ground line, drawable bin zones |

---

## 3. Issues Found

### Issue 1: DB WAL/SHM files committed to git (Medium)
**Location:** `smart_litter.db-shm`, `smart_litter.db-wal` are tracked in git.
**Root cause:** `.gitignore` has `*.db` and `*.sqlite3` but not `*-shm` and `*-wal` (SQLite WAL sidecar files).
**Impact:** These are runtime artifacts that should never be version-controlled. They can cause confusion and merge conflicts.
**Fix:** Add `*-shm` and `*-wal` to `.gitignore`, then `git rm --cached` the two files.

### Issue 2: `video/` directory missing (Low)
**Location:** `api/routes.py` line 550: `globmod.glob("video/*.mp4")`
**Root cause:** The `/process` page tries to list MP4 files from a `video/` directory that doesn't exist in the repo (it's in `.gitignore`).
**Impact:** The video file dropdown on the Live Detection page will be empty for new setups. Users must know to create `video/` and put files there manually.
**Fix:** Either create `video/.gitkeep` (like `events/.gitkeep`) or handle the missing directory gracefully with a try/except.

### Issue 3: Config defaults mismatch (Low — likely intentional)
**Location:** `config.py` vs `.env.example` vs documentation

| Setting | `config.py` default | `.env.example` | README/docs |
|---------|--------------------|-----------------|-------------|
| `conf_threshold` | 0.15 | 0.30 | 0.30 |
| `stationary_seconds` | 2.0 | 5.0 | 5.0 |
| `ground_y_ratio` | 0.30 | 0.55 | 0.55 |

**Likely intentional:** The lower defaults in `config.py` are tuned for short test videos (faster detection at lower thresholds). When a user copies `.env.example`, they get the documented production values. This works but is confusing — someone reading `config.py` sees different "defaults" than the docs describe. A comment in `config.py` explaining this would help.

### Issue 4: No test suite (Known limitation)
**Status:** Acknowledged in README, CLAUDE.md, CONTRIBUTING.md as an MVP limitation. Recommended test structure is documented in CONTRIBUTING.md.

---

## 4. Code Quality

### Strengths
- **Type hints everywhere** with `from __future__ import annotations`
- **Docstrings on every module, class, and public method**
- **No `print()`** — consistent `get_logger(__name__)` usage
- **No `os.getenv()`** — all config through `settings` singleton
- **`@dataclass(frozen=True)`** for immutable value types (Detection, Frame, Violation)
- **Context managers** for DB sessions and video capture
- **Bounded memory** — track history and rule state pruned after configurable TTL
- **Thread safety** — shared detector lock-serialized, WAL mode for concurrent read/write
- **Security** — PBKDF2 password hashing, JWT with `type` claim + `jti`, token rotation, constant-time password comparison
- **Two-click inline delete confirm** instead of `window.confirm()` (doesn't block automation)
- **Bilingual documentation** — English README + Uzbek USE.md

### Minor Observations
- `config.py` uses `@lru_cache` on `get_settings()` AND has a module-level `settings = get_settings()` — the lru_cache is technically redundant since the module-level singleton already caches, but it's harmless and provides a reset path for tests.
- The `process.html` canvas has `width="720" height="1280"` (portrait) — unusual for CCTV but gets overridden dynamically per frame (`canvas.width = img.width`).
- SSE uses 2-second polling with indexed `id > last_id` — simple and effective for MVP scale.

---

## 5. File Map (14 Python modules + 4 templates + 1 JS)

```
smart-linter/
├── main.py                    # CLI: process / serve / hash-password
├── config.py                  # pydantic-settings singleton
├── pipeline.py                # Orchestrates all components
├── logging_utils.py           # get_logger() wrapper
├── camera/video_reader.py     # VideoReader + Frame dataclass
├── detector/
│   ├── types.py               # ObjectClass enum, Detection, TrackedObject
│   ├── detector.py            # YOLO11 adapter with COCO mapping
│   ├── tracker.py             # ByteTrack wrapper, bounded history
│   └── rule_engine.py         # 6-rule state machine (largest logic file)
├── face/face_id.py            # YuNet + SFace wrapper
├── auth/security.py           # JWT + PBKDF2 password hashing
├── recorder/
│   ├── clip_buffer.py          # Rolling deque ring buffer
│   └── recorder.py             # MP4 + JPEG writer
├── database/
│   ├── models.py              # Event, Person, BinZone ORM models
│   └── database.py            # Engine, sessions, CRUD, migration
├── api/
│   ├── schemas.py             # Pydantic response models
│   └── routes.py              # FastAPI app (REST, SSE, WS, HTML, JWT)
├── templates/
│   ├── login.html             # Login page
│   ├── dashboard.html         # Event dashboard with SSE
│   ├── process.html           # Real-time WS detection + canvas
│   └── roster.html            # Face-roster management
├── static/auth.js             # Shared client token/refresh helper
└── Docs: README, ARCHITECTURE, CLAUDE, AGENTS, CONTRIBUTING, CHANGELOG, USE, TEST_VIDEO_TZ
```

---

## 6. Verdict

This is a **well-structured, production-minded MVP** with clean architecture, proper separation of concerns, and thoughtful engineering decisions throughout. The codebase is consistent, well-documented, and follows its own conventions rigorously. The 4 issues found are minor — 1 medium (git-tracked WAL files), 3 low. The project is ready for its next phase (tests, Docker, multi-camera, GPU) as documented in its extensibility points.
