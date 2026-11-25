# Groww Portfolio Assistant

A strictly read-only Python backend for accessing and analysing a personal Groww investment
portfolio. The expanded backend was implemented in six
[ordered phases](docs/implementation-plan.md), with explicit source and coverage limits.
Live account connectivity has **not**
been verified: tests use synthetic data and mocked upstream HTTP, including tests of the real
installed SDK. No credentials are bundled, and no trading or MCP server is implemented.

## Capabilities

The expanded equity module is available under `/api/v1/stocks`, with order details,
per-order executions, valued holdings, official instrument lookup and imported tradebook/FIFO
realised gains. See [equity import instructions](docs/equity-imports.md). Imports run locally;
all HTTP routes remain read-only. The ledger is not assumed to be complete lifetime history.

The mutual-fund module under `/api/v1/mf` reads normalized statements and imported AMFI NAV
observations: holdings, purchases, SIP history, redemptions, dividends and FIFO gains.
See [MF ingestion and metric limitations](docs/mutual-funds.md).

Combined reads under `/api/v1/analytics` cover investment value, asset exposure, imported gains
and snapshot/cash-flow-based performance. [Metric assumptions and input formats](docs/performance.md)
explain when XIRR, CAGR and historical returns are available.

[Historical storage](docs/storage.md) covers versioned migrations, explicit snapshot capture
and verified stock/MF unit adjustments. Private ledger files remain outside Git.

- Fetch holdings, positions, account profile, and paginated orders for the current trading day.
- Retrieve LTP, quotes, current OHLC snapshots, and historical candles.
- Calculate holdings cost, market value, unrealised P&L, simple absolute and percentage returns.
- Report realised P&L separately, limited to the positions snapshot returned by Groww.
- Calculate holding allocation, concentration, top/worst performers, and sector allocation when
  you supply verified classifications with source and date.
- Protect every account and market route with a local API key. Only `/health` is public.

**Scope matters:** positions are never added to holdings valuation. Missing costs and prices
produce explicit `null` totals and completeness fields, not fabricated zeros. Order retrieval
is not a lifetime order archive. Returns exclude fees, taxes, dividends and external cash flows.

## Stack and prerequisites

Python 3.13+, uv, FastAPI, Pydantic v2, Pydantic Settings, official `growwapi==1.5.0`, HTTPX,
Requests (SDK transport), PyOTP, python-dotenv, Uvicorn, pytest and Ruff. Development is pinned
to Python 3.13. Dependencies and hashes are recorded in `uv.lock`.

