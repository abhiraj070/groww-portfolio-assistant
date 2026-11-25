# Architecture

## MCP transport

`app/mcp_server.py` implements local stdio using official MCP SDK 2.3.0. A reviewed explicit
catalog maps each GET endpoint to its own tool; input/output schemas come from internal
OpenAPI generation without enabling public docs. Calls forward through HTTPX ASGI transport
to the same FastAPI application/lifespan, preserving authentication, limits and financial
serialization. No network listener, arbitrary URL dispatcher or duplicate financial logic.
Business services remain transport-independent. See [MCP lifecycle and tool mapping](mcp.md).

## Expanded equity module

The ledger now has [ordered transactional migrations](storage.md), captured holding snapshots
and verified equity/MF adjustment events. HistoryService owns offline adjustment ingestion and
snapshot capture. FIFO consumes events without rewriting original executions.

`/stocks` shares existing portfolio/market handlers, adding valued holdings and thin adapters
for order details, per-order executions, catalog and ledger analytics. `LedgerService` owns
local SQLite connections per operation, transactionally imports canonical delivery executions,
preserves original files/rows and stores Decimal JSON strings. It opens lazily (not on startup).
Schema version 1 introduces imports and equity transactions; no extra DB server is necessary
for this single-account local service. The [storage evaluation](storage.md) retains SQLite.
`EquityHistoryService` recalculates FIFO from the ledger, with incomplete-history and unknown
charge propagation. No business service imports FastAPI. CLI ingestion never calls Groww.
`InstrumentsService` reads the official public catalog with bounded HTTPX streaming, a timeout,
and a lock-protected cache. Services.close owns both provider and catalog clients.

## Boundaries

MFIngestionService validates independent statement/NAV schemas and uses LedgerService's
transactional records table. MFService performs FIFO per folio/scheme and consumes imported
NAV observations. No equity/Groww models or live MF account endpoints are used. `records`
stores validated Decimal JSON, original rows and import provenance for future domains.

FastAPI routes -> reusable services -> read-only GrowwClient -> official Groww SDK or the
narrow HTTPX order-list fallback. Analytics performs Decimal calculations over validated
holdings, positions and prices. Service modules do not import FastAPI.

- `app/main.py`: application factory, lifecycle ownership, authentication at the private router,
  sanitised error responses, and no-store headers.
- `app/__main__.py`: loopback-only server entry point, one worker, no access logging.
- `app/core/config.py`: cached environment settings and masked credentials.
- `app/core/security.py`: constant-time local API-key comparison and fail-closed configuration.
- `app/core/logging.py`: known-secret and Bearer-token redaction after traceback formatting.
- `app/api/routes/`: thin, synchronous routes; FastAPI runs blocking work in its thread pool.
- `app/services/groww_client.py`: lazy SDK authentication, serialized token refresh, read calls,
  bounded network timeouts, error translation, and shared category budgets.
- `app/services/container.py`: application-scoped service ownership and optional sector loading.
- `app/services/*_service.py`: response validation, portfolio orchestration, and pure analytics.
- `app/schemas/`: typed requests/responses; provider extras are retained on account-data models.
- `app/utils/calculations.py`: Decimal percentage calculation and explicit rounding.

Startup loads settings and optional metadata, creates services, and performs no Groww requests.
Shutdown closes the owned HTTPX client and drops token/SDK references. Health is process liveness,
not credential or subscription readiness. Documentation routes are disabled.

## Authentication, transport and errors

The local API key and Groww credentials have separate roles. All `/api/v1` routes require the
local key. Groww auth is lazy; one client and reentrant lock serialize upstream reads and refresh.
A 401 triggers one token refresh and one retry. Auth failures cool down for 60 seconds. No
transient-failure retry loop amplifies requests; callers receive stable status codes instead.

The locked SDK 1.5.0 is used for auth, holdings, positions, profiles, quotes, LTP, OHLC and
historical candles. Its changelog hook is suppressed because constructor initialization would
otherwise make an unrelated network call without a timeout. Its fixed safe greeting may still
appear; no credentials are printed. Order-list pagination uses the documented HTTP endpoint
because the installed SDK drops required pagination parameters; see SDK compatibility notes.

