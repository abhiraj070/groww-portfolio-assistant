from app.core.exceptions import invalid_response
from app.schemas.holdings import Holding, HoldingsResponse
from app.services.groww_client import GrowwClient
from app.services.validation import parse_collection


class HoldingsService:
    def __init__(self, client: GrowwClient):
        self.client = client

    def get_holdings(self) -> HoldingsResponse:
        rows = parse_collection(self.client.get_holdings(), "holdings", Holding)
        if len({row.isin for row in rows}) != len(rows) or len(
            {row.trading_symbol for row in rows}
        ) != len(rows):
            # Fail rather than value an ambiguous duplicate DEMAT asset twice.
            raise invalid_response()
        return HoldingsResponse(holdings=rows)
