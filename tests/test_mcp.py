import json
import re
from pathlib import Path
from unittest.mock import Mock

import anyio
import httpx
import pytest
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_client_server_memory_streams

from app.api.dependencies import get_services
from app.core.exceptions import ServiceError
from app.main import create_app
from app.mcp_catalog import ENDPOINTS, build_catalog
from app.mcp_server import MCPBridge, create_mcp_server
from app.schemas.market_data import LTPResponse
from tests.test_api import TEST_KEY


def test_catalog_covers_every_endpoint_and_retains_constraints():
    document = create_app().openapi()
    catalog = build_catalog(document)
    assert set(ENDPOINTS) == set(document["paths"])
    assert len(catalog) == len(ENDPOINTS) == 57
    for spec in catalog.values():
        assert re.fullmatch(r"[a-z0-9_]{1,64}", spec.tool.name)
        assert "get" in document["paths"][spec.path]
        assert spec.tool.annotations.read_only_hint
        assert not spec.tool.annotations.destructive_hint
        assert spec.tool.input_schema["additionalProperties"] is False
        assert spec.path in spec.tool.description
        Draft202012Validator.check_schema(spec.tool.input_schema)
        Draft202012Validator.check_schema(spec.tool.output_schema)
        for parameter in spec.parameters:
            assert spec.tool.input_schema["properties"][parameter["name"]] == parameter["schema"]
    assert not any("api_key" in json.dumps(s.tool.input_schema).lower() for s in catalog.values())


def test_no_unreviewed_routes_automatically_become_tools():
    app = create_app()

    @app.get("/api/v1/future-route")
    def future():
        return {}

    assert all(s.path != "/api/v1/future-route" for s in build_catalog(app.openapi()).values())


def test_documented_tool_mapping_matches_the_live_catalog():
    root = Path(__file__).resolve().parents[1]
    documented = (root / "docs" / "mcp.md").read_text(encoding="utf-8")
    mapping = re.findall(r"\| `([^`]+)` \| `([^`]+)` \|", documented)
    assert dict(mapping) == {
        name: spec.path for name, spec in build_catalog(create_app().openapi()).items()
    }


def example_arguments(spec):
    examples = {
        "symbol": "SYNTH",
        "order_id": "SYNTH-ORDER",
        "scheme_id": "123",
        "groww_symbol": "NSE-SYNTH",
        "start_time": "2025-01-01T09:00:00+05:30",
        "end_time": "2025-01-02T09:00:00+05:30",
    }
    return {p["name"]: examples[p["name"]] for p in spec.parameters if p.get("required")}


def test_every_tool_dispatches_only_its_get_endpoint(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)

    async def run():
        observed = []

        def respond(request):
            observed.append(request)
            assert request.method == "GET"
            assert request.url.host == "platform.internal"
            return httpx.Response(
                200, json={"exact_decimal": "123456789.1234567890", "unknown": None}
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://platform.internal"
        ) as client:
            bridge = MCPBridge(create_app(), client)
            for name, spec in bridge.catalog.items():
                args = example_arguments(spec)
                result = await bridge.call(name, args)
                assert not result.is_error
                assert result.structured_content["data"]["exact_decimal"] == "123456789.1234567890"
                assert result.structured_content["data"]["unknown"] is None
                expected = spec.path
                for key, value in args.items():
                    expected = expected.replace("{" + key + "}", value)
                assert observed[-1].url.path == expected
                assert (observed[-1].headers.get("X-API-Key") == TEST_KEY) == (
                    spec.path != "/health"
                )
            before = len(observed)
            for name, args in [
                ("place_order", {}),
                ("get_stocks_orders", {"page_size": 26}),
                ("get_stocks_orders", {"page": True}),
                ("get_stocks_ltp_by_symbol", {"symbol": "../private"}),
                ("get_stocks_ltp_by_symbol", {}),
                ("get_mf_nav_by_scheme_id", {"scheme_id": "bad"}),
                ("get_health", {"url": "https://example.invalid"}),
                ("get_health", {"api_key": "synthetic-sensitive-input"}),
            ]:
                result = await bridge.call(name, args)
                assert result.is_error
                assert "synthetic-sensitive-input" not in result.model_dump_json()
            assert len(observed) == before

    anyio.run(run)


