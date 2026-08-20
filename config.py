"""Central application configuration.

All tunables live here and are loaded from environment / ``.env`` via
``pydantic-settings``. Importing ``settings`` anywhere gives a single,
validated, typed configuration object -- no scattered ``os.getenv`` calls.

This is a deliberate extension point: swapping SQLite for PostgreSQL, or a
single camera for many, only means changing values here (or adding fields),
never hunting through the codebase.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings.

    Values are read (in order of precedence) from: real environment
    variables, then a local ``.env`` file, then the defaults below.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Video source -------------------------------------------------------
    video_source: str = "sample.mp4"
    camera_id: str = "cam-01"
    # Static camera geolocation attached to every event this deployment
    # records. None if unset -- single-camera MVP, so this is one pair of
    # coordinates rather than a per-camera registry.
    camera_lat: float | None = None
    camera_lon: float | None = None

    # --- Model --------------------------------------------------------------
    yolo_model: str = "yolo11n.pt"
    device: str = "cpu"
    conf_threshold: float = 0.15
    # Inference image size (pixels). Smaller = much faster on CPU.
    # 640 = YOLO default (accurate, ~80ms/frame on 12-core CPU).
    # 480 = good balance (~55ms, still detects small objects).
    # 320 = maximum FPS (~44ms, but may miss distant/small objects).
    imgsz: int = 480
    # Number of torch intra-op threads. 0 = let torch decide (usually all cores).
    # Set to 12 for 12-core CPU; lower if you need CPU for other tasks.
    torch_num_threads: int = 0

    # --- Rule engine --------------------------------------------------------
    # Seconds an object must sit stationary on the ground, with the owner out
    # of proximity, before it's confirmed as litter (the spec's "10 second
    # timer" from the moment it separates/lands).
    stationary_seconds: float = 10.0
    proximity_px: float = 120.0
    stationary_tolerance_px: float = 25.0
    ground_y_ratio: float = 0.30
    # Seconds a track can go unseen before its rule-engine state is dropped
    # (bounds memory on long-running / RTSP streams).
    track_ttl_seconds: float = 30.0

    # --- Motion-gated inference ----------------------------------------------
    # Skips YOLO/tracking on frames with no meaningful pixel-level motion, so
    # a static scene doesn't burn CPU/GPU. A frame-diff heuristic, not a
    # learned model -- cheap enough to run every frame.
    motion_gate_enabled: bool = True
    # Per-pixel grayscale intensity delta (0-255) above which a pixel counts
    # as "changed" between consecutive frames.
    motion_pixel_threshold: int = 25
    # Fraction of frame pixels that must have changed for the frame to count
    # as "motion" and trigger a full detection pass.
    motion_area_ratio: float = 0.02
    # Even with zero motion, force a detection pass at least this often so a
    # slow/subtle change (or a missed motion event) can't stall the rule
    # engine's timers indefinitely.
    motion_gate_heartbeat_seconds: float = 1.0

    # --- Recorder -----------------------------------------------------------
    # 12-second rolling-buffer clip: 2s before the event, 10s after.
    pre_event_seconds: float = 2.0
    post_event_seconds: float = 10.0
    events_dir: str = "events"
    # FourCC codec for clip output. "mp4v" always works with stock OpenCV
    # wheels; "avc1" (H264) is smaller/faster to decode but needs an OpenCV
    # build with H264 support.
    video_codec: str = "mp4v"

    # --- Live WebSocket processing --------------------------------------------
    # Run detection/tracking on every Nth frame; frames in between reuse the
    # last result. 1 = no skipping. Raise this to trade detection latency for
    # throughput on slow (CPU) hardware.
    ws_detect_every_n_frames: int = 1

    # --- Face identification -------------------------------------------------
    # Matches the person who dropped an item against an enrolled roster
    # (see /people). Uses OpenCV's built-in YuNet detector + SFace
    # recognizer -- no extra ML dependency, just two small ONNX files that
    # auto-download into face_models_dir on first use (same pattern as the
    # YOLO weights).
    face_models_dir: str = "models"
    # SFace's published cosine-similarity threshold at FAR=0.001; higher =
    # stricter match. See github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface.
    face_match_threshold: float = 0.363
    people_dir: str = "people"

    # --- Database -----------------------------------------------------------
    database_url: str = "sqlite:///./smart_litter.db"

    # --- API ----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Logging ------------------------------------------------------------
    log_level: str = "INFO"

    # --- Auth -----------------------------------------------------------------
    # Single-admin JWT auth (no user table -- this is an MVP, not multi-tenant).
    # Generate a hash with: python main.py hash-password <password>
    admin_username: str = "admin"
    admin_password_hash: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # Short-lived: safe to keep tight since the refresh token below renews it
    # without another login.
    jwt_expire_minutes: int = 30
    # Long-lived: exchanged at /auth/refresh for a new access token. Default
    # 7 days.
    jwt_refresh_expire_minutes: int = 10_080


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()


# Convenience module-level singleton for simple imports.
settings = get_settings()
