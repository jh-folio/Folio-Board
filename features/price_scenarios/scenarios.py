"""Assemble the stored scenario results from adjusted history (spec §3).

Pure: the adjusted history, the reference price and the adjusted fiscal-year
closes go in, plain JSON-ready blocks come out. Judgements against a person's
criteria, required-return inversions and "my assumptions" are read-time work
(`project()`), never stored here.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from . import ranges as rng
from .blocks import unavailable
from .decimal_ops import number, rounded
from .decomposition import decompose
from .history import _shift_months
from .returns import NOT_NEEDED, required_exit_pe, required_margin, scenario_irr
from .stats import inverse_percentile

SCENARIO_PERCENTILES = (("conservative", "p25", 25), ("base", "p50", 50), ("optimistic", "p75", 75))
HORIZONS = (5, 10)
STALE_MONTHS = 15


def _months_between(start: dt.date, end: dt.date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month - (1 if end.day < start.day else 0)


def _row(history: dict, metric: str, year: int):
    found = [row for row in history["rows"] if row["metric"] == metric and int(row["fiscalYear"]) == year]
    return found[0] if len(found) == 1 else None


def _stale(row, session_date: str) -> bool:
    return dt.date.fromisoformat(row["period"]["end"]) < _shift_months(dt.date.fromisoformat(session_date), -STALE_MONTHS)


def base_year(history: dict, session_date: str) -> dict:
    """The latest fiscal year's diluted EPS and how old it is at the reference date."""
    years = rng.fiscal_years(history)
    row = _row(history, "EPS Diluted", years[-1]) if years else None
    if row is None:
        return unavailable("base_eps_missing")
    if _stale(row, session_date):
        return unavailable("stale_financials")
    end, session = dt.date.fromisoformat(row["period"]["end"]), dt.date.fromisoformat(session_date)
    return {"status": "available", "fiscalYear": years[-1], "periodEnd": row["period"]["end"],
            "monthsBeforeSession": _months_between(end, session), "eps0": row["value"]}


def _irr_cell(value):
    return {"irr": rounded(value, 4), "irrRange": None} if isinstance(value, Decimal) else {"irr": None, "irrRange": value}


def _blocked(ranges: dict, names) -> str | None:
    """Reason code of the first required range that could not be built."""
    # The frozen spec blocks every calculation that uses the year-end PER range with that range's reason
    # (price_event_unverified), whatever else is also too short.
    if "pe" in names and (ranges["pe"].get("reason") or {}).get("code") == "price_event_unverified":
        return "price_event_unverified"
    for name in names:
        if ranges[name]["status"] != "available":
            return ranges[name]["reason"]["code"]
    return None


def _scenario_rows(price, base, quartiles, ranges):
    out = []
    block = base["reason"]["code"] if base["status"] != "available" else _blocked(ranges, ("growth", "pe", "payout"))
    for horizon in HORIZONS:
        for label, name, percent in SCENARIO_PERCENTILES:
            head = {"label": label, "horizon": horizon}
            if block is None and number(base["eps0"]) <= 0:
                block = "negative_base_eps"
            if block is not None:
                out.append({**head, **unavailable(block)})
                continue
            g, pe, payout = quartiles["growth"][name], quartiles["pe"][name], quartiles["payout"]["p50"]
            out.append({**head, "status": "available", "g": rounded(g, 4), "exitPE": rounded(pe, 2),
                        "payout": rounded(payout, 4),
                        "percentiles": {"g": percent, "exitPE": percent, "payout": 50},
                        "n": {"g": ranges["growth"]["n"], "exitPE": ranges["pe"]["n"], "payout": ranges["payout"]["n"]},
                        **_irr_cell(scenario_irr(price, base["eps0"], g, pe, payout, horizon))})
    return out


def _break_even_pe(price, base, quartiles, ranges):
    """Exit PER at which the median growth/payout path just returns 0%."""
    block = base["reason"]["code"] if base["status"] != "available" else _blocked(ranges, ("growth", "payout"))
    if block is None and number(base["eps0"]) <= 0:
        block = "negative_base_eps"
    out = {}
    for horizon in HORIZONS:
        if block is not None:
            out[str(horizon)] = unavailable(block)
            continue
        value = required_exit_pe(price, base["eps0"], quartiles["growth"]["p50"], quartiles["payout"]["p50"], horizon, 0)
        out[str(horizon)] = ({"status": "available", "state": NOT_NEEDED} if value == NOT_NEEDED
                             else {"status": "available", "state": "needed", "exitPE": rounded(value, 2)})
    return out


def _percent(value):
    return value if isinstance(value, str) else rounded(value, 1)


