from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.main import create_app
from app.schemas.holdings import Holding
from app.services.analytics_service import AnalyticsService
from app.services.container import Services
from app.services.equity_history_service import EquityHistoryService
from app.services.investment_service import InvestmentService
from app.services.ledger_service import LedgerService
from app.services.mf_ingestion_service import MFIngestionService
from app.services.mf_service import MFService
from app.services.performance_service import PerformanceService
from app.utils.returns import cagr, xirr
from tests.test_api import TEST_KEY
from tests.test_equity_history import csv_bytes
from tests.test_mutual_funds import mf_row, nav_row


def observation(day, equity="100", mf="0", cash="0", coverage="2025-01-01"):
    return dict(
        date=day,
        equity_value=equity,
        mf_value=mf,
        cash_value=cash,
        cashflows_complete_from=coverage,
    )


def test_xirr_known_reference_and_decimal_precision():
    assert abs(
        xirr([(date(2025, 1, 1), Decimal(-100)), (date(2026, 1, 1), Decimal(110))]) - Decimal("0.1")
    ) < Decimal("1e-20")
    assert cagr(Decimal(100), Decimal(121), 730) == Decimal("0.1")
    # Microsoft's documented irregular schedule (2008 leap year included).
    flows = [
        (date(2008, 1, 1), Decimal(-10000)),
        (date(2008, 3, 1), Decimal(2750)),
        (date(2008, 10, 30), Decimal(4250)),
        (date(2009, 2, 15), Decimal(3250)),
        (date(2009, 4, 1), Decimal(2750)),
    ]
    # Published Excel result is approximate; independently require near-zero NPV.
    rate = xirr(flows)
    assert abs(rate - Decimal("0.373362535")) < Decimal("0.00000001")
    residual = sum(
        (a / (1 + rate) ** (Decimal((d - flows[0][0]).days) / 365) for d, a in flows), Decimal(0)
    )
    assert abs(residual) < Decimal("1e-20")


def test_xirr_rejects_undefined_and_ambiguous_schedules():
    d = date(2025, 1, 1)
    assert xirr([(d, Decimal(-100)), (d, Decimal(110))]) is None
    assert xirr([(d, Decimal(100)), (date(2026, 1, 1), Decimal(110))]) is None
    assert (
        xirr(
            [
                (d, Decimal(-100)),
                (date(2025, 2, 1), Decimal(200)),
                (date(2026, 1, 1), Decimal(-110)),
            ]
        )
        is None
    )


def test_cashflow_returns_ignore_internal_events_and_require_coverage(tmp_path):
    service = PerformanceService(LedgerService(tmp_path / "ledger.db"))
    assert not service.performance().available
    service.import_observations(
        csv_bytes(observation("2025-01-01"), observation("2026-01-01", "220")), "synthetic"
    )
    service.import_cashflows(
        csv_bytes(
            dict(flow_id="D", date="2025-07-01", kind="DEPOSIT", amount="100"),
            dict(flow_id="BUY", date="2025-07-02", kind="PURCHASE", amount="100"),
            dict(flow_id="DIV", date="2025-07-03", kind="DIVIDEND", amount="5"),
        ),
        "synthetic",
    )
    result = service.performance()
    assert result.available
    assert result.absolute_return == 20
    assert result.net_contributions == 100
    assert result.xirr_percentage is not None
    assert result.return_percentage is result.cagr_percentage is None
    assert not service.performance("daily").available
    incomplete = PerformanceService(LedgerService(tmp_path / "other.db"))
    incomplete.import_observations(
        csv_bytes(
            observation("2025-01-01", coverage=""), observation("2026-01-01", "110", coverage="")
        ),
        "synthetic",
    )
    assert incomplete.performance().absolute_return is None


def test_periods_without_flows_and_range_validation(tmp_path):
    service = PerformanceService(LedgerService(tmp_path / "ledger.db"))
    service.import_observations(
        csv_bytes(observation("2025-01-01"), observation("2026-01-01", "110")), "synthetic"
    )
    result = service.performance("yearly")
    assert result.available
    assert result.return_percentage == 10
    assert abs(result.cagr_percentage - 10) < Decimal("1e-20")
    assert service.performance("monthly").start == date(2025, 12, 1)
    assert service.performance("quarterly").start == date(2025, 10, 1)
    assert service.performance("weekly").start == date(2025, 12, 25)
    with pytest.raises(ServiceError):
        service.performance(start=date(2026, 1, 2), end=date(2026, 1, 1))


def synthetic_investment(tmp_path):
    ledger = LedgerService(tmp_path / "ledger.db")
    ingestion = MFIngestionService(ledger)
    ingestion.import_transactions(csv_bytes(mf_row()), "synthetic")
    ingestion.import_nav_csv(csv_bytes(nav_row()), "synthetic")
    portfolio = Mock()
    portfolio.get_portfolio_analytics.return_value = AnalyticsService().analyse(
        [Holding(trading_symbol="STOCK", isin="ISIN-STOCK", quantity="10", average_price="10")],
        [],
        {"STOCK": Decimal(20)},
    )
    return InvestmentService(portfolio, MFService(ledger), EquityHistoryService(ledger), ledger)


def test_combined_values_risk_and_partial_coverage(tmp_path):
    service = synthetic_investment(tmp_path)
    report = service.combined()
    assert report.current_value == 400
    assert report.invested_value == 200
    assert report.unrealised_pnl == 200
    assert report.asset_allocation[0].allocation_percentage == 50
    risk = service.risk()
    assert risk.hhi == Decimal("0.5")
    assert risk.effective_holdings == 2
    assert risk.holdings[0].unrealised_pnl_contribution_percentage == 50
    assert risk.volatility is None
    assert service.realised().total_gross is None  # No equity execution history.
    assert service.tax_data().history_complete is False


def test_overlap_rejected_instead_of_double_counted(tmp_path):
    service = synthetic_investment(tmp_path)
    service.portfolio.get_portfolio_analytics.return_value.holdings[0].isin = "ISIN-SYNTH"
    # Add an explicitly sourced MF identifier.
    original = service.mf.portfolio

    def with_isin():
        result = original()
        result.holdings[0].isin = "ISIN-SYNTH"
        return result

    service.mf.portfolio = with_isin
    for action in (service.combined, service.risk):
        with pytest.raises(ServiceError) as error:
            action()
        assert error.value.code == "overlapping_assets"


def test_all_analytics_routes_auth_and_valid_reads(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    services = Services.build(Settings(ledger_path=tmp_path / "ledger.db"))
    services.investment = synthetic_investment(tmp_path)
    services.portfolio = services.investment.portfolio
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    paths = [
        "net-worth",
        "total-investment",
        "total-returns",
        "asset-allocation",
        "sector-exposure",
        "performance",
        "realised-gains",
        "unrealised-gains",
        "tax-report",
        "risk",
    ]
    try:
        with TestClient(app) as client:
            for path in paths:
                url = f"/api/v1/analytics/{path}"
                assert client.get(url).status_code == 401
                response = client.get(url, headers={"X-API-Key": TEST_KEY})
                assert response.status_code == 200, (path, response.text)
                assert client.post(url, headers={"X-API-Key": TEST_KEY}).status_code == 405
            assert (
                client.get(
                    "/api/v1/analytics/performance?period=invalid", headers={"X-API-Key": TEST_KEY}
                ).status_code
                == 422
            )
    finally:
        services.close()
