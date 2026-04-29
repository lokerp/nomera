from __future__ import annotations

import logging
from typing import Iterator

import cv2
import numpy as np

from app.domain.interfaces import IVideoSource

logger = logging.getLogger(__name__)


class OpenCVSource(IVideoSource):
    """
    Video source using OpenCV VideoCapture.
    Supports local files and RTSP/HTTP streams.
    """

    def __init__(self, source: str, frame_skip: int = 1) -> None:
        """
        Args:
            source: Path to video file or RTSP/HTTP URL.
            frame_skip: Only yield every Nth frame (1 = every frame).
        """
        self._source = source
        self._frame_skip = max(1, frame_skip)
        self._cap: cv2.VideoCapture | None = None
        self._open()

    def _open(self) -> None:
        self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {self._source}")
        logger.info(
            "Opened video source: %s (%.1f FPS, %dx%d, %d frames)",
            self._source,
            self.get_fps(),
            *self.get_frame_size(),
            int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        )

    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        """Yield (frame_number, timestamp_sec, bgr_frame) with frame skipping."""
        if self._cap is None:
            raise RuntimeError("Video source is not opened")

        frame_no = 0
        while True:
            ret, frame = self._cap.read()
            if not ret:
                logger.info("Video source exhausted: %s", self._source)
                break

            if frame_no % self._frame_skip == 0:
                timestamp = self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                yield frame_no, timestamp, frame

            frame_no += 1

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Released video source: %s", self._source)

    def get_frame_size(self) -> tuple[int, int]:
        if self._cap is None:
            return (0, 0)
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)

    def get_fps(self) -> float:
        if self._cap is None:
            return 0.0
        return self._cap.get(cv2.CAP_PROP_FPS)
