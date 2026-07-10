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
    conf_threshold: float = 0.30

    # --- Rule engine --------------------------------------------------------
    stationary_seconds: float = 5.0
    proximity_px: float = 120.0
    stationary_tolerance_px: float = 25.0
    ground_y_ratio: float = 0.55

    # --- Recorder -----------------------------------------------------------
    pre_event_seconds: float = 5.0
    post_event_seconds: float = 5.0
    events_dir: str = "events"

    # --- Database -----------------------------------------------------------
    database_url: str = "sqlite:///./smart_litter.db"

    # --- API ----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Logging ------------------------------------------------------------
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()


# Convenience module-level singleton for simple imports.
settings = get_settings()
