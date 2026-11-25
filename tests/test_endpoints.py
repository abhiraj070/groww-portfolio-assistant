from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.exceptions import ServiceError
from app.main import create_app
from app.schemas.holdings import HoldingsResponse
from app.schemas.market_data import LTPResponse
from app.schemas.orders import OrdersResponse
from app.schemas.positions import PositionsResponse
from tests.test_api import TEST_KEY

PRIVATE_PATHS = [
    "/api/v1/portfolio/holdings",
    "/api/v1/portfolio/positions",
    "/api/v1/portfolio/orders",
    "/api/v1/portfolio/summary",
    "/api/v1/portfolio/analytics",
    "/api/v1/portfolio/account",
    "/api/v1/market/quote/SYNTH",
    "/api/v1/market/ltp/SYNTH",
    "/api/v1/market/ohlc/SYNTH",
    "/api/v1/market/candles",
]


@pytest.mark.parametrize("path", PRIVATE_PATHS)
def test_all_private_routes_reject_missing_auth(path, monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    application = create_app()
    services = Mock()
    application.dependency_overrides[get_services] = lambda: services
    with TestClient(application) as client:
        response = client.get(path)
    assert response.status_code == 401
    assert not services.mock_calls


def test_routed_reads_and_decimal_serialization(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    application, services = create_app(), Mock()
    services.holdings.get_holdings.return_value = HoldingsResponse(holdings=[])
    services.positions.get_positions.return_value = PositionsResponse(positions=[])
    services.orders.get_orders.return_value = OrdersResponse(
        orders=[], page=2, page_size=25, possible_next_page=None
    )
    services.market.get_ltp.return_value = LTPResponse(
        symbol="SYNTH", price="12.34", retrieved_at="2026-01-01T10:00:00Z"
    )
    application.dependency_overrides[get_services] = lambda: services
    with TestClient(application, headers={"X-API-Key": TEST_KEY}) as client:
        assert client.get("/api/v1/portfolio/holdings").json() == {"holdings": []}
        assert client.get("/api/v1/portfolio/positions?segment=FNO").status_code == 200
        assert client.get("/api/v1/portfolio/orders?page=2").status_code == 200
        assert client.get("/api/v1/market/ltp/SYNTH").json()["price"] == "12.34"
    services.positions.get_positions.assert_called_once_with("FNO")
    services.orders.get_orders.assert_called_once_with(2, 25, None)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/portfolio/orders?page=-1",
        "/api/v1/portfolio/orders?page_size=26",
        "/api/v1/portfolio/positions?segment=INVALID",
        "/api/v1/market/ltp/bad$symbol",
        "/api/v1/market/quote/SYNTH?exchange=INVALID",
        "/api/v1/market/candles?groww_symbol=NSE-SYNTH&start_time=2026-02-01&end_time=2026-01-01",
    ],
)
def test_invalid_inputs_return_sanitised_422(path, monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    with TestClient(create_app()) as client:
        response = client.get(path, headers={"X-API-Key": TEST_KEY})
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "validation_error", "message": "Request validation failed"}
    }


def test_rate_limit_response_has_retry_after(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    application, services = create_app(), Mock()
    services.holdings.get_holdings.side_effect = ServiceError(
        "rate_limited", "Retry later", 429, 60
    )
    application.dependency_overrides[get_services] = lambda: services
    with TestClient(application) as client:
        response = client.get("/api/v1/portfolio/holdings", headers={"X-API-Key": TEST_KEY})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_unconfigured_provider_is_not_a_success_response(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/portfolio/holdings", headers={"X-API-Key": TEST_KEY})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "groww_not_configured"


def test_no_write_endpoints(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    with TestClient(create_app()) as client:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = client.request(
                method, "/api/v1/portfolio/orders", headers={"X-API-Key": TEST_KEY}
            )
            assert response.status_code == 405
