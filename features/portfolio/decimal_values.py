"""Exact, bounded decimal values for Portfolio authority fields.

This module deliberately never calls :meth:`Decimal.normalize`: that method
uses the active context and silently rounds at Python's default precision.
Portfolio quantity and average price are authority values, not display floats.
"""
from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation, localcontext
import math

MAX_INPUT_CHARS = 256
MAX_SIGNIFICANT_DIGITS = 128
MIN_ADJUSTED_EXPONENT = -1000
MAX_ADJUSTED_EXPONENT = 1000
# Subtracting two valid values can span -1127..1000.  This is intentionally
# larger than the accepted input precision so preview deltas stay exact.
_EXACT_CONTEXT = Context(prec=2300, Emin=-999999, Emax=999999)


class DecimalValueError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _source_text(value: object) -> str:
    if value is None or isinstance(value, bool):
        raise DecimalValueError("invalid_decimal")
    text = str(value).strip()
    if not text:
        raise DecimalValueError("invalid_decimal")
    if len(text) > MAX_INPUT_CHARS:
        raise DecimalValueError("precision_unsupported")
    # Legacy manual input accepted grouping separators. Preserve that ergonomic
    # read/save compatibility while still parsing a single decimal value.
    return text.replace(",", "")


def parse_decimal(value: object) -> Decimal:
    """Parse a finite decimal without applying arithmetic or rounding."""
    try:
        parsed = Decimal(_source_text(value))
    except (InvalidOperation, ValueError) as exc:
        if isinstance(exc, DecimalValueError):
            raise
        raise DecimalValueError("invalid_decimal") from None
    if not parsed.is_finite():
        raise DecimalValueError("invalid_decimal")
    # Resource limits apply to significant digits, not the mechanically
    # expanded trailing zeroes in a canonical integer.  ``1e128`` is one
    # significant digit even when its canonical plain spelling has 129
    # characters, and canonical output must always be accepted on re-save.
    coefficient = "".join(str(digit) for digit in parsed.as_tuple().digits).lstrip("0").rstrip("0")
    digits = len(coefficient)
    if digits > MAX_SIGNIFICANT_DIGITS:
        raise DecimalValueError("precision_unsupported")
    if parsed != 0 and not (MIN_ADJUSTED_EXPONENT <= parsed.adjusted() <= MAX_ADJUSTED_EXPONENT):
        raise DecimalValueError("precision_unsupported")
    return parsed


def _render_decimal(parsed: Decimal) -> str:
    """Render a known finite Decimal without applying input resource limits."""
    if parsed.is_zero():
        return "0"
    sign, digits, exponent = parsed.as_tuple()
    coefficient = "".join(str(digit) for digit in digits)
    # Decimal's tuple is exact. Move the radix point by indexing the string,
    # rather than using a context-bearing Decimal operation.
    if exponent >= 0:
        rendered = coefficient + ("0" * exponent)
    else:
        point = len(coefficient) + exponent
        if point > 0:
            rendered = coefficient[:point] + "." + coefficient[point:]
        else:
            rendered = "0." + ("0" * (-point)) + coefficient
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if sign:
        rendered = "-" + rendered
    # The canonical response is also a valid next request: a fully expanded
    # ±1000 exponent would otherwise violate the 256-character input bound on
    # a normal save -> read -> save round trip.  Keep ordinary fractions plain
    # (including 1e-30); compact only when expansion cannot be re-submitted.
    if len(rendered) <= MAX_INPUT_CHARS:
        return rendered
    compact_coefficient = coefficient.rstrip("0")
    scientific_exponent = exponent + (len(coefficient) - len(compact_coefficient)) + len(compact_coefficient) - 1
    coefficient = compact_coefficient
    mantissa = coefficient[0] if len(coefficient) == 1 else coefficient[0] + "." + coefficient[1:]
    return ("-" if sign else "") + mantissa + f"e{scientific_exponent:+d}"


def canonical_decimal(value: object) -> str:
    """Render an accepted authority input in canonical form."""
    return _render_decimal(parse_decimal(value))


def canonical_quantity(value: object) -> str:
    parsed = parse_decimal(value)
    if parsed <= 0:
        raise DecimalValueError("invalid_quantity")
    return canonical_decimal(parsed)


def canonical_average_price(value: object, *, blank_is_zero: bool = True) -> str:
    if blank_is_zero and (value is None or (isinstance(value, str) and not value.strip())):
        return "0"
    parsed = parse_decimal(value)
    if parsed < 0:
        raise DecimalValueError("invalid_average_price")
    return canonical_decimal(parsed)


def exact_subtract(after: object, before: object | None) -> str:
    after_value = parse_decimal(after)
    before_value = Decimal(0) if before is None else parse_decimal(before)
    with localcontext(_EXACT_CONTEXT):
        difference = after_value - before_value
    return _render_decimal(difference)


def finite_float(value: object) -> float | None:
    """A display/analytics conversion that refuses overflow and underflow."""
    try:
        parsed = _calculation_decimal(value)
        rendered = float(parsed)
    except (DecimalValueError, OverflowError, ValueError):
        return None
    if not (rendered == rendered and rendered not in (float("inf"), float("-inf"))):
        return None
    if parsed != 0 and rendered == 0.0:
        return None
    return rendered


def _calculation_decimal(value: object) -> Decimal:
    """Parse an intermediate value without applying authority input limits."""
    if value is None or isinstance(value, bool):
        raise DecimalValueError("invalid_decimal")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        raise DecimalValueError("invalid_decimal") from None
    if not parsed.is_finite():
        raise DecimalValueError("invalid_decimal")
    return parsed


def finite_product(left: object, right: object) -> float | None:
    """Return an analytics-only product, or None rather than a fake zero/inf."""
    try:
        left_value = _calculation_decimal(left)
        right_value = _calculation_decimal(right)
        with localcontext(_EXACT_CONTEXT):
            product = left_value * right_value
    except (DecimalValueError, InvalidOperation):
        return None
    return finite_float(product)


def finite_difference(left: object, right: object) -> float | None:
    try:
        with localcontext(_EXACT_CONTEXT):
            difference = _calculation_decimal(left) - _calculation_decimal(right)
    except (DecimalValueError, InvalidOperation):
        return None
    return finite_float(difference)


def finite_ratio(numerator: object, denominator: object) -> float | None:
    """Return a finite display ratio, with overflow represented by ``None``."""
    try:
        with localcontext(_EXACT_CONTEXT):
            denominator_value = _calculation_decimal(denominator)
            if denominator_value.is_zero():
                return None
            ratio = _calculation_decimal(numerator) / denominator_value
    except (DecimalValueError, InvalidOperation):
        return None
    return finite_float(ratio)


def finite_sum(values: object) -> float | None:
    """Sum finite display values, returning ``None`` on float overflow."""
    total = 0.0
    try:
        iterator = iter(values)
    except TypeError:
        return None
    for value in iterator:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(number):
            return None
        total += number
        if not math.isfinite(total):
            return None
    return total
