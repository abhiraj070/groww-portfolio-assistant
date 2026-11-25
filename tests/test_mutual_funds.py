from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.main import create_app
from app.services.container import Services
from app.services.ledger_service import LedgerService
from app.services.mf_ingestion_service import MFIngestionService
from app.services.mf_service import MFService
from tests.test_api import TEST_KEY
from tests.test_equity_history import csv_bytes


def mf_row(
    transaction_id="BUY",
    kind="PURCHASE",
    units="10",
    amount="100",
    date="2025-01-01",
    charges="1",
    **extra,
):
    return dict(
        transaction_id=transaction_id,
        folio="SYNTH-FOLIO",
        scheme_code="123",
        scheme_name="Synthetic Scheme",
        kind=kind,
        date=date,
        units=units,
        amount=amount,
        nav="10",
        charges=charges,
        **extra,
    )


def nav_row(date="2026-01-01", nav="20"):
    return dict(scheme_code="123", scheme_name="Synthetic Scheme", nav=nav, date=date)


def test_mf_fifo_nav_and_sip_calculations(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion, service = MFIngestionService(ledger), MFService(ledger)
    ingestion.import_transactions(
        csv_bytes(
            mf_row(),
            mf_row("SIP", "SIP", "5", "100", "2025-02-01", "2"),
            mf_row("SELL", "REDEMPTION", "12", "360", "2026-01-01", "3"),
        ),
        "synthetic-cas",
    )
    ingestion.import_nav_csv(csv_bytes(nav_row()), "synthetic-amfi")
    result = service.portfolio()
    assert result.holdings[0].units == 3
    assert result.invested_amount == 60
    assert result.current_value == 60
    assert result.gross_realised_pnl == 220
    assert result.net_realised_pnl == Decimal("215.2")
    assert result.sip_investment == 100
    assert result.matches[0].holding_days == 365
    assert service.transactions({"SIP"}).total == 1
    assert service.latest_nav("123").source == "synthetic-amfi"
    assert len(service.schemes()) == 1
    assert not result.history_complete


def test_missing_nav_opening_units_and_folio_separation(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion, service = MFIngestionService(ledger), MFService(ledger)
    assert service.portfolio().current_value is None
    ingestion.import_transactions(csv_bytes(mf_row()), "synthetic")
    assert service.portfolio().current_value is None
    missing = mf_row("SELL", "REDEMPTION", "1", "10", "2025-02-01")
    missing["folio"] = "OTHER-FOLIO"
    ingestion.import_transactions(csv_bytes(missing), "synthetic")
    assert service.portfolio().gross_realised_pnl is None
    assert service.portfolio().invested_amount is None
    with pytest.raises(ServiceError) as error:
        service.latest_nav("123")
    assert error.value.code == "nav_unavailable"


def test_mf_dedup_conflict_and_originals(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion = MFIngestionService(ledger)
    content = csv_bytes(mf_row())
    assert ingestion.import_transactions(content, "synthetic").inserted == 1
    assert ingestion.import_transactions(content, "synthetic-copy").duplicates == 1
    with pytest.raises(ServiceError) as error:
        ingestion.import_transactions(csv_bytes(mf_row("NEW"), mf_row(amount="200")), "synthetic")
    assert error.value.code == "import_conflict"
    assert MFService(ledger).transactions().total == 1
    assert ledger.records("mf_transaction")[0]["source"] == "synthetic"


def test_nav_dates_and_unknown_charges(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion, service = MFIngestionService(ledger), MFService(ledger)
    ingestion.import_transactions(
        csv_bytes(mf_row(charges=""), mf_row("SELL", "REDEMPTION", "1", "20", "2026-01-01", "0")),
        "synthetic",
    )
    ingestion.import_nav_csv(csv_bytes(nav_row("2025-01-01")), "synthetic")
    assert service.portfolio().current_value is None
    assert service.portfolio().net_realised_pnl is None
    ingestion.import_nav_csv(csv_bytes(nav_row()), "synthetic")
    assert len(service.nav_history("123")) == 2
    assert service.portfolio().current_value == 180


def test_amfi_report_parser_and_missing_nav(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    report = (
        b"Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
        b"Scheme Name;Net Asset Value;Date\n\nOpen Ended Schemes(Equity Scheme)\n"
        b"Synthetic Mutual Fund\n123;ISIN-SYNTH;-;Synthetic Growth;10.1234;01-Jan-2026\n"
        b"124;-;-;Missing;N.A.;01-Jan-2026\n"
    )
    ingestion = MFIngestionService(ledger)
    assert ingestion.import_amfi(report).inserted == 1
    assert ingestion.import_amfi(report).duplicates == 1
    nav = MFService(ledger).latest_nav("123")
    assert nav.nav == Decimal("10.1234")
    assert nav.fund_house == "Synthetic Mutual Fund"
    assert nav.isin == "ISIN-SYNTH"
    with pytest.raises(ServiceError):
        ingestion.import_amfi(report.replace(b"10.1234", b"NaN"))


@pytest.mark.parametrize(
    "change",
    [
        dict(units="-1"),
        dict(nav="NaN"),
        dict(kind="BONUS"),
        dict(kind="SWITCH_IN"),
        dict(date="2099-01-01"),
        dict(kind="DIVIDEND"),
        dict(amount="-1"),
    ],
)
def test_invalid_mf_records_rejected(tmp_path, change):
    row = mf_row()
    row.update(change)
    with pytest.raises(ServiceError):
        MFIngestionService(LedgerService(tmp_path / "ledger.db")).import_transactions(
            csv_bytes(row), "synthetic"
        )


MF_PATHS = [
    "holdings",
    "portfolio/summary",
    "portfolio/allocation",
    "portfolio/analytics",
    "portfolio/returns",
    "transactions",
    "purchases",
    "redemptions",
    "sip",
    "sip/history",
    "dividends",
    "realised-pnl",
    "nav/123",
    "nav/123/history",
    "schemes",
    "benchmark-returns",
    "expense-ratio",
    "fund-overlap",
]


def test_all_mf_routes_auth_valid_reads_and_no_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    services = Services.build(Settings(ledger_path=tmp_path / "ledger.db"))
    ingestion = MFIngestionService(services.ledger)
    ingestion.import_transactions(csv_bytes(mf_row()), "synthetic")
    ingestion.import_nav_csv(csv_bytes(nav_row()), "synthetic")
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    try:
        with TestClient(app) as client:
            for path in MF_PATHS:
                url = f"/api/v1/mf/{path}"
                assert client.get(url).status_code == 401
                response = client.get(url, headers={"X-API-Key": TEST_KEY})
                assert response.status_code == 200, (path, response.text)
                assert response.headers["Cache-Control"] == "no-store"
                assert client.post(url, headers={"X-API-Key": TEST_KEY}).status_code == 405
            for path in (
                "transactions?limit=0",
                "nav/bad",
                "nav/123/history?start=2026-01-01&end=2025-01-01",
            ):
                assert (
                    client.get(f"/api/v1/mf/{path}", headers={"X-API-Key": TEST_KEY}).status_code
                    == 422
                )
    finally:
        services.close()


def test_switch_dividend_and_reinvestment_events(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion = MFIngestionService(ledger)
    rows = [
        mf_row(),
        mf_row("DIV", "DIVIDEND", "0", "5", "2025-02-01"),
        mf_row("REINV", "REINVESTMENT", "1", "10", "2025-02-02"),
    ]
    ingestion.import_transactions(csv_bytes(*rows), "synthetic")
    report = MFService(ledger).portfolio()
    assert report.dividend_income == 15
    assert report.holdings[0].units == 11
    switch = mf_row("SWITCH", "SWITCH_OUT", "1", "20", "2025-03-01", switch_id="SYNTH-SWITCH")
    ingestion.import_transactions(csv_bytes(switch), "synthetic")
    assert MFService(ledger).transactions({"SWITCH_OUT"}).total == 1
