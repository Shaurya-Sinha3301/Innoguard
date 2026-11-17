"""Money helpers. All amounts are Decimal; floats are rejected on purpose."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def D(value: str | int | Decimal) -> Decimal:
    """Build a Decimal from a string, int or Decimal. Floats raise TypeError."""
    if isinstance(value, float):
        raise TypeError("floats are not allowed for money; pass a string or Decimal")
    return Decimal(value)


def quantize_money(value: Decimal) -> Decimal:
    """Round to two decimal places, half up."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def within_tolerance(actual: Decimal, expected: Decimal, pct: Decimal) -> bool:
    """True when `actual` is within `pct` percent of `expected`."""
    return abs(actual - expected) <= abs(expected) * pct / Decimal(100)


def within_amount(actual: Decimal, expected: Decimal, amount: Decimal) -> bool:
    """True when `actual` is within an absolute `amount` of `expected`."""
    return abs(actual - expected) <= amount
