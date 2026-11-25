from app.core.exceptions import ServiceError, invalid_response
from app.schemas.orders import Order, OrdersResponse
from app.services.groww_client import GrowwClient
from app.services.validation import parse_collection


class OrdersService:
    def __init__(self, client: GrowwClient):
        self.client = client

    def get_orders(
        self, page: int = 0, page_size: int = 25, segment: str | None = None
    ) -> OrdersResponse:
        if (
            isinstance(page, bool)
            or isinstance(page_size, bool)
            or not isinstance(page, int)
            or not isinstance(page_size, int)
            or not 0 <= page <= 10000
            or not 1 <= page_size <= 25
            or segment not in {None, "CASH", "FNO", "COMMODITY", "CURRENCY"}
        ):
            raise ServiceError("invalid_order_query", "Invalid order pagination or segment", 422)
        rows = parse_collection(
            self.client.get_orders(page, page_size, segment), "order_list", Order
        )
        if len({r.groww_order_id for r in rows}) != len(rows) or len(rows) > page_size:
            raise invalid_response()
        return OrdersResponse(
            orders=rows,
            page=page,
            page_size=page_size,
            possible_next_page=page + 1 if len(rows) == page_size else None,
        )
