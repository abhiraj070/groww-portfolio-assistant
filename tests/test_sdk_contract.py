"""Exercise real locked SDK methods over mocked HTTP, never a Groww account."""

from unittest.mock import Mock

import httpx
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.config import Settings
from app.main import create_app
from app.services.container import Services
from app.services.groww_client import GrowwClient
from app.services.holdings_service import HoldingsService
from app.services.market_data_service import MarketDataService
from app.services.orders_service import OrdersService
from app.services.portfolio_service import PortfolioService
from app.services.positions_service import PositionsService
from tests.test_api import TEST_KEY


def test_real_sdk_through_rest_routes(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    payloads = {
        "/holdings/user": {
            "holdings": [
                {
                    "trading_symbol": "SYNTH",
                    "isin": "ISIN-SYNTH",
                    "quantity": 2,
                    "average_price": 10,
                    "pledge_quantity": 1,
                }
            ]
        },
        "/positions/user": {
            "positions": [
                {
                    "trading_symbol": "SYNTH",
                    "quantity": 3,
                    "segment": "CASH",
                    "exchange": "NSE",
                    "product": "CNC",
                    "realised_pnl": 5,
                }
            ]
        },
        "/live-data/ltp": {"NSE_SYNTH": 12.5},
        "/live-data/quote": {"last_price": 12.5, "last_trade_time": 123456789},
        "/live-data/ohlc": {"NSE_SYNTH": {"open": 10, "high": 13, "low": 9, "close": 12}},
        "/historical/candles": {"candles": [["2026-01-01T10:00:00", 10, 13, 9, 12, 100, None]]},
        "/user/detail": {
            "vendor_user_id": "synthetic-user",
            "ucc": "synthetic-ucc",
            "active_segments": ["CASH"],
        },
    }
    reads = []

    def sdk_get(url, *, headers, timeout, params=None, **kwargs):
        assert timeout == 10
        assert headers["Authorization"] == "Bearer synthetic-token"
        key = url.removeprefix("https://api.groww.in/v1")
        assert key in payloads, f"Unexpected SDK endpoint: {key}"
        reads.append(key)
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"status": "SUCCESS", "payload": payloads[key]}
        return response

    def sdk_auth(url, *, headers, json, timeout):
        assert url == "https://api.groww.in/v1/token/api/access"
        assert timeout == 15
        assert json["key_type"] == "approval"
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"token": "synthetic-token"}
        return response

    monkeypatch.setattr("requests.get", sdk_get)
    auth = Mock(side_effect=sdk_auth)
    monkeypatch.setattr("requests.post", auth)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "status": "SUCCESS",
                "payload": {
                    "order_list": [
                        {
                            "groww_order_id": "synthetic-order",
                            "trading_symbol": "SYNTH",
                            "order_status": "COMPLETE",
                            "quantity": 2,
                            "filled_quantity": 2,
                            "order_type": "LIMIT",
                            "transaction_type": "BUY",
                            "price": 10,
                            "created_at": "2026-01-01T10:00:00Z",
                        }
                    ]
                },
            },
        )
    )
    gateway = GrowwClient(
        Settings(groww_api_key="synthetic-key", groww_api_secret="synthetic-secret"),
        http_client=httpx.Client(transport=transport),
    )
    holdings, positions, market = (
        HoldingsService(gateway),
        PositionsService(gateway),
        MarketDataService(gateway),
    )
    services = Services(
        gateway,
        holdings,
        positions,
        OrdersService(gateway),
        market,
        PortfolioService(holdings, positions, market),
    )
    application = create_app()
    application.dependency_overrides[get_services] = lambda: services
    with TestClient(application, headers={"X-API-Key": TEST_KEY}) as client:
        assert client.get("/api/v1/portfolio/holdings").json()["holdings"][0]["quantity"] == "2"
        assert client.get("/api/v1/portfolio/positions").status_code == 200
        report = client.get("/api/v1/portfolio/analytics")
        assert report.status_code == 200, report.text
        assert report.json()["summary"]["current_value"] == "25.0"
        assert report.json()["summary"]["unrealised_pnl"] == "5.0"
        assert client.get("/api/v1/portfolio/summary").status_code == 200
        assert (
            client.get("/api/v1/portfolio/orders").json()["orders"][0]["groww_order_id"]
            == "synthetic-order"
        )
        assert client.get("/api/v1/portfolio/account").status_code == 200
        for kind in ("quote", "ltp", "ohlc"):
            response = client.get(f"/api/v1/market/{kind}/SYNTH")
            assert response.status_code == 200, response.text
        response = client.get(
            "/api/v1/market/candles",
            params={
                "groww_symbol": "NSE-SYNTH",
                "start_time": "2026-01-01T09:00:00",
                "end_time": "2026-01-01T11:00:00",
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
    auth.assert_called_once()
    assert "/changelog" not in reads
    gateway.close()
