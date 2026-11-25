# Groww Portfolio Assistant

Independent Python backend for read-only access to a personal Groww investment portfolio.
**Phase 1 is complete: configuration, local authentication foundation, health check, and tests.**
Groww authentication, portfolio retrieval, market data, and analytics are not implemented or
live-tested yet. No trading operations or MCP server are included.

## Stack and prerequisites

- Python 3.12+ (the development interpreter is pinned to 3.13).
- uv, FastAPI, Pydantic v2, Pydantic Settings, official `growwapi`, HTTPX,
  Uvicorn, python-dotenv, PyOTP, pytest, and Ruff.
- For later live integration: a Groww account and an active Trading API subscription.
  See [official prerequisites and authentication](https://groww.in/trade-api/docs/python-sdk).

This project has its own Git repository inside the existing NoteApp directory. Run its Git
and uv commands from this folder. The NoteApp application and dependencies are separate.

## Windows PowerShell setup

Install uv if needed:

```powershell
winget install --id astral-sh.uv --exact
```

Open a new PowerShell session after installation:

```powershell
Set-Location C:\Code\Projects\NoteApp\groww-portfolio-assistant
uv python install 3.13
uv sync --locked
Copy-Item .env.example .env
```

Generate a random local service key and save it directly to `.env` without displaying it:

```powershell
$localServiceKey = uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
$configuration = Get-Content -LiteralPath .env -Raw
$configuration = $configuration.Replace('SERVICE_API_KEY=', "SERVICE_API_KEY=$localServiceKey")
Set-Content -LiteralPath .env -Value $configuration -Encoding utf8
Remove-Variable localServiceKey, configuration
```

Run the key-generation snippet once on the fresh template. To change an existing key, edit
the value locally. Never share `.env`, tokens, or credentials in chat or commit them to Git.

## Configuration

Environment variables override `.env` (resolved from the working directory).

| Variable | Purpose |
| --- | --- |
| `SERVICE_API_KEY` | Local `X-API-Key` credential, minimum 32 characters; unset disables private access |
| `GROWW_AUTH_METHOD` | `api_key` (default) or `totp`; configuration only in Phase 1 |
| `GROWW_API_KEY` | Groww API key, or Groww-issued TOTP token for TOTP mode |
| `GROWW_API_SECRET` | Groww API secret for API key mode |
| `GROWW_TOTP_SECRET` | Groww TOTP seed for TOTP mode |
| `GROWW_REQUEST_TIMEOUT_SECONDS` | Future upstream timeout, greater than 0 and at most 60; default 10 |

Groww credentials are optional for Phase 1. Settings mask secrets in representations and
JSON serialization; validation text omits input values. Do not log raw settings dictionaries,
headers, upstream payloads, or exception objects that could contain secrets.

## Groww setup for Phase 2

The official documentation was checked on 25 November 2026:

1. Activate the Trading API subscription from the link in the official prerequisites.
2. Open the [Groww Cloud API keys page](https://groww.in/trade-api/api-keys).
   Use the link in the official SDK documentation if Groww changes this address.
3. For API key mode, generate a key and secret and store them locally in `.env`.
   Groww documents daily approval for this flow.
4. For TOTP mode, select Generate TOTP token, store that token in `GROWW_API_KEY`, and
   store its secret in `GROWW_TOTP_SECRET`. Set `GROWW_AUTH_METHOD=totp`.

Verified SDK entry points in the official docs are
`GrowwAPI.get_access_token(api_key=..., secret=...)` and
`GrowwAPI.get_access_token(api_key=..., totp=...)`, followed by `GrowwAPI(access_token)`.
These calls are not executed in Phase 1. Phase 2 must verify installed SDK signatures and
implement token reuse, expiry handling, bounded timeouts, and sanitised upstream errors.
Do not assume a TOTP seed's lifetime is the lifetime of an access token.

## Run locally

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second PowerShell window:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
```

The health response is `{"status":"ok","mode":"read_only"}`. This indicates process
health, not Groww connectivity, credential validity, or subscription status. API docs are
disabled. Keep the loopback bind; remote deployment requires a separate security review.

## Endpoints and implementation status

| Method / path | Status |
| --- | --- |
| `GET /health` | Implemented, public, no account information |
| `GET /api/v1/portfolio/summary` | Planned Phase 6 |
| `GET /api/v1/portfolio/holdings` | Planned Phase 6 |
| `GET /api/v1/portfolio/positions` | Planned Phase 6 |
| `GET /api/v1/portfolio/orders` | Planned Phase 6 |
| `GET /api/v1/portfolio/analytics` | Planned Phase 6 |
| `GET /api/v1/market/quote/{symbol}` | Planned Phase 6 |
| `GET /api/v1/market/ltp/{symbol}` | Planned Phase 6 |

Planned paths currently return 404. Future private routers must attach `require_api_key`
and require `X-API-Key`. Missing configuration returns 503; invalid or absent keys return
401. Errors use `{"error":{"code":"...","message":"..."}}` without raw exception detail.

## Checks

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
git status --short
```

Tests isolate configuration from your environment and `.env`. They use synthetic data,
make no Groww calls, and require no account or credentials.

## Architecture and next phases

See [architecture](docs/architecture.md). Planned work proceeds through Groww client
authentication, holdings/positions, orders/market data, analytics, REST adapters, and
expanded tests/documentation. Each phase gets checks and a separate meaningful commit.

Future MCP tools (`get_portfolio_summary`, `get_holdings`, `get_positions`, `get_orders`,
`get_stock_quote`, `get_portfolio_analytics`) will wrap the same service layer as FastAPI.
MCP is intentionally deferred. Financial analytics will use Decimal, keep holdings and
positions separate, and report missing prices or metadata explicitly.

## Connect your private GitHub repository later

Create an empty private repository named `groww-portfolio-assistant`. When you are ready:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/groww-portfolio-assistant.git
git push -u origin main
```

No remote is configured and nothing is pushed by this implementation. Never force-push.
