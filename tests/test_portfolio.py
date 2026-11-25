from decimal import Decimal
from unittest.mock import Mock

from app.schemas.holdings import Holding, HoldingsResponse
from app.schemas.positions import PositionsResponse
from app.services.portfolio_service import PortfolioService


def test_orchestration_and_exchange():
    holdings, positions, market = Mock(), Mock(), Mock()
    holdings.get_holdings.return_value = HoldingsResponse(
        holdings=[Holding(trading_symbol="SYNTH", isin="ISIN-SYNTH", quantity=2, average_price=10)]
    )
    positions.get_positions.return_value = PositionsResponse(positions=[])
    market.get_prices.return_value = {"SYNTH": Decimal("11")}
    service = PortfolioService(holdings, positions, market, exchange="BSE")
    assert service.get_portfolio_summary().current_value == 22
    market.get_prices.assert_called_once_with(["SYNTH"], exchange="BSE")
