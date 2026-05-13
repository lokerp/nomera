from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import RequestStatusEnum, RoleEnum


def _normalize_plate(value: str) -> str:
    normalized = "".join(value.upper().split())
    if not normalized:
        raise ValueError("plate_number cannot be empty")
    return normalized


def _validate_allowed_days(value: str) -> str:
    days = [item.strip() for item in value.split(",") if item.strip()]
    if not days:
        raise ValueError("allowed_days cannot be empty")
    parsed = []
    for day in days:
        day_int = int(day)
        if day_int < 1 or day_int > 7:
            raise ValueError("allowed_days must contain values from 1 to 7")
        parsed.append(str(day_int))
    return ",".join(parsed)


def _validate_time(value: str) -> str:
    if len(value) != 5 or value[2] != ":":
        raise ValueError("time format must be HH:MM")
    hour = int(value[:2])
    minute = int(value[3:])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("invalid time value")
    return value


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    role: str = RoleEnum.guard.value
    parking_lot_ids: list[str] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {RoleEnum.admin.value, RoleEnum.guard.value}:
            raise ValueError("role must be admin or guard")
        return value


class UserUpdateRequest(BaseModel):
    password: str | None = Field(default=None, min_length=4, max_length=128)
    role: str | None = None
    parking_lot_ids: list[str] | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in {RoleEnum.admin.value, RoleEnum.guard.value}:
            raise ValueError("role must be admin or guard")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    parking_lot_ids: list[str] = Field(default_factory=list)


class ParkingLotRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=1000)


class ParkingLotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str


class CameraRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    parking_lot_id: str
    name: str = Field(min_length=1, max_length=128)
    stream_url: str = Field(min_length=1, max_length=1024)


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parking_lot_id: str
    name: str
    stream_url: str


class AllowedPlateRequest(BaseModel):
    parking_lot_id: str
    plate_number: str
    allowed_days: str = "1,2,3,4,5,6,7"
    time_start: str = "00:00"
    time_end: str = "23:59"
    is_active: bool = True

    _validate_plate = field_validator("plate_number")(_normalize_plate)
    _validate_days = field_validator("allowed_days")(_validate_allowed_days)
    _validate_time_start = field_validator("time_start")(_validate_time)
    _validate_time_end = field_validator("time_end")(_validate_time)


class AllowedPlateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parking_lot_id: str
    plate_number: str
    allowed_days: str
    time_start: str
    time_end: str
    is_active: bool


class AccessRequestCreate(BaseModel):
    parking_lot_id: str
    plate_number: str
    allowed_days: str = "1,2,3,4,5,6,7"
    time_start: str = "00:00"
    time_end: str = "23:59"

    _validate_plate = field_validator("plate_number")(_normalize_plate)
    _validate_days = field_validator("allowed_days")(_validate_allowed_days)
    _validate_time_start = field_validator("time_start")(_validate_time)
    _validate_time_end = field_validator("time_end")(_validate_time)


class AccessRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parking_lot_id: str
    plate_number: str
    allowed_days: str
    time_start: str
    time_end: str
    status: str
    created_at: datetime


class ScanLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parking_lot_id: str
    camera_id: str
    plate_number: str
    photo_url: str
    frame_width: int
    frame_height: int
    bbox_x1: float | None = None
    bbox_y1: float | None = None
    bbox_x2: float | None = None
    bbox_y2: float | None = None
    bbox_confidence: float | None = None
    # Decoded plate corners (TL, TR, BR, BL) in pixel coords, or null.
    # Read off the `ScanLog.corners` property which decodes corners_json.
    corners: list[list[float]] | None = None
    timestamp: datetime


class DailyStatsResponse(BaseModel):
    recognitions_today: int
    unique_plates_today: int
    peak_hour: str


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "nomera-backend"
    version: str = "2.0.0"


class MessageResponse(BaseModel):
    message: str
