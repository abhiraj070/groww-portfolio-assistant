import argparse

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.services.ledger_service import MAX_IMPORT_BYTES, LedgerService
from app.services.performance_service import PerformanceService


def main():
    parser = argparse.ArgumentParser(description="Import portfolio observations or cash flows")
    parser.add_argument("kind", choices=["observations", "cashflows"])
    parser.add_argument("path")
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    service = PerformanceService(LedgerService(get_settings().ledger_path))
    try:
        with open(args.path, "rb") as file:
            data = file.read(MAX_IMPORT_BYTES + 1)
        result = (
            service.import_observations(data, args.source)
            if args.kind == "observations"
            else service.import_cashflows(data, args.source)
        )
    except (ServiceError, OSError):
        print("Import failed; check input format and ledger access.")
        return 1
    print(f"Import {result.import_id}: inserted {result.inserted}, duplicates {result.duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
