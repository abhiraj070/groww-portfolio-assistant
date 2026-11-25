from app.core.exceptions import ServiceError, invalid_response
from app.schemas.orders import Order, OrdersResponse, Trade, TradesResponse
from app.services.groww_client import GrowwClient
from app.services.market_data_service import parse_model
from app.services.validation import parse_collection


class OrdersService:
    def __init__(self, client: GrowwClient):
        self.client = client

    @staticmethod
    def validate_order(order_id: str, segment: str) -> None:
        from pydantic import TypeAdapter, ValidationError

        from app.schemas.equity_history import Identifier

        try:
            TypeAdapter(Identifier).validate_python(order_id)
        except ValidationError:
            raise ServiceError("invalid_order", "Invalid order identifier", 422) from None
        if segment not in {"CASH", "FNO", "COMMODITY", "CURRENCY"}:
            raise ServiceError("invalid_segment", "Invalid segment", 422)

    def get_order(self, order_id: str, segment: str = "CASH") -> Order:
        self.validate_order(order_id, segment)
        order = parse_model(Order, self.client.get_order_detail(order_id, segment))
        if order.groww_order_id != order_id:
            raise invalid_response()
        return order

    def get_trades(
        self, order_id: str, segment: str = "CASH", page: int = 0, page_size: int = 50
    ) -> TradesResponse:
        self.validate_order(order_id, segment)
        if (
            type(page) is not int
            or type(page_size) is not int
            or not 0 <= page <= 10000
            or not 1 <= page_size <= 50
        ):
            raise ServiceError("invalid_order_query", "Invalid execution pagination", 422)
        rows = parse_collection(
            self.client.get_order_trades(order_id, segment, page, page_size), "trade_list", Trade
        )
        if (
            len(rows) > page_size
            or any(r.groww_order_id != order_id for r in rows)
            or len({(r.exchange, r.exchange_trade_id) for r in rows}) != len(rows)
        ):
            raise invalid_response()
        return TradesResponse(
            trades=rows,
            page=page,
            page_size=page_size,
            possible_next_page=page + 1 if len(rows) == page_size else None,
        )

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
