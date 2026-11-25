"""Statement normalization and offline AMFI NAV ingestion, with preserved originals."""

import csv
import io
from datetime import datetime

from pydantic import ValidationError

from app.core.exceptions import ServiceError
from app.schemas.mutual_funds import MFTransaction, NAVObservation
from app.services.ledger_service import MAX_IMPORT_BYTES, MAX_IMPORT_ROWS, LedgerService


def canonical_csv(content: bytes, model, required: set[str]):
    if len(content) > MAX_IMPORT_BYTES:
        raise ServiceError("invalid_import", "Import size limit exceeded", 422)
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        fields = reader.fieldnames
        if (
            not fields
            or len(set(fields)) != len(fields)
            or not required <= set(fields)
            or not set(fields) <= model.model_fields.keys()
        ):
            raise ValueError("Invalid headers")
        rows = []
        for raw in reader:
            if len(rows) >= MAX_IMPORT_ROWS or None in raw or any(v is None for v in raw.values()):
                raise ValueError("Invalid row")
            rows.append((model.model_validate({k: v for k, v in raw.items() if v != ""}), raw))
        if not rows:
            raise ValueError("Empty input")
        return rows
    except (ValueError, UnicodeError, csv.Error, ValidationError):
        raise ServiceError("invalid_import", "Invalid canonical statement CSV", 422) from None


class MFIngestionService:
    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def import_transactions(self, content: bytes, source: str):
        rows = canonical_csv(
            content,
            MFTransaction,
            {
                "transaction_id",
                "folio",
                "scheme_code",
                "scheme_name",
                "kind",
                "date",
                "units",
                "amount",
            },
        )
        # RTA transaction references are scoped to folio and scheme, never source filename.
        records = [
            (f"{r.folio}:{r.scheme_code}:{r.transaction_id}", r.model_dump(mode="json"), raw)
            for r, raw in rows
        ]
        return self.ledger.import_records("mf_transaction", content, source, records)

    def import_nav_csv(self, content: bytes, source: str):
        rows = canonical_csv(content, NAVObservation, {"scheme_code", "scheme_name", "date", "nav"})
        return self.ledger.import_records(
            "nav",
            content,
            source,
            [(f"{r.scheme_code}:{r.date}", r.model_dump(mode="json"), raw) for r, raw in rows],
        )

    def import_amfi(self, content: bytes):
        if len(content) > MAX_IMPORT_BYTES:
            raise ServiceError("invalid_import", "Import size limit exceeded", 422)
        try:
            rows = []
            fund_house = None
            header_seen = False
            for raw_line in content.decode("utf-8-sig").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("Scheme Code;"):
                    fields = line.split(";")
                    if fields != [
                        "Scheme Code",
                        "ISIN Div Payout/ ISIN Growth",
                        "ISIN Div Reinvestment",
                        "Scheme Name",
                        "Net Asset Value",
                        "Date",
                    ]:
                        raise ValueError("Unsupported AMFI format")
                    header_seen = True
                    continue
                if ";" not in line:
                    # Category headings carry parentheses; fund-house lines are explicit names.
                    if "(" not in line and header_seen:
                        fund_house = line
                    continue
                cells = line.split(";")
                if not header_seen or len(cells) != 6 or len(rows) >= MAX_IMPORT_ROWS:
                    raise ValueError("Invalid AMFI row")
                code, isin, reinvestment_isin, name, nav, nav_date = cells
                if nav in {"N.A.", "NA", "-", ""}:
                    continue  # Explicitly absent observations cannot overwrite a known NAV.
                record = NAVObservation(
                    scheme_code=code,
                    scheme_name=name,
                    isin=isin if isin not in {"-", ""} else None,
                    fund_house=fund_house,
                    nav=nav,
                    date=datetime.strptime(nav_date, "%d-%b-%Y").date(),
                )
                rows.append(
                    (
                        f"{code}:{record.date}",
                        record.model_dump(mode="json"),
                        {"line": raw_line, "reinvestment_isin": reinvestment_isin},
                    )
                )
            if not rows:
                raise ValueError("No observations")
        except (ValueError, UnicodeError, ValidationError):
            raise ServiceError("invalid_import", "Invalid AMFI NAV report", 422) from None
        return self.ledger.import_records("nav", content, "AMFI NAV report", rows)
