from decimal import Decimal
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.core.exceptions import ServiceError
from app.schemas.market_data import CandleRequest
from app.services.market_data_service import MarketDataService
from app.services.orders_service import OrdersService
from tests.test_groww_client import configured_client


def test_order_http_fallback_sends_pagination_without_segment():
    client, _ = configured_client()

    def handler(request):
        assert request.url.path == "/v1/order/list"
        assert request.url.params["page"] == "2"
        assert request.url.params["page_size"] == "25"
        assert "segment" not in request.url.params
        assert request.headers["Authorization"] == "Bearer synthetic-access-token"
        return httpx.Response(200, json={"payload": {"order_list": []}})

    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    result = OrdersService(client).get_orders(page=2)
    assert result.orders == []
    assert result.scope == "current_trading_day"
    client.close()


def test_order_pagination_reports_possible_next_page():
    client = Mock()
    client.get_orders.return_value = {
        "order_list": [
            {
                "groww_order_id": "synthetic-id",
                "trading_symbol": "SYNTH",
                "order_status": "COMPLETE",
                "quantity": 2,
            }
        ]
    }
    assert OrdersService(client).get_orders(page_size=1).possible_next_page == 1
    with pytest.raises(ServiceError):
        OrdersService(client).get_orders(page_size=26)


def test_market_batches_and_preserves_missing_prices():
    client = Mock()
    client.get_ltp.return_value = {"NSE_SYNTH": "12.34"}
    prices = MarketDataService(client).get_prices(["SYNTH", "MISSING"])
    assert prices == {"SYNTH": Decimal("12.34"), "MISSING": None}
    with pytest.raises(ServiceError, match="No last traded"):
        MarketDataService(client).get_ltp("MISSING")
    with pytest.raises(ServiceError):
        MarketDataService(client).get_ltp("bad/symbol")


def test_market_50_instrument_limit():
    client = Mock()
    client.get_ltp.return_value = {}
    MarketDataService(client).get_prices([f"SYNTH{i}" for i in range(51)])
    assert [len(call.args[0]) for call in client.get_ltp.call_args_list] == [50, 1]


def test_quote_ohlc_and_candles():
    client = Mock()
    client.get_quote.return_value = {"last_price": "11", "volume": 20}
    ohlc = {"open": 10, "high": 12, "low": 9, "close": 11}
    client.get_ohlc.return_value = {"NSE_SYNTH": ohlc}
    client.get_candles.return_value = {"candles": [["2026-01-01T10:00:00", 10, 12, 9, 11, 5, None]]}
    market = MarketDataService(client)
    assert market.get_quote("SYNTH").quote.last_price == 11
    assert market.get_ohlc("SYNTH").ohlc.high == 12
    query = CandleRequest(
        groww_symbol="NSE-SYNTH", start_time="2026-01-01T09:00:00", end_time="2026-01-01T11:00:00"
    )
    assert market.get_candles(query).candles[0].close == 11
    client.get_candles.assert_called_once_with(
        exchange="NSE",
        segment="CASH",
        groww_symbol="NSE-SYNTH",
        start_time="2026-01-01 09:00:00",
        end_time="2026-01-01 11:00:00",
        candle_interval="1day",
    )


def test_invalid_candle_range():
    with pytest.raises(ValidationError):
        CandleRequest(groww_symbol="NSE-SYNTH", start_time="2026-01-01", end_time="2026-12-31")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", {}, True])
def test_invalid_market_price_fails(bad):
    client = Mock()
    client.get_ltp.return_value = {"NSE_SYNTH": bad}
    with pytest.raises(ServiceError):
        MarketDataService(client).get_ltp("SYNTH")
