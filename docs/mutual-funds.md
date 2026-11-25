# Mutual fund data and calculations

MF data comes from private statements, independently of GrowwClient. AMFI documents CAS
sources from CAMS, KFintech and MFCentral at
https://www.amfiindia.com/online-center/download-cas . Detailed statements provide history;
summary statements alone do not establish purchase lots. Obtain statements yourself and
normalize locally. No RTA credentials, email inbox access or financial transactions are used.
Encrypted CAS PDFs have no generic parser here. Preserve originals privately and use this
strict canonical UTF-8 statement CSV (synthetic example):

```csv
transaction_id,folio,scheme_code,scheme_name,kind,date,units,nav,amount,charges
SYNTH-1,SYNTH-FOLIO,123,Synthetic Growth,SIP,2025-01-01,10,10,100,0
SYNTH-2,SYNTH-FOLIO,123,Synthetic Growth,REDEMPTION,2026-01-01,5,20,100,0
```

Required: transaction_id, folio, scheme_code, scheme_name, kind, date, units, amount.
Optional: isin, fund_house, nav, charges, sip_id, switch_id. NAV and units must be positive
for unit transactions. Amount is gross consideration before separately supplied charges,
not cash paid after fees; copy actual statement amounts to retain rounding differences.
Blank charges are unknown. Supported kinds: PURCHASE (including additional subscriptions),
SIP, REDEMPTION, SWITCH_IN, SWITCH_OUT, DIVIDEND (zero units), REINVESTMENT.
Switches require switch_id on both legs; a lone leg may be imported incrementally but is
not evidence of a complete switch. REINVESTMENT records dividend-funded new units and income;
do not also import that dividend as DIVIDEND. No active SIP schedule is inferred from payments.

```powershell
uv run --locked python -m app.import_mf transactions C:\Private\mf.csv --source detailed-cas
uv run --locked python -m app.import_mf amfi C:\Private\NAVAll.txt
uv run --locked python -m app.import_mf nav C:\Private\nav-history.csv --source verified-amfi-history
```

AMFI's official download page https://www.amfiindia.com/net-asset-value/nav-download links
the complete NAV report at https://portal.amfiindia.com/spages/NAVAll.txt and offers historical
downloads in windows of at most 90 days. Download manually and ingest the six-column
semicolon NAVAll format. N.A./NA/-/blank NAV observations are skipped; malformed numeric rows
abort the import. Original lines, ISIN reinvestment field, report bytes and provenance remain
in the local ledger. No automated AMFI access or claim of live NAV is made.
For other verified historical formats normalize to CSV:

```csv
scheme_code,scheme_name,date,nav
123,Synthetic Growth,2026-01-01,20
```

Optional NAV fields: isin, fund_house. Required fields: scheme_code, scheme_name, date, nav.
Observation identity is scheme_code + date. Transaction identity is folio + scheme_code +
transaction_id. Conflicts abort atomically; duplicates skip. All originals/provenance are retained.
Use stable folio aliases if you want to avoid storing actual folio numbers. One account per DB.
Same size/row bounds, privacy controls and source-label guidance as [equity imports](equity-imports.md).

FIFO is per folio and scheme, never across folios. Cost/proceeds use statement amount prorated
by matched units, preserving reported rounding. Charges prorate likewise; missing charges
suppress net gains. Holding days use acquisition and disposal dates. Remaining invested amount
is remaining FIFO cost; current value is units times latest imported NAV on/after the last
unit movement. An older observation remains visible but cannot value later-acquired units.
NAV dates may differ and may be stale; no inferred refresh. Missing opening units suppress
dependent totals. An empty MF ledger is unknown, not proof of zero MF assets. Statements
are never automatically declared complete; reconcile with CAS balances.
Same-date transactions sort by transaction_id; provide IDs that preserve the statement's
execution order when same-day purchase and disposal sequencing matters.

`/portfolio/returns` reports absolute and percentage unrealised changes; it does not claim
cash-flow XIRR. `/sip` and `/sip/history` list executed SIP rows with pagination. Benchmarks,
expense ratios and fund overlap return `available=false` with required sources. NAV alone
cannot provide total-return benchmarks, dated plan-specific TER or constituent weights;
these require separate verified AMC/index integrations. Never infer these from scheme names.
