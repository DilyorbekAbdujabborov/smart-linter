# Smart Litter Detection System (MVP)

Proof-of-concept that detects when a person throws trash on the ground from an
MP4 file or an RTSP CCTV stream, records a 10-second clip of the incident, and
exposes the events through a REST API + web dashboard.

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
Rule engine        (detector/rule_engine.py)   ← the 6 litter rules
     ▼
Clip recorder      (recorder/recorder.py)      ← 5s before + 5s after
     ▼
SQLite database    (database/…)
     ▼
REST API + dashboard (api/routes.py)
```

### Detection rules

1. Person and trash object are close (in-hand).
2. Trash object separates from the person.
3. Trash object moves toward the ground.
4. Trash object stays nearly stationary for ≥ 5 seconds.
5. Person leaves the object's area (no pickup).
6. Trash object is **not** inside a trash bin.

All six must pass → a violation is recorded.

### Supported objects

`person`, `plastic bottle`, `paper`, `trash bin`. Everything else is ignored.

> The stock YOLO11 (COCO) model has no native *paper* / *trash bin* class, so
> the MVP approximates *paper* with COCO `book`. Drop in a custom-trained model
> later by editing the mapping in `detector/detector.py` — nothing else changes.

---

## Setup

Requires **Python 3.12+**.

```bash
cd smart_litter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit VIDEO_SOURCE
```

The YOLO11 weights (`yolo11n.pt`) download automatically on first run.

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
```

Open <http://localhost:8000> for the dashboard.

---

## REST API

| Method | Path                        | Description                     |
|--------|-----------------------------|---------------------------------|
| GET    | `/health`                   | Liveness + event count          |
| GET    | `/events`                   | List all events (newest first)  |
| GET    | `/events/{id}`              | Get one event                   |
| DELETE | `/events/{id}`              | Delete an event + its media     |
| GET    | `/events/{id}/download`     | Download the 10s MP4 clip       |
| GET    | `/`                         | HTML dashboard                  |

Interactive docs at `/docs`.

---

## Configuration

All tunables live in `.env` (see `.env.example`) and are validated in
`config.py`. Key ones:

| Variable              | Meaning                                              |
|-----------------------|------------------------------------------------------|
| `VIDEO_SOURCE`        | MP4 path or RTSP URL                                  |
| `CONF_THRESHOLD`      | Min detection confidence                             |
| `STATIONARY_SECONDS`  | Seconds on ground before it counts (default 5)       |
| `PROXIMITY_PX`        | Person↔object "close" distance in pixels             |
| `GROUND_Y_RATIO`      | Fraction of frame height that counts as ground       |
| `PRE/POST_EVENT_SECONDS` | Clip window around the event                      |
| `DATABASE_URL`        | SQLite by default; PostgreSQL-ready                  |

---

## Project layout

```
smart_litter/
├── camera/      video_reader.py       # frame source (file | RTSP)
├── detector/    detector.py           # YOLO11 adapter
│               tracker.py             # ByteTrack wrapper
│               rule_engine.py         # the 6 litter rules
│               types.py               # shared domain types
├── recorder/    clip_buffer.py        # rolling 5s ring buffer
│               recorder.py            # 10s MP4 + preview writer
├── database/    database.py, models.py
├── api/         routes.py, schemas.py
├── templates/   dashboard.html
├── static/  events/                   # assets / recorded clips
├── config.py, logging_utils.py, pipeline.py, main.py
```

---

## Designed to extend (not built yet)

The architecture leaves clean seams for: multiple cameras (one `Pipeline` per
source), PostgreSQL (`DATABASE_URL` swap), Redis/RabbitMQ queues (between
recorder and DB), GPU inference (`DEVICE=0`), custom YOLO models, action /
pose / face / plate recognition (new detectors behind the same interface),
and Docker/Kubernetes deployment. None are implemented in this MVP.
```
# smart-linter
