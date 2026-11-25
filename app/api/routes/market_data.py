from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_services
from app.schemas.market_data import (
    CandleRequest,
    CandlesResponse,
    Exchange,
    LTPResponse,
    OHLCResponse,
    QuoteResponse,
    Segment,
    Symbol,
)
from app.services.container import Services

router = APIRouter(prefix="/market", tags=["market"])
ServiceDependency = Annotated[Services, Depends(get_services)]


@router.get("/quote/{symbol}", response_model=QuoteResponse)
def quote(
    symbol: Symbol,
    services: ServiceDependency,
    exchange: Exchange = "NSE",
    segment: Segment = "CASH",
) -> QuoteResponse:
    return services.market.get_quote(symbol, exchange, segment)


@router.get("/ltp/{symbol}", response_model=LTPResponse)
def ltp(
    symbol: Symbol,
    services: ServiceDependency,
    exchange: Exchange = "NSE",
    segment: Segment = "CASH",
) -> LTPResponse:
    return services.market.get_ltp(symbol, exchange, segment)


@router.get("/ohlc/{symbol}", response_model=OHLCResponse)
def ohlc(
    symbol: Symbol,
    services: ServiceDependency,
    exchange: Exchange = "NSE",
    segment: Segment = "CASH",
) -> OHLCResponse:
    return services.market.get_ohlc(symbol, exchange, segment)


@router.get("/candles", response_model=CandlesResponse)
def candles(
    services: ServiceDependency, query: Annotated[CandleRequest, Query()]
) -> CandlesResponse:
    return services.market.get_candles(query)
