from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def percentage(value: Decimal, base: Decimal | None) -> Decimal | None:
    if base is None or base == ZERO:
        return None
    return (value / base * HUNDRED).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