The SDK adapter checks HTTP status before parsing failure bodies so provider business codes
cannot hide a 401, and non-JSON downtime is reported as an availability error.
SDK reads pass an explicit timeout. SDK auth has a fixed 15-second timeout. HTTPX uses explicit
timeouts, disables redirect following and environment proxy inheritance. Requests timeouts bound
network inactivity, not an overall transaction wall clock. Shared client locking includes waits
for in-flight requests, so concurrent requests may queue. This is a personal, low-volume service.

Budgets mirror documented auth/read/live limits, including 150 auth calls per rolling day.
They are process-local, reset on restart, and do not coordinate with other apps using the account.
Run one worker. Provider 429s produce Retry-After and a local cooldown; HTTPX preserves a valid
provider Retry-After, while SDK errors lacking headers use 60 seconds. Missing resources, auth,
timeouts, unavailable upstream and unexpected shapes are translated without raw error messages.

## Financial semantics

InvestmentService consumes equity and MF service outputs; PerformanceService consumes dated
cash flows and portfolio observations. Both use LedgerService without FastAPI dependencies.
`app/utils/returns.py` provides Decimal dated XIRR/CAGR functions. Historical inputs are never
silently mixed with live current values. See [performance assumptions](performance.md).

Holdings quantity is the valuation quantity. Pledged/locked/free/T1 quantities are retained as
metadata and are not added to it. Duplicate ISIN or symbol rows are rejected. Position identity
includes exchange, segment, product and trading symbol; duplicate identities are rejected.

Holdings market value uses CASH LTP on the explicit configured exchange. The service does not
infer exchange-specific aliases from ISIN; verify the default NSE assumption for your portfolio.
LTP is retrieved in batches of at most 50 symbols. Retrieval time is distinct from last-trade time.

Money and quantity calculations use Decimal after SDK deserialization. Monetary totals retain
precision; percentages round to four decimal places with ROUND_HALF_UP. HHI uses unrounded
weights on a 0-to-1 scale. Legacy valuation uses the default 28-digit Decimal context;
imported FIFO uses 64 digits, and percentage calculations use at least 64 working digits.
JSON Decimal fields are
strings; clients should parse them as decimals rather than binary floating point.

Positions are reported separately and never added to holdings value. Realised P&L is the sum
of values reported in the current positions snapshot; it does not establish lifetime realised
returns. Missing position P&L produces a null aggregate and a separately labelled reported sum.
Missing price/cost data produces null dependent totals and explicit known subtotals. No market
prices, sector labels or lifetime financial history are fabricated.

## Security and extension

Secrets live in local environment variables or ignored `.env`. The service registers configured
secrets and generated tokens for log redaction. Raw settings, HTTP headers/bodies, account data,
and unfiltered SDK exceptions must never be logged. Redaction is a backstop, not permission to
emit sensitive data. Response caches are disabled. CORS and unauthenticated interactive docs are
not enabled. This version assumes trusted local users; remote/multiuser deployment is separate work.

Future MCP adapters can construct the same Services container and call business services, then
close its client when shutting down. MCP must apply its own caller authorization. No generic SDK
method dispatcher or trading write path is exposed. New SDK versions require compatibility review
before updating the exact pin and lockfile.

ReadTools supplies explicit typed read methods over the same container; see
[AI-readiness contracts](ai-readiness.md). Services.close owns provider/catalog transports.
The read facade exposes no imports, capture, generic SDK calls or financial writes.

## Validation

Unit and API tests use synthetic fixtures; outbound Requests and HTTPX transports are blocked
unless explicitly mocked. Contract tests execute actual SDK methods against mocked HTTP and
exercise the full FastAPI-to-service-to-SDK path. Local socket smoke checks cover health/auth.
These checks do not certify Groww subscription, credentials, permissions or live payloads.
