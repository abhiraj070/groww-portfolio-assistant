"""Minimal Phase 1 application; no Groww operations are implemented yet."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.config import get_settings
from app.schemas.common import ErrorDetail, ErrorResponse, HealthResponse


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump())


@asynccontextmanager
async def lifespan(application: FastAPI):
    get_settings()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Groww Portfolio Assistant",
        version="0.1.0",
        description="Read-only personal portfolio service. Phase 1: configuration and health only.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        messages = {
            401: "Invalid or missing API key",
            403: "Access denied",
            404: "Resource not found",
            405: "Method not allowed",
            503: "Local API authentication is not configured",
        }
        return error_response(
            exc.status_code,
            f"http_{exc.status_code}",
            messages.get(exc.status_code, "Request failed"),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_error", "Request validation failed")

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return error_response(500, "internal_error", "An unexpected error occurred")

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    return application


app = create_app()
