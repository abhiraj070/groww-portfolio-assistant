"""Read-only portfolio HTTP application."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.routes import market_data, portfolio
from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.core.logging import configure_secret_redaction
from app.core.security import require_api_key
from app.schemas.common import ErrorDetail, ErrorResponse, HealthResponse
from app.services.container import Services


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump())


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_secret_redaction(settings)
    application.state.services = Services.build(settings)
    try:
        yield
    finally:
        application.state.services.client.close()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Groww Portfolio Assistant",
        version="0.1.0",
        description="Read-only personal Groww portfolio service.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    private = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
    private.include_router(portfolio.router)
    private.include_router(market_data.router)
    application.include_router(private)

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        response = error_response(exc.status, exc.code, exc.message)
        if exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

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
