# API reference and financial semantics

## Equity namespace

Legacy `/portfolio` and `/market` routes retain their behavior. New protected reads:

| GET path under `/api/v1/stocks` | Response and parameters |
| --- | --- |
| `/holdings` | List of `HoldingValuation`, including costs, LTP, returns, weights and optional source name |
| `/positions` | Existing `PositionsResponse`; optional `segment` |
| `/portfolio/summary` | Existing `PortfolioSummary` (positions P&L scope remains unchanged) |
| `/portfolio/analytics` | Existing `AnalyticsResponse` |
| `/portfolio/allocation` | List of `HoldingValuation` with complete-value-denominator weights |
| `/orders` | Existing `OrdersResponse`; current-day scope, page/page_size/segment |
| `/orders/{order_id}` | `Order`; optional segment (default CASH), exact provider detail |
| `/orders/{order_id}/trades` | `TradesResponse`: trades, page, page_size, possible_next_page, scope |
| `/trades`, `/tradebook` | `TradebookResponse`: imported transactions, total, offset, limit, scope, history_complete |
| `/sold` | `EquityHistoryResponse`, stocks with any imported sales (including incomplete history) |
| `/realised-pnl` | `EquityHistoryResponse`, every imported stock and matched acquisition/disposal lots |
| `/quote/{symbol}`, `/ltp/{symbol}`, `/ohlc/{symbol}`, `/candles` | Existing market response models/parameters |
| `/instruments` | `InstrumentsResponse`: instruments, total, offset, limit, source, retrieved_at |

Execution reads accept page 0..10000 and page_size 1..50 (default 50); identifiers are
1..100 letters, digits, underscores or hyphens. Provider execution scope is per-order,
not lifetime history; paging never asserts an overall total. Invalid/duplicate executions
or mismatched order IDs fail with `invalid_upstream_response`.

Ledger and instrument pagination: offset 0..1000000 (default 0), limit 1..1000 (default 100).
Both accept optional exact `symbol`; instruments accept exchange NSE/BSE (default NSE)
and return CASH instruments from the official public catalog, cached 15 minutes with a
retrieval timestamp. Downloads have configured timeout and a 64 MiB decompressed bound.
Missing source names/ISINs are null, never guessed. Instruments are not portfolio holdings.

`EquityHistoryResponse` contains `stocks`, gross/net realised P&L, scope, history_complete=false
and warnings. Each stock has quantities bought/sold/remaining, weighted purchase/sale prices,
remaining cost, first purchase/last transaction dates, imported-inventory status, unmatched sold
quantity and FIFO `matches`. Each match reports buy/sell IDs, dates, holding_days, quantity,
cost, proceeds, gross gain, charges and net gain. All financial values are Decimal strings.
See [import schema and calculation rules](equity-imports.md). Imports are offline only.
`ledger_unavailable` is a sanitised 503; invalid imports are 422 and identity conflicts 409
in the service/CLI layer. Neither imported gains nor current-position gains establish lifetime
taxable gains. Do not sum them together.

## Mutual fund namespace

All routes under `/api/v1/mf` are protected GETs. Models and ingestion rules are documented
in [mutual funds](mutual-funds.md). No Groww MF endpoint is assumed.

| Path | Response model / query |
| --- | --- |
| `/holdings`, `/portfolio/allocation` | List of MFHolding, by folio/scheme with units, remaining cost, NAV date/source, valuation, returns and weights |
| `/portfolio/summary`, `/portfolio/analytics`, `/portfolio/returns`, `/realised-pnl` | MFPortfolioResponse: holdings, costs/values, gross/net gains, dividend_income, sip_investment, FIFO matches, timestamps and coverage warnings |
| `/transactions`, `/purchases`, `/redemptions`, `/sip`, `/sip/history`, `/dividends` | MFTransactionsResponse: transactions with source/import timestamp, total, offset, limit, scope |
| `/nav/{scheme_id}` | Latest StoredNAV (observation + source/import timestamp), or 404 nav_unavailable |
| `/nav/{scheme_id}/history` | List of StoredNAV, optional inclusive start/end ISO dates |
| `/schemes` | Latest imported NAV metadata per scheme, offset/limit |
| `/benchmark-returns`, `/expense-ratio`, `/fund-overlap` | UnavailableMetric: available=false, metric, reason, required_source |

Scheme IDs are numeric strings of 1..12 digits. Offset 0..1000000 (default 0), limit
1..1000 (default 100); NAV date ranges must be ordered. Financial values serialize as strings.
No NAV history is synthesized between dates. Purchase reads include switch-ins/reinvestments;
redemptions include switch-outs; dividends include reinvestment income (avoid duplicate rows).

