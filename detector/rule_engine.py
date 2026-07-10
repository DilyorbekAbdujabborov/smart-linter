"""Litter-detection rule engine.

Consumes tracked objects frame-by-frame and decides when a *litter violation*
has occurred. The logic is a small per-object state machine implementing the
six MVP rules:

    R1  person and trash object are close (in-hand / being carried)
    R2  the trash object separates from that person
    R3  the trash object moves toward the ground
    R4  the trash object stays (nearly) stationary for >= N seconds
    R5  the person leaves the object's area (does not pick it back up)
    R6  the trash object is not inside a trash bin

When every rule is satisfied for an object, ``process`` returns a
``Violation``. Thresholds come from ``settings`` so behaviour is tunable
without code changes.

The engine is deliberately pure/decoupled: it knows nothing about video files
or databases. That keeps it unit-testable and lets richer detectors (action
recognition, pose) replace/augment it later behind the same interface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from config import settings
from detector.types import ObjectClass, TrackedObject
from logging_utils import get_logger

logger = get_logger(__name__)


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Euclidean distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_in_box(pt: Tuple[float, float], box: Tuple[float, float, float, float]) -> bool:
    """True if point ``pt`` lies within bbox ``box``."""
    x, y = pt
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


class _Phase(Enum):
    """Lifecycle phase of a tracked trash object."""

    CARRIED = auto()      # currently close to a person (R1)
    RELEASED = auto()     # separated from the person (R2), settling
    ON_GROUND = auto()    # stationary on the ground, timing R4
    REPORTED = auto()     # violation already emitted; ignore further frames


@dataclass
class _ObjectState:
    """Mutable per-track state the engine carries across frames."""

    phase: _Phase
    owner_person_id: Optional[int] = None
    last_position: Optional[Tuple[float, float]] = None
    stationary_since: Optional[float] = None
    released_at: Optional[float] = None


@dataclass(frozen=True)
class Violation:
    """A confirmed litter event, ready to be recorded."""

    track_id: int
    object_type: ObjectClass
    confidence: float
    timestamp: float               # seconds into the stream
    bbox: Tuple[float, float, float, float]


class RuleEngine:
    """Stateful evaluator turning tracked objects into violations."""

    def __init__(self, frame_height: int) -> None:
        """
        Args:
            frame_height: Pixel height of the video, used to derive the
                "ground" line from ``settings.ground_y_ratio``.
        """
        self._frame_height = frame_height
        self._ground_y = frame_height * settings.ground_y_ratio
        self._states: Dict[int, _ObjectState] = {}
        logger.info(
            "RuleEngine ready (ground_y=%.0f, stationary=%.1fs, proximity=%.0fpx)",
            self._ground_y,
            settings.stationary_seconds,
            settings.proximity_px,
        )

    def process(
        self, timestamp: float, tracked: List[TrackedObject]
    ) -> List[Violation]:
        """Evaluate one frame's tracked objects.

        Args:
            timestamp: Seconds since stream start for this frame.
            tracked: All tracked objects in the current frame.

        Returns:
            Any violations confirmed on this frame (usually empty).
        """
        persons = [t for t in tracked if t.cls == ObjectClass.PERSON]
        bins = [t for t in tracked if t.cls == ObjectClass.TRASH_BIN]
        trash = [t for t in tracked if t.cls.is_trash]

        violations: List[Violation] = []
        for obj in trash:
            v = self._evaluate_object(timestamp, obj, persons, bins)
            if v is not None:
                violations.append(v)
        return violations

    # -- internals ----------------------------------------------------------

    def _nearest_person(
        self, obj: TrackedObject, persons: List[TrackedObject]
    ) -> Tuple[Optional[TrackedObject], float]:
        """Return the closest person and the distance, or (None, inf)."""
        best: Optional[TrackedObject] = None
        best_d = math.inf
        for p in persons:
            d = _dist(obj.center, p.center)
            if d < best_d:
                best, best_d = p, d
        return best, best_d

    def _evaluate_object(
        self,
        timestamp: float,
        obj: TrackedObject,
        persons: List[TrackedObject],
        bins: List[TrackedObject],
    ) -> Optional[Violation]:
        """Advance the state machine for a single trash object."""
        state = self._states.get(obj.track_id)
        if state is None:
            state = _ObjectState(phase=_Phase.CARRIED)
            self._states[obj.track_id] = state

        if state.phase is _Phase.REPORTED:
            return None

        nearest_person, person_dist = self._nearest_person(obj, persons)
        near_person = person_dist <= settings.proximity_px

        # R6: object inside a bin -> never a violation; reset its state.
        if any(_point_in_box(obj.bottom_center, b.bbox) for b in bins):
            self._states[obj.track_id] = _ObjectState(phase=_Phase.CARRIED)
            return None

        # --- Phase: CARRIED ------------------------------------------------
        if state.phase is _Phase.CARRIED:
            if near_person and nearest_person is not None:
                # R1 satisfied: remember who is holding it.
                state.owner_person_id = nearest_person.track_id
            elif state.owner_person_id is not None:
                # R2: object separated from the person who held it.
                state.phase = _Phase.RELEASED
                state.released_at = timestamp
                logger.debug(
                    "Track %d released by person %d @ %.1fs",
                    obj.track_id,
                    state.owner_person_id,
                    timestamp,
                )
            state.last_position = obj.center
            return None

        # --- Phase: RELEASED (settling toward ground) ----------------------
        if state.phase is _Phase.RELEASED:
            # If the person picked it back up, cancel.
            if near_person:
                self._states[obj.track_id] = _ObjectState(
                    phase=_Phase.CARRIED,
                    owner_person_id=nearest_person.track_id if nearest_person else None,
                )
                return None

            # R3: object is at/below the ground line.
            _, oy = obj.bottom_center
            if oy >= self._ground_y:
                state.phase = _Phase.ON_GROUND
                state.stationary_since = timestamp
                state.last_position = obj.center
            return None

        # --- Phase: ON_GROUND (timing stationarity + person exit) ----------
        if state.phase is _Phase.ON_GROUND:
            # If picked back up, cancel the whole event.
            if near_person:
                self._states[obj.track_id] = _ObjectState(
                    phase=_Phase.CARRIED,
                    owner_person_id=nearest_person.track_id if nearest_person else None,
                )
                return None

            moved = (
                _dist(obj.center, state.last_position)
                if state.last_position is not None
                else 0.0
            )
            # R4: reset the stationary timer if the object drifted too far.
            if moved > settings.stationary_tolerance_px:
                state.stationary_since = timestamp
                state.last_position = obj.center
                return None

            stationary_for = timestamp - (state.stationary_since or timestamp)

            # R5: person must have left the object's vicinity.
            person_left = person_dist > settings.proximity_px

            if stationary_for >= settings.stationary_seconds and person_left:
                state.phase = _Phase.REPORTED
                logger.info(
                    "VIOLATION: track %d (%s) littered, still %.1fs @ %.1fs",
                    obj.track_id,
                    obj.cls.value,
                    stationary_for,
                    timestamp,
                )
                return Violation(
                    track_id=obj.track_id,
                    object_type=obj.cls,
                    confidence=obj.confidence,
                    timestamp=timestamp,
                    bbox=obj.bbox,
                )
            return None

        return None
