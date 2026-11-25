"""Stock namespace: share existing handlers and services, preserve legacy routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.routes import market_data, portfolio
from app.api.routes.portfolio import ServiceDependency
from app.schemas.equity_history import EquityHistoryResponse, Identifier, TradebookResponse
from app.schemas.market_data import Segment, Symbol
from app.schemas.orders import Order, TradesResponse
from app.schemas.portfolio import HoldingValuation
from app.services.instruments_service import InstrumentsResponse

router = APIRouter(prefix="/stocks", tags=["stocks"])
router.add_api_route("/positions", portfolio.positions, methods=["GET"])
router.add_api_route("/orders", portfolio.orders, methods=["GET"])
router.add_api_route("/portfolio/summary", portfolio.summary, methods=["GET"])
router.add_api_route("/portfolio/analytics", portfolio.analytics, methods=["GET"])
for route in market_data.router.routes:
    router.add_api_route(route.path.removeprefix("/market"), route.endpoint, methods=["GET"])


@router.get("/portfolio/allocation", response_model=list[HoldingValuation])
def allocation(services: ServiceDependency):
    return services.portfolio.get_portfolio_analytics().holdings


@router.get("/holdings", response_model=list[HoldingValuation])
def valued_holdings(services: ServiceDependency):
    return services.portfolio.get_portfolio_analytics().holdings


@router.get("/orders/{order_id}", response_model=Order)
def order_detail(order_id: Identifier, services: ServiceDependency, segment: Segment = "CASH"):
    return services.orders.get_order(order_id, segment)


@router.get("/orders/{order_id}/trades", response_model=TradesResponse)
def order_trades(
    order_id: Identifier,
    services: ServiceDependency,
    segment: Segment = "CASH",
    page: Annotated[int, Query(ge=0, le=10000)] = 0,
    page_size: Annotated[int, Query(ge=1, le=50)] = 50,
):
    return services.orders.get_trades(order_id, segment, page, page_size)


@router.get("/trades", response_model=TradebookResponse)
@router.get("/tradebook", response_model=TradebookResponse)
def tradebook(
    services: ServiceDependency,
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    symbol: Symbol | None = None,
):
    return services.ledger.tradebook(offset, limit, symbol)


@router.get("/sold", response_model=EquityHistoryResponse)
def sold(services: ServiceDependency):
    return services.equity_history.analyse(sold_only=True)


@router.get("/realised-pnl", response_model=EquityHistoryResponse)
def realised(services: ServiceDependency):
    return services.equity_history.analyse()


@router.get("/instruments", response_model=InstrumentsResponse)
def instruments(
    services: ServiceDependency,
    exchange: Literal["NSE", "BSE"] = "NSE",
    symbol: Symbol | None = None,
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    return services.instruments.get_instruments(exchange, symbol, offset, limit)