## Combined analytics namespace

Protected GETs under `/api/v1/analytics`; see [performance and financial definitions](performance.md).

| Path | Response model / query |
| --- | --- |
| `/net-worth`, `/total-investment`, `/unrealised-gains`, `/asset-allocation` | CombinedPortfolio: value, remaining cost, unrealised P&L/return, asset_allocation, scope, retrieved_at, warnings |
| `/realised-gains` | RealisedGains: module gross/net gains, totals, MF income, known/unknown costs and imported coverage |
| `/performance`, `/total-returns` | PerformanceResponse: period, boundary dates/values, net_contributions, absolute/percentage returns, CAGR/XIRR percentages, coverage, available, warnings |
| `/risk` | RiskResponse: combined holdings, top five, rankings, HHI, effective holdings, unavailable volatility and warnings |
| `/sector-exposure` | Equity sector allocations with metadata source/date, unclassified value and equity_only scope |
| `/tax-report` | Imported matched equity_lots/mf_lots, coverage warnings; optional inclusive start/end disposal dates |
| `/snapshots` | SnapshotsResponse: captured equity/MF results, total, offset (0..1000000), limit (1..1000), newest first |

Performance query: period=daily|weekly|monthly|quarterly|yearly|all_time (default all_time),
optional ISO start/end. Invalid/inverted ranges are 422. Missing boundary snapshots return
available=false with explicit warnings and null metrics, not fabricated observations.
See [storage and adjustments](storage.md) for migration, capture and action error semantics.

## Access and response format

Base URL: `http://127.0.0.1:8000`. All `/api/v1` routes require `X-API-Key`.
No route accepts a Groww credential as a parameter. Health is the only public route.
Requests that create, modify or cancel orders are not implemented; write methods return 405.

Financial Decimal values are JSON strings. Nullable values indicate unknown or undefined data,
not zero. Unknown additional Groww fields are preserved on holdings, positions, orders, profile
and quote models. Provider extras retain their original decoded JSON types.

## Portfolio reads

- `GET /api/v1/portfolio/holdings`: `{"holdings":[...]}` with symbol, ISIN, quantity, average
  price and available locked/pledged quantities. No quantities are added together.
- `GET /api/v1/portfolio/positions?segment=FNO`: `{"positions":[...]}`; segment is optional
  and may be CASH, FNO, COMMODITY or CURRENCY. Signed net quantities and reported prices/P&L
  are retained. `net_price` is not relabelled as purchase cost of holdings.
- `GET /api/v1/portfolio/orders?page=0&page_size=25&segment=CASH`: `orders`, `page`,
  `page_size`, `possible_next_page`, `scope`. Page is 0..10000; page size is 1..25.
  Segment is optional. `possible_next_page` is a hint when a page is full, not an assertion
  that more records exist. Follow it until an empty/short page; there is no fabricated total.
  Scope is always `current_trading_day`; the SDK does not provide a lifetime order archive.
- `GET /api/v1/portfolio/account`: supported profile fields such as vendor user ID, UCC,
  enabled exchanges, DDPI and active segments. Personal data is protected by the local key.

## Summary and analytics

`GET /api/v1/portfolio/summary` returns holdings-only valuation with these distinctions:

| Field | Meaning |
| --- | --- |
| `invested_value` | Sum of quantity times average purchase price; null if a required cost is missing |
| `current_value` | Sum of quantity times LTP; null if any nonzero holding lacks a price |
| `unrealised_pnl` | Current value minus invested value; null when either is incomplete |
| `absolute_return` | Holdings unrealised value change, equal to unrealised P&L in this version |
| `return_percentage` | Unrealised P&L / invested value times 100; null for missing/zero capital |
| `known_invested_value` | Cost subtotal of holdings with known cost; not a complete portfolio claim |
| `priced_market_value` | Market-value subtotal of priced holdings |
| `missing_prices`, `missing_costs` | Symbols preventing full valuation |
| `realised_pnl` | Sum reported by current positions; null if any position omits it |
| `reported_realised_pnl` | Sum of available position P&L values, even when incomplete |
| `realised_pnl_complete` | Whether every returned position reported realised P&L |
| `realised_pnl_scope` | Always `current_positions_snapshot`; not lifetime or holdings realised gains |
| `valuation_scope` | Always `holdings_only` |
| `valuation_exchange` | Explicit pricing exchange selected by local configuration |
| `retrieved_at` | UTC retrieval/calculation time, not exchange last-trade time |
| `warnings` | Data-scope, coverage, freshness and return-method limitations |

