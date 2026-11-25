import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in (
        "SERVICE_API_KEY",
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
