"""Where past per-share earnings growth came from (spec §3.2a). Explanation only.

EPS* = net income / shares = (revenue / shares) * (net income / revenue), so the
log growth splits exactly into revenue R, margin M and share count S. It is never
an input to the return calculation.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .blocks import unavailable
from .decimal_ops import number, rounded
from .ranges import WINDOW_YEARS, fiscal_years, metric_by_year

EPS_GAP_LIMIT = Decimal("0.01")
MARGIN_SHARE_LIMIT = Decimal("0.5")
BUYBACK_SHARE_LIMIT = Decimal("0.3")
MIN_ANNUAL_TOTAL = Decimal("0.01")


def _gap(disclosed, computed) -> Decimal:
    return abs(disclosed - computed) / abs(computed)


def decompose(history: dict) -> dict:
    rows = history["rows"]
    revenue, profit, shares = (metric_by_year(rows, m) for m in ("Revenue", "Net Income", "Shares Diluted"))
    eps = metric_by_year(rows, "EPS Diluted")
    implied = history.get("sharesBasis") == "shares_implied_from_eps"
    years = fiscal_years(history)
    windows, dropped = [], []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for start in (range(years[0], years[-1] - WINDOW_YEARS + 1) if years else ()):
            end = start + WINDOW_YEARS
            needed = [(table, year) for table in (revenue, profit, shares) for year in (start, end)]
            if any(year not in table for table, year in needed):
                dropped.append({"fiscalYear": start, "endFiscalYear": end, "reason": "missing_value"})
                continue
            if min(revenue[start], revenue[end], profit[start], profit[end], shares[start], shares[end]) <= 0:
                dropped.append({"fiscalYear": start, "endFiscalYear": end, "reason": "non_positive_value"})
                continue
            r = (revenue[end] / revenue[start]).ln()
            m = ((profit[end] / revenue[end]) / (profit[start] / revenue[start])).ln()
            s = (shares[start] / shares[end]).ln()
            total = r + m + s
            if implied:
                gap = {"state": "not_applicable"}
            elif start not in eps or end not in eps:
                gap = {"state": "missing_eps"}
            else:
                gaps = [_gap(eps[year], profit[year] / shares[year]) for year in (start, end)]
                gap = {"state": "exceeds_1pct" if max(gaps) > EPS_GAP_LIMIT else "within_1pct",
                       "start": rounded(gaps[0], 4), "end": rounded(gaps[1], 4)}
            windows.append({"start": start, "end": end, "raw": (r, m, s, total), "epsGap": gap})
        if not windows:
            return {**unavailable("history_too_short"), "windows": [], "excluded": dropped}
        stored = []
        for row in windows:
            r, m, s, total = row["raw"]
            stored.append({"start": row["start"], "end": row["end"], "R": rounded(r, 4), "M": rounded(m, 4),
                           "S": rounded(s, 4), "total": rounded(total, 4),
                           "annual": {"R": rounded(r / WINDOW_YEARS, 4), "M": rounded(m / WINDOW_YEARS, 4),
                                      "S": rounded(s / WINDOW_YEARS, 4), "total": rounded(total / WINDOW_YEARS, 4)},
                           "epsGap": row["epsGap"]})
        r, m, s, total = windows[-1]["raw"]
        notes = []
        # The sentences attach to the most recent window only, and only when its
        # yearly total growth is at least 1%; otherwise a ratio means nothing.
        if total / WINDOW_YEARS >= MIN_ANNUAL_TOTAL:
            if m / total >= MARGIN_SHARE_LIMIT:
                notes.append({"code": "margin_majority", "window": [windows[-1]["start"], windows[-1]["end"]]})
            if s / total >= BUYBACK_SHARE_LIMIT:
                notes.append({"code": "share_reduction_significant", "window": [windows[-1]["start"], windows[-1]["end"]]})
    return {"status": "available", "windows": stored, "excluded": dropped, "notes": notes,
            "recentWindow": [windows[-1]["start"], windows[-1]["end"]]}
