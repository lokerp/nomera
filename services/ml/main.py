"""
Nomera ML Service — License Plate Recognition for Smart Parking.

Entry point: initializes FastAPI, loads models, and starts processing.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api import _state
from app.api.router import router
from app.config import settings
from app.infrastructure.detector.factory import create_detector
from app.infrastructure.sender.http_event_sender import HttpEventSender
from app.application.services.detection_service import DetectionService

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("nomera-ml")


# ─── Application lifespan ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # --- Startup ---
    logger.info("=" * 60)
    logger.info("  Nomera ML Service starting...")
    logger.info("=" * 60)

    # 1. Initialize detector via factory (loads ML models)
    detector = create_detector(settings)
    detector.warmup()

    # 2. Initialize event sender
    sender = HttpEventSender(
        backend_url=settings.backend_url,
        backend_api_key=settings.backend_api_key,
    )

    # 3. Initialize detection service
    service = DetectionService(
        detector=detector,
        event_sender=sender,
        settings=settings,
    )

    # 4. Set global state for API routes
    _state.detection_service = service
    _state.event_sender = sender

    # 5. Keep pipeline always running (24/7), cameras can be added dynamically.
    await service.start()

    logger.info("ML Service ready on http://%s:%d", settings.host, settings.port)
    logger.info("API docs: http://%s:%d/docs", settings.host, settings.port)

    yield

    # --- Shutdown ---
    logger.info("Shutting down ML Service...")
    await service.stop()
    await sender.close()
    logger.info("ML Service stopped.")


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nomera ML Service",
    description="License plate recognition service for smart parking systems",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
