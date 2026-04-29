"""
Mutable global state for the API layer.
These are set during app startup in main.py and accessed by route handlers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.services.detection_service import DetectionService
    from app.infrastructure.sender.http_event_sender import HttpEventSender

detection_service: DetectionService | None = None
event_sender: HttpEventSender | None = None
