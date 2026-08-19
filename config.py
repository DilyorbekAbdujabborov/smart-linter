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

    # --- Model --------------------------------------------------------------
    yolo_model: str = "yolo11n.pt"
    device: str = "cpu"
    conf_threshold: float = 0.15

    # --- Rule engine --------------------------------------------------------
    stationary_seconds: float = 2.0
    proximity_px: float = 120.0
    stationary_tolerance_px: float = 25.0
    ground_y_ratio: float = 0.30
    # Seconds a track can go unseen before its rule-engine state is dropped
    # (bounds memory on long-running / RTSP streams).
    track_ttl_seconds: float = 30.0

    # --- Recorder -----------------------------------------------------------
    pre_event_seconds: float = 5.0
    post_event_seconds: float = 5.0
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
    jwt_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()


# Convenience module-level singleton for simple imports.
settings = get_settings()
