import csv
import io
from decimal import Decimal

import pytest

from app.core.exceptions import ServiceError
from app.schemas.equity_history import EquityTransaction
from app.services.equity_history_service import EquityHistoryService
from app.services.ledger_service import LedgerService


def execution(
    trade_id="BUY1",
    side="BUY",
    quantity="10",
    price="10.1",
    when="2025-01-01T10:00:00",
    charges="1",
    **extra,
):
    return dict(
        trade_id=trade_id,
        trading_symbol="SYNTH",
        isin="ISIN-SYNTH",
        exchange="NSE",
        side=side,
        traded_at=when,
        quantity=quantity,
        price=price,
        charges=charges,
        **extra,
    )


def csv_bytes(*rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def test_persistent_import_deduplication_and_original_records(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = LedgerService(path)
    content = csv_bytes(execution())
    result = ledger.import_csv(content, "synthetic-broker")
    assert (result.inserted, result.duplicates) == (1, 0)
    result = LedgerService(path).import_csv(content, "synthetic-second-source")
    assert (result.inserted, result.duplicates) == (0, 1)
    row = ledger.tradebook().transactions[0]
    assert row.source == "synthetic-broker"
    assert row.imported_at.tzinfo is not None
    assert row.price == Decimal("10.1")
    with ledger.connection() as db:
        assert db.execute("SELECT original FROM imports ORDER BY id").fetchone()[0] == content
        assert '"price": "10.1"' in db.execute("SELECT raw FROM equity_transactions").fetchone()[0]


def test_conflict_rolls_back_whole_import(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(csv_bytes(execution()), "synthetic")
    with pytest.raises(ServiceError, match="conflicting"):
        ledger.import_csv(csv_bytes(execution("NEW"), execution(price="11")), "synthetic")
    assert ledger.tradebook().total == 1
    with ledger.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1


def test_fifo_partial_and_complete_sales_charges_and_dates(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(
        csv_bytes(
            execution(),
            execution("BUY2", quantity="5", price="20", when="2025-02-01T10:00:00", charges="2"),
            execution("SELL1", "SELL", "12", "30", "2026-01-01T10:00:00", "3"),
        ),
        "synthetic",
    )
    report = EquityHistoryService(ledger).analyse()
    stock = report.stocks[0]
    assert stock.status == "partially_sold"
    assert stock.remaining_quantity == 3
    assert stock.remaining_cost == 60
    assert stock.gross_realised_pnl == Decimal("219")
    assert stock.net_realised_pnl == Decimal("214.2")
    assert stock.matches[0].holding_days == 365
    assert [m.quantity for m in stock.matches] == [10, 2]
    assert not report.history_complete
    ledger.import_csv(
        csv_bytes(execution("SELL2", "SELL", "3", "25", "2026-02-01T10:00:00", "0")), "synthetic"
    )
    assert EquityHistoryService(ledger).analyse().stocks[0].status == "completely_sold"


def test_missing_opening_history_suppresses_totals_and_backfill_recalculates(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(
        csv_bytes(execution("SELL1", "SELL", "5", "20", "2025-02-01T10:00:00")), "synthetic"
    )
    service = EquityHistoryService(ledger)
    report = service.analyse()
    assert report.gross_realised_pnl is None
    assert report.stocks[0].unmatched_sold_quantity == 5
    assert report.stocks[0].remaining_quantity is None
    ledger.import_csv(csv_bytes(execution()), "synthetic-backfill")
    assert service.analyse().stocks[0].remaining_quantity == 5
    assert service.analyse().gross_realised_pnl == Decimal("49.5")


def test_unknown_charges_preserve_gross_but_not_net(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(
        csv_bytes(
            execution(charges=""), execution("SELL1", "SELL", "5", "20", "2025-02-01T10:00:00")
        ),
        "synthetic",
    )
    report = EquityHistoryService(ledger).analyse()
    assert report.gross_realised_pnl == Decimal("49.5")
    assert report.net_realised_pnl is None


@pytest.mark.parametrize(
    "change",
    [
        dict(quantity="0"),
        dict(quantity="-1"),
        dict(price="NaN"),
        dict(charges="-1"),
        dict(side="SPLIT"),
        dict(traded_at="2099-01-01"),
        dict(extra="unrecognised"),
        dict(exchange="MCX"),
    ],
)
def test_invalid_csv_never_writes_partial_data(tmp_path, change):
    ledger = LedgerService(tmp_path / "ledger.db")
    row = execution()
    row.update(change)
    with pytest.raises(ServiceError) as error:
        ledger.import_csv(csv_bytes(row), "synthetic")
    assert error.value.code == "invalid_import"
    assert ledger.tradebook().total == 0


def test_timezone_identity_and_pagination(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(csv_bytes(execution()), "synthetic")
    row = execution(when="2025-01-01T04:30:00Z")
    assert ledger.import_csv(csv_bytes(row), "synthetic").duplicates == 1
    assert ledger.tradebook(symbol="ABSENT").total == 0
    assert ledger.tradebook(offset=1).transactions == []
    with pytest.raises(ServiceError):
        ledger.tradebook(limit=1001)
    assert EquityTransaction(**execution()).traded_at.utcoffset().total_seconds() == 19800
