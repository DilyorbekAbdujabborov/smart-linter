# Changelog

All notable changes to the Smart Litter Detection System will be documented in this file.

## [0.2.0] - 2026-08-19

### Added

- **Auth:** JWT login (`/auth/login`), access + refresh tokens with rotation (`/auth/refresh`), PBKDF2 password hashing, `python main.py hash-password` CLI, `static/auth.js` shared client-side token/refresh helper. Every data endpoint now requires a valid access token.
- **Face identification:** `face/face_id.py` (OpenCV YuNet + SFace, no new dependency) matches the person who dropped an item against an enrolled `Person` roster; `/people` CRUD + `/roster` management page; `Event` gains `person_id`/`person_name`/`face_similarity`.
- **Bin zones (R6):** draw a rectangle over a real trash bin on the live-detection canvas (`+ Bin Zone`); persisted (`BinZone` table, `/bin-zones` CRUD), mirrored live into the running `RuleEngine`, remembered across all future sessions (WS and CLI `process`).
- **Live ground-line tuning:** drag the ground line on the `/process` canvas; a WebSocket control message moves the running `RuleEngine`'s threshold immediately, no reconnect.
- `python main.py serve --workers N` for multi-process scaling.
- Paginated + filterable `GET /events` (`limit`/`offset`/`camera_id`/`object_type`); SSE now polls with an indexed `id > last_id` query instead of refetching the whole table.
- SQLite WAL mode so the API (reader) and pipeline (writer) don't lock each other out.
- Configurable clip codec (`VIDEO_CODEC`) and live-WS frame-skip (`WS_DETECT_EVERY_N_FRAMES`) for throughput on slow hardware.
- UI redesign: unified dark-*/brand-* Tailwind tokens across all pages, favicon, loading/error states, per-card delete (two-click inline confirm, not `window.confirm()`), face-match badge on event cards.

### Fixed

- `TRASH_BIN` was never detected — the COCO `toilet` → `TRASH_BIN` mapping was missing, so R6 (object inside a bin) silently never fired.
- Unbounded memory growth on long-running/RTSP streams: `RuleEngine` per-track state and `Tracker` centroid history now prune tracks that haven't been seen in a while (`TRACK_TTL_SECONDS`, missed-frame counter).
- `/ws/process` reloaded the YOLO model on every connection; it's now a shared, lock-serialized singleton per process (ByteTrack's `persist=True` state lives on the model object itself).

### Changed

- No Alembic, but `database.init_db()` now `ALTER TABLE`s in any columns missing from an existing on-disk database, so schema changes don't require deleting it.

## [0.1.0] - 2026-08-19

### Added

- Initial MVP release
- YOLO11 object detection with COCO-to-MVP class mapping
- ByteTrack multi-object tracking with centroid history
- 6-rule state machine for litter detection (CARRIED, RELEASED, ON_GROUND, REPORTED)
- 10-second clip recording (5s pre + 5s post event)
- SQLite persistence with SQLAlchemy 2.0
- FastAPI REST API with CRUD endpoints
- Server-Sent Events (SSE) for live event streaming
- WebSocket real-time annotated frame streaming
- Dark-themed HTML dashboard with SSE live updates
- Real-time detection page with Canvas API rendering
- pydantic-settings configuration from `.env`
- CLI entry point with `process` and `serve` subcommands
- Support for MP4 files, RTSP streams, and webcam input
- Handbag and backpack as trash classes (expanded COCO mapping)
- Preview JPEG for each violation event
- Event download endpoint (MP4 clip)
- Swagger UI at `/docs`
- Bilingual documentation (English README.md, Uzbek USE.md)

### Known Limitations (MVP)

- No test suite
- No Docker/Kubernetes deployment
- No multi-camera support (single pipeline)
- No GPU inference optimization
- Stock COCO model approximates paper/trash_bin classes
- No authentication or rate limiting
- SQLite only (PostgreSQL-ready but not tested at scale)
