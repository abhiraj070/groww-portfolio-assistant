from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.core.exceptions import ServiceError
from app.services.holdings_service import HoldingsService


def test_holding_fields_and_extra_metadata_preserved():
    client = Mock()
    client.get_holdings.return_value = {
        "holdings": [
            {
                "trading_symbol": "SYNTH",
                "isin": "SYNTHETIC-ISIN",
                "quantity": 2.5,
                "average_price": 10.1,
                "pledge_quantity": 1,
                "provider_metadata": "synthetic",
            }
        ]
    }
    result = HoldingsService(client).get_holdings().holdings[0]
    assert result.quantity * result.average_price == Decimal("25.25")
    assert result.pledge_quantity == 1
    assert result.model_extra["provider_metadata"] == "synthetic"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"holdings": None},
        {"holdings": [{}]},
        {"holdings": [{"trading_symbol": "SYNTH", "isin": "SYNTH", "quantity": "NaN"}]},
    ],
)
def test_malformed_holdings_fail_explicitly(payload):
    client = Mock()
    client.get_holdings.return_value = payload
    with pytest.raises(ServiceError) as error:
        HoldingsService(client).get_holdings()
    assert error.value.code == "invalid_upstream_response"


def test_duplicate_isin_is_not_counted_twice():
    client = Mock()
    row = {"trading_symbol": "SYNTH", "isin": "SYNTH", "quantity": 2}
    client.get_holdings.return_value = {"holdings": [row, row]}
    with pytest.raises(ServiceError):
        HoldingsService(client).get_holdings()


def test_empty_holdings_are_valid():
    client = Mock()
    client.get_holdings.return_value = {"holdings": []}
    assert HoldingsService(client).get_holdings().holdings == []
