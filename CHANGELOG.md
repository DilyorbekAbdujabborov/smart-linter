# Changelog

All notable changes to the Smart Litter Detection System will be documented in this file.

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
