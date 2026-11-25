"""Ordered, transactional SQLite migrations, including compatibility with early ledgers."""

import sqlite3

from app.core.exceptions import ServiceError

MIGRATIONS = (
    (
        "CREATE TABLE IF NOT EXISTS imports (id INTEGER PRIMARY KEY, source TEXT NOT NULL, "
        "imported_at TEXT NOT NULL, digest TEXT NOT NULL, original BLOB NOT NULL)",
        "CREATE TABLE IF NOT EXISTS equity_transactions (identity TEXT PRIMARY KEY, "
        "data TEXT NOT NULL, raw TEXT NOT NULL, "
        "import_id INTEGER NOT NULL REFERENCES imports(id))",
    ),
    (
        "CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, identity TEXT NOT NULL, "
        "data TEXT NOT NULL, raw TEXT NOT NULL, import_id INTEGER NOT NULL REFERENCES imports(id), "
        "PRIMARY KEY(kind, identity))",
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_imports_digest ON imports(digest)",
        "CREATE INDEX IF NOT EXISTS ix_equity_import ON equity_transactions(import_id)",
        "CREATE INDEX IF NOT EXISTS ix_records_import ON records(import_id)",
    ),
)


def migrate(db: sqlite3.Connection):
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    current = db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] if exists else 0
    current = current or 0
    if current > len(MIGRATIONS):
        raise ServiceError(
            "unsupported_ledger_version", "Ledger requires a newer application version", 503
        )
    if current == len(MIGRATIONS):
        return
    # Serialize only upgrades. Recheck after the write lock for concurrent first-use imports.
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        current = db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
        if current > len(MIGRATIONS):
            raise ServiceError(
                "unsupported_ledger_version", "Ledger requires a newer application version", 503
            )
        for version in range(current + 1, len(MIGRATIONS) + 1):
            for statement in MIGRATIONS[version - 1]:
                db.execute(statement)
            db.execute("INSERT INTO schema_version VALUES (?)", (version,))
        db.commit()
    except Exception:
        db.rollback()
        raise
