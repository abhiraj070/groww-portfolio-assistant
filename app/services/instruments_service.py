"""Bounded download of the official public instrument catalog, with a short cache."""

import csv
import io
import time
from datetime import UTC, datetime
from threading import RLock
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.core.exceptions import ServiceError, invalid_response
from app.services.groww_client import translate_error

CATALOG_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"
MAX_CATALOG_BYTES = 64 * 1024 * 1024


class Instrument(BaseModel):
    exchange: Literal["NSE", "BSE"]
    trading_symbol: str
    groww_symbol: str
    name: str | None
    isin: str | None
    segment: Literal["CASH"] = "CASH"


class InstrumentsResponse(BaseModel):
    instruments: list[Instrument]
    total: int
    offset: int
    limit: int
    source: str = CATALOG_URL
    retrieved_at: datetime


class InstrumentsService:
    def __init__(self, timeout: float = 10, http_client: httpx.Client | None = None):
        self.http = http_client or httpx.Client(
            timeout=timeout, trust_env=False, follow_redirects=False
        )
        self.timeout = timeout
        self._lock = RLock()
        self._rows: list[Instrument] | None = None
        self._expires = 0.0
        self._retrieved_at = None

    def close(self):
        self.http.close()

    def get_instruments(
        self, exchange: str = "NSE", symbol: str | None = None, offset: int = 0, limit: int = 100
    ) -> InstrumentsResponse:
        if exchange not in {"NSE", "BSE"} or not 0 <= offset <= 1000000 or not 1 <= limit <= 1000:
            raise ServiceError("invalid_instrument_query", "Invalid instrument filters", 422)
        with self._lock:
            if self._rows is None or time.monotonic() >= self._expires:
                try:
                    content = bytearray()
                    with self.http.stream("GET", CATALOG_URL, timeout=self.timeout) as response:
                        response.raise_for_status()
                        for chunk in response.iter_bytes(chunk_size=65536):
                            content.extend(chunk)
                            if len(content) > MAX_CATALOG_BYTES:
                                raise invalid_response()
                    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
                    if not {
                        "exchange",
                        "trading_symbol",
                        "groww_symbol",
                        "segment",
                        "name",
                        "isin",
                    } <= set(reader.fieldnames or []):
                        raise invalid_response()
                    rows = []
                    for row in reader:
                        if row.get("exchange") in {"NSE", "BSE"} and row.get("segment") == "CASH":
                            if not row.get("trading_symbol") or not row.get("groww_symbol"):
                                raise invalid_response()
                            rows.append(
                                Instrument(**{k: row[k] or None for k in Instrument.model_fields})
                            )
                    if not rows:
                        raise invalid_response()
                except (UnicodeError, csv.Error, ValidationError):
                    raise invalid_response() from None
                except httpx.HTTPError as exc:
                    raise translate_error(exc) from None
                self._rows = rows
                self._expires = time.monotonic() + 900
                self._retrieved_at = datetime.now(UTC)
            filtered = [
                r
                for r in self._rows
                if r.exchange == exchange and (symbol is None or r.trading_symbol == symbol)
            ]
            return InstrumentsResponse(
                instruments=filtered[offset : offset + limit],
                total=len(filtered),
                offset=offset,
                limit=limit,
                retrieved_at=self._retrieved_at,
            )
