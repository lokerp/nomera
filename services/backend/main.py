from __future__ import annotations

import logging
import sys

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import verify_backend_api_key
from app.config import settings
from app.ml_client import request_ml
from app.schemas import (
    ConfirmedDetectionPayload,
    HealthResponse,
    MessageResponse,
    RawDetectionPayload,
)
from app.state import confirmed_history, raw_history, ws_hub


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("nomera-backend")

app = FastAPI(
    title="Nomera Backend Demo",
    description="In-memory bridge between ML service and demo frontend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
    await ws_hub.broadcast({"type": "confirmed_detection", "payload": item})
    logger.info("Confirmed detection: %s camera=%s", payload.plate_text, payload.camera_id)
    return MessageResponse(message="Detection accepted")


@app.get("/api/v1/detections", response_model=list[ConfirmedDetectionPayload], tags=["Detections"])
async def list_detections(limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 200))
    return list(confirmed_history)[-limit:]


@app.get("/api/v1/video", tags=["Video"])
async def get_video() -> FileResponse:
    video_path = settings.resolved_video_path
    try:
        return FileResponse(video_path, media_type="video/mp4")
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=f"Video not found: {video_path}") from exc


@app.get("/api/v1/ml/status", tags=["ML"])
async def get_ml_status() -> dict:
    status = await request_ml("GET", "/api/v1/status")
    await ws_hub.broadcast({"type": "ml_status", "payload": status})
    return status


@app.post("/api/v1/ml/start", tags=["ML"])
async def start_ml() -> dict:
    await request_ml("POST", "/api/v1/pipeline/start")
    status = await request_ml("GET", "/api/v1/status")
    await ws_hub.broadcast({"type": "ml_status", "payload": status})
    return status


@app.post("/api/v1/ml/stop", tags=["ML"])
async def stop_ml() -> dict:
    await request_ml("POST", "/api/v1/pipeline/stop")
    status = await request_ml("GET", "/api/v1/status")
    await ws_hub.broadcast({"type": "ml_status", "payload": status})
    return status


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
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
