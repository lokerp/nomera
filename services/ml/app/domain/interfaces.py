from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

import numpy as np

from app.domain.enums import CameraRole
from app.domain.models import DetectionEvent, PlateDetection


class IPlateDetector(ABC):
    """Interface for license plate detection and recognition."""

    @abstractmethod
    def detect(self, frames: list[np.ndarray]) -> list[list[PlateDetection]]:
        """
        Detect and recognize license plates in a batch of frames.

        Args:
            frames: List of BGR numpy arrays (OpenCV format).

        Returns:
            For each frame, a list of PlateDetection objects found.
        """
        ...

    @abstractmethod
    def warmup(self) -> None:
        """Load models and warm up the pipeline."""
        ...


class IVideoSource(ABC):
    """Interface for a video frame source (file, RTSP, etc.)."""

    @abstractmethod
    def frames(self) -> Iterator[tuple[int, float, np.ndarray]]:
        """
        Yield video frames.

        Yields:
            Tuples of (frame_number, timestamp_seconds, bgr_frame).
        """
        ...

    @abstractmethod
    def release(self) -> None:
        """Release the underlying video resource."""
        ...

    @abstractmethod
    def get_frame_size(self) -> tuple[int, int]:
        """Return (width, height) of frames."""
        ...

    @abstractmethod
    def get_fps(self) -> float:
        """Return the FPS of the source."""
        ...


class IEventSender(ABC):
    """Interface for sending detection events to the backend."""

    @abstractmethod
    async def send(self, event: DetectionEvent) -> bool:
        """
        Send a detection event to the backend.

        Returns:
            True if the event was accepted, False otherwise.
        """
        ...

    @abstractmethod
    async def send_raw(
        self,
        *,
        camera_id: str,
        camera_role: CameraRole,
        frame_number: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
        detections: list[PlateDetection],
    ) -> bool:
        """Send raw detections for one processed frame."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close underlying connections."""
        ...