For an empty portfolio invested/current/unrealised values are zero, percentage returns and
concentration are undefined (null). An empty positions snapshot reports zero for that snapshot,
which provides no evidence about lifetime realised P&L. Zero-quantity holdings contribute zero
without requiring a price or cost. Missing prices/costs affect nonzero holdings only.

`GET /api/v1/portfolio/analytics` includes the summary plus:

- `holdings`: per-stock cost, value, unrealised return and market-value allocation percentage.
- `concentration`: largest holding %, top three holdings %, HHI (sum of squared weights, 0..1).
- `top_performers` and `worst_performers`: at most five each, ranked by unrealised percentage
  return with deterministic symbol tie breaking. Small portfolios can appear in both lists.
  Unknown/zero-cost percentage returns are excluded; ranking is among available data only.
- `sector_allocation`: only sectors present in operator-supplied metadata. Each value is null
  if any member lacks a price. Sector weights use the complete portfolio value denominator.
- `sector_metadata_source`, `sector_metadata_as_of`: supplied provenance, or null.
- `unclassified_market_value`: value of unmapped holdings, or null when an unmapped price is missing.

All allocation weights and concentration are null when total value is incomplete or zero.
Prices may refer to older trades; this service does not infer current liquidity or quote age.

## Market reads

Quote, LTP and OHLC routes accept `exchange=NSE|BSE|MCX` (default NSE) and
`segment=CASH|FNO|COMMODITY|CURRENCY` (default CASH). Groww must support the requested
exchange/segment combination. Symbols must match `[A-Z0-9][A-Z0-9&._-]{0,99}`.

- `GET /api/v1/market/quote/{symbol}` returns instrument, quote and retrieval timestamp.
- `GET /api/v1/market/ltp/{symbol}` returns instrument, `price` and retrieval timestamp.
- `GET /api/v1/market/ohlc/{symbol}` returns the current OHLC snapshot, not interval candles.

Unavailable prices yield `missing_market_data`, not fabricated zero. Portfolio batch valuation
can preserve absent LTP keys as unknown prices and emit explicit partial totals. A whole failed
upstream batch instead fails the request; provider outages are not labelled as empty portfolios.

`GET /api/v1/market/candles` parameters:

| Parameter | Allowed values |
| --- | --- |
| `groww_symbol` | Required Groww symbol, e.g. `NSE-RELIANCE`; exchange prefix must match |
| `start_time`, `end_time` | Required ISO date-times, strictly increasing; offsets are accepted |
| `exchange` | NSE (default) or BSE |
| `segment` | CASH (default) or FNO |
| `candle_interval` | 1minute, 2minute, 3minute, 5minute, 10minute, 15minute, 30minute, 1hour, 4hour, 1day (default), 1week, 1month |

Naive inputs are interpreted in Asia/Kolkata; aware inputs are converted before sending Groww
its expected local time strings. Provider candle timestamps are preserved; naive provider times
are exchange-local. Response `retrieved_at` is UTC. Historical windows are limited to 30 days
for 1/2/3/5-minute intervals, 90 for 10/15/30-minute intervals, and 180 for longer intervals.
Historical availability and account access remain governed by Groww.

## Errors and retry behavior

Errors have shape `{"error":{"code":"...","message":"..."}}`; raw provider messages,
credentials, validation inputs and tracebacks are not returned.

| HTTP status / code | Action |
| --- | --- |
| 401 / `http_401` | Supply the correct local X-API-Key |
| 503 / `http_503` | Configure the local SERVICE_API_KEY |
| 422 / `validation_error` | Correct query parameters or symbol syntax |
| 503 / `groww_not_configured` | Configure the selected Groww credential flow locally |
| 503 / `groww_authentication_failed` | Check Groww credentials, daily approval, clock and subscription |
| 429 / `rate_limited` | Respect Retry-After; shared category/provider budget is exhausted |
| 504 / `upstream_timeout` | Groww timed out; retry the safe read later |
| 503 / `upstream_unavailable` | Upstream unavailable; retry later |
| 404 / `instrument_not_found` | Check symbol, exchange and access |
| 400 / `upstream_bad_request` | Groww rejected the request parameters |
| 502 / `missing_market_data` | A quote/price is unavailable |
| 502 / `invalid_upstream_response` | Unexpected/malformed data or duplicate assets; investigate SDK compatibility |
| 500 / `internal_error` | Unexpected internal failure; response remains sanitised |

There is one automatic refresh/read retry on provider 401. Network failures, 429 and downtime
are returned without aggressive automatic retries. Use a single worker for the per-process
request budgets and avoid frequent concurrent polling of the same account from multiple apps.
