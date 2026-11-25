"""Statement-backed MF FIFO and valuation, independent of equity and Groww services."""

from collections import defaultdict, deque
from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import ServiceError
from app.schemas.mutual_funds import (
    MFHolding,
    MFPortfolioResponse,
    MFSaleMatch,
    MFTransactionsResponse,
    StoredMFTransaction,
    StoredNAV,
    UnavailableMetric,
)
from app.services.ledger_service import LedgerService
from app.utils.calculations import percentage

ZERO = Decimal(0)
PURCHASES = {"PURCHASE", "SIP", "SWITCH_IN", "REINVESTMENT"}
REDEMPTIONS = {"REDEMPTION", "SWITCH_OUT"}


class MFService:
    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def all_transactions(self) -> list[StoredMFTransaction]:
        return sorted(
            [
                StoredMFTransaction(
                    **r["data"], **{k: r[k] for k in ("source", "imported_at", "import_id")}
                )
                for r in self.ledger.records("mf_transaction")
            ],
            key=lambda r: (r.date, r.transaction_id),
        )

    def transactions(
        self, kinds: set[str] | None = None, offset: int = 0, limit: int = 100
    ) -> MFTransactionsResponse:
        if not 0 <= offset <= 1000000 or not 1 <= limit <= 1000:
            raise ServiceError("invalid_pagination", "Invalid MF pagination", 422)
        rows = [r for r in self.all_transactions() if kinds is None or r.kind in kinds]
        return MFTransactionsResponse(
            transactions=rows[offset : offset + limit], total=len(rows), offset=offset, limit=limit
        )

    def nav_history(
        self, scheme_code: str, start: date | None = None, end: date | None = None
    ) -> list[StoredNAV]:
        if start and end and start > end:
            raise ServiceError("invalid_range", "Invalid NAV date range", 422)
        rows = [
            StoredNAV(**r["data"], source=r["source"], imported_at=r["imported_at"])
            for r in self.ledger.records("nav")
            if r["data"]["scheme_code"] == scheme_code
        ]
        return sorted(
            [
                r
                for r in rows
                if (start is None or r.date >= start) and (end is None or r.date <= end)
            ],
            key=lambda r: r.date,
        )

    def latest_nav(self, scheme_code: str) -> StoredNAV:
        rows = self.nav_history(scheme_code)
        if not rows:
            raise ServiceError(
                "nav_unavailable", "No imported NAV observation for this scheme", 404
            )
        return rows[-1]

    def schemes(self, offset: int = 0, limit: int = 100) -> list[StoredNAV]:
        if not 0 <= offset <= 1000000 or not 1 <= limit <= 1000:
            raise ServiceError("invalid_pagination", "Invalid scheme pagination", 422)
        latest = {}
        for row in self.ledger.records("nav"):
            observation = StoredNAV(
                **row["data"], source=row["source"], imported_at=row["imported_at"]
            )
            previous = latest.get(observation.scheme_code)
            if previous is None or previous.date < observation.date:
                latest[observation.scheme_code] = observation
        return sorted(latest.values(), key=lambda r: r.scheme_code)[offset : offset + limit]

    @staticmethod
    def unavailable(metric: str) -> UnavailableMetric:
        sources = {
            "benchmark_returns": "Verified benchmark total-return index history and scheme mapping",
            "expense_ratio": "Dated AMC plan-specific total expense ratio disclosures",
            "fund_overlap": "Dated AMC portfolio constituent weights with security identifiers",
        }
        return UnavailableMetric(
            metric=metric,
            reason="Required source is not configured; NAV alone cannot establish this metric",
            required_source=sources[metric],
        )

    def portfolio(self) -> MFPortfolioResponse:
        transactions = self.all_transactions()
        grouped = defaultdict(list)
        for row in transactions:
            grouped[(row.folio, row.scheme_code)].append(row)
        holdings, matches = [], []
        navs = {}
        for record in self.ledger.records("nav"):
            nav = StoredNAV(
                **record["data"], source=record["source"], imported_at=record["imported_at"]
            )
            if nav.scheme_code not in navs or navs[nav.scheme_code].date < nav.date:
                navs[nav.scheme_code] = nav
        for (folio, code), rows in sorted(grouped.items()):
            lots = deque()
            unmatched = ZERO
            scheme_matches = []
            for row in rows:
                if row.kind in PURCHASES:
                    lots.append([row, row.units])
                elif row.kind in REDEMPTIONS:
                    remaining = row.units
                    while remaining and lots:
                        purchase, units = lots[0]
                        matched = min(remaining, units)
                        cost, proceeds = (
                            purchase.amount * matched / purchase.units,
                            row.amount * matched / row.units,
                        )
                        charges = (
                            None
                            if purchase.charges is None or row.charges is None
                            else purchase.charges * matched / purchase.units
                            + row.charges * matched / row.units
                        )
                        scheme_matches.append(
                            MFSaleMatch(
                                folio=folio,
                                scheme_code=code,
                                acquired_on=purchase.date,
                                sold_on=row.date,
                                purchase_id=purchase.transaction_id,
                                redemption_id=row.transaction_id,
                                units=matched,
                                cost=cost,
                                proceeds=proceeds,
                                gross_realised_pnl=proceeds - cost,
                                charges=charges,
                                net_realised_pnl=None
                                if charges is None
                                else proceeds - cost - charges,
                                holding_days=(row.date - purchase.date).days,
                            )
                        )
                        remaining -= matched
                        lots[0][1] -= matched
                        if not lots[0][1]:
                            lots.popleft()
                    unmatched += remaining
            units = None if unmatched else sum((q for _, q in lots), ZERO)
            cost = None if unmatched else sum((p.amount * q / p.units for p, q in lots), ZERO)
            nav = navs.get(code)
            # A NAV before the last imported unit movement cannot value that position.
            movement_dates = [r.date for r in rows if r.kind != "DIVIDEND"]
            usable = nav is not None and (not movement_dates or nav.date >= max(movement_dates))
            value = ZERO if units == 0 else None if units is None or not usable else units * nav.nav
            pnl = None if value is None or cost is None else value - cost
            gross = None if unmatched else sum((m.gross_realised_pnl for m in scheme_matches), ZERO)
            net = (
                None
                if unmatched or any(m.net_realised_pnl is None for m in scheme_matches)
                else sum((m.net_realised_pnl for m in scheme_matches), ZERO)
            )
            latest = rows[-1]
            holdings.append(
                MFHolding(
                    folio=folio,
                    scheme_code=code,
                    scheme_name=latest.scheme_name,
                    isin=latest.isin,
                    fund_house=latest.fund_house,
                    units=units,
                    average_purchase_nav=None if not units or cost is None else cost / units,
                    invested_amount=cost,
                    latest_nav=nav.nav if usable else None,
                    nav_date=None if nav is None else nav.date,
                    nav_source=None if nav is None else nav.source,
                    current_value=value,
                    unrealised_pnl=pnl,
                    return_percentage=None if pnl is None else percentage(pnl, cost),
                    gross_realised_pnl=gross,
                    net_realised_pnl=net,
                    unmatched_redeemed_units=unmatched,
                )
            )
            matches.extend(scheme_matches)

        def total(field):
            values = [getattr(h, field) for h in holdings]
            return None if not values or any(v is None for v in values) else sum(values, ZERO)

        cost, value = total("invested_amount"), total("current_value")
        pnl = None if cost is None or value is None else value - cost
        for holding in holdings:
            holding.allocation_percentage = (
                None if holding.current_value is None else percentage(holding.current_value, value)
            )
        return MFPortfolioResponse(
            holdings=holdings,
            invested_amount=cost,
            current_value=value,
            unrealised_pnl=pnl,
            return_percentage=None if pnl is None else percentage(pnl, cost),
            gross_realised_pnl=total("gross_realised_pnl"),
            net_realised_pnl=total("net_realised_pnl"),
            dividend_income=sum(
                (r.amount for r in transactions if r.kind in {"DIVIDEND", "REINVESTMENT"}), ZERO
            ),
            sip_investment=sum((r.amount for r in transactions if r.kind == "SIP"), ZERO),
            matches=matches,
            retrieved_at=datetime.now(UTC),
            warnings=[
                "Imported statements only; reconcile units with your CAS. No live Groww MF access.",
                "FIFO is per folio and scheme; missing opening units suppress dependent values.",
                "Invested amount is remaining lot cost excluding charges.",
                "NAV dates may differ across schemes; no price freshness is assumed.",
                "SIP data describes executed instalments, not active mandates or future schedules.",
                "Gross gains exclude charges; net gains require explicit matched charges.",
                "Switch legs and reinvestment are statement events; no cash movement is initiated.",
            ],
        )
