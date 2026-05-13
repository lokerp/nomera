"""
Detector factory — creates the right IPlateDetector based on config.
"""
from __future__ import annotations

import logging

from app.config import Settings
from app.domain.interfaces import IPlateDetector

logger = logging.getLogger(__name__)


def create_detector(settings: Settings) -> IPlateDetector:
    engine = (settings.detector_engine or "fast-alpr").strip().lower()

    if engine == "keypoint":
        from app.infrastructure.detector.keypoint_detector import KeypointAlprDetector

        logger.info(
            "Using ALPR engine: keypoint (YOLOv8-Pose + perspective warp, min_ocr_conf=%.2f)",
            settings.min_ocr_confidence,
        )
        return KeypointAlprDetector(
            keypoint_model_path=settings.keypoint_model_path,
            detector_conf=settings.keypoint_detector_conf,
            keypoint_conf=settings.keypoint_min_kp_conf,
            min_avg_keypoint_conf=settings.keypoint_min_avg_kp_conf,
            ocr_model=settings.fastalpr_ocr_model,
            ocr_model_path=settings.fastalpr_ocr_model_path,
            ocr_config_path=settings.fastalpr_ocr_config_path,
            warp_min_size=(
                settings.keypoint_warp_min_width,
                settings.keypoint_warp_min_height,
            ),
            max_skew_ratio=settings.keypoint_max_skew_ratio,
            min_ocr_confidence=settings.min_ocr_confidence,
        )

    from app.infrastructure.detector.fastalpr_detector import FastAlprDetector

    logger.info(
        "Using ALPR engine: fast-alpr (bbox + cropped OCR, min_ocr_conf=%.2f)",
        settings.min_ocr_confidence,
    )
    return FastAlprDetector(
        detector_model=settings.fastalpr_detector_model,
        detector_model_path=settings.fastalpr_detector_model_path,
        detector_conf=settings.fastalpr_detector_conf,
        ocr_model=settings.fastalpr_ocr_model,
        ocr_model_path=settings.fastalpr_ocr_model_path,
        ocr_config_path=settings.fastalpr_ocr_config_path,
        min_ocr_confidence=settings.min_ocr_confidence,
    )
