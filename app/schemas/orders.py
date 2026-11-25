from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.holdings import NonNegative


class Order(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    groww_order_id: str = Field(min_length=1)
    trading_symbol: str = Field(min_length=1)
    order_status: str = Field(min_length=1)
    quantity: NonNegative
    filled_quantity: NonNegative | None = None
    order_type: str | None = None
    transaction_type: str | None = None
    price: NonNegative | None = None
    created_at: datetime | None = None
    exchange_time: datetime | None = None
    exchange: str | None = None
    segment: str | None = None


class OrdersResponse(BaseModel):
    orders: list[Order]
    page: int
    page_size: int
    possible_next_page: int | None
    scope: Literal["current_trading_day"] = "current_trading_day"
