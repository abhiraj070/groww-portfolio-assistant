from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.routes.portfolio import ServiceDependency
from app.schemas.mutual_funds import (
    MFHolding,
    MFPortfolioResponse,
    MFTransactionsResponse,
    SchemeCode,
    StoredNAV,
    UnavailableMetric,
)
from app.services.mf_service import PURCHASES, REDEMPTIONS

router = APIRouter(prefix="/mf", tags=["mutual funds"])
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=1000)]


@router.get("/holdings", response_model=list[MFHolding])
@router.get("/portfolio/allocation", response_model=list[MFHolding])
def holdings(services: ServiceDependency):
    return services.mf.portfolio().holdings


@router.get("/portfolio/summary", response_model=MFPortfolioResponse)
@router.get("/portfolio/analytics", response_model=MFPortfolioResponse)
@router.get("/portfolio/returns", response_model=MFPortfolioResponse)
@router.get("/realised-pnl", response_model=MFPortfolioResponse)
def portfolio(services: ServiceDependency):
    return services.mf.portfolio()


@router.get("/transactions", response_model=MFTransactionsResponse)
def transactions(services: ServiceDependency, offset: Offset = 0, limit: Limit = 100):
    return services.mf.transactions(offset=offset, limit=limit)


@router.get("/purchases", response_model=MFTransactionsResponse)
def purchases(services: ServiceDependency, offset: Offset = 0, limit: Limit = 100):
    return services.mf.transactions(PURCHASES, offset, limit)


@router.get("/redemptions", response_model=MFTransactionsResponse)
def redemptions(services: ServiceDependency, offset: Offset = 0, limit: Limit = 100):
    return services.mf.transactions(REDEMPTIONS, offset, limit)


@router.get("/sip", response_model=MFTransactionsResponse)
@router.get("/sip/history", response_model=MFTransactionsResponse)
def sip(services: ServiceDependency, offset: Offset = 0, limit: Limit = 100):
    return services.mf.transactions({"SIP"}, offset, limit)


@router.get("/dividends", response_model=MFTransactionsResponse)
def dividends(services: ServiceDependency, offset: Offset = 0, limit: Limit = 100):
    return services.mf.transactions({"DIVIDEND", "REINVESTMENT"}, offset, limit)


@router.get("/nav/{scheme_id}", response_model=StoredNAV)
def nav(scheme_id: SchemeCode, services: ServiceDependency):
    return services.mf.latest_nav(scheme_id)


@router.get("/nav/{scheme_id}/history", response_model=list[StoredNAV])
def nav_history(
    scheme_id: SchemeCode,
    services: ServiceDependency,
    start: date | None = None,
    end: date | None = None,
):
    return services.mf.nav_history(scheme_id, start, end)


@router.get("/schemes", response_model=list[StoredNAV])
def schemes(services: ServiceDependency, offset: Offset = 0, limit: Limit = 100):
    return services.mf.schemes(offset, limit)


@router.get("/benchmark-returns", response_model=UnavailableMetric)
def benchmark_returns(services: ServiceDependency):
    return services.mf.unavailable("benchmark_returns")


@router.get("/expense-ratio", response_model=UnavailableMetric)
def expense_ratio(services: ServiceDependency):
    return services.mf.unavailable("expense_ratio")


@router.get("/fund-overlap", response_model=UnavailableMetric)
def fund_overlap(services: ServiceDependency):
    return services.mf.unavailable("fund_overlap")
