"""Clip recorder.

Turns a ``Violation`` into a 10-second MP4 (5s before + 5s after) plus a
preview JPEG. Recording is streaming-friendly:

  * The pre-event footage comes straight from the :class:`ClipBuffer`.
  * The post-event footage is gathered by continuing to feed live frames to an
    active :class:`_PendingClip` until its post-window is full, at which point
    it flushes to disk.

The main loop simply calls ``feed`` every frame and ``trigger`` on a violation;
the recorder handles the rest. Files are written under ``settings.events_dir``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from config import settings
from detector.rule_engine import Violation
from logging_utils import get_logger
from recorder.clip_buffer import ClipBuffer

logger = get_logger(__name__)


@dataclass
class ClipResult:
    """Paths and metadata produced once a clip is written."""

    video_path: str
    preview_image: str
    violation: Violation


@dataclass
class _PendingClip:
    """A clip in the process of collecting its post-event frames."""

    violation: Violation
    frames: List[Tuple[float, np.ndarray]]
    post_frames_needed: int
    preview: np.ndarray
    post_frames_collected: int = 0

    def is_complete(self) -> bool:
        return self.post_frames_collected >= self.post_frames_needed


class Recorder:
    """Manages the rolling buffer and in-flight clip recordings."""

    def __init__(self, fps: float, frame_size: Tuple[int, int]) -> None:
        """
        Args:
            fps: Source frame rate (used for buffer size + output timing).
            frame_size: ``(width, height)`` of frames.
        """
        self.fps = fps
        self.frame_size = frame_size
        self._buffer = ClipBuffer(fps, settings.pre_event_seconds)
        self._post_needed = max(1, int(round(fps * settings.post_event_seconds)))
        self._pending: List[_PendingClip] = []

        self._events_dir = Path(settings.events_dir)
        self._events_dir.mkdir(parents=True, exist_ok=True)

    def feed(self, timestamp: float, frame: np.ndarray) -> List[ClipResult]:
        """Feed one live frame. Returns any clips that completed this frame.

        Must be called for **every** frame, in order.
        """
        # Always keep the rolling pre-event history current.
        self._buffer.add(timestamp, frame)

        results: List[ClipResult] = []
        still_pending: List[_PendingClip] = []
        for clip in self._pending:
            clip.frames.append((timestamp, frame.copy()))
            clip.post_frames_collected += 1
            if clip.is_complete():
                results.append(self._flush(clip))
            else:
                still_pending.append(clip)
        self._pending = still_pending
        return results

    def trigger(self, violation: Violation, preview_frame: np.ndarray) -> None:
        """Begin recording a clip for a violation.

        Seeds the clip with the buffered pre-event frames; the post-event
        frames accumulate through subsequent ``feed`` calls.
        """
        pre_frames = self._buffer.snapshot()
        logger.info(
            "Recording clip for track %d with %d pre-frames",
            violation.track_id,
            len(pre_frames),
        )
        self._pending.append(
            _PendingClip(
                violation=violation,
                frames=list(pre_frames),
                post_frames_needed=self._post_needed,
                preview=preview_frame.copy(),
            )
        )

    def flush_pending(self) -> List[ClipResult]:
        """Force-write any still-incomplete clips (e.g. at stream end)."""
        results = [self._flush(clip) for clip in self._pending if clip.frames]
        self._pending = []
        return results

    # -- internals ----------------------------------------------------------

    def _flush(self, clip: _PendingClip) -> ClipResult:
        """Write a clip's frames + preview to disk and return the paths."""
        clip_id = uuid.uuid4().hex[:12]
        video_path = self._events_dir / f"event_{clip_id}.mp4"
        preview_path = self._events_dir / f"event_{clip_id}.jpg"

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(video_path), fourcc, self.fps, self.frame_size
        )
        if not writer.isOpened():
            logger.error("Failed to open VideoWriter for %s", video_path)
        for _ts, frame in clip.frames:
            writer.write(frame)
        writer.release()

        cv2.imwrite(str(preview_path), clip.preview)
        logger.info(
            "Wrote clip %s (%d frames) + preview", video_path.name, len(clip.frames)
        )
        return ClipResult(
            video_path=str(video_path),
            preview_image=str(preview_path),
            violation=clip.violation,
        )
