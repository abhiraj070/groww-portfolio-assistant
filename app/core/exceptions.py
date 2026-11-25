"""Stable public errors; never include provider messages or credentials."""


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after


def invalid_response() -> ServiceError:
    return ServiceError("invalid_upstream_response", "Groww returned an unexpected response")
