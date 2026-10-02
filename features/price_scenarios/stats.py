"""Percentiles for the historical ranges (spec §3.1): Hyndman-Fan type 7.

Pure Decimal arithmetic. A tied run is treated as one location by the inverse
(the middle of the run), so equal inputs always give one deterministic answer.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .decimal_ops import number

BELOW_SAMPLE = "below_sample"
ABOVE_SAMPLE = "above_sample"


def _sorted(values) -> list[Decimal]:
    rows = sorted(number(value) for value in values)
    if not rows:
        raise ValueError("empty_sample")
    return rows


def percentile(values, p) -> Decimal:
    """Type 7: h = (n - 1) * p, linear between the two neighbouring ranks."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        rows, fraction = _sorted(values), number(p)
        if not Decimal(0) <= fraction <= Decimal(1):
            raise ValueError("invalid_percentile")
        h = (len(rows) - 1) * fraction
        low = int(h.to_integral_value(rounding="ROUND_FLOOR"))
        high = min(low + 1, len(rows) - 1)
        return rows[low] + (h - low) * (rows[high] - rows[low])


def inverse_percentile(values, x):
    """Where x sits in the sample, 0..100, or below_sample / above_sample."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        rows, target = _sorted(values), number(x)
        if target < rows[0]:
            return BELOW_SAMPLE
        if target > rows[-1]:
            return ABOVE_SAMPLE
        if len(rows) == 1:
            return Decimal(0)
        equal = [i for i, row in enumerate(rows) if row == target]
        if equal:
            h = Decimal(equal[0] + equal[-1]) / 2
        else:
            low = max(i for i, row in enumerate(rows) if row < target)
            h = low + (target - rows[low]) / (rows[low + 1] - rows[low])
        return h / (len(rows) - 1) * 100
