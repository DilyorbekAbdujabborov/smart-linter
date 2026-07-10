"""Rolling pre-event frame buffer.

A fixed-size ring buffer (``collections.deque``) that always holds the most
recent N seconds of frames. When a violation fires we already have the "before"
footage in hand -- no need to have been writing to disk speculatively.

Memory is bounded by construction: ``maxlen = fps * seconds``.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Tuple

import numpy as np


class ClipBuffer:
    """Ring buffer of ``(timestamp, frame)`` for the last N seconds."""

    def __init__(self, fps: float, seconds: float) -> None:
        """
        Args:
            fps: Frames per second of the source (sets buffer capacity).
            seconds: How many seconds of history to retain.
        """
        self.fps = fps
        self.seconds = seconds
        self._capacity = max(1, int(round(fps * seconds)))
        self._buf: Deque[Tuple[float, np.ndarray]] = deque(maxlen=self._capacity)

    def add(self, timestamp: float, frame: np.ndarray) -> None:
        """Append a frame; oldest is dropped once at capacity."""
        # Store a copy so later in-place drawing on the live frame cannot
        # corrupt already-buffered history.
        self._buf.append((timestamp, frame.copy()))

    def snapshot(self) -> List[Tuple[float, np.ndarray]]:
        """Return the current buffered frames, oldest first."""
        return list(self._buf)

    def __len__(self) -> int:
        return len(self._buf)
