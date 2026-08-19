"""Detection pipeline orchestrator.

Wires the components together in the documented order:

    VideoReader -> Detector+Tracker (ByteTrack) -> RuleEngine
                -> Recorder -> Database

Each stage is injected, so any single piece can be swapped (e.g. a GPU
detector, a Redis-backed recorder) without touching the others -- this is the
main extension seam of the system.

Face identification (matching the person who dropped an item against the
enrolled ``Person`` roster) also lives here rather than in ``RuleEngine``:
the rule engine is deliberately kept pure/frame-free, while this is the one
place that already has both a track id (from ``RuleEngine``) and the raw
video frame needed to crop a face out of it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import settings
from database import database
from detector.detector import Detector
from detector.rule_engine import RuleEngine, Violation
from detector.tracker import Tracker
from detector.types import ObjectClass, TrackedObject
from camera.video_reader import VideoReader
from face.face_id import FaceIdentifier, embedding_from_json
from logging_utils import get_logger
from recorder.recorder import ClipResult, Recorder

logger = get_logger(__name__)

# (person_id, name, similarity) for a face match, or all-None for no match.
FaceMatch = Tuple[Optional[int], Optional[str], Optional[float]]
_NO_MATCH: FaceMatch = (None, None, None)


class Pipeline:
    """End-to-end litter-detection pipeline over a single video source."""

    def __init__(self, source: str | None = None, camera_id: str | None = None) -> None:
        self.source = source or settings.video_source
        self.camera_id = camera_id or settings.camera_id
        self._detector = Detector()

        # Face identification is opt-in at zero cost: if nobody is enrolled,
        # the roster is empty and none of the crop/detect/match work below
        # ever runs.
        self._face_identifier: Optional[FaceIdentifier] = None
        self._roster: List[Tuple[int, str, np.ndarray]] = []
        # Latest crop seen for each tracked person, used to grab a face for
        # the owner of a trash object at the moment a violation fires.
        self._person_crops: Dict[int, Tuple[float, np.ndarray]] = {}
        # Face match looked up at trigger time, consumed when the clip for
        # that trash object's track id finishes and is stored.
        self._face_matches: Dict[int, FaceMatch] = {}

    def run(self) -> int:
        """Process the entire source, storing any violations found.

        Returns:
            The number of violation events recorded.
        """
        database.init_db()
        self._load_roster()
        tracker = Tracker(self._detector)
        events_recorded = 0

        with VideoReader(self.source) as reader:
            rule_engine = RuleEngine(frame_height=reader.height, frame_width=reader.width)
            for zone in database.list_bin_zones():
                rule_engine.add_bin_zone(zone.id, zone.x1, zone.y1, zone.x2, zone.y2)
            recorder = Recorder(
                fps=reader.fps, frame_size=(reader.width, reader.height)
            )

            for frame in reader.frames():
                # 1) detect + track
                tracked = tracker.update(frame.image)
                self._update_person_crops(frame.timestamp, frame.image, tracked)
                # 2) evaluate rules
                violations = rule_engine.process(frame.timestamp, tracked)
                # 3) keep rolling buffer fed; collect completed clips
                completed = recorder.feed(frame.timestamp, frame.image)
                # 4) start recording new violations
                for v in violations:
                    recorder.trigger(v, preview_frame=frame.image)
                    self._face_matches[v.track_id] = self._identify_owner(v)
                # 5) persist any clip that finished this frame
                for result in completed:
                    self._store(result)
                    events_recorded += 1

            # Flush clips still gathering post-frames at stream end.
            for result in recorder.flush_pending():
                self._store(result)
                events_recorded += 1

        logger.info("Pipeline finished: %d event(s) recorded", events_recorded)
        return events_recorded

    def _store(self, result: ClipResult) -> None:
        """Persist a completed clip as a DB event."""
        person_id, person_name, similarity = self._face_matches.pop(
            result.violation.track_id, _NO_MATCH
        )
        database.create_event(
            camera_id=self.camera_id,
            confidence=result.violation.confidence,
            object_type=result.violation.object_type.value,
            video_path=result.video_path,
            preview_image=result.preview_image,
            timestamp=datetime.now(timezone.utc),
            person_id=person_id,
            person_name=person_name,
            face_similarity=similarity,
        )

    # -- face identification --------------------------------------------------

    def _load_roster(self) -> None:
        """Load enrolled people's embeddings once per run."""
        people = database.list_people()
        self._roster = [
            (p.id, p.name, embedding_from_json(p.embedding)) for p in people
        ]
        if self._roster:
            logger.info("Face matching enabled: %d enrolled people", len(self._roster))

    def _update_person_crops(
        self, timestamp: float, image: np.ndarray, tracked: List[TrackedObject]
    ) -> None:
        """Cache each visible person's latest bbox crop for later face lookup."""
        if not self._roster:
            return  # nobody enrolled -- skip the bookkeeping entirely
        h, w = image.shape[:2]
        for obj in tracked:
            if obj.cls is not ObjectClass.PERSON:
                continue
            x1, y1, x2, y2 = (int(v) for v in obj.bbox)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            self._person_crops[obj.track_id] = (timestamp, image[y1:y2, x1:x2].copy())

        stale = [
            track_id
            for track_id, (last_seen, _crop) in self._person_crops.items()
            if timestamp - last_seen > settings.track_ttl_seconds
        ]
        for track_id in stale:
            del self._person_crops[track_id]

    def _identify_owner(self, violation: Violation) -> FaceMatch:
        """Match the violation's owning person against the enrolled roster."""
        if violation.owner_track_id is None or not self._roster:
            return _NO_MATCH
        cached = self._person_crops.get(violation.owner_track_id)
        if cached is None:
            return _NO_MATCH
        _, crop = cached

        if self._face_identifier is None:
            self._face_identifier = FaceIdentifier()
        detected = self._face_identifier.detect_and_embed(crop)
        if detected is None:
            return _NO_MATCH
        embedding, _bbox = detected
        match = self._face_identifier.best_match(embedding, self._roster)
        return match if match is not None else _NO_MATCH
