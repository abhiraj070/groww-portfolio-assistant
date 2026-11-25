# MCP server

The local stdio MCP server exposes all 57 existing HTTP endpoints as separate tools,
including legacy aliases and health. It uses official `mcp==2.3.0` with a reviewed GET-only
catalog. The endpoint-to-tool table below is exhaustive.

For a hosted MCP URL, use the [Render/Streamable HTTP deployment guide](render.md).
The same tools and payload schemas are exposed through either transport.

## Run and configure a client

```powershell
Set-Location C:\Code\Projects\groww-portfolio-assistant
uv sync --locked
uv run --locked python -m app.mcp_server --list-tools
uv run --locked python -m app.mcp_server
```

Normal mode waits for an MCP client on stdin/stdout; it is not an interactive command prompt.
`--list-tools` prints the mapping without creating services, reading account data or starting
a protocol session. Do not include this flag in an MCP client's launch configuration.

For clients accepting the common JSON stdio configuration format:

```json
{
  "mcpServers": {
    "groww-portfolio-assistant": {
      "command": "uv",
      "args": [
        "--directory", "C:/Code/Projects/groww-portfolio-assistant",
        "run", "--locked", "python", "-m", "app.mcp_server"
      ]
    }
  }
}
```

Use the absolute uv executable path if the client does not inherit PATH. Keep credentials in
the existing private `.env` in that project directory or the launcher's secure environment;
do not paste credentials into tool arguments or committed client configuration. The server
does not register itself in any client automatically. No separate REST process is needed.

## Authentication, lifecycle and safety

Stdio access is authorized by your local OS process launch, as for other local MCP servers.
The process reads existing Settings and supplies SERVICE_API_KEY internally through the same
API authentication boundary. Missing configuration fails closed for private tools; get_health
remains liveness-only. There is no per-tool secret argument and no public MCP HTTP listener.
Do not give an untrusted application the authority to launch this process or read its environment.
The separate hosted factory adds Streamable HTTP with Bearer authentication; OAuth is not
implemented. See [hosted security and client compatibility](render.md).

Each session owns one FastAPI lifespan and its Services/HTTP clients; startup performs no
Groww authentication. Lazy provider reads use existing credentials, timeouts and budgets.
Shutdown closes owned clients. Requests run through an in-process ASGI transport without TCP,
reusing existing services, typed validation, local API rate limits and sanitized errors.
JSON Schema additionally rejects extra arguments, invalid types, bounds and patterns before
dispatch. Date parsing and cross-field rules are enforced by the API. Protocol input rejected
before dispatch does not consume an HTTP request budget.

All tools carry read-only/non-destructive hints. Calls cannot choose arbitrary URLs, headers,
methods or SDK operations. Imports, snapshot capture and financial writes are not tools.
SDK telemetry middleware is disabled. Stdio owns stdout's protocol descriptor and diverts
incidental library prints; do not add print/debug statements containing private data. Default
logs are warning-only; do not enable SDK/HTTP debug logging for personal account sessions.

## Parameters and results

Tools expose the same flat path/query arguments, defaults, enums and numeric/string bounds as
their HTTP endpoints. For example:

```json
{"name":"get_stocks_ltp_by_symbol","arguments":{"symbol":"RELIANCE","exchange":"NSE","segment":"CASH"}}
```

The MCP CallToolResult supplies both structuredContent and a JSON text content block:

```json
{"data":{"symbol":"SYNTH","price":"12.34567890","retrieved_at":"2026-01-01T00:00:00Z","exchange":"NSE","segment":"CASH"}}
```

`data` is the unchanged endpoint payload, including list responses. Decimal values remain
strings; nulls, scope, source dates and completeness warnings remain present. Tool input and
output schemas are derived from the API contract, with self-contained local definitions.
Unavailable MF benchmark/expense/overlap metrics remain available=false; wrapping them in
a tool does not add a data source. Financial definitions are in [API](api.md) and
[performance](performance.md). Do not interpret partial imported history as complete.

Errors set isError=true and return sanitized error.code, error.message and numeric status.
429 responses also include retry_after as a string of seconds. Invalid tool arguments are
validation_error/422; unknown tools are unknown_tool/404. Provider timeout/rate/auth codes and
missing-data semantics are preserved from the REST API. Unexpected exceptions return a generic
internal_error/500 without input values, provider bodies, credentials or tracebacks.

## Validation and compatibility

Tests assert one tool for every current endpoint, no automatic exposure of unreviewed future
routes, retained schemas/bounds, GET-only dispatch, exact Decimal strings, private API-key
forwarding, null preservation, sanitized errors, rate limits, client lifecycle and actual MCP
initialize/tools-list/tools-call roundtrips. A subprocess test uses a real stdio client and
synthetic settings outside the project's `.env`; no live account calls occur.

The exact SDK pin is intentional: version 2 uses constructor-registered handlers and Python
snake_case attributes for wire aliases. Upgrades require protocol and stdio compatibility tests.
The original ReadTools facade remains available for trusted direct service use; MCP tool names
are endpoint-specific, so legacy get_portfolio_summary is equity-only while
get_analytics_net_worth is combined investment value.

