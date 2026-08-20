"""Multi-object tracker built on ByteTrack.

Ultralytics ships ByteTrack; we drive it through ``model.track(persist=True)``
so each object keeps a stable ``track_id`` across frames. The tracker reuses
the ``Detector``'s already-loaded model to avoid double memory cost, and
returns rich ``TrackedObject`` instances (with centroid history) that the rule
engine consumes.

Track history is capped so memory stays bounded on long-running streams.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

import numpy as np

from detector.detector import Detector
from detector.types import ObjectClass, TrackedObject
from logging_utils import get_logger

logger = get_logger(__name__)

# How many past centroids to keep per track (enough for motion analysis).
_MAX_HISTORY = 150

# Drop a track's history once it has gone unseen for this many consecutive
# frames -- otherwise ``_history`` grows without bound as ByteTrack hands out
# new ids over a long-running / RTSP stream.
_MAX_MISSING_FRAMES = 150


class Tracker:
    """Wraps ByteTrack, yielding tracked objects per frame."""

    def __init__(self, detector: Detector) -> None:
        self._detector = detector
        # Persistent per-track centroid history keyed by track id.
        self._history: Dict[int, Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=_MAX_HISTORY)
        )
        # Consecutive frames each known track has gone unseen.
        self._missing: Dict[int, int] = defaultdict(int)

    def update(self, image: np.ndarray) -> List[TrackedObject]:
        """Detect + track objects in one frame.

        Args:
            image: BGR frame.

        Returns:
            Tracked objects (MVP classes only) present in this frame, each
            carrying its centroid history.
        """
        results = self._detector.model.track(
            image,
            persist=True,          # keep tracker state between calls
            tracker="bytetrack.yaml",
            conf=self._detector.conf_threshold,
            device=self._detector.device,
            imgsz=self._detector.imgsz,
            verbose=False,
        )

        tracked: List[TrackedObject] = []
        seen_ids: set[int] = set()

        for result in results:
            if result.boxes is None or result.boxes.id is None:
                continue  # no tracks this frame
            names = result.names
            for box in result.boxes:
                if box.id is None:
                    continue
                coco_name = names.get(int(box.cls.item()), "")
                mapped: ObjectClass | None = Detector.map_class(coco_name)
                if mapped is None:
                    continue

                track_id = int(box.id.item())
                seen_ids.add(track_id)
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                self._history[track_id].append((cx, cy))

                tracked.append(
                    TrackedObject(
                        track_id=track_id,
                        cls=mapped,
                        confidence=float(box.conf.item()),
                        bbox=(x1, y1, x2, y2),
                        history=list(self._history[track_id]),
                    )
                )

        self._prune_missing(seen_ids)
        return tracked

    def _prune_missing(self, seen_ids: set[int]) -> None:
        """Drop history for tracks unseen too long; reset the counter for the rest."""
        for track_id in list(self._history.keys()):
            if track_id in seen_ids:
                self._missing[track_id] = 0
                continue
            self._missing[track_id] += 1
            if self._missing[track_id] > _MAX_MISSING_FRAMES:
                del self._history[track_id]
                del self._missing[track_id]