def test_mcp_protocol_roundtrip_auth_validation_and_lifecycle(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    app, services = create_app(), Mock()
    services.market.get_ltp.return_value = LTPResponse(
        symbol="SYNTH", price="12.34567890", retrieved_at="2026-01-01T00:00:00Z"
    )
    app.dependency_overrides[get_services] = lambda: services
    owned = Mock(wraps=__import__("app.services.container", fromlist=["Services"]).Services.build)
    monkeypatch.setattr("app.main.Services.build", owned)

    async def run():
        server = create_mcp_server(app)
        assert server.middleware == []
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                group.start_soon(
                    server.run, *server_streams, server.create_initialization_options()
                )
                async with ClientSession(*client_streams, read_timeout_seconds=20) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert len(tools.tools) == 57
                    health = await session.call_tool("get_health", {})
                    assert not health.is_error
                    assert health.structured_content["data"]["mode"] == "read_only"
                    quote = await session.call_tool("get_stocks_ltp_by_symbol", {"symbol": "SYNTH"})
                    assert quote.structured_content["data"]["price"] == "12.34567890"
                    schema = next(
                        t.output_schema for t in tools.tools if t.name == "get_stocks_ltp_by_symbol"
                    )
                    Draft202012Validator(schema).validate(quote.structured_content)
                    invalid = await session.call_tool(
                        "get_stocks_candles",
                        {
                            "groww_symbol": "NSE-SYNTH",
                            "start_time": "2026-01-02",
                            "end_time": "2026-01-01",
                        },
                    )
                    assert invalid.is_error
                    assert invalid.structured_content["error"]["code"] == "validation_error"
                    missing = await session.call_tool(
                        "get_mf_nav_by_scheme_id", {"scheme_id": "123"}
                    )
                    # Stubbed services must return validated data; unexpected stub output sanitizes.
                    assert missing.is_error
                group.cancel_scope.cancel()
        assert app.state.services.client._http.is_closed

    anyio.run(run)
    services.market.get_ltp.assert_called_once_with("SYNTH", "NSE", "CASH")


@pytest.mark.parametrize("configured", [False, True])
def test_real_api_auth_rate_limits_and_provider_errors(monkeypatch, configured):
    if configured:
        monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    monkeypatch.setenv("API_REQUESTS_PER_MINUTE", "1")

    async def run():
        app = create_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://platform.internal",
            ) as client:
                bridge = MCPBridge(app, client)
                result = await bridge.call("get_stocks_ltp_by_symbol", {"symbol": "SYNTH"})
                assert result.is_error
                assert result.structured_content["error"]["code"] == (
                    "groww_not_configured" if configured else "http_503"
                )
                result = await bridge.call("get_mf_holdings", {})
                assert result.structured_content["status"] == 429
                assert int(result.structured_content["retry_after"]) > 0
                assert not (await bridge.call("get_health", {})).is_error

    anyio.run(run)


def test_unexpected_errors_never_expose_details():
    async def run():
        async def broken(request):
            raise RuntimeError("synthetic-private-token-account-value")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(broken), base_url="http://platform.internal"
        ) as client:
            result = await MCPBridge(create_app(), client).call("get_health", {})
            assert result.is_error
            assert "synthetic-private" not in result.model_dump_json()

    anyio.run(run)


@pytest.mark.parametrize(
    "code,status,retry", [("upstream_timeout", 504, None), ("rate_limited", 429, 60)]
)
def test_provider_failures_preserved_through_tool_boundary(monkeypatch, code, status, retry):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    services = Mock()
    services.market.get_ltp.side_effect = ServiceError(
        code, "Synthetic safe provider error", status, retry
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services

    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://platform.internal"
            ) as client:
                result = await MCPBridge(app, client).call(
                    "get_stocks_ltp_by_symbol", {"symbol": "SYNTH"}
                )
                assert result.is_error
                assert result.structured_content["status"] == status
                assert result.structured_content["error"]["code"] == code
                if retry:
                    assert result.structured_content["retry_after"] == str(retry)

    anyio.run(run)


def test_real_stdio_handshake_and_tool_call(tmp_path):
    import sys

    root = Path(__file__).resolve().parents[1]

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            cwd=str(tmp_path),
            env={
                "PYTHONPATH": str(root),
                "SERVICE_API_KEY": TEST_KEY,
                "LEDGER_PATH": str(tmp_path / "private.db"),
                "GROWW_API_KEY": "",
                "GROWW_API_SECRET": "",
                "GROWW_TOTP_SECRET": "",
            },
        )
        with anyio.fail_after(30):
            async with stdio_client(params) as streams:
                async with ClientSession(*streams, read_timeout_seconds=20) as session:
                    await session.initialize()
                    assert len((await session.list_tools()).tools) == 57
                    assert not (await session.call_tool("get_health", {})).is_error
                    result = await session.call_tool("get_mf_benchmark_returns", {})
                    assert result.structured_content["data"]["available"] is False

    anyio.run(run)
