"""Execution records, imported coverage and FIFO sale matches."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.market_data import Symbol

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=24, decimal_places=10)]
ImportAmount = Annotated[
    Decimal, Field(ge=0, allow_inf_nan=False, max_digits=24, decimal_places=10)
]


class EquityTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    trade_id: Identifier
    order_id: Identifier | None = None
    trading_symbol: Symbol
    isin: str = Field(min_length=1, max_length=30)
    name: str | None = Field(default=None, max_length=200)
    exchange: Literal["NSE", "BSE"]
    side: Literal["BUY", "SELL"]
    traded_at: datetime
    quantity: Positive
    price: ImportAmount
    charges: ImportAmount | None = None

    @field_validator("traded_at")
    @classmethod
    def exchange_time(cls, value: datetime) -> datetime:
        # Tradebooks often contain exchange-local dates without offsets.
        zone = ZoneInfo("Asia/Kolkata")
        value = value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
        if value.date() > datetime.now(zone).date():
            raise ValueError("Future execution date")
        return value


class StoredEquityTransaction(EquityTransaction):
    source: str
    imported_at: datetime
    import_id: int


class TradebookResponse(BaseModel):
    transactions: list[StoredEquityTransaction]
    total: int
    offset: int
    limit: int
    scope: Literal["imported_equity_executions"] = "imported_equity_executions"
    history_complete: Literal[False] = False


class SaleMatch(BaseModel):
    isin: str
    trading_symbol: str
    buy_trade_id: str
    sell_trade_id: str
    acquired_at: datetime
    sold_at: datetime
    quantity: Decimal
    cost: Decimal
    proceeds: Decimal
    gross_realised_pnl: Decimal
    charges: Decimal | None
    net_realised_pnl: Decimal | None
    holding_days: int


class StockHistory(BaseModel):
    isin: str
    trading_symbol: str
    name: str | None
    purchased_quantity: Decimal
    sold_quantity: Decimal
    remaining_quantity: Decimal | None
    average_purchase_price: Decimal | None
    average_selling_price: Decimal | None
    gross_realised_pnl: Decimal | None
    net_realised_pnl: Decimal | None
    remaining_cost: Decimal | None
    first_purchase_date: date | None
    last_transaction_date: date
    status: Literal["held", "partially_sold", "completely_sold", "incomplete"]
    unmatched_sold_quantity: Decimal
    matches: list[SaleMatch]


class EquityHistoryResponse(BaseModel):
    stocks: list[StockHistory]
    gross_realised_pnl: Decimal | None
    net_realised_pnl: Decimal | None
    scope: Literal["imported_equity_executions_fifo"] = "imported_equity_executions_fifo"
    history_complete: Literal[False] = False
    warnings: list[str]


class ImportResult(BaseModel):
    import_id: int
    inserted: int
    duplicates: int
    source: str
    imported_at: datetime
