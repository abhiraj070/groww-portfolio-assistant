# Historical delivery equity imports

The Trading API order list covers the current day. Per-order executions can be read with
known order IDs, but cannot discover a lifetime history. Export your historical tradebook
from the broker, review it locally and convert execution rows to the canonical UTF-8 CSV below.
Never import pending orders, order aggregates, intraday trades or derivatives as delivery trades.
One account per ledger. Do not combine different accounts or joint ownership scopes.

```csv
trade_id,trading_symbol,isin,exchange,side,traded_at,quantity,price,charges
SYNTH-BUY,SYNTH,ISIN-SYNTH,NSE,BUY,2025-01-01T10:00:00+05:30,10,10.1,1
SYNTH-SELL,SYNTH,ISIN-SYNTH,NSE,SELL,2026-01-01T10:00:00+05:30,5,20,1
```

Required fields: `trade_id`, `trading_symbol`, `isin`, `exchange` (NSE/BSE), `side` (BUY/SELL),
`traded_at` (ISO date/time), positive `quantity`, nonnegative `price`. Optional fields:
`order_id`, `name`, `charges`. A blank charge is unknown; explicit `0` means verified zero.
Quantity has at most 24 digits, 10 fractional. Financial values must be finite Decimals.
Unknown columns, malformed/duplicate headers, missing values and future dates are rejected.
Naive dates are interpreted in Asia/Kolkata. Use execution times when multiple trades occur
on a day; ties sort by exchange then trade ID. Do not invent an execution ID for an aggregate.

```powershell
uv run --locked python -m app.import_tradebook C:\Private\canonical-trades.csv --source groww-export
```

Set `LEDGER_PATH` to an absolute private SQLite path for durable use across working directories.
Default: `data/investments.sqlite3`. Files under `data/`, `imports/`, `statements/` and
`contract-notes/`, and database extensions are ignored. Keep private exports outside the repo.
Use filesystem permissions and disk encryption for account data; the database is not encrypted
by this application. No import HTTP endpoint is exposed. Max file size 10 MiB, max 50,000 rows.

An import is atomic. Identity is exchange + exchange-local execution date + trade ID across
all sources. Identical records are skipped; an ID with changed data aborts the entire import.
This deliberately requires manual review for corrections. Every successful import attempt
retains original bytes, SHA-256, source label and UTC timestamp. Original row JSON and the
first accepted import ID remain attached to each execution. Never use filenames as source
labels if they contain personal identifiers. Unsupported raw broker exports fail validation.

FIFO groups delivery executions by ISIN across NSE/BSE and keeps each acquisition timestamp.
Matched cost = matched units * buy price; proceeds = units * sell price. Gross realised P&L
= proceeds - cost. Charges on each buy/sell execution are prorated by matched quantity;
net gain is unknown if either charge is missing. Remaining cost excludes charges. Average
purchase and sale prices are quantity weighted across all imported purchases/sales.
Holding duration is exchange-local calendar days for each matched lot, not an averaged duration.

Unmatched sales produce `incomplete` status and null remaining inventory/cost and aggregate
gains. Importing older opening purchases later recalculates the entire FIFO sequence.
An empty ledger has unknown aggregate gains. Even a balanced ledger is never automatically
certified as lifetime complete. `held`, `partially_sold` and `completely_sold` describe imported
inventory only; compare against live holdings yourself. Do not use adjusted data and raw split
events together. Corporate actions are not inferred. Verified split/bonus events use the
separate [adjustment ledger](storage.md); do not duplicate already-adjusted tradebook data.

Contract-note PDFs vary and may be encrypted, aggregate charges or contain non-execution rows.
No trustworthy generic parser has been established. Convert verified execution rows and charges
to the same canonical CSV; keep the original note privately as audit evidence. Corporate actions
and dividend history have no verified Trading API integration here. Margin snapshots are
documented by Groww but do not provide itemised historical brokerage; no charges are estimated.
