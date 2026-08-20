"""Hardware capability detection for auto-tuning inference settings.

Detection runs lazily -- only when :class:`~detector.detector.Detector` is
instantiated, never at import time -- so ``python main.py serve`` stays
lightweight until detection actually starts, matching the project's existing
pattern of loading heavy dependencies (torch/ultralytics, face models) on
first use rather than at process startup.

By design, detected hardware capability always overrides ``DEVICE``/
``YOLO_MODEL`` from ``.env``: a present GPU gets used, and a many-core CPU
gets bumped from the nano model to the small one for better accuracy. Every
override is logged so the effective choice is never a silent surprise.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from logging_utils import get_logger

logger = get_logger(__name__)

# CPU-only tier threshold: below this core count, the nano model stays (its
# ~55ms/frame keeps the live view smooth); at/above it there's enough
# headroom to afford the small model's ~227ms/frame (~4.4 FPS) for
# meaningfully better accuracy -- both figures benchmarked on a 12-core CPU
# at imgsz=480 for this project.
_CPU_CORES_FOR_SMALL_MODEL = 8

_NANO_MODEL = "yolo11n.pt"
_SMALL_MODEL = "yolo11s.pt"


@dataclass(frozen=True)
class HardwareProfile:
    """Detected capability of the machine currently running inference."""

    cpu_count: int
    gpu_available: bool


def detect_hardware() -> HardwareProfile:
    """Detect CPU core count and CUDA GPU availability."""
    cpu_count = os.cpu_count() or 1
    gpu_available = False
    try:
        import torch

        gpu_available = bool(torch.cuda.is_available())
    except Exception:
        gpu_available = False
    return HardwareProfile(cpu_count=cpu_count, gpu_available=gpu_available)


def auto_tune(configured_device: str, configured_model: str) -> tuple[str, str]:
    """Return ``(device, model_path)``, upgraded to match detected hardware.

    Only ever upgrades: a GPU takes over from a configured ``"cpu"``, and the
    nano model steps up to the small one on a capable CPU. A model other than
    the nano default (i.e. already a deliberate choice) is left untouched.
    """
    profile = detect_hardware()
    device = configured_device
    model = configured_model

    if profile.gpu_available and configured_device == "cpu":
        device = "0"
        logger.info(
            "Auto-tune: CUDA GPU detected, overriding DEVICE (%r -> %r)",
            configured_device,
            device,
        )

    if (
        not profile.gpu_available
        and profile.cpu_count >= _CPU_CORES_FOR_SMALL_MODEL
        and configured_model == _NANO_MODEL
    ):
        model = _SMALL_MODEL
        logger.info(
            "Auto-tune: %d CPU cores detected, overriding YOLO_MODEL (%r -> %r)",
            profile.cpu_count,
            configured_model,
            model,
        )

    return device, model
