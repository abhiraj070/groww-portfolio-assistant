# Security and reliability

The [hosted MCP boundary](render.md) requires a separate MCP_BEARER_TOKEN on all `/mcp`
requests, including discovery and initialization, and retains SERVICE_API_KEY internally.
Constant-time comparison, secret masking, allowed HTTPS host/origin, bounded request bodies
and a transport budget apply before account access. Only `/health` is public. This is private
single-account Bearer access, not OAuth or a multiuser authorization system.

All HTTP business endpoints are GET-only and share API-key authentication; only health is
public. An OpenAPI regression checks the whole registered API. GrowwClient has no financial
write methods, order dispatcher or transfer capability. Offline imports/snapshot capture write
only the local ledger. Tests use synthetic data and block live HTTP.

`API_REQUESTS_PER_MINUTE` (default 300, range 1..10000) is a global rolling 60-second inbound
budget shared by `/api/v1/` requests, including authentication failures and write attempts.
It stores no caller identity or financial content. Exhaustion returns 429 request_rate_limited,
Retry-After and normal no-store/nosniff headers. Health remains available. This is separate
from provider budgets. Run one worker; restart resets budgets. Shared/remote deployment needs
coordinated limits and transport security.

Secrets remain local masked settings, never request parameters or ledger content. Protect
`.env`/data directories with OS permissions and disk encryption. Existing secret/Bearer
redaction and sanitised errors remain. Imports do not log row values, source labels, paths or
originals. The ledger stores private source documents without application encryption; keep
it and backups out of Git.

Canonical imports are bounded to 10 MiB/50,000 rows, with strict headers/schema and atomic
rollback. Imported financial values allow at most 14 integer and 10 fractional digits; extreme
exponents, non-finite values, disallowed negatives and future dates are rejected. FIFO uses
64-digit Decimal working precision; retained lot remainders conserve cost/charges through
partial disposals. Percentages use at least 64 working digits and round four fractional places.
Clients summing raw prorated values need matching precision. Money remains Decimal JSON
strings. Existing provider contracts are preserved.

Catalog reads stream in 64 KiB chunks with a 64 MiB decompressed bound, timeout and 15-minute
cache. Invalid/oversized data is not cached. Missing sources/history remain explicit.

Tests cover whole-API auth/read-only behavior; provider failures, timeouts, rate budgets and
real-SDK contracts; malformed/duplicate/conflicting imports and provenance; missing lots/NAVs;
folios; Decimal/XIRR calculations; corporate actions; migration rollback/concurrency; privacy
and inbound limits. They do not establish live account connectivity or source accuracy.
