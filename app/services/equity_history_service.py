"""Recalculate FIFO from imported executions without inventing opening inventory."""

from collections import defaultdict, deque
from decimal import Decimal

from app.schemas.equity_history import EquityHistoryResponse, SaleMatch, StockHistory
from app.services.ledger_service import LedgerService

ZERO = Decimal(0)


class EquityHistoryService:
    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def analyse(self, sold_only: bool = False) -> EquityHistoryResponse:
        grouped = defaultdict(list)
        for transaction in self.ledger.all_transactions():
            grouped[transaction.isin].append(transaction)
        stocks = []
        for isin, records in sorted(grouped.items()):
            lots = deque()
            matches = []
            bought = sold = buy_value = sell_value = unmatched = ZERO
            first_purchase = None
            for row in records:
                if row.side == "BUY":
                    bought += row.quantity
                    buy_value += row.quantity * row.price
                    first_purchase = first_purchase or row.traded_at.date()
                    lots.append([row, row.quantity])
                    continue
                sold += row.quantity
                sell_value += row.quantity * row.price
                remaining = row.quantity
                while remaining and lots:
                    purchase, available = lots[0]
                    quantity = min(remaining, available)
                    charges = (
                        None
                        if purchase.charges is None or row.charges is None
                        else (
                            purchase.charges * quantity / purchase.quantity
                            + row.charges * quantity / row.quantity
                        )
                    )
                    cost, proceeds = purchase.price * quantity, row.price * quantity
                    matches.append(
                        SaleMatch(
                            isin=isin,
                            trading_symbol=row.trading_symbol,
                            buy_trade_id=purchase.trade_id,
                            sell_trade_id=row.trade_id,
                            acquired_at=purchase.traded_at,
                            sold_at=row.traded_at,
                            quantity=quantity,
                            cost=cost,
                            proceeds=proceeds,
                            gross_realised_pnl=proceeds - cost,
                            charges=charges,
                            net_realised_pnl=None if charges is None else proceeds - cost - charges,
                            holding_days=(row.traded_at.date() - purchase.traded_at.date()).days,
                        )
                    )
                    remaining -= quantity
                    lots[0][1] -= quantity
                    if not lots[0][1]:
                        lots.popleft()
                unmatched += remaining
            quantity_left = sum((q for _, q in lots), ZERO)
            cost_left = sum((p.price * q for p, q in lots), ZERO)
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
