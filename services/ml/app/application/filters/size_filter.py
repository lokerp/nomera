from __future__ import annotations

import logging

from app.domain.models import PlateDetection

logger = logging.getLogger(__name__)


class SizeFilter:
    """
    Filters detections by minimum bounding box area.
    Rejects small/distant plates that are unlikely to be at the barrier.
    Threshold is specified as a percentage of total frame area.
    """

    def __init__(
        self,
        min_area_pct: float = 0.10,
        frame_width: int = 1,
        frame_height: int = 1,
    ) -> None:
        """
        Args:
            min_area_pct: Minimum bbox area as percentage of frame area (0..100).
            frame_width: Pixel width of the frame.
            frame_height: Pixel height of the frame.
        """
        self._min_area_pct = min_area_pct
        self._frame_area = frame_width * frame_height
        self._min_area_px = self._frame_area * (min_area_pct / 100.0)
        logger.info(
            "SizeFilter: min_area=%.2f%% of frame (%d px²)",
            min_area_pct,
            int(self._min_area_px),
        )

    def update_frame_size(self, width: int, height: int) -> None:
        """Update frame dimensions."""
        self._frame_area = width * height
        self._min_area_px = self._frame_area * (self._min_area_pct / 100.0)

    def apply(self, detections: list[PlateDetection]) -> list[PlateDetection]:
        """Filter detections: keep only those with bbox area above threshold."""
        result = []
        for det in detections:
            if det.bbox.area >= self._min_area_px:
                result.append(det)

        filtered_count = len(detections) - len(result)
        if filtered_count > 0:
            logger.debug(
                "SizeFilter: %d/%d detections too small (min=%.0f px²)",
                filtered_count,
                len(detections),
                self._min_area_px,
            )

        return result
