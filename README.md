# Smart Litter Detection System (MVP)

Proof-of-concept that detects when a person throws trash on the ground from an
MP4 file or an RTSP CCTV stream, records a 10-second clip of the incident,
matches the violator against an enrolled face roster, and exposes the events
through a JWT-authenticated REST API + web dashboard.

> **MVP goal:** prove the concept works — not production hardening.

---

## What it does

```
Video / RTSP
     │
     ▼
Read frames        (camera/video_reader.py)
     ▼
YOLO11 detection   (detector/detector.py)
     ▼
ByteTrack tracking (detector/tracker.py)
     ▼
Rule engine        (detector/rule_engine.py)   ← the 6 litter rules, live-tunable
     ▼
Face match         (face/face_id.py)           ← who dropped it, if enrolled
     ▼
Clip recorder      (recorder/recorder.py)      ← 5s before + 5s after
     ▼
SQLite database    (database/…)                ← WAL mode
     ▼
REST API + dashboard (api/routes.py)           ← JWT-protected
```

### Detection rules

1. Person and trash object are close (in-hand).
2. Trash object separates from the person.
3. Trash object moves toward the ground.
4. Trash object stays nearly stationary for ≥ 5 seconds.
5. Person leaves the object's area (no pickup).
6. Trash object is **not** inside a trash bin — YOLO detection *or* a manually-drawn zone.

All six must pass → a violation is recorded.

### Live tuning from the UI

The `/process` live-detection page isn't just a viewer:

- **Ground line** — drag the red line on the canvas to move rules 3's ground threshold; takes effect immediately on the running stream.
- **Bin zones** — click **+ Bin Zone**, drag a rectangle over a real trash bin. It's remembered (persisted to the database) and applied to every future session, live or CLI-batch. Double-click a zone to remove it.
- **Face roster** — enroll people at `/roster` (name + one clear photo) so violation events carry a name instead of "Unknown".

### Supported objects

`person`, `plastic bottle`, `paper`, `handbag`, `backpack`, `trash bin`. Everything else is ignored.

> The stock YOLO11 (COCO) model has no native *paper* / *trash bin* class, so
> the MVP approximates them via COCO `book`/`tie`/`box` and `toilet`. Drop in
> a custom-trained model later by editing the mapping in `detector/detector.py`
> — nothing else changes.

---

## Setup

Requires **Python 3.12+**.

```bash
cd smart-linter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit VIDEO_SOURCE, JWT_SECRET, ...

# generate the admin login's password hash
python main.py hash-password 'your-password'
# paste the printed hash into .env as ADMIN_PASSWORD_HASH
```

The YOLO11 weights (`yolo11n.pt`) and the face-id models download automatically
on first use.

---

## Usage

**1. Process a video** (writes clips to `events/` and rows to SQLite):

```bash
python main.py process --source path/to/video.mp4 --camera-id cam-01
# or, for CCTV:
python main.py process --source "rtsp://user:pass@host:554/stream"
```

**2. Serve the API + dashboard:**

```bash
python main.py serve            # http://localhost:8000
python main.py serve --workers 4  # multi-process, for concurrent REST/dashboard clients
```

Open <http://localhost:8000/login>, sign in with the admin account, then use
the dashboard, live detection, and people pages from the nav bar.

---

## REST API

| Method | Path                        | Description                     |
|--------|-----------------------------|----------------------------------|
| POST   | `/auth/login`               | Username/password → access + refresh tokens |
| POST   | `/auth/refresh`              | Refresh token → new pair (rotates it) |
| GET    | `/health`                   | Liveness + event count          |
| GET    | `/events`                   | List events, newest first — paginated + filterable |
| GET    | `/events/{id}`              | Get one event                   |
| DELETE | `/events/{id}`              | Delete an event + its media     |
| GET    | `/events/{id}/download`     | Download the 10s MP4 clip       |
| POST/GET | `/people`                  | Enroll / list people for face matching |
| DELETE | `/people/{id}`              | Remove an enrolled person       |
| POST/GET | `/bin-zones`               | Add / list remembered bin zones |
| DELETE | `/bin-zones/{id}`           | Forget a bin zone               |
| WS     | `/ws/process?source=...&token=...` | Real-time annotated frames + live control |
| GET    | `/`                         | HTML dashboard                  |

Every endpoint except `/health` and `/auth/*` requires a JWT access token
(`Authorization: Bearer ...`, or `?token=` for SSE/WebSocket). Interactive docs
at `/docs`.

---

## Configuration

All tunables live in `.env` (see `.env.example`) and are validated in
`config.py`. Key ones:

| Variable              | Meaning                                              |
|-----------------------|--------------------------------------------------------|
| `VIDEO_SOURCE`        | MP4 path or RTSP URL                                  |
| `CONF_THRESHOLD`      | Min detection confidence                             |
| `STATIONARY_SECONDS`  | Seconds on ground before it counts (default 5)       |
| `PROXIMITY_PX`        | Person↔object "close" distance in pixels             |
| `GROUND_Y_RATIO`      | Fraction of frame height that counts as ground (also draggable live) |
| `TRACK_TTL_SECONDS`   | Drop a track's state after this long unseen (memory bound) |
| `PRE/POST_EVENT_SECONDS` | Clip window around the event                      |
| `VIDEO_CODEC`         | Clip codec (`mp4v` default, `avc1` if supported)     |
| `WS_DETECT_EVERY_N_FRAMES` | Detect every Nth live frame (throughput vs. latency) |
| `FACE_MATCH_THRESHOLD` | Cosine-similarity floor for a face match            |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` | Single admin login       |
| `JWT_SECRET` / `JWT_EXPIRE_MINUTES` / `JWT_REFRESH_EXPIRE_MINUTES` | Token signing + lifetimes |
| `DATABASE_URL`        | SQLite by default (WAL mode); PostgreSQL-ready       |

---

## Project layout

```
smart-linter/
├── camera/      video_reader.py       # frame source (file | RTSP)
├── detector/    detector.py           # YOLO11 adapter
│               tracker.py             # ByteTrack wrapper, stale-track pruning
│               rule_engine.py         # the 6 litter rules, live-tunable
│               types.py               # shared domain types
├── face/        face_id.py            # YuNet + SFace face match
├── auth/        security.py           # JWT + password hashing
├── recorder/    clip_buffer.py        # rolling 5s ring buffer
│               recorder.py            # 10s MP4 + preview writer
├── database/    database.py, models.py  # Event, Person, BinZone
├── api/         routes.py, schemas.py
├── templates/   login.html, dashboard.html, process.html, roster.html
├── static/      auth.js               # shared client-side token/refresh helper
├── events/  people/  models/          # recorded clips / enrolled photos / weights
├── config.py, logging_utils.py, pipeline.py, main.py
```

---

## Designed to extend (not built yet)

The architecture leaves clean seams for: multiple cameras (one `Pipeline` per
source), PostgreSQL (`DATABASE_URL` swap), Redis/RabbitMQ queues (between
recorder and DB), GPU inference (`DEVICE=0`), custom YOLO models trained on
real litter/bin classes, action/pose/plate recognition (new detectors behind
the same interface), a per-camera calibration UI for `proximity_px`/
`stationary_seconds`, and Docker/Kubernetes deployment. None are implemented
in this MVP.
