"""No-dividend reading of missing DPS years (spec-3 §3.1-3).

A year with no DPS fact is read as DPS 0 only when (a) its diluted EPS is
positive, (b) the same year has an operating-cash-flow fact (the cash-flow
statement was read), and (c) `Dividends Paid` is absent or 0. Anything else stays
missing. The input history is never changed; the result lists the years it read
so storage and display can say so.
"""
from __future__ import annotations

from decimal import Decimal

from .decimal_ops import number
from .ranges import fiscal_years, metric_by_year

NOTICE = "dividend_assumed_zero_from_absence"


def read_dividends(history: dict, *, unreadable_years: set[int] | None = None) -> tuple[dict[int, Decimal | None], list[int]]:
    """({fiscalYear: DPS or None}, years read as zero). `unreadable_years` are lookup failures, never read."""
    eps = metric_by_year(history["rows"], "EPS Diluted")
    dps = metric_by_year(history["rows"], "DPS")
    cash = metric_by_year(history["rows"], "Operating Cash Flow")
    paid = metric_by_year(history["rows"], "Dividends Paid")
    blocked = unreadable_years or set()
    out: dict[int, Decimal | None] = {}
    zero_years: list[int] = []
    for year in fiscal_years(history):
        if year in dps:
            out[year] = number(dps[year])
        elif year in eps and eps[year] > 0 and year in cash and year not in blocked and (year not in paid or paid[year] == 0):
            out[year] = Decimal(0)
            zero_years.append(year)
        else:
            out[year] = None
    return out, zero_years
