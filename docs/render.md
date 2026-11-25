# Deploy the MCP server on Render

The hosted server supports Streamable HTTP at `/mcp`, with all 57 read-only platform tools.
Use a Render **Web Service**, not a background worker or the stdio start command.
The repository's `.python-version` selects Python 3.13. Do not leave an incompatible
PYTHON_VERSION override on an existing service.

## Manual Web Service setup

Connect this GitHub repository and select branch `codex/mcp-server` (or main after merging
the MCP changes). Choose Python 3 as the runtime and the repository root as the root directory.

Build command:

```bash
uv sync --locked --no-dev
```

Start command:

```bash
uv run --locked --no-dev uvicorn app.mcp_http:create_http_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log
```

Health check path: `/health`. Keep one worker and one instance for the personal ledger and
per-process request budgets. Disable automatic deploys if you want to review each release.
The service speaks MCP at `https://YOUR-SERVICE.onrender.com/mcp`, not at the REST API paths.
The underlying REST application is internal to this server; it is not mounted publicly.

## Environment variables and persistent data

Set these in Render's secret environment-variable UI, never in Git:

| Variable | Value |
| --- | --- |
| SERVICE_API_KEY | Independent random secret of at least 32 characters, used by the internal REST boundary |
| MCP_BEARER_TOKEN | Independent random secret of at least 32 non-whitespace characters, shared only with authorized MCP clients |
| GROWW_AUTH_METHOD | api_key, or totp if using the existing TOTP authentication flow |
| GROWW_API_KEY | Your Groww-issued API key/token |
| GROWW_API_SECRET | API secret for api_key mode |
| GROWW_TOTP_SECRET | TOTP seed only if using totp mode |
| LEDGER_PATH | /var/data/investments.sqlite3 |

The hosted factory uses Render's automatic RENDER_EXTERNAL_URL as the allowed HTTPS origin/host.
For a custom domain set MCP_PUBLIC_URL to its HTTPS origin, e.g. `https://investments.example.com`
without `/mcp`, a query, credentials or fragment. Requests must use that configured host;
an Origin header, if supplied, must match. No cross-origin browser CORS access is enabled.
Outside Render, set MCP_PUBLIC_URL explicitly; the default is local http://localhost:8000.

Attach a persistent disk mounted at `/var/data` for the SQLite ledger and private imports.
Render supports persistent disks on paid services. Without a disk, local history is lost on
restart/redeploy. Existing local imports are not automatically uploaded; transfer them privately
or run the existing offline import commands through an authorized Render shell. Never commit
personal data to deploy it. Import/capture operations remain unavailable as remote tools.

## Blueprint alternative

The root `render.yaml` defines the same commands, a paid starter Web Service, a 1 GB ledger
disk, generated separate service/Bearer secrets, and prompts for Groww key/secret. Create a
Blueprint from this branch in your Render dashboard, review the paid resources and submit it
when ready. Auto-deploy is off. Change authentication variables manually for TOTP mode.
No Render resources are created by the code changes themselves.

## Connect an MCP client

Set the remote URL to:

```text
https://YOUR-SERVICE.onrender.com/mcp
```

Configure this HTTP header in the client's secure connection settings:

```text
Authorization: Bearer YOUR_MCP_BEARER_TOKEN
```

Use a client supporting custom Bearer headers. This is a private, single-account pre-shared
token deployment; it does not implement OAuth discovery, registration or authorization flows.
Clients requiring OAuth need a separate OAuth integration. Do not put the token in the URL,
query string, model prompt or tool arguments. Rotate the environment variable and restart the
service to revoke existing access. Health is public liveness only; it does not verify credentials.

Missing either authentication secret returns 503 for protected HTTP requests; missing/incorrect
Bearer credentials return 401. The transport also limits unauthenticated requests. MCP discovery,
initialize, tools and all other MCP methods require authentication. Output is marked no-store.
The SDK uses stateless JSON responses; services/HTTP clients are shared for the process lifespan,
not recreated for each call. No account-specific MCP session identifier is exposed.

## Verify after deployment

1. Check `/health` returns read_only and streamable_http.
2. A request to `/mcp` without the Bearer header must return 401, not a tool list.
3. Connect an authenticated client, initialize, then list tools: there should be 57.
4. Call get_health and get_mf_benchmark_returns first; these need no live Groww data.
5. Call account tools only after configuring Groww credentials/subscription. Configure a
   persistent ledger and import statements for history/MF data. Missing data stays explicit.

Automated tests use an in-process HTTP transport and synthetic credentials, including the
official MCP Streamable HTTP client. Passing them does not establish Render account setup,
live Groww connectivity or a successful external deployment.

Official deployment references checked 2026-11-26:

- https://render.com/docs/deploy-fastapi
- https://render.com/docs/python-version
- https://render.com/docs/environment-variables
- https://render.com/docs/disks
- https://render.com/docs/blueprint-spec
