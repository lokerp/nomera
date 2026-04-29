from __future__ import annotations

import logging

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    FastAPI dependency that validates the API key from the X-API-Key header.
    Returns the validated key on success, raises 401 on failure.
    """
    if x_api_key != settings.api_key:
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key
