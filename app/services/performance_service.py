import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.core.exceptions import ServiceError
from app.schemas.investment_analytics import (
    CashFlow,
    PerformanceResponse,
    Period,
    PortfolioObservation,
)
from app.services.ledger_service import LedgerService
from app.services.mf_ingestion_service import canonical_csv
from app.utils.calculations import percentage
from app.utils.returns import cagr, xirr


class PerformanceService:
    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def import_cashflows(self, content: bytes, source: str):
        rows = canonical_csv(content, CashFlow, {"flow_id", "date", "kind", "amount"})
        return self.ledger.import_records(
            "cashflow",
            content,
            source,
            [(r.flow_id, r.model_dump(mode="json"), raw) for r, raw in rows],
        )

    def import_observations(self, content: bytes, source: str):
        rows = canonical_csv(
            content, PortfolioObservation, {"date", "equity_value", "mf_value", "cash_value"}
        )
        return self.ledger.import_records(
            "portfolio_observation",
            content,
            source,
            [(str(r.date), r.model_dump(mode="json"), raw) for r, raw in rows],
        )

    def observations(self):
        return sorted(
            [
                PortfolioObservation(**r["data"])
                for r in self.ledger.records("portfolio_observation")
            ],
            key=lambda r: r.date,
        )

    def performance(
        self, period: Period = "all_time", start: date | None = None, end: date | None = None
    ) -> PerformanceResponse:
        if period not in {"daily", "weekly", "monthly", "quarterly", "yearly", "all_time"}:
            raise ServiceError("invalid_period", "Invalid performance period", 422)
        explicit_range = start is not None
        rows = self.observations()
        warnings = [
            "Snapshots include cash; internal trades/dividends/charges are not external flows.",
            "Coverage of deposits/withdrawals is operator-attested by the closing observation.",
            "All-time means the imported snapshot window; it is not a lifetime guarantee.",
        ]
        end = end or (rows[-1].date if rows else None)
        if start is None and end is not None:
            if period == "all_time":
                start = rows[0].date if rows else None
            elif period in {"daily", "weekly"}:
                start = end - timedelta(days=1 if period == "daily" else 7)
            else:
                months = {"monthly": 1, "quarterly": 3, "yearly": 12}[period]
                year, month = divmod(end.year * 12 + end.month - 1 - months, 12)
                start = date(year, month + 1, min(end.day, calendar.monthrange(year, month + 1)[1]))
        if start and end and start >= end:
            if not explicit_range and start == end:
                return PerformanceResponse(
                    period=period,
                    start=start,
                    end=end,
                    warnings=["At least two dated snapshots are required."],
                )
            raise ServiceError(
                "invalid_range", "Performance requires an increasing date range", 422
            )
        result = PerformanceResponse(period=period, start=start, end=end, warnings=warnings)
        indexed = {r.date: r for r in rows}
        if start not in indexed or end not in indexed:
            result.warnings.append(
                "Exact opening and closing snapshots are required; no interpolation."
            )
            return result
        opening, closing = indexed[start], indexed[end]
        result.opening_value = opening.equity_value + opening.mf_value + opening.cash_value
        result.closing_value = closing.equity_value + closing.mf_value + closing.cash_value
        result.cashflows_complete = (
            closing.cashflows_complete_from is not None and closing.cashflows_complete_from <= start
        )
        if not result.cashflows_complete:
            result.warnings.append(
                "External cash-flow coverage is not established; returns are unknown."
            )
            return result
        flows = [CashFlow(**r["data"]) for r in self.ledger.records("cashflow")]
        external = [
            (r.date, -r.amount if r.kind == "DEPOSIT" else r.amount)
            for r in flows
            if start < r.date <= end and r.kind in {"DEPOSIT", "WITHDRAWAL"}
        ]
        result.net_contributions = -sum((a for _, a in external), Decimal(0))
        result.absolute_return = (
            result.closing_value - result.opening_value - result.net_contributions
        )
        result.available = True
        dated = [(start, -result.opening_value), *external, (end, result.closing_value)]
        rate = xirr(dated)
        result.xirr_percentage = None if rate is None else rate * 100
        if not external:
            result.return_percentage = percentage(result.absolute_return, result.opening_value)
            annual = cagr(result.opening_value, result.closing_value, (end - start).days)
            result.cagr_percentage = None if annual is None else annual * 100
        if rate is None:
            result.warnings.append(
                "XIRR is undefined, outside solver bounds or has nonconventional sign changes."
            )
        return result
