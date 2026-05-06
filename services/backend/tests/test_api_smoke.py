from __future__ import annotations

import base64
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from main import app


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_rbac_and_flow() -> None:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    if db_path:
        Path(db_path).unlink(missing_ok=True)

    with TestClient(app) as client:
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]

        parking_name = f"Lot-{uuid.uuid4().hex[:6]}"
        create_lot = client.post(
            "/api/parking-lots",
            headers=auth_headers(admin_token),
            json={"name": parking_name, "description": "Main gate"},
        )
        assert create_lot.status_code == 200
        parking_lot_id = create_lot.json()["id"]

        guard_username = f"guard_{uuid.uuid4().hex[:6]}"
        create_guard = client.post(
            "/api/users",
            headers=auth_headers(admin_token),
            json={
                "username": guard_username,
                "password": "guard1234",
                "role": "guard",
                "parking_lot_ids": [parking_lot_id],
            },
        )
        assert create_guard.status_code == 200

        create_camera = client.post(
            "/api/cameras",
            headers=auth_headers(admin_token),
            json={
                "id": f"cam-{uuid.uuid4().hex[:6]}",
                "parking_lot_id": parking_lot_id,
                "name": "Gate camera",
                "stream_url": "rtsp://example/stream",
            },
        )
        assert create_camera.status_code == 200
        camera_id = create_camera.json()["id"]

        guard_login = client.post("/api/auth/login", json={"username": guard_username, "password": "guard1234"})
        assert guard_login.status_code == 200
        guard_token = guard_login.json()["access_token"]

        forbidden_camera_create = client.post(
            "/api/cameras",
            headers=auth_headers(guard_token),
            json={
                "id": "cam-forbidden",
                "parking_lot_id": parking_lot_id,
                "name": "Nope",
                "stream_url": "rtsp://x",
            },
        )
        assert forbidden_camera_create.status_code == 403

        public_request = client.post(
            "/api/public/requests",
            json={
                "parking_lot_id": parking_lot_id,
                "plate_number": "A123BC777",
                "allowed_days": "1,2,3,4,5",
                "time_start": "08:00",
                "time_end": "18:00",
            },
        )
        assert public_request.status_code == 200
        request_id = public_request.json()["id"]

        approve = client.post(
            f"/api/access-requests/{request_id}/approve",
            headers=auth_headers(guard_token),
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"

        allowed_plates = client.get(
            f"/api/allowed-plates?parking_lot_id={parking_lot_id}",
            headers=auth_headers(guard_token),
        )
        assert allowed_plates.status_code == 200
        assert any(item["plate_number"] == "A123BC777" for item in allowed_plates.json())

        detection = client.post(
            "/api/v1/detections",
            headers={"X-API-Key": settings.backend_api_key},
            json={
                "id": str(uuid.uuid4()),
                "plate_text": "A123BC777",
                "bbox": None,
                "camera_id": camera_id,
                "camera_role": "in",
                "region_name": "RU",
                "confidence": 0.91,
                "first_seen": "2026-05-06T10:00:00Z",
                "last_seen": "2026-05-06T10:00:01Z",
                "occurrences": 3,
                "frame_number": 1,
                "timestamp_seconds": 1.0,
                "frame_width": 1920,
                "frame_height": 1080,
                "snapshot_base64": base64.b64encode(b"test-image").decode(),
            },
        )
        assert detection.status_code == 200

        logs = client.get(
            f"/api/scan-logs?parking_lot_id={parking_lot_id}",
            headers=auth_headers(guard_token),
        )
        assert logs.status_code == 200
        assert len(logs.json()) >= 1
