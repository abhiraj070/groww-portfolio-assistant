from datetime import date

from fastapi import APIRouter

from app.api.routes.portfolio import ServiceDependency
from app.schemas.investment_analytics import (
    CombinedPortfolio,
    PerformanceResponse,
    Period,
    RealisedGains,
    RiskResponse,
    SectorExposureResponse,
    TaxDataResponse,
)

router = APIRouter(prefix="/analytics", tags=["investment analytics"])


@router.get("/net-worth", response_model=CombinedPortfolio)
@router.get("/total-investment", response_model=CombinedPortfolio)
@router.get("/unrealised-gains", response_model=CombinedPortfolio)
@router.get("/asset-allocation", response_model=CombinedPortfolio)
def combined(services: ServiceDependency):
    return services.investment.combined()


@router.get("/realised-gains", response_model=RealisedGains)
def realised(services: ServiceDependency):
    return services.investment.realised()


@router.get("/total-returns", response_model=PerformanceResponse)
@router.get("/performance", response_model=PerformanceResponse)
def performance(
    services: ServiceDependency,
    period: Period = "all_time",
    start: date | None = None,
    end: date | None = None,
):
    return services.performance.performance(period, start, end)


@router.get("/risk", response_model=RiskResponse)
def risk(services: ServiceDependency):
    return services.investment.risk()


@router.get("/sector-exposure", response_model=SectorExposureResponse)
def sectors(services: ServiceDependency):
    report = services.portfolio.get_portfolio_analytics()
    return dict(
        sectors=report.sector_allocation,
        unclassified_market_value=report.unclassified_market_value,
        source=report.sector_metadata_source,
        as_of=report.sector_metadata_as_of,
        scope="equity_only",
        warnings=["MF constituent sector data is unavailable; these are equity portfolio weights."],
    )


@router.get("/tax-report", response_model=TaxDataResponse)
def tax(services: ServiceDependency, start: date | None = None, end: date | None = None):
    return services.investment.tax_data(start, end)
