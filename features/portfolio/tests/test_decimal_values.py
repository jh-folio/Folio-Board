from decimal import Context, Decimal, localcontext

import pytest

from features.portfolio.decimal_values import DecimalValueError, canonical_decimal, canonical_quantity, exact_subtract, finite_product, finite_ratio


@pytest.mark.parametrize(("raw", "expected"), [
    ("1.50", "1.5"),
    ("15e-1", "1.5"),
    ("1e-30", "0.000000000000000000000000000001"),
    ("1e-1000", "1e-1000"),
    ("1e1000", "1e+1000"),
])
def test_canonical_decimal_is_exact_and_resubmittable(raw, expected):
    rendered = canonical_decimal(raw)
    assert rendered == expected
    assert canonical_decimal(rendered) == expected


def test_exact_delta_can_exceed_authority_input_precision_without_rounding():
    delta = exact_subtract("1e-1000", "1e1000")
    with localcontext(Context(prec=2300, Emin=-999999, Emax=999999)):
        expected = Decimal("1e-1000") - Decimal("1e1000")
    assert Decimal(delta) == expected


@pytest.mark.parametrize("raw", ["1e128", "1e255"])
def test_expanded_canonical_integer_uses_significant_digit_limit(raw):
    rendered = canonical_decimal(raw)
    assert "e" not in rendered.lower()
    assert canonical_decimal(rendered) == rendered


def test_derived_math_does_not_reapply_authority_input_limits():
    assert finite_product("1e-300", "1e400") == pytest.approx(1e100)
    assert finite_ratio(1e308, 1e-308) is None


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "0", "-1", "1" * 129, "1e1001"])
def test_invalid_or_out_of_bounds_quantity_is_rejected(raw):
    with pytest.raises(DecimalValueError):
        canonical_quantity(raw)
