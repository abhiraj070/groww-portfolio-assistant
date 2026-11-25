# Historical storage and adjustments

## Storage decision and migrations

Retain local SQLite for this single-account service. The existing ledger already owns
deduplication, originals, provenance, transactions and Decimal JSON. PostgreSQL/SQLAlchemy
would add a deployment dependency without a current shared-server requirement. Re-evaluate
for a multiuser deployment; do not duplicate persistence merely to mirror suggested entities.

`app/services/migrations.py` applies ordered DDL transactionally: v1 import audit/executions,
v2 domain records (MF transactions, NAV history, cash flows, observations, adjustments and
holding snapshots), v3 import/foreign-key indexes. Early version-1 ledgers with a records
table migrate idempotently. Upgrades serialize with BEGIN IMMEDIATE; connections enable
foreign keys. Future schema versions fail closed. No destructive downgrades. Back up the
private database while the application is stopped before upgrading.

```powershell
uv run --locked python -m app.history migrate
uv run --locked python -m app.history snapshot
```

Migrations also run lazily at first ledger use. `snapshot` performs provider reads then stores
validated equity analytics and MF results with capture time, module timestamps, NAV dates,
sources and completeness warnings. It does not infer cash or turn mixed-time values into an
EOD performance observation. `GET /api/v1/analytics/snapshots?offset=0&limit=100` returns
SnapshotsResponse (snapshots, total, offset, limit), newest first. Same pagination bounds as
tradebook. No HTTP writes or automatic snapshot schedule. Failed captures save no fake result.

Use verified EOD observations including cash for [historical returns](performance.md).
FIFO/returns recalculate on reads; older imports can repair missing coverage. No history
is manufactured from current holdings. Original files and executions remain immutable.

## Verified equity actions

There is no automatic corporate-action feed. Normalize a checked announcement/account
statement into canonical CSV, with source and original bytes retained:

```csv
action_id,isin,kind,effective_at,numerator,denominator,eligible_quantity,zero_cost_confirmed
SYNTH-SPLIT,ISIN-SYNTH,SPLIT,2025-02-01T09:00:00+05:30,2,1,10,false
```

```powershell
uv run --locked python -m app.history equity-actions C:\Private\actions.csv --source verified-announcement
```

SPLIT ratio = new units / old units (2/1 doubles shares). Remaining quantities change while
total cost, fees and original acquisition dates are preserved. BONUS ratio = added units /
held units (1/1 adds one share per eligible share). Bonus creates a derived lot labelled by
action ID and allotment date with explicitly confirmed zero cost; no execution is fabricated.
BONUS requires zero_cost_confirmed=true and an allotment on/after 2001-04-01; older bonus basis
and special cases are unsupported. Verify your actual basis. The Income Tax Department
distinguishes older bonus basis from nil basis in other cases:
https://www.incometaxindia.gov.in/w/capital-gain . This does not calculate taxable income.

Required fields: action_id, isin, kind, effective_at, numerator, denominator, eligible_quantity.
Optional zero_cost_confirmed defaults false. Ratios/eligible quantities must be positive.
`eligible_quantity` must exactly match remaining ledger units; unmatched opening sales or
missing history cause adjustment_mismatch (409). Same-time actions apply before trades.
Split results must yield integral individual equity lots; fractional entitlements and
cash-in-lieu fail with unsupported_adjustment (409), never silently round. For bonus, use
an allotment time and entitlement inventory you can reconcile; record-date/allotment inventory
differences need explicit review. ISIN-changing reorganizations, transfers, rights issues and
grandfathering are unsupported. Do not disguise them as executions.
Purchase/sale statistics retain original executed units/prices; remaining inventory/FIFO gains
reflect actions. Bought minus sold need not equal adjusted inventory. Do not import both
adjusted tradebook units and the same action again.

## MF unit adjustments

Verified same-scheme/folio unit splits/consolidations preserving lot basis use:

```csv
action_id,folio,scheme_code,date,numerator,denominator,eligible_units
SYNTH-UNIT-SPLIT,SYNTH-FOLIO,123,2025-02-01,2,1,10
```

```powershell
uv run --locked python -m app.history mf-adjustments C:\Private\units.csv --source verified-statement
```

All columns required. Units scale; amount, charges and acquisition dates remain. Entitlement
must reconcile exactly. Actions apply before same-day transactions and invalidate earlier
NAVs for current valuation. This is not a scheme-merger/transfer mapper. Use actual statement
purchase/reinvestment/redemption/switch rows for those events; unit adjustments do not infer
bonus income or cash. Stable action IDs prevent duplicates; conflicts roll back atomically.

The database contains private source bytes and account records. Protect its directory with
OS permissions and disk encryption; use one account per file and keep backups out of Git.
