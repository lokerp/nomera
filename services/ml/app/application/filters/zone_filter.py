from __future__ import annotations

import logging

from app.domain.models import PlateDetection

logger = logging.getLogger(__name__)


class ZoneFilter:
    """
    Filters detections by Region of Interest (ROI).
    Only plates whose bbox center falls inside the ROI pass through.
    ROI is defined in relative coordinates (0..1) of the frame.
    """

    def __init__(
        self,
        roi: tuple[float, float, float, float] | None = None,
        frame_width: int = 1,
        frame_height: int = 1,
    ) -> None:
        """
        Args:
            roi: (x1_rel, y1_rel, x2_rel, y2_rel) — relative coords 0..1.
                 None means no zone filtering (pass everything).
            frame_width: Pixel width of the frame (for converting relative → absolute).
            frame_height: Pixel height of the frame.
        """
        self._roi_rel = roi
        self._frame_w = frame_width
        self._frame_h = frame_height

        if roi is not None:
            self._roi_abs = (
                roi[0] * frame_width,
                roi[1] * frame_height,
                roi[2] * frame_width,
                roi[3] * frame_height,
            )
            logger.info(
                "ZoneFilter active: ROI=(%d,%d)-(%d,%d) px",
                int(self._roi_abs[0]),
                int(self._roi_abs[1]),
                int(self._roi_abs[2]),
                int(self._roi_abs[3]),
            )
        else:
            self._roi_abs = None
            logger.info("ZoneFilter disabled (no ROI set)")

    def update_frame_size(self, width: int, height: int) -> None:
        """Update frame dimensions (e.g., if source changes)."""
        self._frame_w = width
        self._frame_h = height
        if self._roi_rel is not None:
            self._roi_abs = (
                self._roi_rel[0] * width,
                self._roi_rel[1] * height,
                self._roi_rel[2] * width,
                self._roi_rel[3] * height,
            )

    def apply(self, detections: list[PlateDetection]) -> list[PlateDetection]:
        """Filter detections: keep only those with bbox center inside ROI."""
        if self._roi_abs is None:
            return detections

        rx1, ry1, rx2, ry2 = self._roi_abs
        result = []
        for det in detections:
            cx, cy = det.bbox.center
            if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                result.append(det)

        filtered_count = len(detections) - len(result)
        if filtered_count > 0:
            logger.debug("ZoneFilter: %d/%d detections outside ROI", filtered_count, len(detections))

        return result
