"""Offline import: uv run python -m app.import_tradebook PATH --source LABEL."""

import argparse

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.services.ledger_service import MAX_IMPORT_BYTES, LedgerService


def main() -> int:
    parser = argparse.ArgumentParser(description="Import canonical delivery equity execution CSV")
    parser.add_argument("path")
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    try:
        with open(args.path, "rb") as file:
            content = file.read(MAX_IMPORT_BYTES + 1)
        result = LedgerService(get_settings().ledger_path).import_csv(content, args.source)
    except (OSError, ServiceError):
        print("Import failed; check file format, source and local ledger access.")
        return 1
    print(f"Import {result.import_id}: inserted {result.inserted}, duplicates {result.duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
