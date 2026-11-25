from datetime import UTC, datetime

from app.core.exceptions import ServiceError
from app.schemas.history import EquityAction, HoldingSnapshot, MFUnitAdjustment, SnapshotsResponse
from app.services.ledger_service import LedgerService
from app.services.mf_ingestion_service import canonical_csv


class HistoryService:
    def __init__(self, ledger: LedgerService, portfolio=None, mf=None):
        self.ledger, self.portfolio, self.mf = ledger, portfolio, mf

    def import_equity_actions(self, content: bytes, source: str):
        rows = canonical_csv(
            content,
            EquityAction,
            {
                "action_id",
                "isin",
                "kind",
                "effective_at",
                "numerator",
                "denominator",
                "eligible_quantity",
            },
        )
        return self.ledger.import_records(
            "equity_action",
            content,
            source,
            [(r.action_id, r.model_dump(mode="json"), raw) for r, raw in rows],
        )

    def import_mf_adjustments(self, content: bytes, source: str):
        rows = canonical_csv(
            content,
            MFUnitAdjustment,
            {
                "action_id",
                "folio",
                "scheme_code",
                "date",
                "numerator",
                "denominator",
                "eligible_units",
            },
        )
        return self.ledger.import_records(
            "mf_adjustment",
            content,
            source,
            [(r.action_id, r.model_dump(mode="json"), raw) for r, raw in rows],
        )

    def capture(self) -> HoldingSnapshot:
        if self.portfolio is None or self.mf is None:
            raise ServiceError(
                "snapshot_not_configured", "Snapshot services are not configured", 503
            )
        # Capture retrieval timestamps and missing-data flags, without claiming one price date.
        equity = self.portfolio.get_portfolio_analytics()
        mutual_funds = self.mf.portfolio()
        snapshot = HoldingSnapshot(
            captured_at=datetime.now(UTC), equity=equity, mutual_funds=mutual_funds
        )
        content = snapshot.model_dump_json().encode()
        self.ledger.import_records(
            "holding_snapshot",
            content,
            "service capture",
            [
                (
                    snapshot.captured_at.isoformat(),
                    snapshot.model_dump(mode="json"),
                    snapshot.model_dump(mode="json"),
                )
            ],
        )
        return snapshot

    def snapshots(self, offset: int = 0, limit: int = 100) -> SnapshotsResponse:
        if not 0 <= offset <= 1000000 or not 1 <= limit <= 1000:
            raise ServiceError("invalid_pagination", "Invalid snapshot pagination", 422)
        rows = sorted(
            [HoldingSnapshot(**r["data"]) for r in self.ledger.records("holding_snapshot")],
            key=lambda r: r.captured_at,
            reverse=True,
        )
        return SnapshotsResponse(
            snapshots=rows[offset : offset + limit], total=len(rows), offset=offset, limit=limit
        )
