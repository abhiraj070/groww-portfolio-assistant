"""Redact configured secrets and generated tokens after traceback formatting."""

import logging
import re
from threading import RLock

_lock = RLock()
_secrets: set[str] = set()


def register_secret(value: str) -> None:
    if value:
        with _lock:
            _secrets.add(value)


class RedactingFormatter(logging.Formatter):
    def __init__(self, wrapped: logging.Formatter):
        super().__init__()
        self.wrapped = wrapped

    def format(self, record: logging.LogRecord) -> str:
        rendered = self.wrapped.format(record)
        with _lock:
            for value in sorted(_secrets, key=len, reverse=True):
                rendered = rendered.replace(value, "[REDACTED]")
        return re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [REDACTED]", rendered)


def configure_secret_redaction(settings) -> None:
    for value in (
        settings.service_api_key,
        settings.mcp_bearer_token,
        settings.groww_api_key,
        settings.groww_api_secret,
        settings.groww_totp_secret,
    ):
        if value is not None:
            register_secret(value.get_secret_value())
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore", "urllib3"):
        logger = logging.getLogger(name)
        for handler in logger.handlers:
            if not isinstance(handler.formatter, RedactingFormatter):
                handler.setFormatter(RedactingFormatter(handler.formatter or logging.Formatter()))
