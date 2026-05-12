"""
Detector factory — creates the right IPlateDetector based on config.
"""
from __future__ import annotations

import logging

from app.config import Settings
from app.domain.interfaces import IPlateDetector

logger = logging.getLogger(__name__)

# Supported engine identifiers (case-insensitive).
_ENGINE_FAST_ALPR = "fast-alpr"
_ENGINE_NOMEROFF = "nomeroff"


def create_detector(settings: Settings) -> IPlateDetector:
    """
    Build an IPlateDetector instance for the engine selected in *settings*.

    Supported values for ``settings.alpr_engine``:
        - ``"fast-alpr"`` — lightweight ONNX-based pipeline (default).
        - ``"nomeroff"``  — nomeroff-net PyTorch pipeline.
    """
    engine = settings.alpr_engine.strip().lower()

    if engine == _ENGINE_FAST_ALPR:
        from app.infrastructure.detector.fastalpr_detector import FastAlprDetector

        logger.info("Using ALPR engine: fast-alpr")
        return FastAlprDetector(
            detector_model=settings.fastalpr_detector_model,
            detector_conf=settings.fastalpr_detector_conf,
            ocr_model=settings.fastalpr_ocr_model,
        )

    if engine == _ENGINE_NOMEROFF:
        from app.infrastructure.detector.nomeroff_detector import NomeroffDetector

        logger.info("Using ALPR engine: nomeroff-net")
        return NomeroffDetector(force_ru_ocr=settings.force_ru_ocr)

    raise ValueError(
        f"Unknown ALPR engine: {settings.alpr_engine!r}. "
        f"Supported: {_ENGINE_FAST_ALPR!r}, {_ENGINE_NOMEROFF!r}"
    )
