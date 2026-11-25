"""Offline MF statements and NAV imports. No provider or account writes."""

import argparse

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.services.ledger_service import MAX_IMPORT_BYTES, LedgerService
from app.services.mf_ingestion_service import MFIngestionService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["transactions", "nav", "amfi"])
    parser.add_argument("path")
    parser.add_argument("--source", default="operator-verified statement")
    args = parser.parse_args()
    ingestion = MFIngestionService(LedgerService(get_settings().ledger_path))
    try:
        with open(args.path, "rb") as file:
            content = file.read(MAX_IMPORT_BYTES + 1)
        if args.kind == "transactions":
            result = ingestion.import_transactions(content, args.source)
        elif args.kind == "nav":
            result = ingestion.import_nav_csv(content, args.source)
        else:
            result = ingestion.import_amfi(content)
    except (ServiceError, OSError):
        print("Import failed; check statement format and ledger access.")
        return 1
    print(f"Import {result.import_id}: inserted {result.inserted}, duplicates {result.duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
