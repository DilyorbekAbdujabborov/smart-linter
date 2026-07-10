"""Detection pipeline orchestrator.

Wires the components together in the documented order:

    VideoReader -> Detector+Tracker (ByteTrack) -> RuleEngine
                -> Recorder -> Database

Each stage is injected, so any single piece can be swapped (e.g. a GPU
detector, a Redis-backed recorder) without touching the others -- this is the
main extension seam of the system.
"""

from __future__ import annotations

from datetime import datetime, timezone

from config import settings
from database import database
from detector.detector import Detector
from detector.rule_engine import RuleEngine
from detector.tracker import Tracker
from camera.video_reader import VideoReader
from logging_utils import get_logger
from recorder.recorder import ClipResult, Recorder

logger = get_logger(__name__)


class Pipeline:
    """End-to-end litter-detection pipeline over a single video source."""

    def __init__(self, source: str | None = None, camera_id: str | None = None) -> None:
        self.source = source or settings.video_source
        self.camera_id = camera_id or settings.camera_id
        self._detector = Detector()

    def run(self) -> int:
        """Process the entire source, storing any violations found.

        Returns:
            The number of violation events recorded.
        """
        database.init_db()
        tracker = Tracker(self._detector)
        events_recorded = 0

        with VideoReader(self.source) as reader:
            rule_engine = RuleEngine(frame_height=reader.height)
            recorder = Recorder(
                fps=reader.fps, frame_size=(reader.width, reader.height)
            )

            for frame in reader.frames():
                # 1) detect + track
                tracked = tracker.update(frame.image)
                # 2) evaluate rules
                violations = rule_engine.process(frame.timestamp, tracked)
                # 3) keep rolling buffer fed; collect completed clips
                completed = recorder.feed(frame.timestamp, frame.image)
                # 4) start recording new violations
                for v in violations:
                    recorder.trigger(v, preview_frame=frame.image)
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
        database.create_event(
            camera_id=self.camera_id,
            confidence=result.violation.confidence,
            object_type=result.violation.object_type.value,
            video_path=result.video_path,
            preview_image=result.preview_image,
            timestamp=datetime.now(timezone.utc),
        )
