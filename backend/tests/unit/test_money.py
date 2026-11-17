from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from invoiceguard.domain.money import D, quantize_money, within_amount, within_tolerance


def test_floats_are_rejected():
    with pytest.raises(TypeError):
        D(1.1)


def test_quantize_rounds_half_up():
    assert quantize_money(Decimal("2.345")) == Decimal("2.35")
    assert quantize_money(Decimal("2.344")) == Decimal("2.34")


def test_tolerance_boundaries():
    assert within_tolerance(Decimal("102"), Decimal("100"), Decimal("2"))
    assert not within_tolerance(Decimal("102.01"), Decimal("100"), Decimal("2"))
    assert within_amount(Decimal("10.01"), Decimal("10.00"), Decimal("0.01"))
    assert not within_amount(Decimal("10.02"), Decimal("10.00"), Decimal("0.01"))


@given(st.decimals(min_value="0", max_value="1000000", places=4))
def test_quantize_is_idempotent_and_close(value):
    once = quantize_money(value)
    assert quantize_money(once) == once
    assert abs(once - value) <= Decimal("0.005")


@given(
    st.decimals(min_value="0.01", max_value="100000", places=2),
    st.decimals(min_value="0", max_value="50", places=2),
)
def test_value_is_always_within_its_own_tolerance(expected, pct):
    assert within_tolerance(expected, expected, pct)
