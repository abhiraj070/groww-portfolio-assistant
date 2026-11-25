"""Authenticated, stateless Streamable HTTP for a single-account hosted MCP service."""

import secrets
from urllib.parse import urlsplit

from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.core.request_budget import RequestBudget
from app.mcp_server import create_mcp_server


def denied(status: int, code: str, message: str, headers=None):
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status, headers=headers
    )


class HostedMCPGuard:
    """Authorize the transport before discovery, parsing or access to shared account state."""

    def __init__(self, app, settings: Settings, host: str, origin: str):
        self.app, self.settings = app, settings
        self.host, self.origin = host, origin
        self.budget = RequestBudget(settings.api_requests_per_minute)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        # Health is liveness only, and must remain reachable by Render's internal checks.
        if scope["path"] == "/health" and scope["method"] in {"GET", "HEAD"}:
            await self.app(scope, receive, private_send)
            return
        headers = Headers(scope=scope)
        response = None
        try:
            self.budget.acquire()
        except ServiceError as exc:
            response = denied(
                429,
                "request_rate_limited",
                "MCP request limit reached",
                {"Retry-After": str(exc.retry_after)},
            )
        if response is None:
            expected = self.settings.mcp_bearer_token
            scheme, _, token = headers.get("authorization", "").partition(" ")
            if expected is None or self.settings.service_api_key is None:
                response = denied(503, "mcp_not_configured", "Configure hosted MCP authentication")
            elif scheme.lower() != "bearer" or not secrets.compare_digest(
                token.encode(), expected.get_secret_value().encode()
            ):
                response = denied(
                    401,
                    "unauthorized",
                    "Invalid or missing MCP Bearer token",
                    {"WWW-Authenticate": "Bearer"},
                )
            elif headers.get("host") != self.host:
                response = denied(421, "invalid_host", "Invalid MCP request host")
            elif headers.get("origin") not in {None, self.origin}:
                response = denied(403, "invalid_origin", "Invalid MCP request origin")
        if response is not None:
            await response(scope, receive, private_send)
            return
        await self.app(scope, receive, private_send)


def create_http_app(application=None):
    settings = get_settings()
    public_url = settings.mcp_public_url or settings.render_external_url
    origin = str(public_url).rstrip("/") if public_url else "http://localhost:8000"
    host = urlsplit(origin).netloc

    async def health(request: Request):
        return JSONResponse({"status": "ok", "mode": "read_only", "transport": "streamable_http"})

    server = create_mcp_server(application)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=1024 * 1024,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[host],
            allowed_origins=[origin],
        ),
        custom_starlette_routes=[Route("/health", health, methods=["GET"])],
    )
    app.add_middleware(HostedMCPGuard, settings=settings, host=host, origin=origin)
    return app
