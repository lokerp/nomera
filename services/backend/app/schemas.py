from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BoundingBoxSchema(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class RawPlateDetectionSchema(BaseModel):
    plate_text: str
    bbox: BoundingBoxSchema
    confidence: float
    region_name: str = ""


class RawDetectionPayload(BaseModel):
    camera_id: str
    camera_role: str
    frame_number: int
    timestamp_seconds: float
    frame_width: int
    frame_height: int
    detections: list[RawPlateDetectionSchema] = Field(default_factory=list)


class ConfirmedDetectionPayload(BaseModel):
    id: str
    plate_text: str
    bbox: BoundingBoxSchema | None = None
    camera_id: str
    camera_role: str
    region_name: str = ""
    confidence: float
    first_seen: datetime
    last_seen: datetime
    occurrences: int
    frame_number: int = 0
    timestamp_seconds: float = 0.0
    frame_width: int = 0
    frame_height: int = 0
    snapshot_base64: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "nomera-backend"
    version: str = "1.0.0"


class MessageResponse(BaseModel):
    message: str
