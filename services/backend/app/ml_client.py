from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings


async def request_ml(method: str, path: str) -> dict[str, Any]:
    url = f"{settings.ml_url.rstrip('/')}{path}"
    headers = {"X-API-Key": settings.ml_api_key}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.request(method, url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ML service unavailable: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()
