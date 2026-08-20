"""YOLO11 object detector.

Thin adapter around Ultralytics YOLO that: runs inference on a BGR frame,
filters to the classes this MVP cares about, and returns clean ``Detection``
objects. The rest of the system never imports ultralytics directly, so
swapping in a custom-trained model or GPU batching later is a one-file change.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from ultralytics import YOLO

from config import settings
from detector.types import Detection, ObjectClass
from logging_utils import get_logger

logger = get_logger(__name__)


# Map stock COCO class names -> our MVP object classes.
#
# The stock YOLO11 model has no "paper" or "trash bin" class, so we approximate:
#   - "book" is the closest flat-paper-like COCO class.
# When a custom-trained model is dropped in later, just extend this mapping.
_COCO_TO_CLASS: Dict[str, ObjectClass] = {
    "person": ObjectClass.PERSON,
    # BOTTLE group
    "bottle": ObjectClass.BOTTLE,
    "cup": ObjectClass.BOTTLE,
    "wine glass": ObjectClass.BOTTLE,
    "bowl": ObjectClass.BOTTLE,
    # PAPER group
    "book": ObjectClass.PAPER,
    "tie": ObjectClass.PAPER,
    "box": ObjectClass.PAPER,
    # HANDBAG group
    "handbag": ObjectClass.HANDBAG,
    "umbrella": ObjectClass.HANDBAG,
    # BACKPACK group
    "backpack": ObjectClass.BACKPACK,
    "suitcase": ObjectClass.BACKPACK,
    # TRASH_BIN (reference class, never itself a trash item)
    "toilet": ObjectClass.TRASH_BIN,
}


class Detector:
    """Runs YOLO11 inference and emits filtered ``Detection`` objects."""

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        conf_threshold: float | None = None,
    ) -> None:
        self.model_path = model_path or settings.yolo_model
        self.device = device or settings.device
        self.conf_threshold = (
            conf_threshold if conf_threshold is not None else settings.conf_threshold
        )
        self.imgsz = settings.imgsz
        # Set torch threads for maximum CPU utilization. Default 0 = auto.
        if settings.torch_num_threads > 0:
            try:
                import torch
                torch.set_num_threads(settings.torch_num_threads)
            except Exception:
                pass
        logger.info("Loading YOLO model %s on %s (imgsz=%d)", self.model_path, self.device, self.imgsz)
        self._model = YOLO(self.model_path)
        # Cache id->name so we avoid dict lookups per detection.
        self._names: Dict[int, str] = self._model.names

    @property
    def model(self) -> YOLO:
        """Underlying Ultralytics model.

        Exposed so the tracker can reuse the same loaded weights (and its
        internal tracking state) instead of loading the model twice.
        """
        return self._model

    @property
    def names(self) -> Dict[int, str]:
        """COCO id -> class-name mapping from the loaded model."""
        return self._names

    @staticmethod
    def map_class(coco_name: str) -> ObjectClass | None:
        """Map a raw COCO class name to an MVP ``ObjectClass`` (or None)."""
        return _COCO_TO_CLASS.get(coco_name)

    def detect(self, image: np.ndarray) -> List[Detection]:
        """Run detection on a single BGR frame.

        Args:
            image: BGR image as an ``np.ndarray``.

        Returns:
            Detections restricted to the MVP's object classes.
        """
        results = self._model.predict(
            image,
            conf=self.conf_threshold,
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )
        detections: List[Detection] = []
        # ``predict`` returns a list (one per image); we pass one image.
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls.item())
                name = self._names.get(cls_id, "")
                mapped = _COCO_TO_CLASS.get(name)
                if mapped is None:
                    continue  # ignore everything outside the MVP scope
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    Detection(
                        cls=mapped,
                        confidence=float(box.conf.item()),
                        bbox=(x1, y1, x2, y2),
                    )
                )
        return detections
