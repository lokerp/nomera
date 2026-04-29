from __future__ import annotations

import logging

import numpy as np

from app.domain.interfaces import IPlateDetector
from app.domain.models import BoundingBox, PlateDetection

logger = logging.getLogger(__name__)


def _register_nomeroff_torch_safe_globals() -> None:
    """Allow trusted nomeroff checkpoints to load on PyTorch 2.6+."""
    try:
        from torch.serialization import add_safe_globals
        from torchvision.models.efficientnet import efficientnet_b2
        from torchvision.models.resnet import resnet18

        from nomeroff_net.tools.ocr_tools import StrLabelConverter
    except Exception as exc:
        logger.debug("Unable to register torch safe globals for nomeroff checkpoints: %s", exc)
        return

    add_safe_globals([StrLabelConverter, efficientnet_b2, resnet18])


class NomeroffDetector(IPlateDetector):
    """
    Adapter for nomeroff-net library implementing IPlateDetector.
    Lazy-loads the pipeline on first use or explicit warmup().
    """

    def __init__(self) -> None:
        self._pipeline = None
        self._unzip = None

    def warmup(self) -> None:
        """Load nomeroff-net models. Call once at startup."""
        if self._pipeline is not None:
            return

        logger.info("Loading nomeroff-net pipeline (this may take a minute)...")
        _register_nomeroff_torch_safe_globals()

        from nomeroff_net import pipeline
        from nomeroff_net.tools import unzip

        self._pipeline = pipeline(
            "number_plate_detection_and_reading",
        )
        self._unzip = unzip
        logger.info("Nomeroff-net pipeline ready")

    def detect(self, frames: list[np.ndarray]) -> list[list[PlateDetection]]:
        """
        Run detection + OCR on a batch of BGR frames.

        Args:
            frames: List of BGR numpy arrays.

        Returns:
            For each input frame, a list of PlateDetection objects.
        """
        if self._pipeline is None:
            self.warmup()

        if not frames:
            return []

        try:
            rgb_frames = [frame[..., ::-1].copy() for frame in frames]
            result = self._pipeline(rgb_frames)
            (
                images,
                images_bboxs,
                images_points,
                images_zones,
                region_ids,
                region_names,
                count_lines,
                confidences,
                texts,
            ) = self._unzip(result)
        except Exception:
            logger.exception("Nomeroff-net inference failed")
            return [[] for _ in frames]

        all_detections: list[list[PlateDetection]] = []

        for frame_idx in range(len(frames)):
            frame_detections: list[PlateDetection] = []

            if frame_idx >= len(texts):
                all_detections.append([])
                continue

            frame_texts = texts[frame_idx] if frame_idx < len(texts) else []
            frame_bboxs = images_bboxs[frame_idx] if frame_idx < len(images_bboxs) else []
            frame_regions = region_names[frame_idx] if frame_idx < len(region_names) else []
            frame_confidences = confidences[frame_idx] if frame_idx < len(confidences) else []

            for det_idx in range(len(frame_texts)):
                text = frame_texts[det_idx] if det_idx < len(frame_texts) else ""
                if not text or not text.strip():
                    continue

                # Parse bbox: [x1, y1, x2, y2, conf, class_id, keypoints]
                bbox_data = frame_bboxs[det_idx] if det_idx < len(frame_bboxs) else None
                if bbox_data is None:
                    continue

                try:
                    x1 = float(bbox_data[0])
                    y1 = float(bbox_data[1])
                    x2 = float(bbox_data[2])
                    y2 = float(bbox_data[3])
                    bbox_conf = float(bbox_data[4]) if len(bbox_data) > 4 else 0.0
                except (IndexError, TypeError, ValueError):
                    logger.warning("Failed to parse bbox for detection %d in frame %d", det_idx, frame_idx)
                    continue

                region = frame_regions[det_idx] if det_idx < len(frame_regions) else "unknown"

                # Confidence from classification
                det_conf = 0.0
                if det_idx < len(frame_confidences):
                    c = frame_confidences[det_idx]
                    if isinstance(c, (list, tuple)) and len(c) > 0:
                        det_conf = float(c[0])
                    elif isinstance(c, (int, float)):
                        det_conf = float(c)

                combined_confidence = (bbox_conf + det_conf) / 2 if det_conf > 0 else bbox_conf

                detection = PlateDetection(
                    plate_text=text.strip().upper(),
                    bbox=BoundingBox(
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        confidence=bbox_conf,
                    ),
                    region_name=str(region),
                    confidence=combined_confidence,
                    frame_number=0,  # will be set by caller
                    timestamp=0.0,   # will be set by caller
                )
                frame_detections.append(detection)

            all_detections.append(frame_detections)

        return all_detections
