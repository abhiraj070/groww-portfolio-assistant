"""Local, transactional execution ledger. No network calls or financial writes.

Decimals are stored as JSON strings (never SQLite REAL). Every import retains its
original bytes and every execution retains its original row. One account per database.
"""

import csv
import hashlib
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.core.exceptions import ServiceError
from app.schemas.equity_history import (
    EquityTransaction,
    ImportResult,
    StoredEquityTransaction,
    TradebookResponse,
)

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 50000


class LedgerService:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_version VALUES (1);
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, imported_at TEXT NOT NULL,
                    digest TEXT NOT NULL, original BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS equity_transactions (
                    identity TEXT PRIMARY KEY, data TEXT NOT NULL, raw TEXT NOT NULL,
                    import_id INTEGER NOT NULL REFERENCES imports(id)
                );
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, identity TEXT NOT NULL, data TEXT NOT NULL,
                    raw TEXT NOT NULL, import_id INTEGER NOT NULL REFERENCES imports(id),
                    PRIMARY KEY(kind, identity)
                );
            """)
            with connection:
                yield connection
        except (sqlite3.Error, OSError):
            raise ServiceError(
                "ledger_unavailable", "Local investment ledger is unavailable", 503
            ) from None
        finally:
            if connection is not None:
                connection.close()

    def import_csv(self, content: bytes, source: str) -> ImportResult:
        if not source.strip() or len(source) > 200 or len(content) > MAX_IMPORT_BYTES:
            raise ServiceError("invalid_import", "Invalid import source or file size", 422)
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
            fields = reader.fieldnames
            required = {
                "trade_id",
                "trading_symbol",
                "isin",
                "exchange",
                "side",
                "traded_at",
                "quantity",
                "price",
            }
            if (
                not fields
                or len(set(fields)) != len(fields)
                or not required <= set(fields)
                or not set(fields) <= EquityTransaction.model_fields.keys()
            ):
                raise ValueError("Invalid header")
            records = []
            for raw in reader:
                if (
                    len(records) >= MAX_IMPORT_ROWS
                    or None in raw
                    or any(v is None for v in raw.values())
                ):
                    raise ValueError("Invalid row")
                record = EquityTransaction.model_validate({k: v for k, v in raw.items() if v != ""})
                records.append((record, raw))
            if not records:
                raise ValueError("Empty import")
        except (UnicodeError, ValueError, csv.Error, ValidationError):
            raise ServiceError("invalid_import", "Invalid canonical equity CSV", 422) from None
        now = datetime.now(UTC)
        inserted = duplicates = 0
        with self.connection() as db:
            cursor = db.execute(
                "INSERT INTO imports(source, imported_at, digest, original) VALUES (?, ?, ?, ?)",
                (source, now.isoformat(), hashlib.sha256(content).hexdigest(), content),
            )
            import_id = cursor.lastrowid
            for record, raw in records:
                identity = f"{record.exchange}:{record.traded_at.date()}:{record.trade_id}"
                data = record.model_dump_json()
                existing = db.execute(
                    "SELECT data FROM equity_transactions WHERE identity=?", (identity,)
                ).fetchone()
                if existing:
                    if EquityTransaction.model_validate_json(existing["data"]) != record:
                        raise ServiceError(
                            "import_conflict",
                            "An execution ID has conflicting data; import rolled back",
                            409,
                        )
                    duplicates += 1
                else:
                    db.execute(
                        "INSERT INTO equity_transactions VALUES (?, ?, ?, ?)",
                        (identity, data, json.dumps(raw), import_id),
                    )
                    inserted += 1
        return ImportResult(
            import_id=import_id,
            inserted=inserted,
            duplicates=duplicates,
            source=source,
            imported_at=now,
        )

    def all_transactions(self) -> list[StoredEquityTransaction]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT t.data, t.import_id, i.source, i.imported_at "
                "FROM equity_transactions t JOIN imports i ON i.id=t.import_id"
            ).fetchall()
        return sorted(
            [
                StoredEquityTransaction(
                    **json.loads(r["data"]),
                    import_id=r["import_id"],
                    source=r["source"],
                    imported_at=r["imported_at"],
                )
                for r in rows
            ],
            key=lambda r: (r.traded_at, r.exchange, r.trade_id),
        )

    def tradebook(
        self, offset: int = 0, limit: int = 100, symbol: str | None = None
    ) -> TradebookResponse:
        if not 0 <= offset <= 1000000 or not 1 <= limit <= 1000:
            raise ServiceError("invalid_pagination", "Invalid ledger pagination", 422)
        records = [
            r for r in self.all_transactions() if symbol is None or r.trading_symbol == symbol
        ]
        return TradebookResponse(
            transactions=records[offset : offset + limit],
            total=len(records),
            offset=offset,
            limit=limit,
        )

    def import_records(
        self, kind: str, content: bytes, source: str, records: list[tuple[str, dict, dict]]
    ) -> ImportResult:
        """Persist validated domain records; callers own schema and stable identity validation."""
        if (
            not source.strip()
            or len(source) > 200
            or len(content) > MAX_IMPORT_BYTES
            or not 0 < len(records) <= MAX_IMPORT_ROWS
        ):
            raise ServiceError("invalid_import", "Invalid import source, size or row count", 422)
        now = datetime.now(UTC)
        inserted = duplicates = 0
        with self.connection() as db:
            import_id = db.execute(
                "INSERT INTO imports(source, imported_at, digest, original) VALUES (?, ?, ?, ?)",
                (source, now.isoformat(), hashlib.sha256(content).hexdigest(), content),
            ).lastrowid
            for identity, data, raw in records:
                encoded = json.dumps(data, sort_keys=True)
                existing = db.execute(
                    "SELECT data FROM records WHERE kind=? AND identity=?", (kind, identity)
                ).fetchone()
                if existing:
                    if json.loads(existing["data"]) != data:
                        raise ServiceError(
                            "import_conflict",
                            "Conflicting imported record; import rolled back",
                            409,
                        )
                    duplicates += 1
                else:
                    db.execute(
                        "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
                        (kind, identity, encoded, json.dumps(raw), import_id),
                    )
                    inserted += 1
        return ImportResult(
            import_id=import_id,
            inserted=inserted,
            duplicates=duplicates,
            source=source,
            imported_at=now,
        )

    def records(self, kind: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT r.data, r.import_id, i.source, i.imported_at "
                "FROM records r JOIN imports i ON i.id=r.import_id "
                "WHERE kind=? ORDER BY r.identity",
                (kind,),
            ).fetchall()
        return [
            dict(
                data=json.loads(row["data"]),
                import_id=row["import_id"],
                source=row["source"],
                imported_at=row["imported_at"],
            )
            for row in rows
        ]
