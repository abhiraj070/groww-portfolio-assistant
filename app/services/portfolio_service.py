from app.schemas.portfolio import AnalyticsResponse, PortfolioSummary
from app.services.analytics_service import AnalyticsService, SectorMetadata
from app.services.holdings_service import HoldingsService
from app.services.market_data_service import MarketDataService
from app.services.positions_service import PositionsService


class PortfolioService:
    def __init__(
        self,
        holdings: HoldingsService,
        positions: PositionsService,
        market: MarketDataService,
        exchange: str = "NSE",
        sectors: SectorMetadata | None = None,
    ):
        self.holdings = holdings
        self.positions = positions
        self.market = market
        self.exchange = exchange
        self.sectors = sectors
        self.analytics = AnalyticsService()

    def get_portfolio_analytics(self) -> AnalyticsResponse:
        holdings = self.holdings.get_holdings().holdings
        positions = self.positions.get_positions().positions
        prices = self.market.get_prices(
            [h.trading_symbol for h in holdings if h.quantity > 0], exchange=self.exchange
        )
        return self.analytics.analyse(holdings, positions, prices, self.exchange, self.sectors)

    def get_portfolio_summary(self) -> PortfolioSummary:
        return self.get_portfolio_analytics().summary
