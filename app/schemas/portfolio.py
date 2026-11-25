from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.holdings import NonNegative


class HoldingValuation(BaseModel):
    trading_symbol: str
    isin: str
    quantity: NonNegative
    average_price: NonNegative | None
    current_price: NonNegative | None
    invested_value: NonNegative | None
    market_value: NonNegative | None
    unrealised_pnl: Decimal | None
    absolute_return: Decimal | None
    return_percentage: Decimal | None
    allocation_percentage: Decimal | None = None
    sector: str | None = None


class PortfolioSummary(BaseModel):
    currency: Literal["INR"] = "INR"
    valuation_scope: Literal["holdings_only"] = "holdings_only"
    valuation_exchange: Literal["NSE", "BSE"]
    retrieved_at: datetime
    holdings_count: int
    positions_count: int
    invested_value: NonNegative | None
    current_value: NonNegative | None
    unrealised_pnl: Decimal | None
    absolute_return: Decimal | None
    return_percentage: Decimal | None
    known_invested_value: NonNegative
    priced_market_value: NonNegative
    missing_prices: list[str]
    missing_costs: list[str]
    realised_pnl: Decimal | None
    reported_realised_pnl: Decimal
    realised_pnl_complete: bool
    realised_pnl_scope: Literal["current_positions_snapshot"] = "current_positions_snapshot"
    warnings: list[str]


class SectorAllocation(BaseModel):
    sector: str
    market_value: NonNegative | None
    allocation_percentage: Decimal | None


class Concentration(BaseModel):
    largest_holding_percentage: Decimal | None
    top_three_percentage: Decimal | None
    hhi: Decimal | None = Field(description="Sum of squared market-value weights, from 0 to 1")


class AnalyticsResponse(BaseModel):
    summary: PortfolioSummary
    holdings: list[HoldingValuation]
    sector_allocation: list[SectorAllocation]
    sector_metadata_source: str | None
    sector_metadata_as_of: date | None
    unclassified_market_value: NonNegative | None
    concentration: Concentration
    top_performers: list[HoldingValuation]
    worst_performers: list[HoldingValuation]
    ranking_basis: Literal["unrealised_return_percentage"] = "unrealised_return_percentage"
