from app.core.exceptions import ServiceError, invalid_response
from app.schemas.positions import Position, PositionsResponse
from app.services.groww_client import GrowwClient
from app.services.validation import parse_collection


class PositionsService:
    def __init__(self, client: GrowwClient):
        self.client = client

    def get_positions(self, segment: str | None = None) -> PositionsResponse:
        if segment not in {None, "CASH", "FNO", "COMMODITY", "CURRENCY"}:
            raise ServiceError("invalid_segment", "Unsupported segment", 422)
        rows = parse_collection(self.client.get_positions(segment), "positions", Position)
        identifiers = [(r.exchange, r.segment, r.product, r.trading_symbol) for r in rows]
        if len(set(identifiers)) != len(identifiers):
            raise invalid_response()
        return PositionsResponse(positions=rows)
