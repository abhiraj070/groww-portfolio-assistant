from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


class Holding(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    trading_symbol: str = Field(min_length=1, max_length=100)
    isin: str = Field(min_length=1, max_length=30)
    name: str | None = None
    quantity: NonNegative
    average_price: NonNegative | None = None
    pledge_quantity: NonNegative | None = None
    demat_locked_quantity: NonNegative | None = None
    groww_locked_quantity: NonNegative | None = None
    repledge_quantity: NonNegative | None = None
    t1_quantity: NonNegative | None = None
    demat_free_quantity: NonNegative | None = None
    corporate_action_additional_quantity: NonNegative | None = None
    active_demat_transfer_quantity: NonNegative | None = None


class HoldingsResponse(BaseModel):
    holdings: list[Holding]
