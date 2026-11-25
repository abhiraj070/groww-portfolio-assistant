"""Local history maintenance; no automatic scheduler or provider financial writes."""

import argparse

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.services.container import Services
from app.services.history_service import HistoryService
from app.services.ledger_service import MAX_IMPORT_BYTES, LedgerService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["migrate", "snapshot", "equity-actions", "mf-adjustments"]
    )
    parser.add_argument("path", nargs="?")
    parser.add_argument("--source", default="operator-verified adjustment")
    args = parser.parse_args()
    services = None
    try:
        ledger = LedgerService(get_settings().ledger_path)
        history = HistoryService(ledger)
        if args.command == "migrate":
            with ledger.connection():
                pass
        elif args.command == "snapshot":
            services = Services.build(get_settings())
            services.history.capture()
        else:
            if not args.path:
                parser.error("Adjustment CSV path is required")
            with open(args.path, "rb") as file:
                content = file.read(MAX_IMPORT_BYTES + 1)
            if args.command == "equity-actions":
                history.import_equity_actions(content, args.source)
            else:
                history.import_mf_adjustments(content, args.source)
    except (ServiceError, OSError):
        print("History operation failed; check data, configuration and ledger access.")
        return 1
    finally:
        if services is not None:
            services.close()
    print("History operation completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
