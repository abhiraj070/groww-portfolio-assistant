from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.main import create_app
from app.services.container import Services
from app.services.groww_client import GrowwClient
from app.services.instruments_service import InstrumentsService
from app.services.orders_service import OrdersService
from tests.test_api import TEST_KEY
from tests.test_equity_history import csv_bytes, execution

STOCK_PATHS = [
    "holdings",
    "positions",
    "portfolio/summary",
    "portfolio/allocation",
    "portfolio/analytics",
    "orders",
    "orders/SYNTH-ORDER",
    "orders/SYNTH-ORDER/trades",
    "trades",
    "tradebook",
    "sold",
    "realised-pnl",
    "quote/SYNTH",
    "ltp/SYNTH",
    "ohlc/SYNTH",
    "candles",
    "instruments",
]


@pytest.mark.parametrize("path", STOCK_PATHS)
def test_stock_routes_require_key_before_service_access(monkeypatch, path):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    app, services = create_app(), Mock()
    app.dependency_overrides[get_services] = lambda: services
    with TestClient(app) as client:
        assert client.get(f"/api/v1/stocks/{path}").status_code == 401
    assert services.mock_calls == []


def test_imported_history_through_protected_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    services = Services.build(Settings(ledger_path=tmp_path / "ledger.db"))
    services.ledger.import_csv(
        csv_bytes(execution(), execution("SELL", "SELL", "10", "20", "2026-01-01T10:00:00")),
        "synthetic",
    )
    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    with TestClient(app, headers={"X-API-Key": TEST_KEY}) as client:
        for path in ("trades", "tradebook"):
            data = client.get(f"/api/v1/stocks/{path}").json()
            assert data["total"] == 2
            assert data["history_complete"] is False
            assert data["transactions"][0]["price"] == "10.1"
        for path in ("sold", "realised-pnl"):
            response = client.get(f"/api/v1/stocks/{path}")
            assert response.status_code == 200, response.text
            assert response.json()["stocks"][0]["status"] == "completely_sold"
            assert response.headers["Cache-Control"] == "no-store"
        for path in (
            "tradebook?limit=1001",
            "orders/BAD$ID",
            "orders/SYNTH/trades?page_size=51",
            "instruments?exchange=MCX",
        ):
            assert client.get(f"/api/v1/stocks/{path}").status_code == 422
        for path in STOCK_PATHS:
            assert client.post(f"/api/v1/stocks/{path}").status_code == 405
    services.close()


def test_real_sdk_order_detail_and_execution_contract(monkeypatch):
    detail = dict(
        groww_order_id="SYNTH-ORDER", trading_symbol="SYNTH", order_status="EXECUTED", quantity=2
    )
    trade = dict(
        groww_order_id="SYNTH-ORDER",
        trading_symbol="SYNTH",
        exchange_trade_id="SYNTH-TRADE",
        isin="ISIN-SYNTH",
        quantity=2,
        price=10.1,
        exchange="BSE",
        segment="CASH",
        transaction_type="BUY",
        trade_date_time="2026-01-01T10:00:00+05:30",
    )

    def get(url, *, headers, timeout, params):
        assert headers["Authorization"] == "Bearer synthetic-token"
        assert timeout == 10
        assert params["segment"] == "CASH"
        if url.endswith("/order/detail/SYNTH-ORDER"):
            payload = detail
        else:
            assert url.endswith("/order/trades/SYNTH-ORDER")
            assert params == {"segment": "CASH", "page": 2, "page_size": 1}
            payload = {"trade_list": [trade]}
        response = Mock(status_code=200, ok=True)
        response.json.return_value = {"status": "SUCCESS", "payload": payload}
        return response

    monkeypatch.setattr("requests.get", get)
    auth = Mock(status_code=200, ok=True)
    auth.json.return_value = {"token": "synthetic-token"}
    monkeypatch.setattr("requests.post", Mock(return_value=auth))
    gateway = GrowwClient(
        Settings(groww_api_key="synthetic-key", groww_api_secret="synthetic-secret")
    )
    service = OrdersService(gateway)
    try:
        assert service.get_order("SYNTH-ORDER").quantity == 2
        response = service.get_trades("SYNTH-ORDER", page=2, page_size=1)
        assert response.possible_next_page == 3
        assert str(response.trades[0].price) == "10.1"
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "payload", [{}, {"trade_list": [{}]}, {"trade_list": [dict(groww_order_id="WRONG")]}]
)
def test_invalid_order_executions_rejected(payload):
    gateway = Mock()
    gateway.get_order_trades.return_value = payload
    with pytest.raises(ServiceError):
        OrdersService(gateway).get_trades("SYNTH-ORDER")


def test_official_catalog_pagination_cache_and_source():
    calls = []

    def fetch(request):
        calls.append(request)
        return httpx.Response(
            200,
            text="exchange,trading_symbol,groww_symbol,name,isin,segment\nNSE,SYNTH,NSE-SYNTH,Synthetic,ISIN-SYNTH,CASH\nBSE,SECOND,BSE-SECOND,,,CASH\nNSE,FUT,NSE-FUT,,,FNO\n",
        )

    service = InstrumentsService(http_client=httpx.Client(transport=httpx.MockTransport(fetch)))
    try:
        response = service.get_instruments()
        assert response.total == 1
        assert response.instruments[0].name == "Synthetic"
        assert response.retrieved_at.tzinfo is not None
        assert service.get_instruments("BSE").instruments[0].name is None
        assert service.get_instruments(symbol="ABSENT").total == 0
        assert len(calls) == 1
        assert str(calls[0].url) == response.source
    finally:
        service.close()


@pytest.mark.parametrize(
    "status, body, code",
    [
        (200, "bad,data\n1,2", "invalid_upstream_response"),
        (503, "down", "upstream_unavailable"),
        (429, "limited", "rate_limited"),
    ],
)
def test_catalog_invalid_and_upstream_failures(status, body, code):
    service = InstrumentsService(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(status, text=body))
        )
    )
    try:
        with pytest.raises(ServiceError) as error:
            service.get_instruments()
        assert error.value.code == code
    finally:
        service.close()


def test_catalog_timeout():
    def timeout(request):
        raise httpx.ReadTimeout("synthetic-sensitive-detail")

    service = InstrumentsService(http_client=httpx.Client(transport=httpx.MockTransport(timeout)))
    try:
        with pytest.raises(ServiceError) as error:
            service.get_instruments()
        assert error.value.code == "upstream_timeout"
        assert "sensitive" not in str(error.value)
    finally:
        service.close()
