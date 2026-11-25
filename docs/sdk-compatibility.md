# Groww SDK compatibility audit

The [MCP adapter](mcp.md) pins official `mcp==2.3.0` separately from Groww SDK 1.5.0. Its
stdio and in-memory protocol tests exercise initialization, all 57 tool definitions, calls,
schemas, lifecycle and sanitized errors. No additional Groww endpoint or financial capability
is introduced by MCP.

Verified against the official documentation and installed `growwapi==1.5.0` source on
25 November 2026. The exact SDK version is pinned because this adapter depends on audited
behavior, not just names from examples. `uv.lock` pins all dependencies and hashes.

| Feature | SDK signature used (all optional defaults omitted here) |
| --- | --- |
| API key auth | `GrowwAPI.get_access_token(api_key=..., secret=...)` |
| TOTP auth | `GrowwAPI.get_access_token(api_key=..., totp=...)` |
| SDK init | `GrowwAPI(token)` through QuietGrowwAPI |
| Holdings | `get_holdings_for_user(timeout=...)` |
| Positions | `get_positions_for_user(segment=..., timeout=...)` |
| Profile | `get_user_profile(timeout=...)` |
| Order detail | `get_order_detail(groww_order_id=..., segment=..., timeout=...)` |
| Order executions | `get_trade_list_for_order(groww_order_id=..., segment=..., page=..., page_size=..., timeout=...)` |
| Quote | `get_quote(trading_symbol=..., exchange=..., segment=..., timeout=...)` |
| LTP | `get_ltp(exchange_trading_symbols=tuple(...), segment=..., timeout=...)` |
| OHLC | `get_ohlc(exchange_trading_symbols=tuple(...), segment=..., timeout=...)` |
| Candles | `get_historical_candles(exchange=..., segment=..., groww_symbol=..., start_time=..., end_time=..., candle_interval=..., timeout=...)` |

The execution method transmits both page and page_size correctly in SDK 1.5.0. Detail and
execution reads share existing authentication, error translation and read budgets. They do
not establish historical discovery. No provider writes are used. Catalog reads use the official
CSV linked from the instruments documentation through bounded HTTPX, because SDK catalog
helpers download/cache through pandas without the application's timeout/size controls.

LTP/OHLC use exchange-prefixed symbols such as `NSE_RELIANCE`. Historical Groww symbols use
hyphens, such as `NSE-RELIANCE`. The deprecated `get_historical_candle_data` is not used.
SDK reads unwrap `payload` and raise SDK exceptions. The auth function returns a token string
in 1.5.0 even though its return annotation says dict; the adapter validates the actual shape.

## Narrow compatibility measures

HTTP status is checked before the SDK parses the response body. SDK 1.5.0 otherwise checks
business failure payloads first, potentially hiding a 401 behind a provider-specific code.
The audited adapter preserves HTTP authentication/rate errors and handles non-JSON downtime
without treating it as successful data. Regression tests cover token refresh with a business
failure payload and non-JSON 503 responses.


1. **Constructor side effect:** `_display_changelog()` triggers an unrelated GET without a
   timeout. QuietGrowwAPI overrides that hook to prevent the request. SDK initialization
   otherwise runs normally and may emit its fixed greeting. A regression test verifies no
   changelog HTTP call occurs.
2. **Order pagination bug:** `get_order_list(page=0, page_size=25, segment=None, timeout=None)`
   accepts pagination arguments but never includes page_size and drops page unless segment
   is specified. GrowwClient instead uses HTTPX for the documented
   `GET https://api.groww.in/v1/order/list`, sending page/page_size and optional segment with
   `Authorization: Bearer ...` and `X-API-VERSION: 1.0`. It uses the same token, budgets,
   refresh path, timeout and sanitised errors as SDK calls.
3. **Conflicting page-size docs:** documentation prose/example permits 100 while the request
   schema says maximum 25. This service conservatively accepts at most 25.
4. **Auth timeout:** `get_access_token` has no timeout argument and internally uses 15 seconds.
   The configurable read timeout does not change this. No global Requests monkeypatch is used
   in production. Tests explicitly mock transport functions.
5. **SDK exceptions lose headers:** rate-limit errors have no Retry-After field. The service
   returns a conservative 60 seconds for these errors and preserves valid HTTPX Retry-After.

Only the order list uses direct HTTPX. The adapter does not expose SDK order writes or a generic
method dispatcher. A real-SDK contract test exercises actual methods through the REST endpoints
against mocked Requests/HTTPX responses, checking endpoint/header/timeout and payload behavior.
No account data, actual credentials or live Groww calls are used.

## Primary references

Mutual funds use independent offline CAS/statement and AMFI ingestion. The audited SDK does
not establish an MF portfolio integration; no unverified SDK or private website APIs are called.

- [Introduction, authentication and rate limits](https://groww.in/trade-api/docs/python-sdk)
- [Holdings and positions](https://groww.in/trade-api/docs/python-sdk/portfolio)
- [Orders SDK](https://groww.in/trade-api/docs/python-sdk/orders)
- [Order REST documentation](https://groww.in/trade-api/docs/curl/orders)
- [Live quotes, LTP and OHLC](https://groww.in/trade-api/docs/python-sdk/live-data)
- [Current historical candles API](https://groww.in/trade-api/docs/python-sdk/backtesting)
- [Profile](https://groww.in/trade-api/docs/python-sdk/user)
- [Exceptions](https://groww.in/trade-api/docs/python-sdk/exceptions)

Before upgrading the SDK, recheck method signatures, response shapes, auth timeout, constructor
side effects and the pagination bug. Remove the HTTP fallback only when real SDK transport tests
show pagination is transmitted correctly. Re-lock, run the full suite and review the diff.
