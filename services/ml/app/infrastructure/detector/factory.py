"""
Detector factory — creates the right IPlateDetector based on config.
"""
from __future__ import annotations

import logging

from app.config import Settings
from app.domain.interfaces import IPlateDetector

logger = logging.getLogger(__name__)


def create_detector(settings: Settings) -> IPlateDetector:
    from app.infrastructure.detector.fastalpr_detector import FastAlprDetector

    logger.info("Using ALPR engine: fast-alpr")
    return FastAlprDetector(
        detector_model=settings.fastalpr_detector_model,
        detector_model_path=settings.fastalpr_detector_model_path,
        detector_conf=settings.fastalpr_detector_conf,
        ocr_model=settings.fastalpr_ocr_model,
        ocr_model_path=settings.fastalpr_ocr_model_path,
        ocr_config_path=settings.fastalpr_ocr_config_path,
    )
