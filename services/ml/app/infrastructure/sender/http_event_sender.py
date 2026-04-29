from __future__ import annotations

import base64
import logging

import httpx

from app.domain.interfaces import IEventSender
from app.domain.enums import CameraRole
from app.domain.models import DetectionEvent, PlateDetection

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1.0  # seconds: 1, 2, 4


class HttpEventSender(IEventSender):
    """
    Sends DetectionEvent to the backend service via HTTP POST.
    Includes retry logic with exponential backoff.
    """

    def __init__(self, backend_url: str, backend_api_key: str) -> None:
        self._url = f"{backend_url.rstrip('/')}/api/v1/detections"
        self._raw_url = f"{backend_url.rstrip('/')}/api/v1/detections/raw"
        self._api_key = backend_api_key
        self._client: httpx.AsyncClient | None = None
        self._events_sent: int = 0
        self._events_failed: int = 0

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={
                    "X-API-Key": self._api_key,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def _event_to_payload(self, event: DetectionEvent) -> dict:
        """Serialize DetectionEvent to JSON-compatible dict."""
        payload = {
            "id": event.id,
            "plate_text": event.plate_text,
            "bbox": {
                "x1": event.bbox.x1,
                "y1": event.bbox.y1,
                "x2": event.bbox.x2,
                "y2": event.bbox.y2,
                "confidence": event.bbox.confidence,
            } if event.bbox else None,
            "camera_id": event.camera_id,
            "camera_role": event.camera_role.value,
            "region_name": event.region_name,
            "confidence": event.confidence,
            "first_seen": event.first_seen.isoformat(),
            "last_seen": event.last_seen.isoformat(),
            "occurrences": event.occurrences,
            "frame_number": event.frame_number,
            "timestamp_seconds": event.timestamp_seconds,
            "frame_width": event.frame_width,
            "frame_height": event.frame_height,
            "snapshot_base64": (
                base64.b64encode(event.snapshot_jpeg).decode("ascii")
                if event.snapshot_jpeg
                else None
            ),
        }
        return payload

    def _raw_payload(
        self,
        *,
        camera_id: str,
        camera_role: CameraRole,
        frame_number: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
        detections: list[PlateDetection],
    ) -> dict:
        return {
            "camera_id": camera_id,
            "camera_role": camera_role.value,
            "frame_number": frame_number,
            "timestamp_seconds": timestamp_seconds,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "detections": [
                {
                    "plate_text": det.plate_text,
                    "bbox": {
                        "x1": det.bbox.x1,
                        "y1": det.bbox.y1,
                        "x2": det.bbox.x2,
                        "y2": det.bbox.y2,
                        "confidence": det.bbox.confidence,
                    },
                    "confidence": det.confidence,
                    "region_name": det.region_name,
                }
                for det in detections
            ],
        }

    async def send(self, event: DetectionEvent) -> bool:
        """
        POST the detection event to the backend.
        Retries up to MAX_RETRIES times with exponential backoff.
        Returns True if accepted, False otherwise (but never raises).
        """
        import asyncio

        client = await self._ensure_client()
        payload = self._event_to_payload(event)

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.post(self._url, json=payload)
                if response.status_code in (200, 201, 202):
                    self._events_sent += 1
                    logger.info(
                        "Event sent to backend: plate=%s camera=%s (attempt %d)",
                        event.plate_text,
                        event.camera_id,
                        attempt + 1,
                    )
                    return True
                else:
                    logger.warning(
                        "Backend rejected event (HTTP %d): %s",
                        response.status_code,
                        response.text[:200],
                    )
            except httpx.HTTPError as e:
                logger.warning(
                    "Failed to send event to backend (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                )

            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_FACTOR * (2 ** attempt)
                await asyncio.sleep(delay)

        self._events_failed += 1
        logger.error(
            "Failed to send event after %d attempts: plate=%s",
            MAX_RETRIES,
            event.plate_text,
        )
        return False

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
        """POST raw detections once, without retrying or raising."""
        client = await self._ensure_client()
        payload = self._raw_payload(
            camera_id=camera_id,
            camera_role=camera_role,
            frame_number=frame_number,
            timestamp_seconds=timestamp_seconds,
            frame_width=frame_width,
            frame_height=frame_height,
            detections=detections,
        )

        try:
            response = await client.post(self._raw_url, json=payload, timeout=2.0)
            if response.status_code in (200, 201, 202):
                return True
            logger.debug("Backend rejected raw detections (HTTP %d)", response.status_code)
        except httpx.HTTPError as e:
            logger.debug("Failed to send raw detections: %s", e)
        return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def events_sent(self) -> int:
        return self._events_sent

    @property
    def events_failed(self) -> int:
        return self._events_failed
