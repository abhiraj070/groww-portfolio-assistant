from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import ServiceError
from app.schemas.investment_analytics import (
    AssetAllocation,
    CombinedPortfolio,
    RealisedGains,
    RiskHolding,
    RiskResponse,
    SectorExposureResponse,
    TaxDataResponse,
)
from app.utils.calculations import percentage

ZERO = Decimal(0)


def complete_sum(*values):
    return None if any(v is None for v in values) else sum(values, ZERO)


class InvestmentService:
    def __init__(self, portfolio, mf, equity_history, ledger):
        self.portfolio, self.mf, self.equity_history, self.ledger = (
            portfolio,
            mf,
            equity_history,
            ledger,
        )

    def combined(self) -> CombinedPortfolio:
        report, mf = self.portfolio.get_portfolio_analytics(), self.mf.portfolio()
        self.check_overlap(report.holdings, mf.holdings)
        equity = report.summary
        value = complete_sum(equity.current_value, mf.current_value)
        cost = complete_sum(equity.invested_value, mf.invested_amount)
        pnl = None if value is None or cost is None else value - cost
        return CombinedPortfolio(
            current_value=value,
            invested_value=cost,
            unrealised_pnl=pnl,
            return_percentage=None if pnl is None else percentage(pnl, cost),
            asset_allocation=[
                AssetAllocation(
                    asset_class=name,
                    current_value=v,
                    invested_value=c,
                    allocation_percentage=None if v is None else percentage(v, value),
                )
                for name, v, c in [
                    ("equity", equity.current_value, equity.invested_value),
                    ("mf", mf.current_value, mf.invested_amount),
                ]
            ],
            retrieved_at=datetime.now(UTC),
            warnings=[
                "Investment assets only: excludes cash, liabilities, property and other assets.",
                "Live equity and imported MF values can have different dates; inspect coverage.",
                "MF units must not also be present in equity holdings; overlap is checked by ISIN.",
                "Remaining acquisition cost is not total historical cash invested.",
            ],
        )

    def realised(self) -> RealisedGains:
        eq, mf = self.equity_history.analyse(), self.mf.portfolio()
        charges = [r.charges for r in self.ledger.all_transactions()] + [
            r.charges for r in self.mf.all_transactions()
        ]
        return RealisedGains(
            equity_gross=eq.gross_realised_pnl,
            mf_gross=mf.gross_realised_pnl,
            total_gross=complete_sum(eq.gross_realised_pnl, mf.gross_realised_pnl),
            equity_net=eq.net_realised_pnl,
            mf_net=mf.net_realised_pnl,
            total_net=complete_sum(eq.net_realised_pnl, mf.net_realised_pnl),
            mf_dividend_income=mf.dividend_income,
            total_investment_costs=None
            if not charges or any(c is None for c in charges)
            else sum(charges, ZERO),
        )

    def sector_exposure(self) -> SectorExposureResponse:
        report = self.portfolio.get_portfolio_analytics()
        return SectorExposureResponse(
            sectors=report.sector_allocation,
            unclassified_market_value=report.unclassified_market_value,
            source=report.sector_metadata_source,
            as_of=report.sector_metadata_as_of,
            warnings=["MF constituent sector data is unavailable; these are equity weights."],
        )

    def risk(self) -> RiskResponse:
        equity, mf = self.portfolio.get_portfolio_analytics(), self.mf.portfolio()
        self.check_overlap(equity.holdings, mf.holdings)
        holdings = [
            RiskHolding(
                asset_class="equity",
                identifier=h.isin,
                value=h.market_value,
                unrealised_pnl=h.unrealised_pnl,
                return_percentage=h.return_percentage,
            )
            for h in equity.holdings
        ]
        schemes = defaultdict(list)
        for holding in mf.holdings:
            schemes[holding.scheme_code].append(holding)
        for code, rows in sorted(schemes.items()):
            market_value = complete_sum(*(r.current_value for r in rows))
            invested = complete_sum(*(r.invested_amount for r in rows))
            pnl = complete_sum(*(r.unrealised_pnl for r in rows))
            holdings.append(
                RiskHolding(
                    asset_class="mf",
                    identifier=code,
                    value=market_value,
                    unrealised_pnl=pnl,
                    return_percentage=None if pnl is None else percentage(pnl, invested),
                )
            )
        value = complete_sum(equity.summary.current_value, mf.current_value)
        cost = complete_sum(equity.summary.invested_value, mf.invested_amount)
        for holding in holdings:
            holding.allocation_percentage = (
                None if holding.value is None else percentage(holding.value, value)
            )
            holding.unrealised_pnl_contribution_percentage = (
                None if holding.unrealised_pnl is None else percentage(holding.unrealised_pnl, cost)
            )
        hhi = (
            None
            if value is None or value == 0
            else sum(((h.value / value) ** 2 for h in holdings), ZERO)
        )
        ranked = sorted(
            (h for h in holdings if h.return_percentage is not None),
            key=lambda h: (h.return_percentage, h.identifier),
        )
        return RiskResponse(
            holdings=holdings,
            top_five_holdings=sorted(
                (h for h in holdings if h.value is not None), key=lambda h: (-h.value, h.identifier)
            )[:5],
            best_performers=list(reversed(ranked))[:5],
            worst_performers=ranked[:5],
            hhi=hhi,
            effective_holdings=None if not hhi else 1 / hhi,
            warnings=[
                "Concentration groups MF folios by scheme; no constituent look-through.",
                "Volatility needs a cash-flow-adjusted historical series; unavailable here.",
                "P&L contribution is unrealised gain divided by remaining acquisition cost.",
            ],
        )

    def tax_data(self, start: date | None = None, end: date | None = None):
        if start and end and start > end:
            raise ServiceError("invalid_range", "Invalid disposal date range", 422)
        eq, mf = self.equity_history.analyse(), self.mf.portfolio()
        return TaxDataResponse(
            equity_lots=[
                m
                for s in eq.stocks
                for m in s.matches
                if (start is None or m.sold_at.date() >= start)
                and (end is None or m.sold_at.date() <= end)
            ],
            mf_lots=[
                m
                for m in mf.matches
                if (start is None or m.sold_on >= start) and (end is None or m.sold_on <= end)
            ],
            history_complete=False,
            warnings=[
                "Imported FIFO disposal data only; not tax liability or a filing-ready report.",
                "No STCG/LTCG classification, grandfathering, exemptions or rates are inferred.",
                "Unmatched disposals are excluded from lot matches; inspect module coverage.",
            ],
        )

    @staticmethod
    def check_overlap(equity, mf):
        if {h.isin for h in equity if h.quantity != 0} & {
            h.isin for h in mf if h.isin and h.units != 0
        }:
            raise ServiceError(
                "overlapping_assets",
                "Resolve overlapping equity/MF identifiers before combining",
                409,
            )
