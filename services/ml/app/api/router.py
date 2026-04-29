from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import verify_api_key
from app.api.schemas import (
    CameraCreateRequest,
    CameraCreatedResponse,
    CameraStatusSchema,
    HealthResponse,
    MessageResponse,
    PipelineStatusSchema,
)
from app.domain.enums import CameraRole
from app.domain.models import CameraConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _get_detection_service():
    """Get the global DetectionService instance (set at app startup)."""
    from app.api._state import detection_service
    if detection_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return detection_service


def _get_event_sender():
    """Get the global EventSender instance (set at app startup)."""
    from app.api._state import event_sender
    return event_sender


# ─── Health (no auth) ────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for Docker/k8s probes. No authentication required."""
    return HealthResponse()


# ─── Pipeline management ─────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=PipelineStatusSchema,
    tags=["Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
async def get_status():
    """Get current pipeline status and all camera statuses."""
    svc = _get_detection_service()
    sender = _get_event_sender()

    cameras = []
    for cam_id, state in svc.cameras.items():
        cameras.append(CameraStatusSchema(
            camera_id=cam_id,
            role=state.config.role.value,
            source=state.config.source,
            is_active=state.is_active,
            frames_processed=state.frames_processed,
            detections_count=state.detections_count,
            error=state.last_error,
        ))

    return PipelineStatusSchema(
        status=svc.status.value,
        cameras=cameras,
        total_events_sent=sender.events_sent if sender else 0,
        total_events_failed=sender.events_failed if sender else 0,
        uptime_seconds=round(svc.uptime, 1),
    )


@router.post(
    "/pipeline/start",
    response_model=MessageResponse,
    tags=["Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
async def start_pipeline():
    """Start the detection pipeline for all registered cameras."""
    svc = _get_detection_service()
    await svc.start()
    return MessageResponse(message="Pipeline started")


@router.post(
    "/pipeline/stop",
    response_model=MessageResponse,
    tags=["Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
async def stop_pipeline():
    """Stop the detection pipeline for all cameras."""
    svc = _get_detection_service()
    await svc.stop()
    return MessageResponse(message="Pipeline stopped")


# ─── Camera management ───────────────────────────────────────────────────────

@router.get(
    "/cameras",
    response_model=list[CameraStatusSchema],
    tags=["Cameras"],
    dependencies=[Depends(verify_api_key)],
)
async def list_cameras():
    """List all registered cameras and their statuses."""
    svc = _get_detection_service()
    result = []
    for cam_id, state in svc.cameras.items():
        result.append(CameraStatusSchema(
            camera_id=cam_id,
            role=state.config.role.value,
            source=state.config.source,
            is_active=state.is_active,
            frames_processed=state.frames_processed,
            detections_count=state.detections_count,
            error=state.last_error,
        ))
    return result


@router.post(
    "/cameras",
    response_model=CameraCreatedResponse,
    status_code=201,
    tags=["Cameras"],
    dependencies=[Depends(verify_api_key)],
)
async def add_camera(req: CameraCreateRequest):
    """Register a new camera source."""
    svc = _get_detection_service()

    camera_id = req.camera_id or f"cam-{uuid4().hex[:8]}"
    roi = tuple(req.roi_zone) if req.roi_zone else None

    config = CameraConfig(
        camera_id=camera_id,
        source=req.source,
        role=req.role,
        roi_zone=roi,
    )

    try:
        cam_id = await svc.add_camera(config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return CameraCreatedResponse(camera_id=cam_id)


@router.delete(
    "/cameras/{camera_id}",
    response_model=MessageResponse,
    tags=["Cameras"],
    dependencies=[Depends(verify_api_key)],
)
async def remove_camera(camera_id: str):
    """Remove a camera and stop its processing."""
    svc = _get_detection_service()
    try:
        await svc.remove_camera(camera_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return MessageResponse(message=f"Camera {camera_id} removed")
