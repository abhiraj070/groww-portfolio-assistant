import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in (
        "SERVICE_API_KEY",
        "MCP_BEARER_TOKEN",
        "MCP_PUBLIC_URL",
        "RENDER_EXTERNAL_URL",
        "VALUATION_EXCHANGE",
        "SECTOR_METADATA_FILE",
        "LEDGER_PATH",
        "API_REQUESTS_PER_MINUTE",
        "GROWW_AUTH_METHOD",
        "GROWW_API_KEY",
        "GROWW_API_SECRET",
        "GROWW_TOTP_SECRET",
        "GROWW_REQUEST_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def prevent_live_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must mock upstream HTTP; live network is disabled")

    monkeypatch.setattr("requests.sessions.Session.request", blocked)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", blocked)
