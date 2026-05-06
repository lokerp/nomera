from __future__ import annotations

import base64
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_schemas import (
    AccessRequestCreate,
    AccessRequestResponse,
    AllowedPlateRequest,
    AllowedPlateResponse,
    AuthLoginRequest,
    CameraRequest,
    CameraResponse,
    DailyStatsResponse,
    HealthResponse,
    MessageResponse,
    ParkingLotRequest,
    ParkingLotResponse,
    ScanLogResponse,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.auth import verify_backend_api_key
from app.config import settings
from app.database import SessionLocal, get_db, init_db
from app.dependencies.auth import ensure_user_has_parking_access, get_current_user, require_admin
from app.ml_client import request_ml
from app.models import (
    AccessRequest,
    AllowedPlate,
    Camera,
    ParkingLot,
    RequestStatusEnum,
    RoleEnum,
    ScanLog,
    User,
    UserParkingLot,
)
from app.schemas import ConfirmedDetectionPayload, RawDetectionPayload
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.state import confirmed_history, raw_history, ws_hub


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("nomera-backend")

app = FastAPI(
    title="Nomera Parking Management",
    description="Parking management API with RBAC and ML ingestion",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(settings.logs_images_dir).mkdir(parents=True, exist_ok=True)
Path(settings.static_dir).mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    await init_db()
    await ensure_bootstrap_admin()
    async with SessionLocal() as db:
        try:
            await sync_all_cameras_to_ml(db)
            await ensure_ml_pipeline_running()
        except HTTPException:
            logger.warning("Startup ML sync skipped: ML service unavailable", exc_info=True)


async def ensure_bootstrap_admin() -> None:
    async with SessionLocal() as db:
        existing_admin = await db.scalar(select(User).where(User.role == RoleEnum.admin.value))
        if existing_admin:
            return
        user = User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(settings.bootstrap_admin_password),
            role=RoleEnum.admin.value,
        )
        db.add(user)
        await db.commit()
        logger.info("Bootstrap admin user created: %s", settings.bootstrap_admin_username)
        return


def model_to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        parking_lot_ids=[link.parking_lot_id for link in user.parking_links],
    )


async def get_user_or_404(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def get_parking_or_404(db: AsyncSession, parking_lot_id: str) -> ParkingLot:
    parking = await db.get(ParkingLot, parking_lot_id)
    if not parking:
        raise HTTPException(status_code=404, detail="Parking lot not found")
    return parking


async def get_camera_or_404(db: AsyncSession, camera_id: str) -> Camera:
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def save_snapshot(snapshot_base64: str | None) -> str:
    if not snapshot_base64:
        return ""
    value = snapshot_base64
    if "," in value:
        value = value.split(",", 1)[1]
    image_bytes = base64.b64decode(value)
    image_name = f"{uuid.uuid4().hex}.jpg"
    file_path = Path(settings.logs_images_dir) / image_name
    file_path.write_bytes(image_bytes)
    return f"/static/logs/{image_name}"


def infer_ml_camera_role(camera: Camera) -> str:
    name_blob = f"{camera.id} {camera.name}".lower()
    if "exit" in name_blob or "out" in name_blob or "выезд" in name_blob:
        return "exit"
    return "entry"


async def sync_camera_to_ml(camera: Camera, *, strict: bool = False) -> None:
    payload = {
        "camera_id": camera.id,
        "source": camera.stream_url,
        "role": infer_ml_camera_role(camera),
    }
    try:
        await request_ml("DELETE", f"/api/v1/cameras/{camera.id}")
    except HTTPException:
        # Ignore when camera is not yet present in ML.
        pass
    try:
        await request_ml("POST", "/api/v1/cameras", json=payload)
        logger.info("Camera synced to ML: %s source=%s", camera.id, camera.stream_url)
    except HTTPException:
        if strict:
            raise
        logger.warning("Camera sync to ML failed for %s", camera.id, exc_info=True)


async def remove_camera_from_ml(camera_id: str, *, strict: bool = False) -> None:
    try:
        await request_ml("DELETE", f"/api/v1/cameras/{camera_id}")
        logger.info("Camera removed from ML: %s", camera_id)
    except HTTPException:
        if strict:
            raise
        logger.warning("Camera removal from ML failed for %s", camera_id, exc_info=True)


async def sync_all_cameras_to_ml(db: AsyncSession) -> None:
    ml_cameras = await request_ml("GET", "/api/v1/cameras")
    for item in ml_cameras:
        camera_id = item.get("camera_id")
        if camera_id:
            await remove_camera_from_ml(camera_id, strict=False)

    cameras = (await db.scalars(select(Camera))).all()
    for camera in cameras:
        await sync_camera_to_ml(camera, strict=True)
    logger.info("ML camera sync completed: %d camera(s)", len(cameras))


async def ensure_ml_pipeline_running() -> None:
    status = await request_ml("GET", "/api/v1/status")
    if status.get("status") != "running":
        await request_ml("POST", "/api/v1/pipeline/start")
        logger.info("ML pipeline auto-start requested by backend")


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(payload: AuthLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token)


@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"])
async def auth_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserResponse:
    user = await get_user_or_404(db, current_user.id)
    await db.refresh(user, attribute_names=["parking_links"])
    return model_to_user_response(user)


@app.get("/api/users", response_model=list[UserResponse], tags=["Users"])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)) -> list[UserResponse]:
    users = (await db.scalars(select(User))).all()
    response: list[UserResponse] = []
    for user in users:
        await db.refresh(user, attribute_names=["parking_links"])
        response.append(model_to_user_response(user))
    return response


