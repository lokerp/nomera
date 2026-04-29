from __future__ import annotations

import logging

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_backend_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if x_api_key != settings.backend_api_key:
        logger.warning("Invalid backend API key attempt")
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key
