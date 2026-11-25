from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.equity_history import EquityTransaction, Identifier, Positive
from app.schemas.mutual_funds import MFPortfolioResponse, SchemeCode
from app.schemas.portfolio import AnalyticsResponse


class EquityAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: Identifier
    isin: str = Field(min_length=1, max_length=30)
    kind: Literal["SPLIT", "BONUS"]
    effective_at: datetime
    numerator: Positive
    denominator: Positive
    eligible_quantity: Positive
    zero_cost_confirmed: bool = False

    _exchange_time = field_validator("effective_at")(EquityTransaction.exchange_time.__func__)

    @model_validator(mode="after")
    def validate_bonus(self):
        if self.kind == "BONUS" and (
            not self.zero_cost_confirmed or self.effective_at.date() < date(2001, 4, 1)
        ):
            raise ValueError("Bonus requires verified zero basis and supported allotment date")
        return self


class MFUnitAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: Identifier
    folio: str = Field(min_length=1, max_length=100)
    scheme_code: SchemeCode
    date: date
    numerator: Positive
    denominator: Positive
    eligible_units: Positive

    @field_validator("date")
    @classmethod
    def not_future(cls, value: date):
        # Reuse the same domain date constraint as NAV observations.
        from app.schemas.mutual_funds import NAVObservation

        return NAVObservation.not_future(value)


class HoldingSnapshot(BaseModel):
    captured_at: datetime
    equity: AnalyticsResponse
    mutual_funds: MFPortfolioResponse
    scope: Literal["separate_equity_and_mf_observations"] = "separate_equity_and_mf_observations"


class SnapshotsResponse(BaseModel):
    snapshots: list[HoldingSnapshot]
    total: int
    offset: int
    limit: int
