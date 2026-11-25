"""Shared local API authentication for future portfolio and market routes."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    provided: Annotated[str | None, Security(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    expected = settings.service_api_key
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local API authentication is not configured",
        )
    if provided is None or not secrets.compare_digest(
        provided.encode("utf-8"), expected.get_secret_value().encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
