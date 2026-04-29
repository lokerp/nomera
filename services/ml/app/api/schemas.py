from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import CameraRole


# ─── Requests ────────────────────────────────────────────────────────────────

class CameraCreateRequest(BaseModel):
    """Request to register a new camera."""
    source: str = Field(..., description="Path to video file or RTSP/HTTP stream URL")
    role: CameraRole = Field(..., description="Camera role: 'entry' or 'exit'")
    camera_id: str | None = Field(None, description="Custom camera ID (auto-generated if omitted)")
    roi_zone: list[float] | None = Field(
        None,
        description="Region of interest as [x1%, y1%, x2%, y2%] in relative coords (0..1)",
        min_length=4,
        max_length=4,
    )


# ─── Responses ───────────────────────────────────────────────────────────────

class BoundingBoxSchema(BaseModel):
    """Bounding box of a detected license plate."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class DetectionEventSchema(BaseModel):
    """A confirmed license plate detection event."""
    id: str
    plate_text: str
    bbox: BoundingBoxSchema | None
    camera_id: str
    camera_role: str
    region_name: str
    confidence: float
    first_seen: datetime
    last_seen: datetime
    occurrences: int
    snapshot_base64: str | None = None


class CameraStatusSchema(BaseModel):
    """Status of a single camera."""
    camera_id: str
    role: str
    source: str
    is_active: bool
    frames_processed: int
    detections_count: int
    error: str | None = None


class PipelineStatusSchema(BaseModel):
    """Overall pipeline status."""
    status: str
    cameras: list[CameraStatusSchema]
    total_events_sent: int
    total_events_failed: int
    uptime_seconds: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    service: str = "nomera-ml"
    version: str = "1.0.0"


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


class CameraCreatedResponse(BaseModel):
    """Response after successfully creating a camera."""
    camera_id: str
    message: str = "Camera registered successfully"
