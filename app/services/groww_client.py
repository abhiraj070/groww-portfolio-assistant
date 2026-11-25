"""Read-only gateway for the audited growwapi 1.5.0 SDK.

Calls are serialized per client, including token refresh. All network calls have timeouts.
SDK authentication has its own fixed 15-second timeout. No token is generated at startup.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import RLock
from typing import Any

import httpx
import pyotp
import requests
from growwapi import GrowwAPI
from growwapi.groww.exceptions import GrowwAPIException, InstrumentNotFoundException

from app.core.config import Settings
from app.core.exceptions import ServiceError, invalid_response
from app.core.logging import register_secret


class QuietGrowwAPI(GrowwAPI):
    def _display_changelog(self):
        # SDK 1.5.0 constructor otherwise makes an unrelated request with no timeout.
        return None


class RateLimiter:
    """Conservative per-process budgets shared by endpoint category, without sleeping."""

    LIMITS = {
        "auth": ((1, 5), (60, 30), (86400, 150)),
        "read": ((1, 20), (60, 500)),
        "live": ((1, 10), (60, 300)),
    }

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.events = defaultdict(deque)
        self.blocked_until = 0.0

    def acquire(self, category: str) -> None:
        now = self.clock()
        if now < self.blocked_until:
            raise ServiceError(
                "rate_limited",
                "Groww request budget is temporarily exhausted",
                429,
                max(1, int(self.blocked_until - now) + 1),
            )
        for window, limit in self.LIMITS[category]:
            events = self.events[(category, window)]
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                raise ServiceError(
                    "rate_limited",
                    "Groww request budget is temporarily exhausted",
                    429,
                    max(1, int(events[0] + window - now) + 1),
                )
        for window, _ in self.LIMITS[category]:
            self.events[(category, window)].append(now)


def translate_error(exc: Exception, authenticating: bool = False) -> ServiceError:
    if isinstance(exc, ServiceError):
        return exc
    status = str(getattr(exc, "code", ""))
    if isinstance(exc, httpx.HTTPStatusError):
        status = str(exc.response.status_code)
    if status == "429":
        return ServiceError("rate_limited", "Groww rate limit reached; retry later", 429, 60)
    if status in {"401", "403"} or authenticating and status == "400":
        return ServiceError(
            "groww_authentication_failed",
            "Groww authentication failed; check credentials, approval and subscription",
            503,
        )
    if isinstance(exc, (requests.Timeout, httpx.TimeoutException)) or status == "504":
        return ServiceError("upstream_timeout", "Groww request timed out", 504)
    if status == "404" or isinstance(exc, InstrumentNotFoundException):
        return ServiceError(
            "instrument_not_found", "Groww resource or instrument was not found", 404
        )
    if status == "400":
        return ServiceError("upstream_bad_request", "Groww rejected the requested parameters", 400)
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return invalid_response()
    return ServiceError("upstream_unavailable", "Groww is currently unavailable", 503)


class GrowwClient:
    def __init__(
        self, settings: Settings, sdk_factory=QuietGrowwAPI, http_client: httpx.Client | None = None
    ):
        self.settings = settings
        self._sdk_factory = sdk_factory
        self._sdk = None
        self._token = None
        self._lock = RLock()
        self._limiter = RateLimiter()
        self._auth_retry_at = 0.0
        self._http = http_client or httpx.Client(
            timeout=settings.groww_request_timeout_seconds, follow_redirects=False, trust_env=False
        )

    def close(self) -> None:
        with self._lock:
            self._http.close()
            self._sdk = None
            self._token = None

    def _authenticate(self) -> None:
        if time.monotonic() < self._auth_retry_at:
            raise ServiceError(
                "groww_authentication_failed",
                "Groww authentication is cooling down; check local configuration",
                503,
            )
        key = self.settings.groww_api_key
        credential = (
            self.settings.groww_api_secret
            if self.settings.groww_auth_method == "api_key"
            else self.settings.groww_totp_secret
        )
        if key is None or credential is None:
            raise ServiceError("groww_not_configured", "Configure Groww credentials locally", 503)
        self._limiter.acquire("auth")
        try:
            kwargs = {"api_key": key.get_secret_value()}
            if self.settings.groww_auth_method == "api_key":
                kwargs["secret"] = credential.get_secret_value()
            else:
                try:
                    kwargs["totp"] = pyotp.TOTP(credential.get_secret_value()).now()
                except (ValueError, TypeError):
                    raise ServiceError(
                        "groww_not_configured", "GROWW_TOTP_SECRET is not a valid TOTP seed", 503
                    ) from None
            token = self._sdk_factory.get_access_token(**kwargs)
            if not isinstance(token, str) or not token.strip():
                raise invalid_response()
            register_secret(token)
            self._sdk = self._sdk_factory(token)
            self._token = token
        except Exception as exc:
            self._auth_retry_at = time.monotonic() + 60
            raise translate_error(exc, authenticating=True) from None

    def _read(self, operation: Callable[[], Any], category: str = "read") -> dict:
        with self._lock:
            if self._sdk is None:
                self._authenticate()
            for attempt in range(2):
                self._limiter.acquire(category)
                try:
                    result = operation()
                    if not isinstance(result, dict):
                        raise invalid_response()
                    return result
                except Exception as exc:
                    unauthorized = (
                        isinstance(exc, GrowwAPIException) and str(exc.code) == "401"
                    ) or (
                        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401
                    )
                    if unauthorized:
                        self._sdk = self._token = None
                        if attempt == 0:
                            self._authenticate()
                            continue
                        self._auth_retry_at = time.monotonic() + 60
                    error = translate_error(exc)
                    if error.status == 429:
                        self._limiter.blocked_until = time.monotonic() + (error.retry_after or 60)
                    raise error from None
            raise invalid_response()

    def get_holdings(self) -> dict:
        return self._read(
            lambda: self._sdk.get_holdings_for_user(
                timeout=self.settings.groww_request_timeout_seconds
            )
        )

    def get_positions(self, segment: str | None = None) -> dict:
        return self._read(
            lambda: self._sdk.get_positions_for_user(
                segment=segment, timeout=self.settings.groww_request_timeout_seconds
            )
        )

    def get_account(self) -> dict:
        return self._read(
            lambda: self._sdk.get_user_profile(timeout=self.settings.groww_request_timeout_seconds)
        )

    def get_orders(self, page: int, page_size: int, segment: str | None = None) -> dict:
        def fetch():
            # SDK 1.5.0 drops page_size and page without segment. Audited HTTP fallback.
            params = {"page": page, "page_size": page_size}
            if segment is not None:
                params["segment"] = segment
            response = self._http.get(
                "https://api.groww.in/v1/order/list",
                params=params,
                headers={"Authorization": f"Bearer {self._token}", "x-api-version": "1.0"},
                timeout=self.settings.groww_request_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise invalid_response()
            if body.get("status") == "FAILURE":
                error = body.get("error", {})
                raise GrowwAPIException("Groww request failed", str(error.get("code", "")))
            return body.get("payload", body)

        return self._read(fetch)

    def get_quote(self, symbol: str, exchange: str, segment: str) -> dict:
        return self._read(
            lambda: self._sdk.get_quote(
                trading_symbol=symbol,
                exchange=exchange,
                segment=segment,
                timeout=self.settings.groww_request_timeout_seconds,
            ),
            "live",
        )

    def get_ltp(self, symbols: tuple[str, ...], segment: str) -> dict:
        return self._read(
            lambda: self._sdk.get_ltp(
                exchange_trading_symbols=symbols,
                segment=segment,
                timeout=self.settings.groww_request_timeout_seconds,
            ),
            "live",
        )

    def get_ohlc(self, symbols: tuple[str, ...], segment: str) -> dict:
        return self._read(
            lambda: self._sdk.get_ohlc(
                exchange_trading_symbols=symbols,
                segment=segment,
                timeout=self.settings.groww_request_timeout_seconds,
            ),
            "live",
        )

    def get_candles(
        self,
        exchange: str,
        segment: str,
        groww_symbol: str,
        start_time: str,
        end_time: str,
        candle_interval: str,
    ) -> dict:
        return self._read(
            lambda: self._sdk.get_historical_candles(
                exchange=exchange,
                segment=segment,
                groww_symbol=groww_symbol,
                start_time=start_time,
                end_time=end_time,
                candle_interval=candle_interval,
                timeout=self.settings.groww_request_timeout_seconds,
            )
        )
