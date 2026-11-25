from datetime import datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.holdings import NonNegative

Exchange = Literal["NSE", "BSE", "MCX"]
Segment = Literal["CASH", "FNO", "COMMODITY", "CURRENCY"]
Symbol = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9&._-]{0,99}$")]
CandleInterval = Literal[
    "1minute",
    "2minute",
    "3minute",
    "5minute",
    "10minute",
    "15minute",
    "30minute",
    "1hour",
    "4hour",
    "1day",
    "1week",
    "1month",
]


class InstrumentRequest(BaseModel):
    symbol: Symbol
    exchange: Exchange = "NSE"
    segment: Segment = "CASH"


class OHLC(BaseModel):
    open: NonNegative
    high: NonNegative
    low: NonNegative
    close: NonNegative


class Quote(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    last_price: NonNegative | None = None
    last_trade_time: int | None = None
    ohlc: OHLC | None = None


class QuoteResponse(InstrumentRequest):
    quote: Quote
    retrieved_at: datetime


class LTPResponse(InstrumentRequest):
    price: NonNegative
    retrieved_at: datetime


class OHLCResponse(InstrumentRequest):
    ohlc: OHLC
    retrieved_at: datetime


class CandleRequest(BaseModel):
    exchange: Literal["NSE", "BSE"] = "NSE"
    segment: Literal["CASH", "FNO"] = "CASH"
    groww_symbol: str = Field(pattern=r"^(NSE|BSE)-[A-Za-z0-9&._-]{1,100}$")
    start_time: datetime
    end_time: datetime
    candle_interval: CandleInterval = "1day"

    @model_validator(mode="after")
    def validate_range(self):
        for name in ("start_time", "end_time"):
            value = getattr(self, name)
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            setattr(self, name, value.astimezone(ZoneInfo("Asia/Kolkata")))
        max_days = (
            30
            if self.candle_interval in {"1minute", "2minute", "3minute", "5minute"}
            else 90
            if self.candle_interval in {"10minute", "15minute", "30minute"}
            else 180
        )
        if not self.start_time < self.end_time <= self.start_time + timedelta(days=max_days):
            raise ValueError("Invalid candle time range or duration")
        if not self.groww_symbol.startswith(self.exchange + "-"):
            raise ValueError("Groww symbol exchange must match exchange")
        return self


class Candle(BaseModel):
    timestamp: datetime
    open: NonNegative
    high: NonNegative
    low: NonNegative
    close: NonNegative
    volume: NonNegative
    open_interest: NonNegative | None = None


class CandlesResponse(BaseModel):
    request: CandleRequest
    candles: list[Candle]
    retrieved_at: datetime


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    vendor_user_id: str
    ucc: str
    nse_enabled: bool | None = None
    bse_enabled: bool | None = None
    ddpi_enabled: bool | None = None
    active_segments: list[str] = Field(default_factory=list)
