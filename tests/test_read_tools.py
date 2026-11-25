import ast
from pathlib import Path
from unittest.mock import Mock

from app.services.read_tools import ReadTools


def test_explicit_facade_delegates_to_existing_services():
    services = Mock()
    tools = ReadTools(services)
    assert (
        tools.get_stock_holdings()
        is services.portfolio.get_portfolio_analytics.return_value.holdings
    )
    assert tools.get_sold_stocks() is services.equity_history.analyse.return_value
    services.equity_history.analyse.assert_called_once_with(sold_only=True)
    assert (
        tools.get_stock_transaction_history(2, 10, "SYNTH")
        is services.ledger.tradebook.return_value
    )
    services.ledger.tradebook.assert_called_once_with(2, 10, "SYNTH")
    assert tools.get_realised_pnl() is services.investment.realised.return_value
    assert tools.get_mf_holdings() is services.mf.portfolio.return_value.holdings
    assert tools.get_mf_transactions(2, 10) is services.mf.transactions.return_value
    services.mf.transactions.assert_called_once_with(offset=2, limit=10)
    assert tools.get_portfolio_summary() is services.investment.combined.return_value
    assert tools.get_asset_allocation() is services.investment.combined.return_value
    assert tools.get_portfolio_analytics() is services.investment.risk.return_value
    assert tools.get_sector_exposure() is services.investment.sector_exposure.return_value
    assert (
        tools.get_investment_performance("weekly") is services.performance.performance.return_value
    )
    services.performance.performance.assert_called_once_with("weekly", None, None)
    assert tools.get_stock_quote("SYNTH", "BSE") is services.market.get_quote.return_value
    services.market.get_quote.assert_called_once_with("SYNTH", "BSE", "CASH")


def test_facade_exposes_only_explicit_read_methods():
    public = {name for name in dir(ReadTools) if not name.startswith("_")}
    assert len(public) == 12
    assert all(name.startswith("get_") for name in public)
    assert not {"import_csv", "capture", "dispatch", "place_order", "cancel_order"} & public


def test_business_services_do_not_depend_on_fastapi_or_mcp():
    services = Path(__file__).resolve().parents[1] / "app" / "services"
    for path in services.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("fastapi", "starlette", "mcp")), (
                    path.name
                )
            elif isinstance(node, ast.Import):
                assert all(
                    not item.name.startswith(("fastapi", "starlette", "mcp")) for item in node.names
                ), path.name
