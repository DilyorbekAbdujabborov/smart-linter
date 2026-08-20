"""Frame-diff motion gate.

Cheap pixel-level motion check used to decide whether a frame is worth
running full YOLO detection/tracking on. A static scene (empty street,
parked frame) burns no inference time; a full detection pass still runs
periodically (``motion_gate_heartbeat_seconds``) so subtle motion under the
threshold, or a scene that never moves, can't stall the rule engine's
stationary/proximity timers indefinitely.

Deliberately not a learned model or background subtractor: consecutive-frame
grayscale differencing is enough to gate "is anything happening here" and
costs a fraction of a millisecond per frame.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from config import settings
from logging_utils import get_logger

logger = get_logger(__name__)


class MotionGate:
    """Decides per-frame whether to run full detection."""

    def __init__(self) -> None:
        self._prev_gray: Optional[np.ndarray] = None
        self._pixel_threshold = settings.motion_pixel_threshold
        self._area_ratio = settings.motion_area_ratio
        self._heartbeat_seconds = settings.motion_gate_heartbeat_seconds
        self._last_detect_at: Optional[float] = None
        self.frames_seen = 0
        self.frames_gated = 0

    def should_detect(self, timestamp: float, image: np.ndarray) -> bool:
        """Return True if this frame should get a full detection pass.

        Args:
            timestamp: Seconds into the stream for this frame.
            image: BGR frame.
        """
        self.frames_seen += 1
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        moved = self._prev_gray is None or self._has_motion(gray)
        self._prev_gray = gray

        heartbeat_due = (
            self._last_detect_at is None
            or (timestamp - self._last_detect_at) >= self._heartbeat_seconds
        )

        run = moved or heartbeat_due
        if run:
            self._last_detect_at = timestamp
        else:
            self.frames_gated += 1
        return run

    def _has_motion(self, gray: np.ndarray) -> bool:
        diff = cv2.absdiff(self._prev_gray, gray)
        changed = int(np.count_nonzero(diff > self._pixel_threshold))
        return (changed / diff.size) >= self._area_ratio

    @property
    def skip_ratio(self) -> float:
        """Fraction of frames skipped so far (0-1)."""
        return self.frames_gated / self.frames_seen if self.frames_seen else 0.0
