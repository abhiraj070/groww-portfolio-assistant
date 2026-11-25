import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.main import create_app
from app.services.analytics_service import AnalyticsService
from app.services.container import Services
from app.services.equity_history_service import EquityHistoryService
from app.services.history_service import HistoryService
from app.services.ledger_service import LedgerService
from app.services.mf_ingestion_service import MFIngestionService
from app.services.mf_service import MFService
from app.services.migrations import MIGRATIONS
from tests.test_api import TEST_KEY
from tests.test_equity_history import csv_bytes, execution
from tests.test_mutual_funds import mf_row, nav_row


def action(
    kind="SPLIT", numerator="2", denominator="1", eligible="10", when="2025-02-01T09:00:00", **extra
):
    return dict(
        action_id="SYNTH-ACTION",
        isin="ISIN-SYNTH",
        kind=kind,
        effective_at=when,
        numerator=numerator,
        denominator=denominator,
        eligible_quantity=eligible,
        **extra,
    )


def test_old_ledger_migrates_without_data_loss(tmp_path):
    path = tmp_path / "old.db"
    ledger = LedgerService(path)
    ledger.import_csv(csv_bytes(execution()), "synthetic")
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM schema_version WHERE version>1")
        db.execute("DROP TABLE records")
    assert ledger.tradebook().total == 1
    with ledger.connection() as db:
        assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == len(
            MIGRATIONS
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_future_schema_rejected_without_mutating_data(tmp_path):
    ledger = LedgerService(tmp_path / "future.db")
    with ledger.connection() as db:
        db.execute("INSERT INTO schema_version VALUES (999)")
    with pytest.raises(ServiceError) as error:
        ledger.tradebook()
    assert error.value.code == "unsupported_ledger_version"


def test_failed_upgrade_rolls_back_schema_and_preserves_records(tmp_path, monkeypatch):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(csv_bytes(execution()), "synthetic")
    monkeypatch.setattr(
        "app.services.migrations.MIGRATIONS",
        (*MIGRATIONS, ("CREATE TABLE never_committed (id INTEGER)", "INVALID SQL")),
    )
    with pytest.raises(ServiceError):
        ledger.tradebook()
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT COUNT(*) FROM equity_transactions").fetchone()[0] == 1
        assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == len(
            MIGRATIONS
        )
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name='never_committed'"
        ).fetchall()


def test_concurrent_incremental_imports_deduplicate(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: ledger.import_csv(csv_bytes(execution()), "synthetic"), range(2))
        )
    assert sum(r.inserted for r in results) == 1
    assert sum(r.duplicates for r in results) == 1
    assert ledger.tradebook().total == 1


