"""Face detection + recognition wrapper around OpenCV's YuNet/SFace models.

Both models ship as small ONNX files in the `opencv_zoo` repo (Apache-2.0)
and are supported natively by ``cv2.FaceDetectorYN``/``cv2.FaceRecognizerSF``
-- no extra ML dependency beyond the ``opencv-python`` this project already
requires. Weights auto-download into ``settings.face_models_dir`` on first
use, mirroring how the YOLO weights already auto-download.

Used to answer one question: "does this face match an enrolled Person?" --
not to identify strangers or build a general face database.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import settings
from logging_utils import get_logger

logger = get_logger(__name__)

_DETECTOR_FILENAME = "face_detection_yunet_2023mar.onnx"
_RECOGNIZER_FILENAME = "face_recognition_sface_2021dec.onnx"
_ZOO_BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
_DETECTOR_URL = f"{_ZOO_BASE}/face_detection_yunet/{_DETECTOR_FILENAME}"
_RECOGNIZER_URL = f"{_ZOO_BASE}/face_recognition_sface/{_RECOGNIZER_FILENAME}"


def _ensure_model(filename: str, url: str) -> Path:
    """Return the local path to ``filename``, downloading it if missing."""
    models_dir = Path(settings.face_models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / filename
    if path.exists():
        return path
    logger.info("Downloading face model %s ...", filename)
    request = urllib.request.Request(url, headers={"User-Agent": "smart-litter/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        path.write_bytes(response.read())
    logger.info("Saved %s (%d bytes)", path, path.stat().st_size)
    return path


def embedding_to_json(embedding: np.ndarray) -> str:
    """Serialize a face embedding for storage in ``Person.embedding``."""
    return json.dumps(embedding.flatten().tolist())


def embedding_from_json(data: str) -> np.ndarray:
    """Deserialize a face embedding stored via :func:`embedding_to_json`."""
    return np.array(json.loads(data), dtype=np.float32).reshape(1, -1)


class FaceIdentifier:
    """Detects the primary face in an image and compares it to a roster."""

    def __init__(self) -> None:
        detector_path = _ensure_model(_DETECTOR_FILENAME, _DETECTOR_URL)
        recognizer_path = _ensure_model(_RECOGNIZER_FILENAME, _RECOGNIZER_URL)
        # Input size is set per-call in `detect_and_embed` (must match the
        # actual image); (0, 0) here is just a placeholder.
        self._detector = cv2.FaceDetectorYN_create(str(detector_path), "", (0, 0))
        self._recognizer = cv2.FaceRecognizerSF_create(str(recognizer_path), "")

    def detect_and_embed(
        self, image: np.ndarray
    ) -> Optional[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
        """Detect the highest-confidence face and return (embedding, bbox).

        Returns ``None`` if no face is found. ``bbox`` is ``(x, y, w, h)`` in
        the input image's pixel coordinates.
        """
        if image.size == 0:
            return None
        h, w = image.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(image)
        if faces is None or len(faces) == 0:
            return None

        # Column layout: [x, y, w, h, <5 landmark pairs>, score]. Pick the
        # most confident detection.
        best = faces[np.argmax(faces[:, -1])]
        aligned = self._recognizer.alignCrop(image, best)
        feature = self._recognizer.feature(aligned)
        bbox = tuple(int(v) for v in best[:4])
        return feature, bbox

    def compare(self, feature_a: np.ndarray, feature_b: np.ndarray) -> float:
        """Cosine similarity between two embeddings (higher = more alike)."""
        return float(
            self._recognizer.match(feature_a, feature_b, cv2.FaceRecognizerSF_FR_COSINE)
        )

    def best_match(
        self, feature: np.ndarray, roster: List[Tuple[int, str, np.ndarray]]
    ) -> Optional[Tuple[int, str, float]]:
        """Return (person_id, name, similarity) for the best roster match
        above ``settings.face_match_threshold``, or ``None``.
        """
        best: Optional[Tuple[int, str, float]] = None
        for person_id, name, candidate in roster:
            similarity = self.compare(feature, candidate)
            if similarity >= settings.face_match_threshold and (
                best is None or similarity > best[2]
            ):
                best = (person_id, name, similarity)
        return best
