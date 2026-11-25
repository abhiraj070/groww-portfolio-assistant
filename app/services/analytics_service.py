"""Pure Decimal calculations over validated holdings and a separate positions snapshot."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.holdings import Holding
from app.schemas.portfolio import (
    AnalyticsResponse,
    Concentration,
    HoldingValuation,
    PortfolioSummary,
    SectorAllocation,
)
from app.schemas.positions import Position
from app.utils.calculations import ZERO, percentage


class SectorMetadata(BaseModel):
    # The operator must verify this source; no sector classifications are inferred.
    source: str = Field(min_length=1)
    as_of: date
    sectors: dict[str, Annotated[str, Field(min_length=1)]]


class AnalyticsService:
    def analyse(
        self,
        holdings: list[Holding],
        positions: list[Position],
        prices: dict[str, Decimal | None],
        exchange: str = "NSE",
        sectors: SectorMetadata | None = None,
    ) -> AnalyticsResponse:
        rows = []
        missing_prices = []
        missing_costs = []
        for holding in holdings:
            price = prices.get(holding.trading_symbol)
            # A zero-quantity asset contributes zero without requiring a quote or cost.
            cost = (
                ZERO
                if holding.quantity == 0
                else None
                if holding.average_price is None
                else holding.quantity * holding.average_price
            )
            value = (
                ZERO
                if holding.quantity == 0
                else None
                if price is None
                else holding.quantity * price
            )
            pnl = None if value is None or cost is None else value - cost
            if value is None:
                missing_prices.append(holding.trading_symbol)
            if cost is None:
                missing_costs.append(holding.trading_symbol)
            rows.append(
                HoldingValuation(
                    trading_symbol=holding.trading_symbol,
                    isin=holding.isin,
                    quantity=holding.quantity,
                    average_price=holding.average_price,
                    current_price=price,
                    invested_value=cost,
                    market_value=value,
                    unrealised_pnl=pnl,
                    absolute_return=pnl,
                    return_percentage=None if pnl is None else percentage(pnl, cost),
                    sector=None if sectors is None else sectors.sectors.get(holding.isin),
                )
            )
        known_cost = sum((r.invested_value for r in rows if r.invested_value is not None), ZERO)
        known_value = sum((r.market_value for r in rows if r.market_value is not None), ZERO)
        cost = None if missing_costs else known_cost
        value = None if missing_prices else known_value
        pnl = None if cost is None or value is None else value - cost
        reported_realised = sum(
            (p.realised_pnl for p in positions if p.realised_pnl is not None), ZERO
        )
        realised_complete = all(p.realised_pnl is not None for p in positions)
        warnings = [
            "Holdings and positions are separate; positions are not added to holdings valuation.",
            "Realised P&L covers the returned positions snapshot, not lifetime trading history.",
            f"Holdings are priced on {exchange}; verify listings for this valuation exchange.",
            "LTP retrieval time is not the last-trade time; quote freshness is not guaranteed.",
            "Returns exclude fees, taxes, dividends and cash flows; "
            "they are not XIRR or total return.",
        ]
        if missing_prices:
            warnings.append(
                "Missing prices: total value, returns and concentration are incomplete."
            )
        if missing_costs:
            warnings.append("Missing purchase costs: invested value and returns are incomplete.")
        if not realised_complete:
            warnings.append("Some positions have no reported realised P&L.")
        if sectors is None:
            warnings.append(
                "Sector metadata is unavailable; no sector classifications are inferred."
            )
        elif any(r.sector is None and r.quantity > 0 for r in rows):
            warnings.append("Some holdings have no sector classification in the supplied metadata.")
        summary = PortfolioSummary(
            valuation_exchange=exchange,
            retrieved_at=datetime.now(UTC),
            holdings_count=len(rows),
            positions_count=len(positions),
            invested_value=cost,
            current_value=value,
            unrealised_pnl=pnl,
            absolute_return=pnl,
            return_percentage=None if pnl is None else percentage(pnl, cost),
            known_invested_value=known_cost,
            priced_market_value=known_value,
            missing_prices=missing_prices,
            missing_costs=missing_costs,
            realised_pnl=reported_realised if realised_complete else None,
            reported_realised_pnl=reported_realised,
            realised_pnl_complete=realised_complete,
            warnings=warnings,
        )
        for row in rows:
            if row.market_value is not None:
                row.allocation_percentage = percentage(row.market_value, value)
        valid_weights = value is not None and value > ZERO
        values = sorted((r.market_value for r in rows if r.market_value is not None), reverse=True)
        concentration = Concentration(
            largest_holding_percentage=percentage(values[0], value)
            if valid_weights and values
            else None,
            top_three_percentage=percentage(sum(values[:3], ZERO), value)
            if valid_weights
            else None,
            hhi=sum(((v / value) ** 2 for v in values), ZERO) if valid_weights else None,
        )
        allocations = []
        for name in sorted({r.sector for r in rows if r.sector is not None}):
            sector_rows = [r for r in rows if r.sector == name]
            sector_value = (
                None
                if any(r.market_value is None for r in sector_rows)
                else sum((r.market_value for r in sector_rows), ZERO)
            )
            allocations.append(
                SectorAllocation(
                    sector=name,
                    market_value=sector_value,
                    allocation_percentage=None
                    if sector_value is None
                    else percentage(sector_value, value),
                )
            )
        unclassified = [r for r in rows if r.sector is None]
        unclassified_value = (
            None
            if any(r.market_value is None for r in unclassified)
            else sum((r.market_value for r in unclassified), ZERO)
        )
        ranked = sorted(
            (r for r in rows if r.return_percentage is not None),
            key=lambda r: (r.return_percentage, r.trading_symbol),
            reverse=True,
        )
        return AnalyticsResponse(
            summary=summary,
            holdings=rows,
            sector_allocation=allocations,
            sector_metadata_source=None if sectors is None else sectors.source,
            sector_metadata_as_of=None if sectors is None else sectors.as_of,
            unclassified_market_value=unclassified_value,
            concentration=concentration,
            top_performers=ranked[:5],
            worst_performers=list(reversed(ranked))[:5],
        )
