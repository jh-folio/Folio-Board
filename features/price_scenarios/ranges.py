"""Historical ranges (spec §3.1) built from the already event-adjusted history.

Each builder returns (block, quartiles): `block` is the storable result
({status, values, p25, p50, p75, n, excluded} or an unavailable reason) and
`quartiles` keeps the unrounded Decimals that scenarios consume, so rounding
happens once at storage. A 5-year window pairs fiscal year y with y + 5; missing
or excluded endpoints drop that window with a recorded reason and no year is
ever filled in.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .blocks import unavailable
from .decimal_ops import number, rounded
from .stats import percentile

MIN_WINDOWS, MIN_YEARS = 3, 5
WINDOW_YEARS = 5


def metric_by_year(rows: list[dict], metric: str) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for row in rows:
        if row["metric"] != metric:
            continue
        year = int(row["fiscalYear"])
        if year in out:
            raise ValueError("ambiguous_fiscal_year")
        out[year] = number(row["value"])
    return out


def fiscal_years(history: dict) -> list[int]:
    years = {int(row["fiscalYear"]) for row in history["rows"]}
    years |= {int(row["fiscalYear"]) for row in history.get("excludedYears", [])}
    return sorted(years)


def _finish(values: list[dict], excluded: list[dict], minimum: int, places: int):
    raw = [row["raw"] for row in values]
    stored = [{key: value for key, value in row.items() if key != "raw"} for row in values]
    for row, item in zip(stored, raw):
        row["value"] = rounded(item, places)
    if len(raw) < minimum:
        return {**unavailable("history_too_short"), "n": len(raw), "required": minimum,
                "values": stored, "excluded": excluded}, None
    q = {name: percentile(raw, p) for name, p in (("p25", "0.25"), ("p50", "0.5"), ("p75", "0.75"))}
    return {"status": "available", "values": stored, "n": len(raw), "excluded": excluded,
            **{name: rounded(value, places) for name, value in q.items()}}, q


def _windows(years: list[int], value_at, *, positive: str):
    """Yield valid 5-year growth windows plus the dropped ones."""
    if not years:
        return [], []
    first, last = years[0], years[-1]
    valid, dropped = [], []
    for start in range(first, last - WINDOW_YEARS + 1):
        end = start + WINDOW_YEARS
        a, b = value_at(start), value_at(end)
        if a is None or b is None:
            dropped.append({"fiscalYear": start, "endFiscalYear": end, "reason": "missing_value"})
        elif a <= 0 or b <= 0:
            dropped.append({"fiscalYear": start, "endFiscalYear": end, "reason": positive})
        else:
            valid.append((start, end, a, b))
    return valid, dropped


def _growth(valid):
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        return [{"fiscalYear": start, "endFiscalYear": end, "raw": (b / a) ** (Decimal(1) / WINDOW_YEARS) - 1}
                for start, end, a, b in valid]


def growth_range(history: dict):
    eps = metric_by_year(history["rows"], "EPS Diluted")
    valid, dropped = _windows(fiscal_years(history), eps.get, positive="non_positive_eps")
    return _finish(_growth(valid), dropped, MIN_WINDOWS, 4)


def rps_growth_range(history: dict):
    revenue, shares = metric_by_year(history["rows"], "Revenue"), metric_by_year(history["rows"], "Shares Diluted")
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        per_share = {y: revenue[y] / shares[y] for y in revenue if y in shares and shares[y] > 0}
    valid, dropped = _windows(fiscal_years(history), per_share.get, positive="non_positive_revenue_per_share")
    return _finish(_growth(valid), dropped, MIN_WINDOWS, 4)


def pe_range(history: dict, fiscal_prices: list[dict] | None, prices_reason: dict | None = None):
    """Year-end close / diluted EPS. `fiscal_prices` None means the closes are unusable."""
    if fiscal_prices is None:
        return unavailable((prices_reason or {}).get("code", "price_event_unverified")), None
    eps = metric_by_year(history["rows"], "EPS Diluted")
    close = {int(row["fiscalYear"]): number(row["close"]) for row in fiscal_prices}
    values, dropped = [], []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for year in fiscal_years(history):
            if year not in eps or year not in close:
                dropped.append({"fiscalYear": year, "reason": "missing_value"})
            elif eps[year] <= 0:
                dropped.append({"fiscalYear": year, "reason": "non_positive_eps"})
            else:
                values.append({"fiscalYear": year, "raw": close[year] / eps[year]})
    return _finish(values, dropped, MIN_YEARS, 2)


def margin_range(history: dict):
    revenue, profit = metric_by_year(history["rows"], "Revenue"), metric_by_year(history["rows"], "Net Income")
    values, dropped = [], []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for year in fiscal_years(history):
            if year not in revenue or year not in profit:
                dropped.append({"fiscalYear": year, "reason": "missing_value"})
            elif revenue[year] <= 0:
                dropped.append({"fiscalYear": year, "reason": "non_positive_revenue"})
            else:
                values.append({"fiscalYear": year, "raw": profit[year] / revenue[year]})
    return _finish(values, dropped, MIN_YEARS, 4)


def payout_range(history: dict, dividends: dict[int, Decimal | None] | None = None):
    """DPS / EPS in 0..100%. `dividends` overrides the DPS column (None = missing).

    A missing DPS is never read as zero here; whatever policy fills proven
    zero-dividend years does so before this function.
    """
    eps = metric_by_year(history["rows"], "EPS Diluted")
    dps = dividends if dividends is not None else metric_by_year(history["rows"], "DPS")
    values, dropped = [], []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for year in fiscal_years(history):
            if year not in eps:
                dropped.append({"fiscalYear": year, "reason": "missing_value"})
            elif eps[year] <= 0:
                dropped.append({"fiscalYear": year, "reason": "non_positive_eps"})
            elif dps.get(year) is None:
                dropped.append({"fiscalYear": year, "reason": "missing_value"})
            else:
                ratio = number(dps[year]) / eps[year]
                if ratio < 0 or ratio > 1:
                    dropped.append({"fiscalYear": year, "reason": "payout_out_of_range"})
                else:
                    values.append({"fiscalYear": year, "raw": ratio})
    return _finish(values, dropped, MIN_YEARS, 4)
