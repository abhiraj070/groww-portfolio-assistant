from decimal import Decimal

from app.schemas.holdings import Holding
from app.schemas.positions import Position
from app.services.analytics_service import AnalyticsService, SectorMetadata


def holding(symbol="SYNTH", quantity="2.5", cost="10.1"):
    return Holding(
        trading_symbol=symbol, isin=f"ISIN-{symbol}", quantity=quantity, average_price=cost
    )


def test_decimal_valuation_and_positions_not_double_counted():
    position = Position(trading_symbol="SYNTH", segment="CASH", quantity=50, realised_pnl="3.2")
    report = AnalyticsService().analyse([holding()], [position], {"SYNTH": Decimal("12.34")})
    summary = report.summary
    assert summary.invested_value == Decimal("25.25")
    assert summary.current_value == Decimal("30.85")
    assert summary.unrealised_pnl == Decimal("5.60")
    assert summary.realised_pnl == Decimal("3.2")
    assert summary.return_percentage == Decimal("22.1782")
    assert report.concentration.hhi == 1
    assert report.holdings[0].allocation_percentage == 100


def test_missing_price_does_not_fabricate_zero_or_total():
    report = AnalyticsService().analyse(
        [holding(), holding("SECOND")], [], {"SYNTH": Decimal("12")}
    )
    assert report.summary.current_value is None
    assert report.summary.unrealised_pnl is None
    assert report.summary.priced_market_value == 30
    assert report.summary.missing_prices == ["SECOND"]
    assert all(row.allocation_percentage is None for row in report.holdings)
    assert report.concentration.hhi is None


def test_missing_cost_and_partial_realised_pnl():
    positions = [
        Position(trading_symbol="SYNTH", segment="FNO", quantity=-1, realised_pnl=-2),
        Position(trading_symbol="SECOND", segment="CASH", quantity=1),
    ]
    report = AnalyticsService().analyse([holding(cost=None)], positions, {"SYNTH": Decimal("10")})
    assert report.summary.invested_value is None
    assert report.summary.current_value == 25
    assert report.summary.realised_pnl is None
    assert report.summary.reported_realised_pnl == -2
    assert not report.summary.realised_pnl_complete


def test_empty_portfolio_and_zero_cost():
    summary = AnalyticsService().analyse([], [], {}).summary
    assert summary.invested_value == summary.current_value == summary.unrealised_pnl == 0
    assert summary.return_percentage is None
    report = AnalyticsService().analyse([holding(cost="0")], [], {"SYNTH": Decimal("10")})
    assert report.holdings[0].return_percentage is None
    assert report.summary.unrealised_pnl == 25


def test_sector_source_allocation_rankings_and_concentration():
    metadata = SectorMetadata(
        source="Operator-verified synthetic source",
        as_of="2026-01-01",
        sectors={"ISIN-SYNTH": "Synthetic sector"},
    )
    report = AnalyticsService().analyse(
        [holding(quantity="1", cost="5"), holding("SECOND", quantity="1", cost="20")],
        [],
        {"SYNTH": Decimal("10"), "SECOND": Decimal("10")},
        sectors=metadata,
    )
    assert report.sector_allocation[0].allocation_percentage == 50
    assert report.unclassified_market_value == 10
    assert report.concentration.hhi == Decimal("0.50")
    assert report.top_performers[0].trading_symbol == "SYNTH"
    assert report.worst_performers[0].trading_symbol == "SECOND"


def test_zero_quantity_does_not_require_price_or_cost():
    report = AnalyticsService().analyse([holding(quantity="0", cost=None)], [], {})
    assert report.summary.current_value == report.summary.invested_value == 0
    assert report.summary.missing_prices == report.summary.missing_costs == []
