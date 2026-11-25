# Combined analytics and cash-flow returns

InvestmentService combines live equity holdings and statement-backed MF units; it never adds
positions or current-position realised P&L to lifetime ledger gains. Missing either module's
value/cost makes dependent totals unknown. MF identifiers overlapping nonzero equity holdings
fail with `overlapping_assets` (409) rather than double count. Unknown MF ISINs cannot be
reconciled automatically; operator classification remains necessary.

`net-worth` means equity + MF investment value only, excluding cash, debts and other personal
assets. `total-investment` reports remaining acquisition cost, not lifetime subscriptions or
net deposits. Weights use a complete combined-value denominator. Risk aggregates MF folios
by scheme, includes top five holdings, percentage-return rankings, HHI and effective holdings
(1/HHI). These are exposure/concentration measures, not volatility forecasts. Unrealised
contribution is individual unrealised P&L / complete remaining cost * 100. Sector exposure
remains explicitly equity-only; no MF constituent sectors are invented.

Realised gains combine imported FIFO results only. Total costs require explicit charges on all
imported transactions. Equity dividend income is unknown until a verified dividend source is
provided; MF dividend/reinvestment income is separately labelled. Tax-report contains matched
acquisition/disposal data with optional inclusive disposal date bounds, not a tax liability,
STCG/LTCG classification, exemption calculation or filing-ready tax document.

## Historical inputs

Historical performance uses dated end-of-day observations including cash, independently of live
valuation. Import canonical CSVs with originals/provenance preserved and duplicate conflict checks:

```csv
date,equity_value,mf_value,cash_value,cashflows_complete_from
2025-01-01,100,0,0,
2026-01-01,220,0,0,2025-01-01
```

Required: date, equity_value, mf_value, cash_value (nonnegative INR, all assets in the same
account boundary, no overlap). `cashflows_complete_from` is optional, an operator attestation
that every external deposit/withdrawal after that date through this closing observation is
recorded. Leave blank if uncertain. Do not attest complete coverage from a summary statement.

```csv
flow_id,date,kind,amount
SYNTH-DEPOSIT,2025-07-01,DEPOSIT,100
```

CashFlow fields are all required; IDs must be stable and amounts positive. Kinds: DEPOSIT,
WITHDRAWAL, PURCHASE, SALE, REDEMPTION, DIVIDEND, CHARGE. Only deposits/withdrawals cross
the investor/portfolio boundary. Buys, sells, redemptions, retained dividends and charges are
internal (already reflected in snapshot assets/cash). Record a distributed dividend as an
additional WITHDRAWAL only if cash actually leaves this portfolio boundary. Likewise record
fees funded externally through their actual deposit; do not deduct them twice. Transaction
ledgers are not automatically turned into deposits. Internal switch legs and reinvestment do
not generate fictitious external flows.

```powershell
uv run --locked python -m app.import_performance observations C:\Private\values.csv --source verified-eod
uv run --locked python -m app.import_performance cashflows C:\Private\flows.csv --source verified-cash-ledger
```

## Metric semantics

`performance` and `total-returns` accept period=daily|weekly|monthly|quarterly|yearly|all_time,
optional start/end ISO dates. End defaults to latest imported observation, not today's live value.
Daily/weekly select 1/7 calendar days earlier; monthly/quarterly/yearly subtract 1/3/12 calendar
months, clamping day to the target month's end. All-time begins at earliest imported observation.
Explicit start overrides the default window. Exact boundary observations are required; missing
weekends/holidays are not interpolated or silently replaced. One observation cannot establish
performance. Flows use (start, end], because opening values are end-of-day inclusive.

Absolute gain = closing assets - opening assets - net deposits (deposits minus withdrawals).
Unknown coverage yields available=false and null gains/returns, while showing known valuations.
Simple percentage return and CAGR are provided only if the period has no external flows:
gain/opening*100; CAGR = ((closing/opening)^(365/days)-1)*100. Zero opening value makes these
undefined. A total loss can have CAGR -100%, while a finite XIRR may remain undefined.

XIRR uses dated investor flows: negative opening value/deposits, positive withdrawals/closing
value. Same-day flows net; discount years are actual days / 365. The Decimal solver bisects
rates in [-0.999999, 1000000] with 40-digit working precision and at most 240 iterations.
It requires one sign change after date-netting; nonconventional schedules may have multiple
roots and return null. Rates outside bounds, no opposite signs or no date span are unknown.
This is a window-specific money-weighted return, not a certified lifetime actual return.
No current-value-plus-total-capital shortcut is used. Reference formula and regression example:
https://support.microsoft.com/en-us/excel/functions/xirr-function?nochrome=true .

Volatility and time-weighted risk are unavailable without a sufficiently dense, reconciled,
cash-flow-adjusted return series. These metrics are not inferred from a current snapshot.