For live use you need a Groww account, an active Trading API subscription, and API credentials.
Follow [Groww's official prerequisites](https://groww.in/trade-api/docs/python-sdk), including
its current subscription activation process. Subscription prices and account permissions are
managed by Groww; this service does not activate them.

## Windows PowerShell installation

Install uv if needed, then open a new PowerShell window:

```powershell
winget install --id astral-sh.uv --exact
```

Use the existing local checkout:

```powershell
Set-Location C:\Code\Projects\groww-portfolio-assistant
uv python install 3.13
uv sync --locked
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

For a fresh checkout on another machine:

```powershell
Set-Location C:\Code\Projects
git clone https://github.com/abhiraj070/groww-portfolio-assistant.git
Set-Location .\groww-portfolio-assistant
uv python install 3.13
uv sync --locked
Copy-Item .env.example .env
```

The repository must be accessible to your GitHub account. Generate a local service key without
printing it; run this once for a fresh configuration (running again rotates the local key):

```powershell
uv run --locked python -c "from dotenv import set_key; import secrets; set_key('.env', 'SERVICE_API_KEY', secrets.token_urlsafe(32))"
notepad .env
```

Enter Groww credentials only in your local `.env` editor. Never paste them into source, chat,
Git commands, or bug reports. `.env` and local sector metadata are excluded from Git.

## Groww authentication setup

Official documentation and locked SDK source were checked on 25 November 2026.

Open [Groww Cloud API keys](https://groww.in/trade-api/api-keys) after activating your subscription.
Choose one flow:

1. **API key and secret:** Generate an API key, set `GROWW_AUTH_METHOD=api_key`, and fill
   `GROWW_API_KEY` and `GROWW_API_SECRET`. Groww documents daily approval for this flow.
2. **TOTP:** Choose Generate TOTP token. Set `GROWW_AUTH_METHOD=totp`, place the issued token
   in `GROWW_API_KEY`, and its Base32 seed in `GROWW_TOTP_SECRET`. Keep the machine clock
   synchronized. The installed PyOTP release enforces a minimum decoded seed size of 112 bits.

Tokens are generated lazily on the first upstream read and kept only in memory. A provider 401
invalidates the token and permits one refresh and read retry. Repeated rejection or failed token
generation imposes a 60-second cooldown. Restart after changing local configuration. An opaque
access token is reused until Groww rejects it; a TOTP seed's lifetime is not an access-token TTL.

The SDK's authentication request has a fixed 15-second timeout. Other requests use the configured
timeout. Nothing authenticates to Groww during application startup or `/health`.

## Configuration

Environment variables override `.env`, which is read from the working directory.

| Variable | Meaning |
| --- | --- |
| `SERVICE_API_KEY` | Local service key, at least 32 characters; blank fails closed |
| `GROWW_AUTH_METHOD` | `api_key` (default) or `totp` |
| `GROWW_API_KEY` | API key, or Groww-issued TOTP token in TOTP mode |
| `GROWW_API_SECRET` | Required for API key mode |
| `GROWW_TOTP_SECRET` | Required Base32 TOTP seed for TOTP mode |
| `GROWW_REQUEST_TIMEOUT_SECONDS` | SDK read and HTTPX timeout; default 10, greater than 0 and at most 60 |
| `VALUATION_EXCHANGE` | `NSE` (default) or `BSE`; verify that holdings trade under these symbols there |
| `SECTOR_METADATA_FILE` | Optional path to operator-verified classification JSON; leave unset otherwise |
| `LEDGER_PATH` | Private local SQLite ledger; default data/investments.sqlite3 |
| `API_REQUESTS_PER_MINUTE` | Process-wide inbound budget; default 300 per rolling minute |

Groww credentials can be absent while checking process health. Private reads then return
`groww_not_configured`, never a fake successful portfolio. If a configured sector file is missing,
malformed, or dated in the future, startup fails with a sanitised configuration error.

## Run and call the service

```powershell
Set-Location C:\Code\Projects\groww-portfolio-assistant
uv run --locked python -m app
```

The entry point binds **127.0.0.1:8000**, uses one worker, and disables access logs. Equivalent:

```powershell
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

In another PowerShell window:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
$secureKey = Read-Host 'Local SERVICE_API_KEY from your .env' -AsSecureString
$headers = @{ 'X-API-Key' = [System.Net.NetworkCredential]::new('', $secureKey).Password }
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/portfolio/holdings -Headers $headers
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/portfolio/summary -Headers $headers
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/portfolio/analytics -Headers $headers
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/market/ltp/RELIANCE?exchange=NSE&segment=CASH' -Headers $headers
Remove-Variable headers, secureKey
```

`/health` returns `{"status":"ok","mode":"read_only"}`; it does not establish upstream readiness.
Do not expose this personal service publicly. API docs are disabled. Cache-control headers
prevent storage of private responses; do not enable HTTP body/header debug logging.

## REST API

All paths below require `X-API-Key` except `/health`. Financial Decimal values are JSON strings.

| Method / path | Result |
| --- | --- |
| `GET /health` | Public process liveness |
| `GET /api/v1/portfolio/holdings` | Holdings, including pledged and locked quantities |
| `GET /api/v1/portfolio/positions` | Positions; optional `segment` filter |
| `GET /api/v1/portfolio/orders` | Current-day orders; `page`, `page_size`, optional `segment` |
| `GET /api/v1/portfolio/account` | Supported account profile fields |
| `GET /api/v1/portfolio/summary` | Holdings valuation and separately scoped realised P&L |
| `GET /api/v1/portfolio/analytics` | Summary, allocation, concentration, sectors and rankings |
| `GET /api/v1/market/quote/{symbol}` | Latest quote; optional `exchange`, `segment` |
| `GET /api/v1/market/ltp/{symbol}` | Last traded price; optional `exchange`, `segment` |
| `GET /api/v1/market/ohlc/{symbol}` | Current OHLC snapshot; optional `exchange`, `segment` |
| `GET /api/v1/market/candles` | Historical candles with validated time range |

See [API semantics and errors](docs/api.md) for query parameters, completeness rules and error
codes, and [SDK compatibility](docs/sdk-compatibility.md) for verified methods and exceptions.
See [security and reliability](docs/security.md) for inbound limits, import bounds and privacy.

## Optional sector classifications

Create a private JSON file outside the repository and set `SECTOR_METADATA_FILE` to its path.
Only supply classifications you have checked against a reliable source; the service validates
structure and provenance fields, not the source's factual accuracy. Synthetic format example:

```json
{
  "source": "Operator-verified classification source and version",
  "as_of": "2026-11-25",
  "sectors": {"ISIN-SYNTH": "Synthetic sector"}
}
```

Mappings use ISIN, not inferred company names. Unmapped holdings remain unclassified. The
response includes the supplied source and date; stale files are not automatically refreshed.

## Tests and development checks

```powershell
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
git diff --check
git status --short
```

Tests isolate environment configuration and `.env` and block real upstream HTTP by default.
They cover both auth modes, token reuse/refresh/concurrency, malformed upstream data, holdings,
positions, orders, market data, valuation/P&L, allocation, missing data, API authentication,
validation, rate limits, secret redaction and actual installed SDK contracts over mocked HTTP.
A Starlette deprecation warning about its HTTPX TestClient integration is currently expected;
HTTPX remains the requested direct HTTP client.

Before a live check, activate your subscription, configure credentials locally, and call holdings
and positions first. Then verify quotes and compare the scope of summary results with your Groww
account. Do not interpret passing mocked tests as proof of real account connectivity.

The repository is connected to `https://github.com/abhiraj070/groww-portfolio-assistant.git`.
Expanded milestones have separate commits on stacked phase branches. Main is unchanged.
Check tests, lint, staged filenames and diffs before
committing; never stage `.env` or force-push.

## Architecture and future MCP

See [architecture](docs/architecture.md) and the [typed read facade](docs/ai-readiness.md).
FastAPI and future AI adapters share service objects. No financial logic needs to move into
MCP, and no MCP server is implemented.

The service has no trading routes, generic SDK dispatcher, order creation, modification or
cancellation methods. Historical imports, persistent records and dated performance are available
with the coverage limits documented above. MCP transport remains outside this version.
