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


class Tracker:
    """Wraps ByteTrack, yielding tracked objects per frame."""

    def __init__(self, detector: Detector) -> None:
        self._detector = detector
        # Persistent per-track centroid history keyed by track id.
        self._history: Dict[int, Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=_MAX_HISTORY)
        )

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

        return tracked
