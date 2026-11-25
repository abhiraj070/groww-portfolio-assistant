import logging

import anyio
import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import RedactingFormatter, configure_secret_redaction
from app.main import create_app
from app.mcp_http import create_http_app
from tests.test_api import TEST_KEY

BEARER = "synthetic-hosted-mcp-bearer-token-not-real"
ORIGIN = "https://synthetic-mcp.onrender.com"


def configure(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    monkeypatch.setenv("MCP_BEARER_TOKEN", BEARER)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", ORIGIN)


def test_http_auth_guards_discovery_and_all_methods(monkeypatch):
    configure(monkeypatch)

    async def run():
        app = create_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=ORIGIN
            ) as client:
                for method in ("GET", "POST", "DELETE", "OPTIONS"):
                    for headers in ({}, {"Authorization": "Bearer wrong"}, {"X-API-Key": TEST_KEY}):
                        response = await client.request(method, "/mcp", headers=headers)
                        assert response.status_code == 401
                        assert response.headers["WWW-Authenticate"] == "Bearer"
                        assert response.headers["Cache-Control"] == "no-store"
                        assert BEARER not in response.text and TEST_KEY not in response.text
                assert (await client.get("/health")).json()["transport"] == "streamable_http"
                assert (await client.get("/api/v1/stocks/holdings")).status_code == 401

    anyio.run(run)


def test_real_http_mcp_protocol_and_shared_lifecycle(monkeypatch):
    configure(monkeypatch)

    async def run():
        platform = create_app()
        app = create_http_app(platform)
        with anyio.fail_after(30):
            async with app.router.lifespan_context(app):
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    headers={"Authorization": f"Bearer {BEARER}"},
                ) as client:
                    async with streamable_http_client(
                        ORIGIN + "/mcp", http_client=client
                    ) as streams:
                        async with ClientSession(*streams[:2], read_timeout_seconds=20) as session:
                            await session.initialize()
                            assert len((await session.list_tools()).tools) == 57
                            result = await session.call_tool("get_health", {})
                            assert not result.is_error
                            result = await session.call_tool("get_mf_benchmark_returns", {})
                            assert result.structured_content["data"]["available"] is False
                            result = await session.call_tool(
                                "get_stocks_ltp_by_symbol", {"symbol": "SYNTH"}
                            )
                            assert result.is_error
                            assert (
                                result.structured_content["error"]["code"] == "groww_not_configured"
                            )
        assert platform.state.services.client._http.is_closed

    anyio.run(run)


def test_host_origin_size_guards_and_private_headers(monkeypatch):
    configure(monkeypatch)

    async def run():
        app = create_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
                headers={"Authorization": f"Bearer {BEARER}"},
            ) as client:
                for headers, status in [
                    ({"Host": "evil.invalid"}, 421),
                    ({"Origin": "https://evil.invalid"}, 403),
                ]:
                    response = await client.post("/mcp", json={}, headers=headers)
                    assert response.status_code == status
                    assert response.headers["Cache-Control"] == "no-store"
                response = await client.post(
                    "/mcp",
                    content=b" " * (1024 * 1024 + 1),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
                assert response.status_code == 413
                response = await client.get("/api/v1/stocks/holdings")
                assert (
                    response.status_code == 404
                )  # REST platform is internal, not mounted publicly.

    anyio.run(run)


@pytest.mark.parametrize("missing", ["SERVICE_API_KEY", "MCP_BEARER_TOKEN"])
def test_missing_auth_configuration_fails_closed(monkeypatch, missing):
    configure(monkeypatch)
    monkeypatch.delenv(missing)

    async def run():
        app = create_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=ORIGIN
            ) as client:
                assert (await client.get("/health")).status_code == 200
                response = await client.post("/mcp", headers={"Authorization": f"Bearer {BEARER}"})
                assert response.status_code == 503

    anyio.run(run)


def test_bad_auth_requests_consume_transport_budget(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("API_REQUESTS_PER_MINUTE", "1")

    async def run():
        app = create_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=ORIGIN
            ) as client:
                assert (await client.get("/mcp")).status_code == 401
                response = await client.get("/mcp")
                assert response.status_code == 429
                assert int(response.headers["Retry-After"]) > 0
                assert (await client.get("/health")).status_code == 200

    anyio.run(run)


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.invalid",
        "https://user:pass@remote.invalid",
        "https://remote.invalid/mcp",
        "https://remote.invalid?secret=bad",
    ],
)
def test_unsafe_public_url_rejected(url):
    with pytest.raises(ValidationError):
        Settings(mcp_public_url=url)


def test_token_validation_and_redaction():
    for value in ("short", "abc def" * 10):
        with pytest.raises(ValidationError):
            Settings(mcp_bearer_token=value)
    settings = Settings(mcp_bearer_token=BEARER)
    assert BEARER not in repr(settings)
    configure_secret_redaction(settings)
    record = logging.LogRecord("test", logging.WARNING, "synthetic", 1, BEARER, (), None)
    assert BEARER not in RedactingFormatter(logging.Formatter()).format(record)
