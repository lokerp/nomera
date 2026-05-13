from __future__ import annotations

import logging
import statistics
import sys
from pathlib import Path

import numpy as np

from app.domain.interfaces import IPlateDetector
from app.domain.models import BoundingBox, PlateDetection

logger = logging.getLogger(__name__)

# fast_alpr is vendored locally — make sure it's importable.
_FAST_ALPR_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "fast-alpr"
if str(_FAST_ALPR_ROOT) not in sys.path:
    sys.path.insert(0, str(_FAST_ALPR_ROOT))


class FastAlprDetector(IPlateDetector):
    """
    Adapter for the fast-alpr library implementing IPlateDetector.

    Uses ONNX-based plate detection (open-image-models) and
    OCR (fast-plate-ocr) under the hood.
    """

    def __init__(
        self,
        detector_model: str = "yolo-v9-t-640-license-plate-end2end",
        detector_model_path: str = "",
        detector_conf: float = 0.4,
        ocr_model: str = "",
        ocr_model_path: str = "",
        ocr_config_path: str = "",
        min_ocr_confidence: float = 0.0,
    ) -> None:
        self._detector_model = detector_model
        self._detector_model_path = detector_model_path
        self._detector_conf = detector_conf
        self._ocr_model = ocr_model
        self._ocr_model_path = ocr_model_path
        self._ocr_config_path = ocr_config_path
        self._min_ocr_confidence = min_ocr_confidence
        self._alpr = None

    def warmup(self) -> None:
        """Load ONNX models and warm up the pipeline."""
        if self._alpr is not None:
            return

        from app.config import SERVICE_ROOT
        from fast_alpr import ALPR

        _providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

        # Resolve and build local detector if a path is provided
        detector_instance = None
        if self._detector_model_path:
            from fast_alpr.base import BaseDetector as _BaseDetector
            from open_image_models.detection.core.yolo_v9.inference import YoloV9ObjectDetector

            det_path = Path(self._detector_model_path)
            if not det_path.is_absolute():
                det_path = SERVICE_ROOT / det_path

            logger.info("Loading local detector model: %s", det_path)

            class _LocalDetector(_BaseDetector):
                def __init__(self, path: Path, conf: float, providers: list) -> None:
                    self._det = YoloV9ObjectDetector(
                        model_path=str(path),
                        conf_thresh=conf,
                        class_labels=["License Plate"],
                        providers=providers,
                    )

                def predict(self, frame: np.ndarray):
                    return self._det.predict(frame)

            detector_instance = _LocalDetector(det_path, self._detector_conf, _providers)

        # Resolve custom OCR model paths relative to SERVICE_ROOT
        ocr_kwargs: dict = {}
        if self._ocr_model_path:
            model_path = Path(self._ocr_model_path)
            if not model_path.is_absolute():
                model_path = SERVICE_ROOT / model_path

            config_path = Path(self._ocr_config_path) if self._ocr_config_path else None
            if config_path and not config_path.is_absolute():
                config_path = SERVICE_ROOT / config_path

            logger.info("Loading fast-alpr pipeline (custom OCR)...")
            logger.info(
                "  detector=%s  conf=%.2f  ocr_model=%s  ocr_config=%s",
                self._detector_model_path or self._detector_model,
                self._detector_conf,
                model_path,
                config_path,
            )

            ocr_kwargs["ocr_model"] = None
            ocr_kwargs["ocr_model_path"] = str(model_path)
            if config_path:
                ocr_kwargs["ocr_config_path"] = str(config_path)
        else:
            logger.info("Loading fast-alpr pipeline (hub OCR model)...")
            logger.info(
                "  detector=%s  conf=%.2f  ocr=%s",
                self._detector_model_path or self._detector_model,
                self._detector_conf,
                self._ocr_model,
            )
            ocr_kwargs["ocr_model"] = self._ocr_model or None

        alpr_kwargs: dict = dict(
            detector_conf_thresh=self._detector_conf,
            detector_providers=_providers,
            ocr_device="cuda",
            ocr_providers=_providers,
            **ocr_kwargs,
        )
        if detector_instance is not None:
            alpr_kwargs["detector"] = detector_instance
        else:
            alpr_kwargs["detector_model"] = self._detector_model

        self._alpr = ALPR(**alpr_kwargs)

        # Warm up with a tiny dummy frame so ONNX sessions are fully initialized.
        dummy = np.zeros((64, 128, 3), dtype=np.uint8)
        self._alpr.predict(dummy)

        logger.info("fast-alpr pipeline ready")

    def detect(self, frames: list[np.ndarray]) -> list[list[PlateDetection]]:
        """
        Run detection + OCR on a batch of BGR frames.

        fast-alpr processes one frame at a time, so we loop internally.

        Args:
            frames: List of BGR numpy arrays (OpenCV format).

        Returns:
            For each input frame, a list of PlateDetection objects.
        """
        if self._alpr is None:
            self.warmup()

        if not frames:
            return []

        all_detections: list[list[PlateDetection]] = []

        for frame in frames:
            frame_detections: list[PlateDetection] = []

            try:
                results = self._alpr.predict(frame)
            except Exception:
                logger.exception("fast-alpr inference failed on frame")
                all_detections.append([])
                continue

            for result in results:
                detection = result.detection
                ocr = result.ocr

                # Skip if OCR produced nothing
                if ocr is None or not ocr.text or not ocr.text.strip():
                    continue

                # --- Bounding box ---
                bbox = detection.bounding_box
                bbox_conf = float(detection.confidence)

                # --- OCR confidence ---
                ocr_conf = 0.0
                if ocr.confidence is not None:
                    if isinstance(ocr.confidence, list):
                        # Per-character confidences → average
                        non_pad = [c for c in ocr.confidence if c > 0.0]
                        ocr_conf = statistics.mean(non_pad) if non_pad else 0.0
                    else:
                        ocr_conf = float(ocr.confidence)

                # Hard gate: low-confidence OCR results are the main source of
                # false positives — drop them before they enter the tracker.
                if ocr_conf < self._min_ocr_confidence:
                    continue

                combined_confidence = (bbox_conf + ocr_conf) / 2 if ocr_conf > 0 else bbox_conf

                # --- Region ---
                region = ocr.region if ocr.region else "unknown"

                plate = PlateDetection(
                    plate_text=ocr.text.strip().upper(),
                    bbox=BoundingBox(
                        x1=float(bbox.x1),
                        y1=float(bbox.y1),
                        x2=float(bbox.x2),
                        y2=float(bbox.y2),
                        confidence=bbox_conf,
                    ),
                    region_name=str(region),
                    confidence=combined_confidence,
                    frame_number=0,  # will be set by caller
                    timestamp=0.0,   # will be set by caller
                    ocr_confidence=ocr_conf,
                )
                frame_detections.append(plate)

            all_detections.append(frame_detections)

        return all_detections
