"""Official MCP stdio transport over the platform's authenticated in-process REST boundary."""

import argparse
import json
import logging
import sys
from contextlib import asynccontextmanager
from urllib.parse import quote

import anyio
import httpx
from jsonschema import Draft202012Validator
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from app.core.config import get_settings
from app.main import create_app
from app.mcp_catalog import build_catalog


def failure(code: str, message: str, status: int, retry_after: str | None = None):
    error = {"error": {"code": code, "message": message}, "status": status}
    if retry_after is not None:
        error["retry_after"] = retry_after
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=json.dumps(error))],
        structuredContent=error,
    )


class MCPBridge:
    def __init__(self, application, client: httpx.AsyncClient):
        self.catalog = build_catalog(application.openapi())
        self.client = client
        self.validators = {
            name: Draft202012Validator(spec.tool.input_schema)
            for name, spec in self.catalog.items()
        }

    async def call(self, name: str, arguments: dict | None):
        spec = self.catalog.get(name)
        if spec is None:
            return failure("unknown_tool", "Unknown read-only platform tool", 404)
        arguments = {} if arguments is None else arguments
        if not self.validators[name].is_valid(arguments):
            return failure("validation_error", "Tool argument validation failed", 422)
        path, query = spec.path, {}
        for parameter in spec.parameters:
            value = arguments.get(parameter["name"])
            if value is None:
                continue
            if parameter["in"] == "path":
                path = path.replace("{" + parameter["name"] + "}", quote(str(value), safe=""))
            else:
                query[parameter["name"]] = value
        # Keys are local transport configuration, never model arguments or discovery metadata.
        key = get_settings().service_api_key
        headers = (
            {} if key is None or spec.path == "/health" else {"X-API-Key": key.get_secret_value()}
        )
        try:
            response = await self.client.get(path, params=query, headers=headers)
            payload = response.json()
            if response.is_error:
                # The existing API owns error sanitization. Never return a raw provider response.
                detail = payload.get("error", {})
                return failure(
                    detail.get("code", "request_failed"),
                    detail.get("message", "Platform request failed"),
                    response.status_code,
                    response.headers.get("Retry-After"),
                )
            data = {"data": payload}
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(data, allow_nan=False))],
                structuredContent=data,
            )
        except Exception:
            # Do not log exceptions: validation/provider errors can contain private input/data.
            return failure("internal_error", "Platform tool failed", 500)


def create_mcp_server(application=None) -> Server:
    application = application if application is not None else create_app()
    catalog = build_catalog(application.openapi())

    @asynccontextmanager
    async def lifespan(server):
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
                base_url="http://platform.internal",
                trust_env=False,
            ) as client:
                yield MCPBridge(application, client)

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[entry.tool for entry in catalog.values()])

    async def call_tool(ctx, params):
        return await ctx.lifespan_context.call(params.name, params.arguments)

    server = Server(
        "groww-portfolio-assistant",
        version="0.1.0",
        lifespan=lifespan,
        instructions=(
            "Read-only personal investment data. Keep source dates, nulls, scope and coverage "
            "warnings. Never infer missing history or financial capabilities."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
    # Disable optional telemetry middleware so account calls cannot become exported spans.
    server.middleware.clear()
    return server


async def run_stdio():
    # SDK 2 owns stdout's protocol descriptor, diverting incidental library prints to stderr.
    async with stdio_server() as (read_stream, write_stream):
        server = create_mcp_server()
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Groww platform MCP server (stdio)")
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print endpoint/tool mapping without starting a session",
    )
    args = parser.parse_args()
    if args.list_tools:
        for entry in build_catalog(create_app().openapi()).values():
            print(f"{entry.tool.name}\tGET {entry.path}")
        return 0
    logging.basicConfig(level=logging.WARNING)
    try:
        anyio.run(run_stdio)
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("MCP startup failed; check local configuration and dependencies.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
