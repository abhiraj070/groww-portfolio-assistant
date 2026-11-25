from datetime import UTC, datetime
from decimal import Decimal

from pydantic import TypeAdapter, ValidationError

from app.core.exceptions import ServiceError, invalid_response
from app.schemas.holdings import NonNegative
from app.schemas.market_data import (
    OHLC,
    AccountResponse,
    Candle,
    CandleRequest,
    CandlesResponse,
    InstrumentRequest,
    LTPResponse,
    OHLCResponse,
    Quote,
    QuoteResponse,
)
from app.services.groww_client import GrowwClient

price_adapter = TypeAdapter(NonNegative)


def validate_instrument(symbol: str, exchange: str, segment: str) -> InstrumentRequest:
    try:
        return InstrumentRequest(symbol=symbol, exchange=exchange, segment=segment)
    except ValidationError:
        raise ServiceError(
            "invalid_instrument", "Invalid symbol, exchange or segment", 422
        ) from None


def parse_model(model, data):
    try:
        return model.model_validate(data)
    except (ValidationError, TypeError, ValueError):
        raise invalid_response() from None


class MarketDataService:
    def __init__(self, client: GrowwClient):
        self.client = client

    def get_quote(self, symbol: str, exchange: str = "NSE", segment: str = "CASH") -> QuoteResponse:
        instrument = validate_instrument(symbol, exchange, segment)
        quote = parse_model(Quote, self.client.get_quote(symbol, exchange, segment))
        if quote.last_price is None:
            raise ServiceError("missing_market_data", "No quote price is available", 502)
        return QuoteResponse(**instrument.model_dump(), quote=quote, retrieved_at=datetime.now(UTC))

    def get_prices(
        self, symbols: list[str], exchange: str = "NSE", segment: str = "CASH"
    ) -> dict[str, Decimal | None]:
        unique = list(dict.fromkeys(symbols))
        for symbol in unique:
            validate_instrument(symbol, exchange, segment)
        result = {}
        for start in range(0, len(unique), 50):
            batch = unique[start : start + 50]
            payload = self.client.get_ltp(tuple(f"{exchange}_{s}" for s in batch), segment)
            for symbol in batch:
                raw = payload.get(f"{exchange}_{symbol}")
                try:
                    result[symbol] = None if raw is None else price_adapter.validate_python(raw)
                except ValidationError:
                    raise invalid_response() from None
        return result

    def get_ltp(self, symbol: str, exchange: str = "NSE", segment: str = "CASH") -> LTPResponse:
        instrument = validate_instrument(symbol, exchange, segment)
        price = self.get_prices([symbol], exchange, segment)[symbol]
        if price is None:
            raise ServiceError("missing_market_data", "No last traded price is available", 502)
        return LTPResponse(**instrument.model_dump(), price=price, retrieved_at=datetime.now(UTC))

    def get_ohlc(self, symbol: str, exchange: str = "NSE", segment: str = "CASH") -> OHLCResponse:
        instrument = validate_instrument(symbol, exchange, segment)
        payload = self.client.get_ohlc((f"{exchange}_{symbol}",), segment)
        raw = payload.get(f"{exchange}_{symbol}")
        if raw is None:
            raise ServiceError("missing_market_data", "No OHLC data is available", 502)
        return OHLCResponse(
            **instrument.model_dump(), ohlc=parse_model(OHLC, raw), retrieved_at=datetime.now(UTC)
        )

    def get_candles(self, query: CandleRequest) -> CandlesResponse:
        payload = self.client.get_candles(
            exchange=query.exchange,
            segment=query.segment,
            groww_symbol=query.groww_symbol,
            start_time=query.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=query.end_time.strftime("%Y-%m-%d %H:%M:%S"),
            candle_interval=query.candle_interval,
        )
        rows = payload.get("candles")
        if not isinstance(rows, list):
            raise invalid_response()
        candles = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 7:
                raise invalid_response()
            candles.append(
                parse_model(
                    Candle,
                    dict(
                        zip(
                            (
                                "timestamp",
                                "open",
                                "high",
                                "low",
                                "close",
                                "volume",
                                "open_interest",
                            ),
                            row,
                            strict=True,
                        )
                    ),
                )
            )
        return CandlesResponse(request=query, candles=candles, retrieved_at=datetime.now(UTC))

    def get_account(self) -> AccountResponse:
        return parse_model(AccountResponse, self.client.get_account())