def test_split_preserves_cost_and_acquisition_date_and_prorates_charges(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(
        csv_bytes(execution(), execution("SELL", "SELL", "15", "10", "2026-01-01T10:00:00", "3")),
        "synthetic",
    )
    HistoryService(ledger).import_equity_actions(csv_bytes(action()), "verified-split")
    result = EquityHistoryService(ledger).analyse().stocks[0]
    assert result.remaining_quantity == 5
    assert result.remaining_cost == Decimal("25.25")
    assert result.gross_realised_pnl == Decimal("74.25")
    assert result.net_realised_pnl == Decimal("70.50")
    assert result.matches[0].holding_days == 365
    assert ledger.all_transactions()[0].quantity == 10  # Original not overwritten.


def test_bonus_is_separate_derived_zero_cost_lot(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(
        csv_bytes(execution(), execution("SELL", "SELL", "15", "20", "2026-01-01T10:00:00", "0")),
        "synthetic",
    )
    HistoryService(ledger).import_equity_actions(
        csv_bytes(action("BONUS", "1", zero_cost_confirmed="true")), "verified-bonus"
    )
    result = EquityHistoryService(ledger).analyse().stocks[0]
    assert result.remaining_quantity == 5
    assert result.remaining_cost == 0
    assert result.matches[1].buy_trade_id == "ACTION-SYNTH-ACTION"
    assert result.matches[1].cost == 0
    assert result.matches[1].acquired_at.month == 2
    assert result.gross_realised_pnl == 199
    assert ledger.tradebook().total == 2  # Derived lots are not fabricated executions.


def test_adjustment_mismatch_and_fractional_actions_fail_closed(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ledger.import_csv(csv_bytes(execution()), "synthetic")
    history = HistoryService(ledger)
    history.import_equity_actions(csv_bytes(action(eligible="11")), "synthetic")
    with pytest.raises(ServiceError) as error:
        EquityHistoryService(ledger).analyse()
    assert error.value.code == "adjustment_mismatch"
    other = LedgerService(tmp_path / "other.db")
    other.import_csv(csv_bytes(execution()), "synthetic")
    HistoryService(other).import_equity_actions(
        csv_bytes(action(numerator="1", denominator="3")), "synthetic"
    )
    with pytest.raises(ServiceError) as error:
        EquityHistoryService(other).analyse()
    assert error.value.code == "unsupported_adjustment"
    with pytest.raises(ServiceError):
        history.import_equity_actions(csv_bytes(action("BONUS")), "synthetic")


def test_mf_unit_adjustments_preserve_basis(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion = MFIngestionService(ledger)
    ingestion.import_transactions(
        csv_bytes(mf_row(), mf_row("SELL", "REDEMPTION", "15", "150", "2026-01-01", "0")),
        "synthetic",
    )
    ingestion.import_nav_csv(csv_bytes(nav_row(nav="10")), "synthetic")
    adjustment = dict(
        action_id="UNIT-SPLIT",
        folio="SYNTH-FOLIO",
        scheme_code="123",
        date="2025-02-01",
        numerator="2",
        denominator="1",
        eligible_units="10",
    )
    assert (
        HistoryService(ledger).import_mf_adjustments(csv_bytes(adjustment), "verified").inserted
        == 1
    )
    result = MFService(ledger).portfolio()
    assert result.holdings[0].units == 5
    assert result.invested_amount == 25
    assert result.gross_realised_pnl == 75
    assert result.matches[0].holding_days == 365
    assert MFService(ledger).all_transactions()[0].units == 10


def test_repeated_partial_sales_conserve_lot_costs_and_charges(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    equity = [execution(quantity="3", price="10", charges="1")]
    equity += [
        execution(f"SELL-{i}", "SELL", "1", "20", f"2026-01-0{i}T10:00:00", "0")
        for i in range(1, 4)
    ]
    ledger.import_csv(csv_bytes(*equity), "synthetic")
    stock = EquityHistoryService(ledger).analyse().stocks[0]
    with localcontext() as context:
        context.prec = 64
        assert sum(m.charges for m in stock.matches) == 1
    assert stock.remaining_cost == 0
    mf = [mf_row(units="3", amount="100", charges="1")]
    mf += [mf_row(f"SELL-{i}", "REDEMPTION", "1", "50", f"2026-01-0{i}", "0") for i in range(1, 4)]
    MFIngestionService(ledger).import_transactions(csv_bytes(*mf), "synthetic")
    result = MFService(ledger).portfolio()
    with localcontext() as context:
        context.prec = 64
        assert sum(m.cost for m in result.matches) == 100
        assert sum(m.charges for m in result.matches) == 1
    assert result.invested_amount == 0


def test_snapshots_persist_module_timestamps_and_missing_data(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    portfolio = Mock()
    portfolio.get_portfolio_analytics.return_value = AnalyticsService().analyse([], [], {})
    history = HistoryService(ledger, portfolio, MFService(ledger))
    captured = history.capture()
    result = HistoryService(ledger).snapshots()
    assert result.total == 1
    assert result.snapshots[0] == captured
    assert result.snapshots[0].mutual_funds.current_value is None
    assert result.snapshots[0].equity.summary.current_value == 0
    assert HistoryService(ledger).snapshots(offset=1).snapshots == []


def test_snapshot_endpoint_is_protected_and_read_only(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    services = Services.build(Settings(ledger_path=tmp_path / "ledger.db"))
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/analytics/snapshots").status_code == 401
            response = client.get("/api/v1/analytics/snapshots", headers={"X-API-Key": TEST_KEY})
            assert response.status_code == 200
            assert response.json()["total"] == 0
            assert (
                client.post(
                    "/api/v1/analytics/snapshots", headers={"X-API-Key": TEST_KEY}
                ).status_code
                == 405
            )
    finally:
        services.close()
