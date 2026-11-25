# Reusable reads for future AI adapters

`app/services/read_tools.py` defines ReadTools, a typed facade over the services used by
FastAPI. The [MCP stdio server](mcp.md) now exposes all endpoint reads through the existing
API boundary. No generic SDK dispatcher, trading method, import tool or snapshot-write tool
is exposed. Business services do not depend on FastAPI/MCP. Sector composition
lives in InvestmentService, shared by HTTP and the facade.

| Future tool | Existing service / returned model |
| --- | --- |
| get_stock_holdings | PortfolioService / list[HoldingValuation] |
| get_sold_stocks | EquityHistoryService / EquityHistoryResponse |
| get_stock_transaction_history | LedgerService pagination/symbol filter / TradebookResponse |
| get_realised_pnl | InvestmentService imported gains / RealisedGains |
| get_mf_holdings | MFService / list[MFHolding] |
| get_mf_transactions | MFService paginated reads / MFTransactionsResponse |
| get_portfolio_summary | InvestmentService combined values / CombinedPortfolio |
| get_portfolio_analytics | InvestmentService concentration/rankings / RiskResponse |
| get_investment_performance | PerformanceService dated returns / PerformanceResponse |
| get_asset_allocation | InvestmentService combined weights / CombinedPortfolio |
| get_sector_exposure | InvestmentService equity coverage / SectorExposureResponse |
| get_stock_quote | MarketDataService / QuoteResponse |

Trusted local usage:

```python
from app.core.config import get_settings
from app.services.container import Services
from app.services.read_tools import ReadTools

services = Services.build(get_settings())
try:
    tools = ReadTools(services)
    result = tools.get_investment_performance(period="yearly")
    payload = result.model_dump(mode="json")
finally:
    services.close()
```

Do not log private payloads in a shared process. Construction does not authenticate to Groww;
live reads remain lazy. Owning application closes Services and its HTTP clients. Never expose
the container/client, settings or import/history services as arbitrary model-callable objects.

An eventual transport must authenticate/authorize callers, validate arguments against declared
Pydantic schema types and endpoint bounds, impose inbound budgets and sanitize validation and
ServiceError failures. Python annotations alone do not validate transport input. Preserve
scope, nulls, dates, source and warnings; use model_dump(mode="json") to retain Decimal strings.
REST already applies its own authorization/typed validation/budgets. These remain transport
responsibilities, without duplicating financial logic.

AI summaries must not label imported history as lifetime complete, position P&L as lifetime
gains, or unavailable returns as zero. Keep coverage warnings with cited metrics. Never add
generic SDK invocation or financial writes to future tools.
