"""Reviewed GET-only MCP surface. New REST routes require explicit review before exposure."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from mcp import types

# Paths are explicit: no caller-selected URL, SDK method, import, or financial write.
ENDPOINTS = {
    "/health": "Process liveness only; does not verify provider readiness.",
    "/api/v1/portfolio/holdings": "Legacy raw equity holdings; no market valuation.",
    "/api/v1/portfolio/positions": "Positions snapshot, separate from holdings valuation.",
    "/api/v1/portfolio/orders": "Paginated current-day orders, not lifetime history.",
    "/api/v1/portfolio/summary": "Holdings valuation; realised P&L covers current positions only.",
    "/api/v1/portfolio/analytics": "Equity valuation, sectors, concentration and rankings.",
    "/api/v1/portfolio/account": "Private account profile, not credentials.",
    "/api/v1/market/quote/{symbol}": "Latest provider quote and retrieval timestamp.",
    "/api/v1/market/ltp/{symbol}": "Last traded price; retrieval time is not last-trade time.",
    "/api/v1/market/ohlc/{symbol}": "Current OHLC snapshot, not interval candles.",
    "/api/v1/market/candles": "Historical interval candles for a validated time window.",
    "/api/v1/stocks/positions": "Positions snapshot, separate from holdings valuation.",
    "/api/v1/stocks/orders": "Paginated current-day orders, not lifetime history.",
    "/api/v1/stocks/portfolio/summary": "Holdings value; realised P&L is current positions only.",
    "/api/v1/stocks/portfolio/analytics": "Equity valuation, sectors, concentration and rankings.",
    "/api/v1/stocks/quote/{symbol}": "Latest provider quote and retrieval timestamp.",
    "/api/v1/stocks/ltp/{symbol}": "Last traded price and retrieval timestamp.",
    "/api/v1/stocks/ohlc/{symbol}": "Current OHLC snapshot, not interval candles.",
    "/api/v1/stocks/candles": "Historical interval candles for a validated time window.",
    "/api/v1/stocks/portfolio/allocation": "Valued holdings and complete-denominator weights.",
    "/api/v1/stocks/holdings": "Valued stock holdings with cost, prices, returns and weights.",
    "/api/v1/stocks/orders/{order_id}": "Provider detail for a known order ID.",
    "/api/v1/stocks/orders/{order_id}/trades": "Paginated provider executions for one known order.",
    "/api/v1/stocks/tradebook": "Imported delivery execution ledger; not certified complete.",
    "/api/v1/stocks/trades": "Imported delivery ledger alias, not live execution discovery.",
    "/api/v1/stocks/sold": "Imported stocks with sales, including partial/incomplete histories.",
    "/api/v1/stocks/realised-pnl": "Imported equity FIFO lots and gains, not position P&L.",
    "/api/v1/stocks/instruments": "Bounded official public CASH instrument catalog.",
    "/api/v1/mf/portfolio/allocation": "Statement MF units and value weights by folio/scheme.",
    "/api/v1/mf/holdings": "Statement-backed MF holdings; imported NAV dates may be stale.",
    "/api/v1/mf/realised-pnl": "Imported MF FIFO matches, charges and gross/net gains.",
    "/api/v1/mf/portfolio/returns": "MF unrealised changes; not cash-flow XIRR.",
    "/api/v1/mf/portfolio/analytics": "Statement-backed MF valuation and FIFO analytics.",
    "/api/v1/mf/portfolio/summary": "Statement-backed MF valuation, coverage and NAV dates.",
    "/api/v1/mf/transactions": "Paginated imported MF statement events and provenance.",
    "/api/v1/mf/purchases": "MF purchases, SIPs, switch-ins and reinvestments.",
    "/api/v1/mf/redemptions": "Imported redemptions and switch-outs.",
    "/api/v1/mf/sip/history": "Executed SIP instalments; not active mandates or future schedules.",
    "/api/v1/mf/sip": "Executed SIP instalments; not active mandates or future schedules.",
    "/api/v1/mf/dividends": "Imported dividends and reinvestment income; avoid double counting.",
    "/api/v1/mf/nav/{scheme_id}": "Latest imported NAV observation, source and date; not live NAV.",
    "/api/v1/mf/nav/{scheme_id}/history": "Imported NAV history within inclusive date bounds.",
    "/api/v1/mf/schemes": "Latest imported NAV metadata per scheme.",
    "/api/v1/mf/benchmark-returns": "Unavailable metric with required benchmark data sources.",
    "/api/v1/mf/expense-ratio": "Unavailable metric with required plan-specific disclosure source.",
    "/api/v1/mf/fund-overlap": "Unavailable metric with required constituent-weight sources.",
    "/api/v1/analytics/asset-allocation": "Equity/MF values and allocation, excluding cash.",
    "/api/v1/analytics/unrealised-gains": "Combined remaining cost and unrealised gains.",
    "/api/v1/analytics/total-investment": "Remaining acquisition cost, not lifetime subscriptions.",
    "/api/v1/analytics/net-worth": "Equity plus MF value; excludes cash, debts and other assets.",
    "/api/v1/analytics/realised-gains": "Imported equity/MF FIFO gains, income and fee coverage.",
    "/api/v1/analytics/performance": "Dated returns/XIRR; missing snapshots yield unknowns.",
    "/api/v1/analytics/total-returns": "Dated performance alias, not a capital-only estimate.",
    "/api/v1/analytics/risk": "Current concentration and rankings; not historical volatility.",
    "/api/v1/analytics/sector-exposure": "Equity-only sector exposure; no MF look-through.",
    "/api/v1/analytics/tax-report": "FIFO disposal data; not tax liability or filing advice.",
    "/api/v1/analytics/snapshots": "Saved module snapshots; does not create a snapshot.",
}


def tool_name(path: str) -> str:
    parts = path.removeprefix("/api/v1").strip("/").split("/")
    return "get_" + "_".join(
        f"by_{p[1:-1]}" if p.startswith("{") else p.replace("-", "_") for p in parts
    )


def standalone_schema(schema: dict, document: dict) -> dict:
    """Copy only referenced definitions and rewrite OpenAPI local refs to JSON Schema $defs."""
    definitions = {}

    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: visit(item) for key, item in value.items() if key != "$ref"}
        if "$ref" in value:
            ref = value["$ref"]
            prefix = "#/components/schemas/"
            if not ref.startswith(prefix):
                raise ValueError("Only local API schema references are supported")
            name = ref.removeprefix(prefix)
            if name not in definitions:
                definitions[name] = {}  # Reserve before traversing recursive definitions.
                definitions[name] = visit(document["components"]["schemas"][name])
            result["$ref"] = f"#/$defs/{name}"
        return result

    result = visit(deepcopy(schema))
    if definitions:
        result["$defs"] = definitions
    return result


@dataclass(frozen=True)
class EndpointTool:
    path: str
    parameters: tuple[dict, ...]
    tool: types.Tool


def build_catalog(document: dict[str, Any]) -> dict[str, EndpointTool]:
    catalog = {}
    for path, description in ENDPOINTS.items():
        operation = document["paths"][path]["get"]
        parameters = tuple(operation.get("parameters", []))
        if any(p["in"] not in {"path", "query"} for p in parameters):
            raise ValueError("MCP tools accept only reviewed path/query arguments")
        inputs = {p["name"]: p["schema"] for p in parameters}
        if len(inputs) != len(parameters):
            raise ValueError("Ambiguous endpoint arguments")
        input_schema = standalone_schema(
            {
                "type": "object",
                "properties": inputs,
                "required": [p["name"] for p in parameters if p.get("required")],
                "additionalProperties": False,
            },
            document,
        )
        output_schema = standalone_schema(
            {
                "type": "object",
                "properties": {
                    "data": operation["responses"]["200"]["content"]["application/json"]["schema"]
                },
                "required": ["data"],
                "additionalProperties": False,
            },
            document,
        )
        name = tool_name(path)
        if name in catalog:
            raise ValueError("Duplicate MCP tool name")
        catalog[name] = EndpointTool(
            path,
            parameters,
            types.Tool(
                name=name,
                description=f"GET {path}. {description} Preserve nulls and coverage warnings.",
                inputSchema=input_schema,
                outputSchema=output_schema,
                annotations=types.ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=path != "/health",
                ),
            ),
        )
    return catalog
