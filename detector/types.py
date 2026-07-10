"""Shared domain types for the detection pipeline.

Keeping these dataclasses in one small module (with no heavy imports) lets
every layer -- detector, tracker, rule engine, recorder -- speak the same
vocabulary without circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


class ObjectClass(str, Enum):
    """The only object classes this MVP cares about.

    Values map onto COCO class names produced by the stock YOLO11 model, so
    no custom training is required to run. Adding a custom-trained model later
    just means extending this enum and the mapping in ``detector.py``.
    """

    PERSON = "person"
    BOTTLE = "bottle"          # plastic bottle
    PAPER = "paper"            # approximated by COCO "book" (see detector.py)
    TRASH_BIN = "trash_bin"    # approximated by COCO "toilet"/custom later

    @property
    def is_trash(self) -> bool:
        """True for classes that count as discardable litter."""
        return self in (ObjectClass.BOTTLE, ObjectClass.PAPER)


# Bounding box in pixel coords: (x1, y1, x2, y2).
BBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    """A single YOLO detection within one frame."""

    cls: ObjectClass
    confidence: float
    bbox: BBox

    @property
    def center(self) -> Tuple[float, float]:
        """Pixel centroid of the box."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def bottom_center(self) -> Tuple[float, float]:
        """Bottom-center point -- a decent proxy for where an object rests."""
        x1, _y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, y2)


@dataclass
class TrackedObject:
    """A detection enriched with a persistent track id from ByteTrack."""

    track_id: int
    cls: ObjectClass
    confidence: float
    bbox: BBox
    # History of centroids across frames, used by the rule engine for motion.
    history: list[Tuple[float, float]] = field(default_factory=list)

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def bottom_center(self) -> Tuple[float, float]:
        x1, _y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, y2)