@app.post("/api/users", response_model=UserResponse, tags=["Users"])
async def create_user(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    existing = await db.scalar(select(User.id).where(User.username == payload.username))
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    await db.flush()
    for parking_lot_id in payload.parking_lot_ids:
        await get_parking_or_404(db, parking_lot_id)
        db.add(UserParkingLot(user_id=user.id, parking_lot_id=parking_lot_id))
    await db.commit()
    await db.refresh(user, attribute_names=["parking_links"])
    return model_to_user_response(user)


@app.put("/api/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    user = await get_user_or_404(db, user_id)
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.role:
        user.role = payload.role
    if payload.parking_lot_ids is not None:
        await db.execute(delete(UserParkingLot).where(UserParkingLot.user_id == user.id))
        for parking_lot_id in payload.parking_lot_ids:
            await get_parking_or_404(db, parking_lot_id)
            db.add(UserParkingLot(user_id=user.id, parking_lot_id=parking_lot_id))
    await db.commit()
    await db.refresh(user, attribute_names=["parking_links"])
    return model_to_user_response(user)


@app.delete("/api/users/{user_id}", response_model=MessageResponse, tags=["Users"])
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)) -> MessageResponse:
    user = await get_user_or_404(db, user_id)
    if user.role == RoleEnum.admin.value:
        admin_count = await db.scalar(select(func.count(User.id)).where(User.role == RoleEnum.admin.value))
        if (admin_count or 0) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    await db.delete(user)
    await db.commit()
    return MessageResponse(message="User deleted")


@app.get("/api/parking-lots", response_model=list[ParkingLotResponse], tags=["ParkingLots"])
async def list_parking_lots(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ParkingLotResponse]:
    if current_user.role == RoleEnum.admin.value:
        lots = (await db.scalars(select(ParkingLot).order_by(ParkingLot.name))).all()
        return [ParkingLotResponse.model_validate(item) for item in lots]
    stmt = (
        select(ParkingLot)
        .join(UserParkingLot, UserParkingLot.parking_lot_id == ParkingLot.id)
        .where(UserParkingLot.user_id == current_user.id)
        .order_by(ParkingLot.name)
    )
    lots = (await db.scalars(stmt)).all()
    return [ParkingLotResponse.model_validate(item) for item in lots]


