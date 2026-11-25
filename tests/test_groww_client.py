from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
import requests
from growwapi.groww.exceptions import GrowwAPIAuthenticationException, GrowwAPIRateLimitException

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.services.groww_client import GrowwClient, QuietGrowwAPI


def configured_client():
    factory = MagicMock()
    factory.get_access_token.return_value = "synthetic-access-token"
    factory.return_value.get_holdings_for_user.return_value = {"holdings": []}
    settings = Settings(groww_api_key="synthetic-key", groww_api_secret="synthetic-secret")
    return GrowwClient(settings, sdk_factory=factory), factory


def test_auth_is_lazy_and_token_reused():
    client, factory = configured_client()
    factory.get_access_token.assert_not_called()
    client.get_holdings()
    client.get_holdings()
    factory.get_access_token.assert_called_once_with(
        api_key="synthetic-key", secret="synthetic-secret"
    )
    factory.return_value.get_holdings_for_user.assert_called_with(timeout=10)
    client.close()


def test_concurrent_reads_share_authentication():
    client, factory = configured_client()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: client.get_holdings(), range(4)))
    factory.get_access_token.assert_called_once()
    client.close()


def test_totp_flow():
    factory = MagicMock()
    factory.get_access_token.return_value = "synthetic-token"
    factory.return_value.get_holdings_for_user.return_value = {"holdings": []}
    client = GrowwClient(
        Settings(
            groww_auth_method="totp",
            groww_api_key="synthetic-token",
            groww_totp_secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
        ),
        sdk_factory=factory,
    )
    client.get_holdings()
    kwargs = factory.get_access_token.call_args.kwargs
    assert len(kwargs["totp"]) == 6
    assert "secret" not in kwargs
    client.close()


def test_expired_token_refreshes_once():
    client, factory = configured_client()
    factory.return_value.get_holdings_for_user.side_effect = [
        GrowwAPIAuthenticationException(),
        {"holdings": []},
    ]
    assert client.get_holdings() == {"holdings": []}
    assert factory.get_access_token.call_count == 2
    client.close()


def test_rejected_refresh_cools_down():
    client, factory = configured_client()
    factory.return_value.get_holdings_for_user.side_effect = GrowwAPIAuthenticationException()
    for _ in range(2):
        with pytest.raises(ServiceError) as error:
            client.get_holdings()
        assert error.value.code == "groww_authentication_failed"
    assert factory.get_access_token.call_count == 2
    client.close()


@pytest.mark.parametrize(
    "exception,code",
    [
        (requests.Timeout("synthetic-secret"), "upstream_timeout"),
        (GrowwAPIRateLimitException(), "rate_limited"),
        (requests.ConnectionError("synthetic-secret"), "upstream_unavailable"),
    ],
)
def test_errors_are_sanitised(exception, code):
    client, factory = configured_client()
    factory.return_value.get_holdings_for_user.side_effect = exception
    with pytest.raises(ServiceError) as error:
        client.get_holdings()
    assert error.value.code == code
    assert "synthetic-secret" not in str(error.value)
    client.close()


def test_missing_credentials_never_calls_sdk():
    factory = MagicMock()
    client = GrowwClient(Settings(), sdk_factory=factory)
    with pytest.raises(ServiceError, match="Configure Groww"):
        client.get_holdings()
    factory.get_access_token.assert_not_called()
    client.close()


def test_sdk_construction_does_not_fetch_changelog(monkeypatch):
    get = MagicMock(side_effect=AssertionError("unexpected network"))
    monkeypatch.setattr("requests.get", get)
    sdk = QuietGrowwAPI("synthetic-token")
    assert sdk.token == "synthetic-token"
    get.assert_not_called()
