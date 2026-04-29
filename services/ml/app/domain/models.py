from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from app.domain.enums import CameraRole


@dataclass
class BoundingBox:
    """Bounding box of a detected license plate in pixel coordinates."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


@dataclass
class PlateDetection:
    """
    A single license plate detection on a single frame.
    Raw output from the detector before any filtering or tracking.
    """
    plate_text: str
    bbox: BoundingBox
    region_name: str
    confidence: float
    frame_number: int
    timestamp: float  # seconds from video start

    @property
    def bbox_area(self) -> float:
        return self.bbox.area


@dataclass
class DetectionEvent:
    """
    Aggregated detection event — a license plate that has been
    confidently recognized across multiple frames.
    This is what gets pushed to the backend.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    plate_text: str = ""
    bbox: BoundingBox | None = None
    camera_id: str = ""
    camera_role: CameraRole = CameraRole.ENTRY
    region_name: str = ""
    confidence: float = 0.0
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    occurrences: int = 0
    frame_number: int = 0
    timestamp_seconds: float = 0.0
    frame_width: int = 0
    frame_height: int = 0
    snapshot_jpeg: bytes | None = None  # JPEG-encoded frame crop


@dataclass
class CameraConfig:
    """Configuration for a single camera source."""
    camera_id: str = field(default_factory=lambda: str(uuid4()))
    source: str = ""  # file path or RTSP URL
    role: CameraRole = CameraRole.ENTRY
    roi_zone: tuple[float, float, float, float] | None = None  # (x1%, y1%, x2%, y2%) relative coords 0..1
