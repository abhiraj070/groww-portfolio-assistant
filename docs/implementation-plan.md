# Investment platform implementation plan

Audit date: 2026-11-25. Baseline: `18ed56b`, clean `main` checkout.

## Delivery status

Subsequent user-authorized extension: a [local MCP server](mcp.md) now exposes every endpoint
as an individual read-only tool. The original Phase 6 delivery below was the service facade.

Implemented sequentially on six phase branches, with tests, documentation and separate
milestone commits/pushes. Branches are stacked: later phases contain earlier phases.
Main remains unchanged; nothing is deployed automatically.

| Phase | Branch | Delivered scope |
| --- | --- | --- |
| 1 | feature/equity-analytics | Stock namespace, verified order/execution reads, catalog, tradebook ledger and FIFO |
| 2 | feature/mutual-fund-analytics | Statements/AMFI ingestion, NAV/scheme history, SIP/dividend/switch records and FIFO valuation |
| 3 | feature/combined-analytics | Combined exposure, covered performance/XIRR/CAGR, concentration and disposal data |
| 4 | feature/historical-data | Migrations, snapshots, verified split/bonus/MF unit adjustments |
| 5 | feature/security-testing | Whole-API auth/read-only checks, inbound limits, bounded inputs and Decimal precision |
| 6 | feature/ai-readiness | Typed reusable read facade; no MCP server |

Source limitations stay explicit: canonical normalization replaces generic contract-note/CAS
PDF parsing; no inferred active SIP mandates; benchmark/TER/fund-overlap sources unconfigured;
no MF sector look-through, equity dividend feed, fractional cash-in-lieu/reorganization mapper,
tax liability or volatility from insufficient history. AMFI reports are imported, not live.
XIRR needs covered snapshots and actual external cash flows. No live account tests or financial
transactions were performed.

## Audit and gaps

The existing FastAPI application owns a single Services container. Routes are adapters;
holdings, positions, orders, market data and Decimal analytics are reusable services.
GrowwClient owns lazy authentication, refresh, request budgets, timeouts and sanitised errors.
All account routes are protected by the local API key. Existing endpoints must remain available.
The pinned official SDK is 1.5.0; order-list pagination uses an audited HTTPX fallback.
Tests block live network calls and include real installed SDK methods over mocked transport.

Existing: holdings and positions; current-day orders; profile; quotes/LTP/OHLC/candles;
holdings-only valuation; missing-data propagation; allocation, sectors and rankings.
Missing: stock namespace, order details/executions, historical ledger/imports/FIFO gains,
instruments endpoint, MF ingestion/valuation, cash-flow returns, snapshots and persistence.
The README's previous completion claim refers to the original smaller backend, not this plan.

## Ordered milestones and branches

1. `feature/equity-analytics`: stock adapters over existing services; verified order details
   and execution reads; bounded official instrument catalog; persistent local CSV tradebook
   ingestion with original records, provenance and deduplication; FIFO sale matches and
   per-stock history. Contract-note PDF parsing requires a verified format and is deferred
   in favour of a documented canonical execution CSV. Do not infer corporate actions.
2. `feature/mutual-fund-analytics`: independent statement ingestion, purchases/redemptions,
   switches/SIP/dividends, AMFI NAV and scheme ingestion; holdings and portfolio calculations.
   No assumed Groww MF access. Unsupported external metrics must state missing sources.
3. `feature/combined-analytics`: aggregate equity and MF values without double counting;
   dated cash flows, Decimal XIRR and bounded historical performance; capital-gain lot data,
   coverage and metric assumptions. Tax data is not a tax liability calculation.
4. `feature/historical-data`: migrations, dated snapshots, adjustment events and reproducible
   calculations. Evaluate SQLAlchemy/PostgreSQL against the personal local ledger before
   adding infrastructure; persistence needed by Phase 1 must be introduced in Phase 1.
5. `feature/security-testing`: inbound limits, privacy and read-only regression coverage,
   malformed/partial data, financial precision and provider failures.
6. `feature/ai-readiness`: typed reusable service facade and capability documentation;
   no MCP server or trading methods.

Branches build sequentially on their predecessor. Do not merge or deploy automatically.
Commit and push reviewed, coherent milestones within each phase. Before each phase is
complete: full pytest suite, Ruff lint and format checks, diff whitespace check and staged
filename/diff inspection. No statements, ledger files, credentials or tokens enter Git.

## Sources and limitations

Official Groww order docs: https://groww.in/trade-api/docs/python-sdk/orders
explicitly scope order lists to orders placed during the day. Details and per-order trades
exist, but these do not establish a lifetime archive. Use imported execution records.
Instrument source: https://groww.in/trade-api/docs/python-sdk/instruments and its linked
https://growwapi-assets.groww.in/instruments/instrument.csv . SDK instrument helpers use
unbounded download/cache side effects; use a bounded, timeout-controlled catalog adapter.
Available margin is documented at https://groww.in/trade-api/docs/python-sdk/margin .
This is an account snapshot, not historical itemised brokerage or charges. Corporate-action
and dividend history are not established by the audited Trading API; accept verified imports
only. Live account connectivity remains unverified; automated tests use synthetic data.

Imported history is always labelled as imported coverage, never automatically lifetime complete.
Unknown opening lots must suppress realised totals, not create zero-cost gains. FIFO matches
must retain acquisition dates and prorate charges. Current live holdings and imported ledger
balances are separate scopes and must not be silently substituted or reconciled.
