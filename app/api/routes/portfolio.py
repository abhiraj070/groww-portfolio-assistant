from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_services
from app.schemas.holdings import HoldingsResponse
from app.schemas.market_data import AccountResponse, Segment
from app.schemas.orders import OrdersResponse
from app.schemas.portfolio import AnalyticsResponse, PortfolioSummary
from app.schemas.positions import PositionsResponse
from app.services.container import Services

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
ServiceDependency = Annotated[Services, Depends(get_services)]


@router.get("/holdings", response_model=HoldingsResponse)
def holdings(services: ServiceDependency) -> HoldingsResponse:
    return services.holdings.get_holdings()


@router.get("/positions", response_model=PositionsResponse)
def positions(services: ServiceDependency, segment: Segment | None = None) -> PositionsResponse:
    return services.positions.get_positions(segment)


@router.get("/orders", response_model=OrdersResponse)
def orders(
    services: ServiceDependency,
    page: Annotated[int, Query(ge=0, le=10000)] = 0,
    page_size: Annotated[int, Query(ge=1, le=25)] = 25,
    segment: Segment | None = None,
) -> OrdersResponse:
    return services.orders.get_orders(page, page_size, segment)


@router.get("/summary", response_model=PortfolioSummary)
def summary(services: ServiceDependency) -> PortfolioSummary:
    return services.portfolio.get_portfolio_summary()


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(services: ServiceDependency) -> AnalyticsResponse:
    return services.portfolio.get_portfolio_analytics()


@router.get("/account", response_model=AccountResponse)
def account(services: ServiceDependency) -> AccountResponse:
    return services.market.get_account()
