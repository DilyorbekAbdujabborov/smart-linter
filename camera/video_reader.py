"""Video / RTSP frame source.

``VideoReader`` wraps ``cv2.VideoCapture`` behind a small, iterable interface.
It works identically for an MP4 file and an RTSP CCTV stream -- the caller
does not care which. This is the single seam through which frames enter the
system, so multi-camera support later means instantiating one reader per
camera (each in its own worker), not rewriting the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import cv2
import numpy as np

from logging_utils import get_logger

logger = get_logger(__name__)


class VideoSourceError(RuntimeError):
    """Raised when the video source cannot be opened or read."""


@dataclass(frozen=True)
class Frame:
    """A single decoded frame plus its metadata.

    Attributes:
        index: Monotonic frame counter starting at 0.
        timestamp: Seconds since stream start (derived from FPS).
        image: BGR ``np.ndarray`` as produced by OpenCV.
    """

    index: int
    timestamp: float
    image: np.ndarray


class VideoReader:
    """Iterable wrapper over an OpenCV capture (file or RTSP)."""

    def __init__(self, source: str) -> None:
        """Open the given source.

        Args:
            source: Path to an MP4 file or an ``rtsp://`` URL.

        Raises:
            VideoSourceError: If the source cannot be opened.
        """
        self.source = source
        # A bare number ("0", "1", ...) means a local webcam device index;
        # OpenCV needs a real int for that, not the string. Anything else
        # (file path, rtsp:// URL) is passed through untouched.
        cap_source: str | int = int(source) if str(source).isdigit() else source
        self._cap = cv2.VideoCapture(cap_source)
        if not self._cap.isOpened():
            raise VideoSourceError(f"Cannot open video source: {source!r}")

        # FPS is needed to translate frame index -> wall-clock seconds. Some
        # RTSP streams report 0/NaN; fall back to a sensible default.
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps: float = fps if fps and fps > 0 else 25.0
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(
            "Opened source %s (%dx%d @ %.1f fps)",
            source,
            self.width,
            self.height,
            self.fps,
        )

    def frames(self) -> Iterator[Frame]:
        """Yield frames until the stream ends or errors.

        For a file this stops at EOF. For RTSP it stops when the connection
        drops; reconnection strategy is intentionally left to the caller so
        it can be made robust (backoff, alerting) without touching this class.
        """
        index = 0
        while True:
            ok, image = self._cap.read()
            if not ok:
                logger.info("Stream ended after %d frames", index)
                break
            yield Frame(index=index, timestamp=index / self.fps, image=image)
            index += 1

    def release(self) -> None:
        """Release the underlying capture handle."""
        if self._cap is not None:
            self._cap.release()
            logger.debug("Released source %s", self.source)

    def __enter__(self) -> "VideoReader":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
