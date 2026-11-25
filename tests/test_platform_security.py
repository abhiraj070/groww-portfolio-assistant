from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.core.exceptions import ServiceError
from app.core.request_budget import RequestBudget
from app.main import create_app
from app.services.equity_history_service import EquityHistoryService
from app.services.groww_client import GrowwClient
from app.services.instruments_service import InstrumentsService
from app.services.ledger_service import LedgerService
from app.services.mf_ingestion_service import MFIngestionService
from tests.test_api import TEST_KEY
from tests.test_equity_history import csv_bytes, execution
from tests.test_mutual_funds import mf_row


def test_local_budget_rolling_window_and_concurrency():
    now = [0.0]
    budget = RequestBudget(7, clock=lambda: now[0])

    def acquire(_):
        try:
            budget.acquire()
            return True
        except ServiceError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(acquire, range(20))) == 7
    with pytest.raises(ServiceError) as error:
        budget.acquire()
    assert error.value.status == 429
    assert error.value.retry_after == 61
    now[0] = 60
    budget.acquire()
    assert len(budget.events) == 1


def test_inbound_budget_counts_auth_failures_preserves_health_and_privacy(monkeypatch):
    monkeypatch.setenv("API_REQUESTS_PER_MINUTE", "2")
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    app, services = create_app(), Mock()
    app.dependency_overrides[get_services] = lambda: services
    with TestClient(app) as client:
        assert client.get("/api/v1/mf/holdings").status_code == 401
        assert client.get("/api/v1/stocks/holdings").status_code == 401
        response = client.get("/api/v1/analytics/net-worth", headers={"X-API-Key": TEST_KEY})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "request_rate_limited"
        assert int(response.headers["Retry-After"]) >= 1
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert TEST_KEY not in response.text
        assert client.get("/health").status_code == 200
    assert not services.mock_calls


def test_every_registered_business_route_is_get_only_and_private(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    app = create_app()
    paths = app.openapi()["paths"]
    private = [entry for path, entry in paths.items() if path.startswith("/api/v1/")]
    assert len(private) >= 50
    for entry in private:
        assert set(entry) == {"get"}
        assert {"APIKeyHeader": []} in entry["get"]["security"]
    assert app.docs_url is app.openapi_url is app.redoc_url is None
    assert not {"place_order", "modify_order", "cancel_order", "transfer_funds"} & set(
        dir(GrowwClient)
    )


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"a,a\n1,2",
        b"\xff\xfe",
        b"trade_id,trading_symbol\nx,y",
        b"trade_id,trading_symbol,isin,exchange,side,traded_at,quantity,price\nx,SYNTH,I,NSE,BUY,2025-01-01,1,10,unexpected",
    ],
)
def test_malformed_equity_imports_are_sanitised_and_atomic(tmp_path, content):
    ledger = LedgerService(tmp_path / "ledger.db")
    with pytest.raises(ServiceError) as error:
        ledger.import_csv(content, "synthetic-private-source")
    assert error.value.code == "invalid_import"
    assert "synthetic-private-source" not in str(error.value)
    assert ledger.tradebook().total == 0


def test_oversized_and_extreme_numeric_imports_rejected(tmp_path, monkeypatch):
    ledger = LedgerService(tmp_path / "ledger.db")
    with pytest.raises(ServiceError):
        ledger.import_csv(csv_bytes(execution(price="1e1000")), "synthetic")
    with pytest.raises(ServiceError):
        MFIngestionService(ledger).import_transactions(
            csv_bytes(mf_row(amount="1e1000")), "synthetic"
        )
    monkeypatch.setattr("app.services.ledger_service.MAX_IMPORT_BYTES", 4)
    with pytest.raises(ServiceError):
        ledger.import_csv(b"oversized", "synthetic")


def test_high_precision_equity_product_and_no_financial_logging(tmp_path, caplog):
    ledger = LedgerService(tmp_path / "ledger.db")
    row = execution(quantity="12345678901234.1234567890", price="98765432101234.9876543210")
    ledger.import_csv(csv_bytes(row), "synthetic-private-source")
    result = EquityHistoryService(ledger).analyse()
    with localcontext() as context:
        context.prec = 64
        assert result.stocks[0].remaining_cost == Decimal(row["quantity"]) * Decimal(row["price"])
    assert row["price"] not in caplog.text
    assert row["quantity"] not in caplog.text
    assert "synthetic-private-source" not in caplog.text


def test_ledger_filesystem_errors_are_sanitised(tmp_path):
    directory = tmp_path / "private-directory"
    directory.mkdir()
    with pytest.raises(ServiceError) as error:
        LedgerService(directory).tradebook()
    assert error.value.code == "ledger_unavailable"
    assert str(directory) not in str(error.value)


def test_catalog_size_limit_does_not_cache_invalid_data(monkeypatch):
    monkeypatch.setattr("app.services.instruments_service.MAX_CATALOG_BYTES", 4)
    service = InstrumentsService(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"too large"))
        )
    )
    try:
        with pytest.raises(ServiceError):
            service.get_instruments()
        assert service._rows is None
    finally:
        service.close()
