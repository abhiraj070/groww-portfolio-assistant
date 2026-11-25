from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.equity_history import Identifier, Positive, SaleMatch
from app.schemas.holdings import NonNegative
from app.schemas.mutual_funds import MFSaleMatch
from app.schemas.portfolio import SectorAllocation

Period = Literal["daily", "weekly", "monthly", "quarterly", "yearly", "all_time"]


class CashFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_id: Identifier
    date: date
    kind: Literal["DEPOSIT", "WITHDRAWAL", "PURCHASE", "SALE", "REDEMPTION", "DIVIDEND", "CHARGE"]
    amount: Positive

    @field_validator("date")
    @classmethod
    def not_future(cls, value: date):
        if value > datetime.now(ZoneInfo("Asia/Kolkata")).date():
            raise ValueError("Future flow")
        return value


class PortfolioObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    equity_value: NonNegative
    mf_value: NonNegative
    cash_value: NonNegative
    cashflows_complete_from: date | None = None

    _not_future = field_validator("date")(CashFlow.not_future.__func__)


class AssetAllocation(BaseModel):
    asset_class: str
    current_value: Decimal | None
    invested_value: Decimal | None
    allocation_percentage: Decimal | None


class CombinedPortfolio(BaseModel):
    current_value: Decimal | None
    invested_value: Decimal | None
    unrealised_pnl: Decimal | None
    return_percentage: Decimal | None
    asset_allocation: list[AssetAllocation]
    retrieved_at: datetime
    scope: Literal["equity_and_mf_excluding_cash_other_assets"] = (
        "equity_and_mf_excluding_cash_other_assets"
    )
    warnings: list[str]


class PerformanceResponse(BaseModel):
    period: Period
    start: date | None
    end: date | None
    opening_value: Decimal | None = None
    closing_value: Decimal | None = None
    net_contributions: Decimal | None = None
    absolute_return: Decimal | None = None
    return_percentage: Decimal | None = None
    cagr_percentage: Decimal | None = None
    xirr_percentage: Decimal | None = None
    cashflows_complete: bool = False
    available: bool = False
    warnings: list[str] = Field(default_factory=list)


class RealisedGains(BaseModel):
    equity_gross: Decimal | None
    mf_gross: Decimal | None
    total_gross: Decimal | None
    equity_net: Decimal | None
    mf_net: Decimal | None
    total_net: Decimal | None
    mf_dividend_income: Decimal
    equity_dividend_income: Decimal | None = None
    total_investment_costs: Decimal | None
    scope: Literal["imported_history"] = "imported_history"
    history_complete: Literal[False] = False


class RiskHolding(BaseModel):
    asset_class: Literal["equity", "mf"]
    identifier: str
    value: Decimal | None
    unrealised_pnl: Decimal | None
    return_percentage: Decimal | None
    allocation_percentage: Decimal | None = None
    unrealised_pnl_contribution_percentage: Decimal | None = None


class RiskResponse(BaseModel):
    holdings: list[RiskHolding]
    top_five_holdings: list[RiskHolding]
    best_performers: list[RiskHolding]
    worst_performers: list[RiskHolding]
    hhi: Decimal | None
    effective_holdings: Decimal | None
    volatility: Decimal | None = None
    warnings: list[str]


class SectorExposureResponse(BaseModel):
    sectors: list[SectorAllocation]
    unclassified_market_value: Decimal | None
    source: str | None
    as_of: date | None
    scope: Literal["equity_only"] = "equity_only"
    warnings: list[str]


class TaxDataResponse(BaseModel):
    equity_lots: list[SaleMatch]
    mf_lots: list[MFSaleMatch]
    history_complete: Literal[False] = False
    warnings: list[str]
