from pydantic import BaseModel, ConfigDict, Field

from app.schemas.holdings import FiniteDecimal, NonNegative


class Position(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    trading_symbol: str = Field(min_length=1, max_length=100)
    segment: str = Field(min_length=1)
    quantity: FiniteDecimal
    exchange: str | None = None
    product: str | None = None
    symbol_isin: str | None = None
    credit_quantity: NonNegative | None = None
    credit_price: NonNegative | None = None
    debit_quantity: NonNegative | None = None
    debit_price: NonNegative | None = None
    carry_forward_credit_quantity: NonNegative | None = None
    carry_forward_credit_price: NonNegative | None = None
    carry_forward_debit_quantity: NonNegative | None = None
    carry_forward_debit_price: NonNegative | None = None
    net_carry_forward_quantity: FiniteDecimal | None = None
    net_price: FiniteDecimal | None = None
    net_carry_forward_price: FiniteDecimal | None = None
    realised_pnl: FiniteDecimal | None = None


class PositionsResponse(BaseModel):
    positions: list[Position]