@app.post("/api/parking-lots", response_model=ParkingLotResponse, tags=["ParkingLots"])
async def create_parking_lot(
    payload: ParkingLotRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ParkingLotResponse:
    lot = ParkingLot(name=payload.name, description=payload.description)
    db.add(lot)
    await db.commit()
    await db.refresh(lot)
    return ParkingLotResponse.model_validate(lot)


@app.put("/api/parking-lots/{parking_lot_id}", response_model=ParkingLotResponse, tags=["ParkingLots"])
async def update_parking_lot(
    parking_lot_id: str,
    payload: ParkingLotRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ParkingLotResponse:
    lot = await get_parking_or_404(db, parking_lot_id)
    lot.name = payload.name
    lot.description = payload.description
    await db.commit()
    await db.refresh(lot)
    return ParkingLotResponse.model_validate(lot)


@app.delete("/api/parking-lots/{parking_lot_id}", response_model=MessageResponse, tags=["ParkingLots"])
async def delete_parking_lot(
    parking_lot_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> MessageResponse:
    lot = await get_parking_or_404(db, parking_lot_id)
    await db.delete(lot)
    await db.commit()
    return MessageResponse(message="Parking lot deleted")


@app.get("/api/cameras", response_model=list[CameraResponse], tags=["Cameras"])
async def list_cameras(
    parking_lot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CameraResponse]:
    await ensure_user_has_parking_access(db, current_user, parking_lot_id)
    stmt = select(Camera).where(Camera.parking_lot_id == parking_lot_id).order_by(Camera.name)
    cameras = (await db.scalars(stmt)).all()
    return [CameraResponse.model_validate(item) for item in cameras]


@app.post("/api/cameras", response_model=CameraResponse, tags=["Cameras"])
async def create_camera(
    payload: CameraRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> CameraResponse:
    await get_parking_or_404(db, payload.parking_lot_id)
    camera = Camera(
        id=payload.id,
        parking_lot_id=payload.parking_lot_id,
        name=payload.name,
        stream_url=payload.stream_url,
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    await sync_camera_to_ml(camera, strict=False)
    try:
        await ensure_ml_pipeline_running()
    except HTTPException:
        logger.warning("Failed to ensure ML pipeline running after camera create", exc_info=True)
    return CameraResponse.model_validate(camera)


@app.put("/api/cameras/{camera_id}", response_model=CameraResponse, tags=["Cameras"])
async def update_camera(
    camera_id: str,
    payload: CameraRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> CameraResponse:
    camera = await get_camera_or_404(db, camera_id)
    await get_parking_or_404(db, payload.parking_lot_id)
    camera.parking_lot_id = payload.parking_lot_id
    camera.name = payload.name
    camera.stream_url = payload.stream_url
    await db.commit()
    await db.refresh(camera)
    await sync_camera_to_ml(camera, strict=False)
    try:
        await ensure_ml_pipeline_running()
    except HTTPException:
        logger.warning("Failed to ensure ML pipeline running after camera update", exc_info=True)
    return CameraResponse.model_validate(camera)


@app.delete("/api/cameras/{camera_id}", response_model=MessageResponse, tags=["Cameras"])
async def delete_camera(camera_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)) -> MessageResponse:
    camera = await get_camera_or_404(db, camera_id)
    await db.delete(camera)
    await db.commit()
    await remove_camera_from_ml(camera_id, strict=False)
    return MessageResponse(message="Camera deleted")


@app.get("/api/allowed-plates", response_model=list[AllowedPlateResponse], tags=["AllowedPlates"])
async def list_allowed_plates(
    parking_lot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AllowedPlateResponse]:
    await ensure_user_has_parking_access(db, current_user, parking_lot_id)
    stmt = select(AllowedPlate).where(AllowedPlate.parking_lot_id == parking_lot_id).order_by(AllowedPlate.plate_number)
    items = (await db.scalars(stmt)).all()
    return [AllowedPlateResponse.model_validate(item) for item in items]


@app.post("/api/allowed-plates", response_model=AllowedPlateResponse, tags=["AllowedPlates"])
async def create_allowed_plate(
    payload: AllowedPlateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AllowedPlateResponse:
    await ensure_user_has_parking_access(db, current_user, payload.parking_lot_id)
    existing = await db.scalar(
        select(AllowedPlate.id).where(
            AllowedPlate.parking_lot_id == payload.parking_lot_id,
            AllowedPlate.plate_number == payload.plate_number,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="Plate already exists for parking lot")
    item = AllowedPlate(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return AllowedPlateResponse.model_validate(item)


@app.put("/api/allowed-plates/{allowed_plate_id}", response_model=AllowedPlateResponse, tags=["AllowedPlates"])
async def update_allowed_plate(
    allowed_plate_id: str,
    payload: AllowedPlateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AllowedPlateResponse:
    item = await db.get(AllowedPlate, allowed_plate_id)
    if not item:
        raise HTTPException(status_code=404, detail="Allowed plate not found")
    await ensure_user_has_parking_access(db, current_user, item.parking_lot_id)
    if item.parking_lot_id != payload.parking_lot_id:
        await ensure_user_has_parking_access(db, current_user, payload.parking_lot_id)
    item.parking_lot_id = payload.parking_lot_id
    item.plate_number = payload.plate_number
    item.allowed_days = payload.allowed_days
    item.time_start = payload.time_start
    item.time_end = payload.time_end
    item.is_active = payload.is_active
    await db.commit()
    await db.refresh(item)
    return AllowedPlateResponse.model_validate(item)


@app.delete("/api/allowed-plates/{allowed_plate_id}", response_model=MessageResponse, tags=["AllowedPlates"])
async def delete_allowed_plate(
    allowed_plate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    item = await db.get(AllowedPlate, allowed_plate_id)
    if not item:
        raise HTTPException(status_code=404, detail="Allowed plate not found")
    await ensure_user_has_parking_access(db, current_user, item.parking_lot_id)
    await db.delete(item)
    await db.commit()
    return MessageResponse(message="Allowed plate deleted")


@app.post("/api/public/requests", response_model=AccessRequestResponse, tags=["Public"])
async def create_public_request(payload: AccessRequestCreate, db: AsyncSession = Depends(get_db)) -> AccessRequestResponse:
    await get_parking_or_404(db, payload.parking_lot_id)
    request = AccessRequest(**payload.model_dump(), status=RequestStatusEnum.pending.value)
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return AccessRequestResponse.model_validate(request)


@app.get("/api/access-requests", response_model=list[AccessRequestResponse], tags=["AccessRequests"])
async def list_access_requests(
    parking_lot_id: str,
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AccessRequestResponse]:
    await ensure_user_has_parking_access(db, current_user, parking_lot_id)
    stmt = select(AccessRequest).where(AccessRequest.parking_lot_id == parking_lot_id)
    if status_filter:
        stmt = stmt.where(AccessRequest.status == status_filter)
    stmt = stmt.order_by(AccessRequest.created_at.desc())
    items = (await db.scalars(stmt)).all()
    return [AccessRequestResponse.model_validate(item) for item in items]


@app.post("/api/access-requests/{request_id}/approve", response_model=AccessRequestResponse, tags=["AccessRequests"])
async def approve_access_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccessRequestResponse:
    request = await db.get(AccessRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Access request not found")
    await ensure_user_has_parking_access(db, current_user, request.parking_lot_id)
    if request.status != RequestStatusEnum.pending.value:
        raise HTTPException(status_code=400, detail="Only pending requests can be approved")
    request.status = RequestStatusEnum.approved.value

    plate = await db.scalar(
        select(AllowedPlate).where(
            AllowedPlate.parking_lot_id == request.parking_lot_id,
            AllowedPlate.plate_number == request.plate_number,
        )
    )
    if not plate:
        plate = AllowedPlate(
            parking_lot_id=request.parking_lot_id,
            plate_number=request.plate_number,
            allowed_days=request.allowed_days,
            time_start=request.time_start,
            time_end=request.time_end,
            is_active=True,
        )
        db.add(plate)
    await db.commit()
    await db.refresh(request)
    return AccessRequestResponse.model_validate(request)


@app.post("/api/access-requests/{request_id}/reject", response_model=AccessRequestResponse, tags=["AccessRequests"])
async def reject_access_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccessRequestResponse:
    request = await db.get(AccessRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Access request not found")
    await ensure_user_has_parking_access(db, current_user, request.parking_lot_id)
    if request.status != RequestStatusEnum.pending.value:
        raise HTTPException(status_code=400, detail="Only pending requests can be rejected")
    request.status = RequestStatusEnum.rejected.value
    await db.commit()
    await db.refresh(request)
    return AccessRequestResponse.model_validate(request)


@app.get("/api/scan-logs", response_model=list[ScanLogResponse], tags=["ScanLogs"])
async def list_scan_logs(
    parking_lot_id: str,
    camera_id: str | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ScanLogResponse]:
    await ensure_user_has_parking_access(db, current_user, parking_lot_id)
    bounded_limit = max(1, min(limit, 1000))
    stmt = select(ScanLog).where(ScanLog.parking_lot_id == parking_lot_id)
    if camera_id:
        stmt = stmt.where(ScanLog.camera_id == camera_id)
    stmt = stmt.order_by(ScanLog.timestamp.desc()).limit(bounded_limit)
    logs = (await db.scalars(stmt)).all()
    return [ScanLogResponse.model_validate(item) for item in logs]


@app.get("/api/scan-logs/analytics", response_model=DailyStatsResponse, tags=["ScanLogs"])
async def scan_logs_analytics(
    parking_lot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DailyStatsResponse:
    await ensure_user_has_parking_access(db, current_user, parking_lot_id)
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    logs_today_stmt = select(ScanLog).where(
        ScanLog.parking_lot_id == parking_lot_id,
        ScanLog.timestamp >= day_start,
        ScanLog.timestamp <= day_end,
    )
    logs_today = (await db.scalars(logs_today_stmt)).all()

    recognitions = len(logs_today)
    unique_plates = len({log.plate_number for log in logs_today})
    hours: dict[int, int] = {}
    for log in logs_today:
        hour = log.timestamp.astimezone(timezone.utc).hour
        hours[hour] = hours.get(hour, 0) + 1
    peak_hour_value = max(hours.items(), key=lambda item: item[1])[0] if hours else 0
    return DailyStatsResponse(
        recognitions_today=recognitions,
        unique_plates_today=unique_plates,
        peak_hour=f"{peak_hour_value:02d}:00-{peak_hour_value:02d}:59",
    )


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    return HealthResponse()


@app.post(
    "/api/v1/detections/raw",
    response_model=MessageResponse,
    dependencies=[Depends(verify_backend_api_key)],
    tags=["Detections"],
)
async def receive_raw_detection(payload: RawDetectionPayload) -> MessageResponse:
    item = payload.model_dump(mode="json")
    raw_history.append(item)
    await ws_hub.broadcast({"type": "raw_detection", "payload": item})
    return MessageResponse(message="Raw detection accepted")


@app.post(
    "/api/v1/detections",
    response_model=MessageResponse,
    dependencies=[Depends(verify_backend_api_key)],
    tags=["Detections"],
)
async def receive_confirmed_detection(payload: ConfirmedDetectionPayload) -> MessageResponse:
    item = payload.model_dump(mode="json")
    confirmed_history.append(item)
    ws_payload = dict(item)
    async for db in get_db():
        camera = await db.get(Camera, payload.camera_id)
        if camera:
            image_url = save_snapshot(payload.snapshot_base64)
            log_entry = ScanLog(
                parking_lot_id=camera.parking_lot_id,
                camera_id=camera.id,
                plate_number=payload.plate_text,
                photo_url=image_url,
                frame_width=payload.frame_width,
                frame_height=payload.frame_height,
                bbox_x1=payload.bbox.x1 if payload.bbox else None,
                bbox_y1=payload.bbox.y1 if payload.bbox else None,
                bbox_x2=payload.bbox.x2 if payload.bbox else None,
                bbox_y2=payload.bbox.y2 if payload.bbox else None,
                bbox_confidence=payload.bbox.confidence if payload.bbox else None,
            )
            db.add(log_entry)
            await db.commit()
            ws_payload["photo_url"] = log_entry.photo_url
            ws_payload["parking_lot_id"] = log_entry.parking_lot_id
            ws_payload["scan_log_id"] = log_entry.id
            ws_payload["timestamp"] = log_entry.timestamp.isoformat()
        else:
            logger.warning("Detection skipped for unknown camera id: %s", payload.camera_id)
        break
    await ws_hub.broadcast({"type": "confirmed_detection", "payload": ws_payload})
    logger.info("Confirmed detection: %s camera=%s", payload.plate_text, payload.camera_id)
    return MessageResponse(message="Detection accepted")


@app.get("/api/v1/detections", response_model=list[dict], tags=["Detections"])
async def list_detections(
    limit: int = 100,
    _: User = Depends(get_current_user),
) -> list[dict]:
    bounded_limit = max(1, min(limit, 200))
    return list(confirmed_history)[-bounded_limit:]


@app.get("/api/v1/video", tags=["Video"])
async def get_video(token: str | None = None) -> FileResponse:
    if not token:
        raise HTTPException(status_code=401, detail="Token is required")
    decode_access_token(token)
    video_path = settings.resolved_video_path
    try:
        return FileResponse(video_path, media_type="video/mp4")
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=f"Video not found: {video_path}") from exc


@app.get("/api/v1/ml/status", tags=["ML"])
async def get_ml_status(_: User = Depends(get_current_user)) -> dict:
    status = await request_ml("GET", "/api/v1/status")
    await ws_hub.broadcast({"type": "ml_status", "payload": status})
    return status


@app.post("/api/v1/ml/start", tags=["ML"])
async def start_ml(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    await sync_all_cameras_to_ml(db)
    await request_ml("POST", "/api/v1/pipeline/start")
    status = await request_ml("GET", "/api/v1/status")
    await ws_hub.broadcast({"type": "ml_status", "payload": status})
    return status


@app.post("/api/v1/ml/stop", tags=["ML"])
async def stop_ml(_: User = Depends(get_current_user)) -> dict:
    await request_ml("POST", "/api/v1/pipeline/stop")
    status = await request_ml("GET", "/api/v1/status")
    await ws_hub.broadcast({"type": "ml_status", "payload": status})
    return status


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decode_access_token(token)
    except HTTPException:
        await websocket.close(code=4401)
        return
    await ws_hub.connect(websocket)
    try:
        await ws_hub.send(
            websocket,
            {
                "type": "history",
                "payload": {
                    "confirmed": list(confirmed_history),
                    "raw": list(raw_history)[-50:],
                },
            },
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_hub.disconnect(websocket)
    except Exception:
        ws_hub.disconnect(websocket)
        raise


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
