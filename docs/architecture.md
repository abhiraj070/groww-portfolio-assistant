# Architecture

## Phase 1 boundary

The only production route is `/health`. Startup loads and validates environment settings
without creating an SDK client or contacting Groww. The public liveness response contains
no account data and makes no upstream readiness claim. No trading capabilities exist.

- `app/main.py`: application factory, liveness, sanitised error responses.
- `app/core/config.py`: cached Pydantic Settings, masked secrets, bounded timeout configuration.
- `app/core/security.py`: reusable constant-time local API-key check, failing closed.
- `app/schemas/common.py`: explicit health and error response models.
- `app/api/routes/`: future thin HTTP adapters with router-level API-key enforcement.
- `app/services/`: future authentication, SDK reads, portfolio orchestration, and analytics.
- `app/utils/`: future Decimal calculations.
- `tests/`: isolated configuration and HTTP tests; no live credentials.

Dependencies are locked with uv. The project has an independent Git repository at C:\Code\Projects\groww-portfolio-assistant.

## Integration design for subsequent phases

GrowwClient will own authentication and SDK initialization, reuse tokens, and expose only
explicit read methods. No generic method dispatcher, order placement, modification, or
cancellation will be exposed. Verify each method and signature against official documentation
and the locked SDK before implementing it. Synchronous SDK work must run off the async event
loop. Bound actual network timeouts; worker cancellation alone does not stop a network call.

Service objects must remain usable without FastAPI dependencies so MCP adapters can call
them later. Routers validate inputs, call services, and return typed models. Upstream errors
must be translated to stable, sanitised error codes; never return raw SDK exception strings.
Retry only safe reads with bounded attempts and respect provider rate limits.

Portfolio valuation will cover holdings separately from positions, preserving quantity
semantics to avoid double counting. Missing prices produce incomplete valuation metadata,
not invented zeros. Realised P&L must state its data scope and period; daily positions do
not establish lifetime realised returns. Sector classification requires reliable metadata.
All financial calculations should use Decimal and make rounding policies explicit.

## Verification scope

Phase 1 tests verify config isolation, secret masking, environment precedence, timeout and
auth-mode validation, local API-key enforcement, liveness, and error sanitisation. They do
not validate Groww connectivity. Live verification requires the user's subscription and
local credentials after the client has been implemented.