Primary references checked 2026-11-26:

- https://github.com/modelcontextprotocol/python-sdk
- https://modelcontextprotocol.io/docs/develop/build-server

## Every endpoint and its tool

<!-- endpoint-tools:start -->

| MCP tool | GET endpoint |
| --- | --- |
| `get_health` | `/health` |
| `get_portfolio_holdings` | `/api/v1/portfolio/holdings` |
| `get_portfolio_positions` | `/api/v1/portfolio/positions` |
| `get_portfolio_orders` | `/api/v1/portfolio/orders` |
| `get_portfolio_summary` | `/api/v1/portfolio/summary` |
| `get_portfolio_analytics` | `/api/v1/portfolio/analytics` |
| `get_portfolio_account` | `/api/v1/portfolio/account` |
| `get_market_quote_by_symbol` | `/api/v1/market/quote/{symbol}` |
| `get_market_ltp_by_symbol` | `/api/v1/market/ltp/{symbol}` |
| `get_market_ohlc_by_symbol` | `/api/v1/market/ohlc/{symbol}` |
| `get_market_candles` | `/api/v1/market/candles` |
| `get_stocks_positions` | `/api/v1/stocks/positions` |
| `get_stocks_orders` | `/api/v1/stocks/orders` |
| `get_stocks_portfolio_summary` | `/api/v1/stocks/portfolio/summary` |
| `get_stocks_portfolio_analytics` | `/api/v1/stocks/portfolio/analytics` |
| `get_stocks_quote_by_symbol` | `/api/v1/stocks/quote/{symbol}` |
| `get_stocks_ltp_by_symbol` | `/api/v1/stocks/ltp/{symbol}` |
| `get_stocks_ohlc_by_symbol` | `/api/v1/stocks/ohlc/{symbol}` |
| `get_stocks_candles` | `/api/v1/stocks/candles` |
| `get_stocks_portfolio_allocation` | `/api/v1/stocks/portfolio/allocation` |
| `get_stocks_holdings` | `/api/v1/stocks/holdings` |
| `get_stocks_orders_by_order_id` | `/api/v1/stocks/orders/{order_id}` |
| `get_stocks_orders_by_order_id_trades` | `/api/v1/stocks/orders/{order_id}/trades` |
| `get_stocks_tradebook` | `/api/v1/stocks/tradebook` |
| `get_stocks_trades` | `/api/v1/stocks/trades` |
| `get_stocks_sold` | `/api/v1/stocks/sold` |
| `get_stocks_realised_pnl` | `/api/v1/stocks/realised-pnl` |
| `get_stocks_instruments` | `/api/v1/stocks/instruments` |
| `get_mf_portfolio_allocation` | `/api/v1/mf/portfolio/allocation` |
| `get_mf_holdings` | `/api/v1/mf/holdings` |
| `get_mf_realised_pnl` | `/api/v1/mf/realised-pnl` |
| `get_mf_portfolio_returns` | `/api/v1/mf/portfolio/returns` |
| `get_mf_portfolio_analytics` | `/api/v1/mf/portfolio/analytics` |
| `get_mf_portfolio_summary` | `/api/v1/mf/portfolio/summary` |
| `get_mf_transactions` | `/api/v1/mf/transactions` |
| `get_mf_purchases` | `/api/v1/mf/purchases` |
| `get_mf_redemptions` | `/api/v1/mf/redemptions` |
| `get_mf_sip_history` | `/api/v1/mf/sip/history` |
| `get_mf_sip` | `/api/v1/mf/sip` |
| `get_mf_dividends` | `/api/v1/mf/dividends` |
| `get_mf_nav_by_scheme_id` | `/api/v1/mf/nav/{scheme_id}` |
| `get_mf_nav_by_scheme_id_history` | `/api/v1/mf/nav/{scheme_id}/history` |
| `get_mf_schemes` | `/api/v1/mf/schemes` |
| `get_mf_benchmark_returns` | `/api/v1/mf/benchmark-returns` |
| `get_mf_expense_ratio` | `/api/v1/mf/expense-ratio` |
| `get_mf_fund_overlap` | `/api/v1/mf/fund-overlap` |
| `get_analytics_asset_allocation` | `/api/v1/analytics/asset-allocation` |
| `get_analytics_unrealised_gains` | `/api/v1/analytics/unrealised-gains` |
| `get_analytics_total_investment` | `/api/v1/analytics/total-investment` |
| `get_analytics_net_worth` | `/api/v1/analytics/net-worth` |
| `get_analytics_realised_gains` | `/api/v1/analytics/realised-gains` |
| `get_analytics_performance` | `/api/v1/analytics/performance` |
| `get_analytics_total_returns` | `/api/v1/analytics/total-returns` |
| `get_analytics_risk` | `/api/v1/analytics/risk` |
| `get_analytics_sector_exposure` | `/api/v1/analytics/sector-exposure` |
| `get_analytics_tax_report` | `/api/v1/analytics/tax-report` |
| `get_analytics_snapshots` | `/api/v1/analytics/snapshots` |

<!-- endpoint-tools:end -->
