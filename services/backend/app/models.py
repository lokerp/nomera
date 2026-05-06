from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RoleEnum(str, enum.Enum):
    admin = "admin"
    guard = "guard"


class RequestStatusEnum(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=RoleEnum.guard.value, index=True)

    parking_lots: Mapped[list[ParkingLot]] = relationship(
        secondary="user_parking_lots",
        back_populates="users",
        overlaps="parking_links,user_links",
    )
    parking_links: Mapped[list[UserParkingLot]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        overlaps="parking_lots,users",
    )


class ParkingLot(Base):
    __tablename__ = "parking_lots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")

    users: Mapped[list[User]] = relationship(
        secondary="user_parking_lots",
        back_populates="parking_lots",
        overlaps="parking_links,user_links",
    )
    user_links: Mapped[list[UserParkingLot]] = relationship(
        back_populates="parking_lot",
        cascade="all, delete-orphan",
        overlaps="users,parking_lots",
    )
    cameras: Mapped[list[Camera]] = relationship(back_populates="parking_lot", cascade="all, delete-orphan")
    allowed_plates: Mapped[list[AllowedPlate]] = relationship(back_populates="parking_lot", cascade="all, delete-orphan")
    access_requests: Mapped[list[AccessRequest]] = relationship(back_populates="parking_lot", cascade="all, delete-orphan")
    scan_logs: Mapped[list[ScanLog]] = relationship(back_populates="parking_lot", cascade="all, delete-orphan")


class UserParkingLot(Base):
    __tablename__ = "user_parking_lots"
    __table_args__ = (
        UniqueConstraint("user_id", "parking_lot_id", name="uq_user_parking"),
        Index("ix_user_parking_user_id", "user_id"),
        Index("ix_user_parking_parking_lot_id", "parking_lot_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parking_lot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_lots.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="parking_links", overlaps="users,parking_lots")
    parking_lot: Mapped[ParkingLot] = relationship(back_populates="user_links", overlaps="users,parking_lots")


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        Index("ix_cameras_parking_lot_id", "parking_lot_id"),
        UniqueConstraint("parking_lot_id", "name", name="uq_camera_name_in_parking"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parking_lot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_lots.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128))
    stream_url: Mapped[str] = mapped_column(String(1024))

    parking_lot: Mapped[ParkingLot] = relationship(back_populates="cameras")
    scan_logs: Mapped[list[ScanLog]] = relationship(back_populates="camera")


class AllowedPlate(Base):
    __tablename__ = "allowed_plates"
    __table_args__ = (
        Index("ix_allowed_plates_parking_lot_id", "parking_lot_id"),
        Index("ix_allowed_plates_plate_number", "plate_number"),
        UniqueConstraint("parking_lot_id", "plate_number", name="uq_allowed_plate_per_parking"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parking_lot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_lots.id", ondelete="CASCADE"), nullable=False
    )
    plate_number: Mapped[str] = mapped_column(String(32))
    allowed_days: Mapped[str] = mapped_column(String(64), default="1,2,3,4,5,6,7")
    time_start: Mapped[str] = mapped_column(String(5), default="00:00")
    time_end: Mapped[str] = mapped_column(String(5), default="23:59")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    parking_lot: Mapped[ParkingLot] = relationship(back_populates="allowed_plates")


class AccessRequest(Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        Index("ix_access_requests_parking_lot_id", "parking_lot_id"),
        Index("ix_access_requests_status", "status"),
        Index("ix_access_requests_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parking_lot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_lots.id", ondelete="CASCADE"), nullable=False
    )
    plate_number: Mapped[str] = mapped_column(String(32))
    allowed_days: Mapped[str] = mapped_column(String(64), default="1,2,3,4,5,6,7")
    time_start: Mapped[str] = mapped_column(String(5), default="00:00")
    time_end: Mapped[str] = mapped_column(String(5), default="23:59")
    status: Mapped[str] = mapped_column(String(16), default=RequestStatusEnum.pending.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    parking_lot: Mapped[ParkingLot] = relationship(back_populates="access_requests")


class ScanLog(Base):
    __tablename__ = "scan_logs"
    __table_args__ = (
        Index("ix_scan_logs_parking_lot_id", "parking_lot_id"),
        Index("ix_scan_logs_camera_id", "camera_id"),
        Index("ix_scan_logs_timestamp", "timestamp"),
        Index("ix_scan_logs_plate_number", "plate_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parking_lot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_lots.id", ondelete="CASCADE"), nullable=False
    )
    camera_id: Mapped[str] = mapped_column(String(64), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(32))
    photo_url: Mapped[str] = mapped_column(String(1024))
    frame_width: Mapped[int] = mapped_column(default=0)
    frame_height: Mapped[int] = mapped_column(default=0)
    bbox_x1: Mapped[float | None] = mapped_column(default=None)
    bbox_y1: Mapped[float | None] = mapped_column(default=None)
    bbox_x2: Mapped[float | None] = mapped_column(default=None)
    bbox_y2: Mapped[float | None] = mapped_column(default=None)
    bbox_confidence: Mapped[float | None] = mapped_column(default=None)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    parking_lot: Mapped[ParkingLot] = relationship(back_populates="scan_logs")
    camera: Mapped[Camera] = relationship(back_populates="scan_logs")
