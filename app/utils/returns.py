"""Dated cash-flow returns using Decimal, actual days / 365."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, DecimalException, localcontext


def xirr(flows: list[tuple[date, Decimal]]) -> Decimal | None:
    """Return a rate fraction for a conventional schedule, otherwise unknown.

    Same-day flows are netted. Nonconventional schedules may have several roots;
    reject them rather than choosing a root based on an arbitrary initial guess.
    """
    totals = defaultdict(lambda: Decimal(0))
    for day, amount in flows:
        if not amount.is_finite():
            return None
        totals[day] += amount
    values = [(d, a) for d, a in sorted(totals.items()) if a]
    if len(values) < 2 or values[0][0] == values[-1][0]:
        return None
    signs = [a > 0 for _, a in values]
    if sum(a != b for a, b in zip(signs, signs[1:], strict=False)) != 1:
        return None
    try:
        with localcontext() as context:
            context.prec = 40
            years = [(Decimal((d - values[0][0]).days) / 365, a) for d, a in values]

            def npv(rate):
                return sum((amount / (1 + rate) ** years for years, amount in years), Decimal(0))

            low, high = Decimal("-0.999999"), Decimal("1000000")
            left, right = npv(low), npv(high)
            if left * right > 0:
                return None
            for _ in range(240):
                middle = (low + high) / 2
                value = npv(middle)
                if abs(value) <= Decimal("1e-24") or high - low <= Decimal("1e-24"):
                    return +middle
                if value * left > 0:
                    low, left = middle, value
                else:
                    high = middle
    except DecimalException:
        return None
    return None


def cagr(opening: Decimal, closing: Decimal, days: int) -> Decimal | None:
    if opening <= 0 or closing < 0 or days <= 0:
        return None
    with localcontext() as context:
        context.prec = 40
        return (closing / opening) ** (Decimal(365) / days) - 1
