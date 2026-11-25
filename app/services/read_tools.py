"""Explicit reusable reads for future AI adapters. No server, dispatcher or write tools."""

from datetime import date

from app.schemas.equity_history import EquityHistoryResponse, TradebookResponse
from app.schemas.investment_analytics import (
    CombinedPortfolio,
    PerformanceResponse,
    Period,
    RealisedGains,
    RiskResponse,
    SectorExposureResponse,
)
from app.schemas.market_data import Exchange, QuoteResponse, Segment, Symbol
from app.schemas.mutual_funds import MFHolding, MFTransactionsResponse
from app.schemas.portfolio import HoldingValuation
from app.services.container import Services


class ReadTools:
    """Trusted local service facade; an eventual transport must authorize its own callers.

    Returns Pydantic models so adapters can use model_dump(mode='json'), retaining
    Decimal strings and scope/coverage warnings. Owning caller closes Services.
    """

    def __init__(self, services: Services):
        self._services = services

    def get_stock_holdings(self) -> list[HoldingValuation]:
        return self._services.portfolio.get_portfolio_analytics().holdings

    def get_sold_stocks(self) -> EquityHistoryResponse:
        return self._services.equity_history.analyse(sold_only=True)

    def get_stock_transaction_history(
        self, offset: int = 0, limit: int = 100, symbol: Symbol | None = None
    ) -> TradebookResponse:
        return self._services.ledger.tradebook(offset, limit, symbol)

    def get_realised_pnl(self) -> RealisedGains:
        return self._services.investment.realised()

    def get_mf_holdings(self) -> list[MFHolding]:
        return self._services.mf.portfolio().holdings

    def get_mf_transactions(self, offset: int = 0, limit: int = 100) -> MFTransactionsResponse:
        return self._services.mf.transactions(offset=offset, limit=limit)

    def get_portfolio_summary(self) -> CombinedPortfolio:
        return self._services.investment.combined()

    def get_portfolio_analytics(self) -> RiskResponse:
        return self._services.investment.risk()

    def get_investment_performance(
        self, period: Period = "all_time", start: date | None = None, end: date | None = None
    ) -> PerformanceResponse:
        return self._services.performance.performance(period, start, end)

    def get_asset_allocation(self) -> CombinedPortfolio:
        return self._services.investment.combined()

    def get_sector_exposure(self) -> SectorExposureResponse:
        return self._services.investment.sector_exposure()

    def get_stock_quote(
        self, symbol: Symbol, exchange: Exchange = "NSE", segment: Segment = "CASH"
    ) -> QuoteResponse:
        return self._services.market.get_quote(symbol, exchange, segment)
