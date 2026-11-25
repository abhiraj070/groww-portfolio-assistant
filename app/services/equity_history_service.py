"""Recalculate FIFO from imported executions without inventing opening inventory."""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from app.core.exceptions import ServiceError
from app.schemas.equity_history import EquityHistoryResponse, SaleMatch, StockHistory
from app.schemas.history import EquityAction
from app.services.ledger_service import LedgerService

ZERO = Decimal(0)


@dataclass
class EquityLot:
    trade_id: str
    acquired_at: datetime
    remaining: Decimal
    remaining_cost: Decimal
    remaining_charges: Decimal | None


class EquityHistoryService:
    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def analyse(self, sold_only: bool = False) -> EquityHistoryResponse:
        with localcontext() as context:
            context.prec = 64
            return self._analyse(sold_only)

    def _analyse(self, sold_only: bool) -> EquityHistoryResponse:
        grouped = defaultdict(list)
        for transaction in self.ledger.all_transactions():
            grouped[transaction.isin].append(transaction)
        actions = defaultdict(list)
        for record in self.ledger.records("equity_action"):
            action = EquityAction(**record["data"])
            actions[action.isin].append(action)
        if set(actions) - set(grouped):
            raise ServiceError(
                "adjustment_mismatch", "Corporate action has no imported opening history", 409
            )
        stocks = []
        for isin, records in sorted(grouped.items()):
            lots = deque()
            matches = []
            bought = sold = buy_value = sell_value = unmatched = ZERO
            first_purchase = None
            events = [(r.traded_at, 1, r.trade_id, r) for r in records]
            events += [(a.effective_at, 0, a.action_id, a) for a in actions[isin]]
            for _, _, _, row in sorted(events, key=lambda event: event[:3]):
                if isinstance(row, EquityAction):
                    eligible = sum((lot.remaining for lot in lots), ZERO)
                    if eligible != row.eligible_quantity or unmatched:
                        raise ServiceError(
                            "adjustment_mismatch",
                            "Corporate-action entitlement differs from imported inventory",
                            409,
                        )
                    if row.kind == "SPLIT":
                        for lot in lots:
                            quantity = lot.remaining * row.numerator / row.denominator
                            if quantity != quantity.to_integral_value():
                                raise ServiceError(
                                    "unsupported_adjustment",
                                    "Fractional lots require verified cash-in-lieu accounting",
                                    409,
                                )
                            lot.remaining = quantity
                    else:
                        bonus = eligible * row.numerator / row.denominator
                        if bonus != bonus.to_integral_value():
                            raise ServiceError(
                                "unsupported_adjustment",
                                "Fractional bonus entitlements need verified treatment",
                                409,
                            )
                        lots.append(
                            EquityLot(
                                f"ACTION-{row.action_id}",
                                row.effective_at,
                                bonus,
                                ZERO,
                                ZERO,
                            )
                        )
                    continue
                if row.side == "BUY":
                    bought += row.quantity
                    buy_value += row.quantity * row.price
                    first_purchase = first_purchase or row.traded_at.date()
                    lots.append(
                        EquityLot(
                            row.trade_id,
                            row.traded_at,
                            row.quantity,
                            row.price * row.quantity,
                            row.charges,
                        )
                    )
                    continue
                sold += row.quantity
                sell_value += row.quantity * row.price
                remaining = row.quantity
                sale_charges = row.charges
                while remaining and lots:
                    purchase = lots[0]
                    quantity = min(remaining, purchase.remaining)
                    cost = (
                        purchase.remaining_cost
                        if quantity == purchase.remaining
                        else purchase.remaining_cost * quantity / purchase.remaining
                    )
                    buy_charge = (
                        None
                        if purchase.remaining_charges is None
                        else purchase.remaining_charges
                        if quantity == purchase.remaining
                        else purchase.remaining_charges * quantity / purchase.remaining
                    )
                    sell_charge = (
                        None
                        if sale_charges is None
                        else sale_charges
                        if quantity == remaining
                        else sale_charges * quantity / remaining
                    )
                    charges = (
                        None
                        if buy_charge is None or sell_charge is None
                        else buy_charge + sell_charge
                    )
                    proceeds = row.price * quantity
                    matches.append(
                        SaleMatch(
                            isin=isin,
                            trading_symbol=row.trading_symbol,
                            buy_trade_id=purchase.trade_id,
                            sell_trade_id=row.trade_id,
                            acquired_at=purchase.acquired_at,
                            sold_at=row.traded_at,
                            quantity=quantity,
                            cost=cost,
                            proceeds=proceeds,
                            gross_realised_pnl=proceeds - cost,
                            charges=charges,
                            net_realised_pnl=None if charges is None else proceeds - cost - charges,
                            holding_days=(row.traded_at.date() - purchase.acquired_at.date()).days,
                        )
                    )
                    remaining -= quantity
                    purchase.remaining -= quantity
                    purchase.remaining_cost -= cost
                    if buy_charge is not None:
                        purchase.remaining_charges -= buy_charge
                    if sell_charge is not None:
                        sale_charges -= sell_charge
                    if not purchase.remaining:
                        lots.popleft()
                unmatched += remaining
            quantity_left = sum((lot.remaining for lot in lots), ZERO)
            cost_left = sum((lot.remaining_cost for lot in lots), ZERO)
            gross = None if unmatched else sum((m.gross_realised_pnl for m in matches), ZERO)
            net = (
                None
                if unmatched or any(m.net_realised_pnl is None for m in matches)
                else sum((m.net_realised_pnl for m in matches), ZERO)
            )
            stock = StockHistory(
                isin=isin,
                trading_symbol=records[-1].trading_symbol,
                name=records[-1].name,
                purchased_quantity=bought,
                sold_quantity=sold,
                remaining_quantity=None if unmatched else quantity_left,
                remaining_cost=None if unmatched else cost_left,
                average_purchase_price=buy_value / bought if bought else None,
                average_selling_price=sell_value / sold if sold else None,
                gross_realised_pnl=gross,
                net_realised_pnl=net,
                first_purchase_date=first_purchase,
                last_transaction_date=records[-1].traded_at.date(),
                unmatched_sold_quantity=unmatched,
                matches=matches,
                status="incomplete"
                if unmatched
                else "completely_sold"
                if not quantity_left
                else "partially_sold"
                if sold
                else "held",
            )
            if not sold_only or sold:
                stocks.append(stock)
        return EquityHistoryResponse(
            stocks=stocks,
            gross_realised_pnl=None
            if not stocks or any(s.gross_realised_pnl is None for s in stocks)
            else sum((s.gross_realised_pnl for s in stocks), ZERO),
            net_realised_pnl=None
            if not stocks or any(s.net_realised_pnl is None for s in stocks)
            else sum((s.net_realised_pnl for s in stocks), ZERO),
            warnings=[
                "Imported history only; not certified complete or reconciled to live holdings.",
                "Delivery-equity FIFO across exchanges by ISIN; excludes intraday and derivatives.",
                "Gross gains exclude charges; net gains require charges on every matched lot.",
                "Unmatched sales suppress totals; corporate actions need verified adjustments.",
                "Same-time executions sort by exchange and trade ID; supply accurate timestamps.",
            ],
        )