def _break_even_margin(history, price, session_date, quartiles, ranges):
    """Net margin in year N that returns 0% when per-share revenue grows at its median."""
    years = rng.fiscal_years(history)
    latest = {metric: (_row(history, metric, years[-1]) if years else None)
              for metric in ("Revenue", "Shares Diluted", "Net Income", "EPS Diluted")}
    revenue, shares, profit, eps = (latest[m] for m in ("Revenue", "Shares Diluted", "Net Income", "EPS Diluted"))
    block = _blocked(ranges, ("rpsGrowth", "pe", "payout"))
    if block is None and (not (revenue and shares and profit) or number(revenue["value"]) <= 0
                          or number(shares["value"]) <= 0):
        block = "non_positive_revenue"
    if block is None and _stale(revenue, session_date):
        block = "stale_financials"
    out = {}
    for horizon in HORIZONS:
        if block is not None:
            out[str(horizon)] = unavailable(block)
            continue
        with localcontext() as context:
            context.prec, context.rounding = 28, ROUND_HALF_EVEN
            rps0 = number(revenue["value"]) / number(shares["value"])
            margin0 = number(profit["value"]) / number(revenue["value"])
            value = required_margin(price, rps0, quartiles["rpsGrowth"]["p50"], margin0, quartiles["pe"]["p50"],
                                    quartiles["payout"]["p50"], horizon, 0)
            # revenuePerShare keeps full precision: the read-time inversion for a person's
            # required return starts from it, and a rounded start would not replay.
            entry = {"status": "available", "currentMargin": rounded(margin0, 4), "revenuePerShare": str(rps0),
                     "epsFromRevenue": rounded(rps0 * margin0, 4), "disclosedEps": eps["value"] if eps else None}
            if isinstance(value, Decimal):
                entry.update(margin=rounded(value, 4), marginRange=None)
            else:
                entry.update(margin=None, marginRange=value)
            if ranges["netMargin"]["status"] == "available":
                history_values = [row["value"] for row in ranges["netMargin"]["values"]]
                entry["currentMarginPercentile"] = _percent(inverse_percentile(history_values, entry["currentMargin"]))
                if entry["margin"] is not None:
                    entry["marginPercentile"] = _percent(inverse_percentile(history_values, entry["margin"]))
            out[str(horizon)] = entry
    return out


def _sensitivity(price, base, quartiles, ranges):
    """Move each median assumption one step to p25 / p75; largest return change first."""
    block = base["reason"]["code"] if base["status"] != "available" else _blocked(ranges, ("growth", "pe", "payout"))
    if block is None and number(base["eps0"]) <= 0:
        block = "negative_base_eps"
    if block is not None:
        return unavailable(block)
    eps0, rows = number(base["eps0"]), []
    source = {"growth": quartiles["growth"], "exitPE": quartiles["pe"], "payout": quartiles["payout"]}
    centre = {field: source[field]["p50"] for field in source}
    for horizon in HORIZONS:
        centred = scenario_irr(price, eps0, centre["growth"], centre["exitPE"], centre["payout"], horizon)
        for order, field in enumerate(("growth", "exitPE", "payout")):
            for direction, name in enumerate(("p25", "p75")):
                moved = dict(centre, **{field: source[field][name]})
                value = scenario_irr(price, eps0, moved["growth"], moved["exitPE"], moved["payout"], horizon)
                delta = value - centred if isinstance(value, Decimal) and isinstance(centred, Decimal) else None
                rows.append({"horizon": horizon, "input": field, "from": "p50", "to": name,
                             **_irr_cell(value), "delta": None if delta is None else rounded(delta, 4),
                             "_sort": (horizon, delta is None, -abs(delta) if delta is not None else 0, order, direction)})
    rows.sort(key=lambda row: row["_sort"])
    for row in rows:
        del row["_sort"]
    return {"status": "available", "rows": rows}


def compute(history: dict, price: dict, *, fiscal_prices: list[dict] | None, prices_reason: dict | None = None,
            dividends: dict | None = None) -> dict:
    """Ranges, scenarios, decomposition and the stored reverse blocks."""
    session_date, reference = price["sessionDate"], number(price["value"])
    ranges, quartiles = {}, {}
    for key, build in (("growth", lambda: rng.growth_range(history)),
                       ("pe", lambda: rng.pe_range(history, fiscal_prices, prices_reason)),
                       ("payout", lambda: rng.payout_range(history, dividends)),
                       ("rpsGrowth", lambda: rng.rps_growth_range(history)),
                       ("netMargin", lambda: rng.margin_range(history))):
        ranges[key], quartiles[key] = build()
    base = base_year(history, session_date)
    return {"ranges": ranges, "base": base, "scenarios": _scenario_rows(reference, base, quartiles, ranges),
            "decomposition": decompose(history),
            "reverse": {"breakEvenPE": _break_even_pe(reference, base, quartiles, ranges),
                        "breakEvenMargin": _break_even_margin(history, reference, session_date, quartiles, ranges),
                        "sensitivity": _sensitivity(reference, base, quartiles, ranges)},
            "notices": ["excluded_growth_windows"] if any(ranges[key].get("excluded") for key in ("growth", "rpsGrowth")) else []}


def unavailable_results(code: str, sub_code: str | None = None) -> dict:
    """The same block shapes as `compute`, every one carrying the same reason."""
    block = unavailable(code, sub_code)
    return {"ranges": {name: dict(block) for name in ("growth", "pe", "payout", "rpsGrowth", "netMargin")},
            "base": dict(block),
            "scenarios": [{"label": label, "horizon": horizon, **block}
                          for horizon in HORIZONS for label, _, _ in SCENARIO_PERCENTILES],
            "decomposition": dict(block),
            "reverse": {"breakEvenPE": {str(h): dict(block) for h in HORIZONS},
                        "breakEvenMargin": {str(h): dict(block) for h in HORIZONS}, "sensitivity": dict(block)},
            "notices": []}
