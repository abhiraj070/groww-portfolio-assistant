"""MF statement and AMFI observations; no dependency on Groww account schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.equity_history import Identifier, Positive
from app.schemas.holdings import NonNegative

SchemeCode = Annotated[str, Field(pattern=r"^[0-9]{1,12}$")]
MFKind = Literal[
    "PURCHASE", "SIP", "REDEMPTION", "SWITCH_IN", "SWITCH_OUT", "DIVIDEND", "REINVESTMENT"
]


class MFTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    transaction_id: Identifier
    folio: str = Field(min_length=1, max_length=100)
    scheme_code: SchemeCode
    scheme_name: str = Field(min_length=1, max_length=300)
    isin: str | None = Field(default=None, max_length=30)
    fund_house: str | None = Field(default=None, max_length=200)
    kind: MFKind
    date: date
    units: NonNegative
    nav: NonNegative | None = None
    amount: NonNegative
    charges: NonNegative | None = None
    sip_id: Identifier | None = None
    switch_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_transaction(self):
        if self.date > datetime.now(ZoneInfo("Asia/Kolkata")).date():
            raise ValueError("Future transaction")
        if self.kind == "DIVIDEND":
            if self.units != 0:
                raise ValueError("Cash dividend must have zero units")
        elif not self.units > 0 or self.nav is None or self.nav <= 0:
            raise ValueError("Unit transactions require positive units and NAV")
        if self.kind in {"SWITCH_IN", "SWITCH_OUT"} and self.switch_id is None:
            raise ValueError("Switch requires a link identifier")
        return self


class StoredMFTransaction(MFTransaction):
    source: str
    imported_at: datetime
    import_id: int


class NAVObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheme_code: SchemeCode
    scheme_name: str = Field(min_length=1, max_length=300)
    isin: str | None = Field(default=None, max_length=30)
    fund_house: str | None = Field(default=None, max_length=200)
    date: date
    nav: Positive

    @field_validator("date")
    @classmethod
    def not_future(cls, value: date):
        if value > datetime.now(ZoneInfo("Asia/Kolkata")).date():
            raise ValueError("Future NAV")
        return value


class StoredNAV(NAVObservation):
    source: str
    imported_at: datetime


class MFHolding(BaseModel):
    folio: str
    scheme_code: str
    scheme_name: str
    isin: str | None
    fund_house: str | None
    units: Decimal | None
    average_purchase_nav: Decimal | None
    invested_amount: Decimal | None
    latest_nav: Decimal | None
    nav_date: date | None
    nav_source: str | None
    current_value: Decimal | None
    unrealised_pnl: Decimal | None
    return_percentage: Decimal | None
    allocation_percentage: Decimal | None = None
    gross_realised_pnl: Decimal | None
    net_realised_pnl: Decimal | None
    unmatched_redeemed_units: Decimal


class MFSaleMatch(BaseModel):
    folio: str
    scheme_code: str
    acquired_on: date
    sold_on: date
    purchase_id: str
    redemption_id: str
    units: Decimal
    cost: Decimal
    proceeds: Decimal
    gross_realised_pnl: Decimal
    charges: Decimal | None
    net_realised_pnl: Decimal | None
    holding_days: int


class MFPortfolioResponse(BaseModel):
    holdings: list[MFHolding]
    invested_amount: Decimal | None
    current_value: Decimal | None
    unrealised_pnl: Decimal | None
    return_percentage: Decimal | None
    gross_realised_pnl: Decimal | None
    net_realised_pnl: Decimal | None
    dividend_income: Decimal
    sip_investment: Decimal
    matches: list[MFSaleMatch]
    retrieved_at: datetime
    scope: Literal["imported_mf_statements"] = "imported_mf_statements"
    history_complete: Literal[False] = False
    warnings: list[str]


class MFTransactionsResponse(BaseModel):
    transactions: list[StoredMFTransaction]
    total: int
    offset: int
    limit: int
    scope: Literal["imported_mf_statements"] = "imported_mf_statements"


class UnavailableMetric(BaseModel):
    available: Literal[False] = False
    metric: str
    reason: str
    required_source: str
