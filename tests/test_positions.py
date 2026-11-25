from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.core.exceptions import ServiceError
from app.services.positions_service import PositionsService


def test_short_and_carry_forward_fields():
    client = Mock()
    client.get_positions.return_value = {
        "positions": [
            {
                "trading_symbol": "SYNTH",
                "segment": "FNO",
                "quantity": -2,
                "realised_pnl": "12.34",
                "carry_forward_debit_quantity": 2,
                "net_price": "-50",
            }
        ]
    }
    result = PositionsService(client).get_positions("FNO").positions[0]
    assert result.quantity == -2
    assert result.realised_pnl == Decimal("12.34")
    assert result.carry_forward_debit_quantity == 2
    client.get_positions.assert_called_once_with("FNO")


def test_missing_realised_is_unknown():
    client = Mock()
    client.get_positions.return_value = {
        "positions": [{"trading_symbol": "SYNTH", "segment": "CASH", "quantity": 0}]
    }
    assert PositionsService(client).get_positions().positions[0].realised_pnl is None


def test_invalid_segment_never_calls_provider():
    client = Mock()
    with pytest.raises(ServiceError):
        PositionsService(client).get_positions("INVALID")
    client.get_positions.assert_not_called()
