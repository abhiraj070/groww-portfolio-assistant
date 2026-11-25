from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.services.analytics_service import SectorMetadata
from app.services.equity_history_service import EquityHistoryService
from app.services.groww_client import GrowwClient
from app.services.history_service import HistoryService
from app.services.holdings_service import HoldingsService
from app.services.instruments_service import InstrumentsService
from app.services.investment_service import InvestmentService
from app.services.ledger_service import LedgerService
from app.services.market_data_service import MarketDataService
from app.services.mf_service import MFService
from app.services.orders_service import OrdersService
from app.services.performance_service import PerformanceService
from app.services.portfolio_service import PortfolioService
from app.services.positions_service import PositionsService


@dataclass
class Services:
    client: GrowwClient
    holdings: HoldingsService
    positions: PositionsService
    orders: OrdersService
    market: MarketDataService
    portfolio: PortfolioService
    ledger: LedgerService | None = None
    equity_history: EquityHistoryService | None = None
    instruments: InstrumentsService | None = None
    mf: MFService | None = None
    investment: InvestmentService | None = None
    performance: PerformanceService | None = None
    history: HistoryService | None = None

    def close(self):
        self.client.close()
        if self.instruments is not None:
            self.instruments.close()

    @classmethod
    def build(cls, settings: Settings):
        sectors = None
        if settings.sector_metadata_file is not None:
            try:
                sectors = SectorMetadata.model_validate_json(
                    settings.sector_metadata_file.read_text(encoding="utf-8")
                )
                if sectors.as_of > datetime.now(ZoneInfo("Asia/Kolkata")).date():
                    raise ValueError("Future classification date")
            except (OSError, ValidationError, ValueError, UnicodeError):
                raise ServiceError(
                    "invalid_sector_metadata", "Sector metadata file is missing or invalid", 503
                ) from None
        client = GrowwClient(settings)
        holdings, positions = HoldingsService(client), PositionsService(client)
        orders, market = OrdersService(client), MarketDataService(client)
        portfolio = PortfolioService(
            holdings, positions, market, settings.valuation_exchange, sectors
        )
        ledger = LedgerService(settings.ledger_path)
        mf = MFService(ledger)
        history = EquityHistoryService(ledger)
        return cls(
            client,
            holdings,
            positions,
            orders,
            market,
            portfolio,
            ledger,
            history,
            InstrumentsService(settings.groww_request_timeout_seconds),
            mf,
            InvestmentService(portfolio, mf, history, ledger),
            PerformanceService(ledger),
            HistoryService(ledger, portfolio, mf),
        )
