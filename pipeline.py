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
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import cv2
import numpy as np

from config import settings
from database import database
from detector.detector import Detector
from detector.motion_gate import MotionGate
from detector.rule_engine import RuleEngine, Violation
from detector.tracker import Tracker
from detector.types import ObjectClass, TrackedObject
from camera.video_reader import VideoReader
from face.face_id import FaceIdentifier, embedding_from_json, embedding_to_json
from logging_utils import get_logger
from recorder.recorder import ClipResult, Recorder

logger = get_logger(__name__)


class OwnerIdentification(NamedTuple):
    """Everything learned about a violation's owner at trigger time."""

    person_id: Optional[int]
    person_name: Optional[str]
    similarity: Optional[float]
    # Tight crop around the detected face (not the whole person box), saved
    # as evidence regardless of whether it matched anyone on the roster.
    face_crop: Optional[np.ndarray]
    face_embedding_json: Optional[str]


_NO_MATCH = OwnerIdentification(None, None, None, None, None)


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
        # Best (largest-area) crop seen so far for each tracked person, used
        # to grab a face for the owner of a trash object at the moment a
        # violation fires -- larger usually means more frontal/higher-res.
        self._person_crops: Dict[int, Tuple[float, np.ndarray]] = {}
        self._person_last_seen: Dict[int, float] = {}
        # Face match looked up at trigger time, consumed when the clip for
        # that trash object's track id finishes and is stored.
        self._face_matches: Dict[int, OwnerIdentification] = {}

    def run(self) -> int:
        """Process the entire source, storing any violations found.

        Returns:
            The number of violation events recorded.
        """
        database.init_db()
        self._load_roster()
        tracker = Tracker(self._detector)
        motion_gate = MotionGate() if settings.motion_gate_enabled else None
        events_recorded = 0
        tracked: List[TrackedObject] = []

        with VideoReader(self.source) as reader:
            rule_engine = RuleEngine(frame_height=reader.height, frame_width=reader.width)
            for zone in database.list_bin_zones():
                rule_engine.add_bin_zone(zone.id, zone.x1, zone.y1, zone.x2, zone.y2)
            recorder = Recorder(
                fps=reader.fps, frame_size=(reader.width, reader.height)
            )

            for frame in reader.frames():
                # 1) motion gate: skip the expensive detect+track pass on
                # frames with no meaningful change (heartbeat still forces
                # one periodically so the rule engine's timers can't stall).
                run_detect = motion_gate is None or motion_gate.should_detect(
                    frame.timestamp, frame.image
                )
                violations: List[Violation] = []
                if run_detect:
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

        if motion_gate is not None and motion_gate.frames_seen:
            logger.info(
                "Motion gate skipped %d/%d frames (%.0f%%)",
                motion_gate.frames_gated,
                motion_gate.frames_seen,
                motion_gate.skip_ratio * 100,
            )
        logger.info("Pipeline finished: %d event(s) recorded", events_recorded)
        return events_recorded

    def _store(self, result: ClipResult) -> None:
        """Persist a completed clip as a DB event."""
        owner = self._face_matches.pop(result.violation.track_id, _NO_MATCH)

        face_crop_path: Optional[str] = None
        if owner.face_crop is not None and owner.face_crop.size:
            stem = Path(result.video_path).stem
            face_crop_path = str(Path(settings.events_dir) / f"{stem}_face.jpg")
            cv2.imwrite(face_crop_path, owner.face_crop)

        database.create_event(
            camera_id=self.camera_id,
            confidence=result.violation.confidence,
            object_type=result.violation.object_type.value,
            video_path=result.video_path,
            preview_image=result.preview_image,
            timestamp=datetime.now(timezone.utc),
            person_id=owner.person_id,
            person_name=owner.person_name,
            face_similarity=owner.similarity,
            object_crop_path=result.object_crop,
            face_crop_path=face_crop_path,
            face_embedding=owner.face_embedding_json,
            camera_lat=settings.camera_lat,
            camera_lon=settings.camera_lon,
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
        """Cache each visible person's best (largest-area) crop so far.

        Largest-area is a cheap proxy for "most frontal / highest-res" --
        the spec's "Best Resolution Crop" -- without running face detection
        on every frame just to score candidates.
        """
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
            self._person_last_seen[obj.track_id] = timestamp
            area = (x2 - x1) * (y2 - y1)
            best = self._person_crops.get(obj.track_id)
            if best is None or area > best[0]:
                self._person_crops[obj.track_id] = (area, image[y1:y2, x1:x2].copy())

        stale = [
            track_id
            for track_id, last_seen in self._person_last_seen.items()
            if timestamp - last_seen > settings.track_ttl_seconds
        ]
        for track_id in stale:
            self._person_crops.pop(track_id, None)
            self._person_last_seen.pop(track_id, None)

    def _identify_owner(self, violation: Violation) -> OwnerIdentification:
        """Match the violation's owning person against the enrolled roster.

        Also returns a tight face crop + embedding whenever a face is found,
        even without a roster match -- evidence for the event regardless of
        whether the violator happens to be enrolled.
        """
        if violation.owner_track_id is None or not self._roster:
            return _NO_MATCH
        cached = self._person_crops.get(violation.owner_track_id)
        if cached is None:
            return _NO_MATCH
        _area, crop = cached

        if self._face_identifier is None:
            self._face_identifier = FaceIdentifier()
        detected = self._face_identifier.detect_and_embed(crop)
        if detected is None:
            return _NO_MATCH
        embedding, (fx, fy, fw, fh) = detected

        ch, cw = crop.shape[:2]
        fx, fy = max(0, fx), max(0, fy)
        fx2, fy2 = min(cw, fx + fw), min(ch, fy + fh)
        face_crop = crop[fy:fy2, fx:fx2].copy() if fx2 > fx and fy2 > fy else None

        embedding_json = embedding_to_json(embedding)
        match = self._face_identifier.best_match(embedding, self._roster)
        if match is None:
            return OwnerIdentification(None, None, None, face_crop, embedding_json)
        person_id, name, similarity = match
        return OwnerIdentification(person_id, name, similarity, face_crop, embedding_json)
