import logging
import sys
from unittest.mock import Mock

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.logging import RedactingFormatter, register_secret
from app.services.container import Services
from app.services.groww_client import RateLimiter, translate_error
from tests.test_groww_client import configured_client


def test_sliding_rate_windows_and_category_sharing():
    clock = Mock(return_value=0.0)
    limiter = RateLimiter(clock=clock)
    for _ in range(10):
        limiter.acquire("live")
    with pytest.raises(ServiceError) as error:
        limiter.acquire("live")
    assert error.value.status == 429
    limiter.acquire("read")
    clock.return_value = 1.01
    limiter.acquire("live")


def test_authentication_daily_budget():
    clock = Mock()
    limiter = RateLimiter(clock=clock)
    for i in range(150):
        clock.return_value = i * 61.0
        limiter.acquire("auth")
    clock.return_value = 151 * 61.0
    with pytest.raises(ServiceError):
        limiter.acquire("auth")
    clock.return_value = 86401.0
    limiter.acquire("auth")


def test_provider_retry_after_is_respected_and_not_retried():
    client, _ = configured_client()
    hits = []

    def handler(request):
        hits.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"}, json={})

    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    for _ in range(2):
        with pytest.raises(ServiceError) as error:
            client.get_orders(0, 25)
        assert error.value.status == 429
        assert error.value.retry_after >= 120
    assert len(hits) == 1
    client.close()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "groww_authentication_failed"),
        (403, "groww_authentication_failed"),
        (400, "upstream_bad_request"),
        (404, "instrument_not_found"),
        (500, "upstream_unavailable"),
        (504, "upstream_timeout"),
    ],
)
def test_http_error_translation(status, code):
    response = httpx.Response(status, request=httpx.Request("GET", "https://api.groww.in"))
    with pytest.raises(httpx.HTTPStatusError) as error:
        response.raise_for_status()
    assert translate_error(error.value).code == code


def test_redaction_includes_formatted_tracebacks():
    register_secret("synthetic-sensitive-secret")
    try:
        raise RuntimeError("synthetic-sensitive-secret")
    except RuntimeError:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "Authorization: Bearer synthetic-token",
            (),
            sys.exc_info(),
        )
    rendered = RedactingFormatter(logging.Formatter("%(message)s")).format(record)
    assert "synthetic-sensitive-secret" not in rendered
    assert "synthetic-token" not in rendered
    assert "[REDACTED]" in rendered


def test_invalid_sector_file_fails_without_disclosing_path(tmp_path):
    path = tmp_path / "private-metadata.json"
    path.write_text('{"sectors": "invalid"}', encoding="utf-8")
    with pytest.raises(ServiceError) as error:
        Services.build(Settings(sector_metadata_file=path))
    assert error.value.code == "invalid_sector_metadata"
    assert str(path) not in str(error.value)


def test_valid_sector_file_is_loaded(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(
        '{"source":"synthetic verified source","as_of":"2026-01-01",'
        '"sectors":{"ISIN-SYNTH":"Synthetic sector"}}',
        encoding="utf-8",
    )
    services = Services.build(Settings(sector_metadata_file=path))
    assert services.portfolio.sectors.sectors == {"ISIN-SYNTH": "Synthetic sector"}
    services.client.close()
