"""The one read-time function (spec §3.6): a stored snapshot seen through a person's criteria.

`project()` never writes. Every consumer (watchlist, report reader, Agent) calls
it, so they all show the same judgement. The judgement belongs to the stored
base scenario only; "my assumptions" produce returns but no judgement. `met` means
the person's own criterion is met by the calculation, nothing more.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .blocks import unavailable
from .decimal_ops import number, rounded
from .returns import ABOVE_RANGE, BELOW_RANGE, NOT_NEEDED, required_exit_pe, required_growth, required_margin, scenario_irr
from .stats import inverse_percentile

SNAPSHOT_OLD_DAYS = 30
HUNDRED = Decimal(100)


def _percent_to_fraction(value) -> Decimal | None:
    return None if value is None else number(value) / HUNDRED


def _base_rows(results: dict) -> dict[int, dict]:
    return {row["horizon"]: row for row in results.get("scenarios", []) if row.get("label") == "base"}


def _verdict(state: str, **detail) -> dict:
    return {"state": state, **detail}


def _return_verdict(results: dict, required: Decimal | None, years: int | None) -> dict:
    if required is None or years is None:
        return _verdict("unknown", reason="criteria_not_set")
    row = _base_rows(results).get(years)
    if row is None or row.get("status") != "available":
        reason = ((row or {}).get("reason") or {}).get("code", "scenario_unavailable")
        return _verdict("unknown", reason=reason, horizon=years)
    if row.get("irrRange") == ABOVE_RANGE:
        # The search stops at 100% a year; a requirement at or below it is met.
        return _verdict("met" if required <= 1 else "unknown", horizon=years, irrRange=ABOVE_RANGE,
                        **({} if required <= 1 else {"reason": "required_return_above_search_range"}))
    if row.get("irrRange") == BELOW_RANGE:
        return _verdict("unmet", horizon=years, irrRange=BELOW_RANGE)
    value = number(row["irr"])
    return _verdict("met" if value >= required else "unmet", horizon=years, irr=row["irr"])


def _margin_verdict(results: dict, price, minimum: Decimal | None) -> dict:
    if minimum is None:
        return _verdict("unknown", reason="criteria_not_set")
    dcf = results.get("dcf") or {}
    if dcf.get("status") != "available":
        return _verdict("unknown", reason=(dcf.get("reason") or {}).get("code", "dcf_unavailable"))
    if dcf.get("marginOfSafetyJudgment") != "eligible":
        return _verdict("unknown", reason="dcf_fallback")
    base = next((row for row in (dcf.get("result") or {}).get("scenarios", []) if row.get("name") == "기준"), None)
    intrinsic = number(base["perShare"]) if base and base.get("perShare") is not None else None
    if intrinsic is None or intrinsic <= 0:
        return _verdict("unknown", reason="non_positive_intrinsic_value")
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        margin = (intrinsic - number(price)) / intrinsic
    return _verdict("met" if margin >= minimum else "unmet", intrinsicValue=rounded(intrinsic, 2), margin=rounded(margin, 4))


def _median(row: dict, field: str) -> Decimal:
    return number(row[field])


def _requirement(results: dict, price, eps0, required: Decimal | None) -> dict:
    """What a person's required return needs from growth, exit PER and net margin (none are forecasts)."""
    if required is None:
        return {"status": "unavailable", "reason": {"code": "criteria_not_set"}}
    base = _base_rows(results)
    out = {"status": "available", "exitPE": {}, "growth": {}, "netMargin": {}}
    growth_values = [row["value"] for row in (results.get("ranges", {}).get("growth") or {}).get("values", [])]
    margin_ranges = results.get("ranges", {}).get("netMargin") or {}
    margin_values = [row["value"] for row in margin_ranges.get("values", [])]
    for years in (5, 10):
        key = str(years)
        row, margin_entry = base.get(years), ((results.get("reverse") or {}).get("breakEvenMargin") or {}).get(key) or {}
        if row is None or row.get("status") != "available" or eps0 is None or eps0 <= 0:
            reason = ((row or {}).get("reason") or {}).get("code", "negative_base_eps" if eps0 is not None and eps0 <= 0 else "scenario_unavailable")
            out["exitPE"][key] = out["growth"][key] = unavailable(reason)
        else:
            growth, pe, payout = _median(row, "g"), _median(row, "exitPE"), _median(row, "payout")
            need_pe = required_exit_pe(price, eps0, growth, payout, years, required)
            out["exitPE"][key] = ({"status": "available", "state": NOT_NEEDED} if need_pe == NOT_NEEDED
                                  else {"status": "available", "state": "needed", "value": rounded(need_pe, 2)})
            need_g = required_growth(price, eps0, pe, payout, years, required)
            if isinstance(need_g, Decimal):
                out["growth"][key] = {"status": "available", "value": rounded(need_g, 4),
                                      "percentile": _percentile(growth_values, rounded(need_g, 4))}
            else:
                out["growth"][key] = {"status": "available", "range": need_g}
        if margin_entry.get("status") != "available" or row is None or row.get("status") != "available":
            out["netMargin"][key] = unavailable(((margin_entry.get("reason") or {}).get("code")) or "scenario_unavailable")
            continue
        ranges = results["ranges"]
        need_m = required_margin(price, margin_entry["revenuePerShare"], ranges["rpsGrowth"]["p50"], margin_entry["currentMargin"],
                                 ranges["pe"]["p50"], ranges["payout"]["p50"], years, required)
        out["netMargin"][key] = ({"status": "available", "value": rounded(need_m, 4), "currentMargin": margin_entry["currentMargin"],
                                  "percentile": _percentile(margin_values, rounded(need_m, 4)) if margin_values else None}
                                 if isinstance(need_m, Decimal) else {"status": "available", "range": need_m})
    return out


def _percentile(values, x):
    if not values:
        return None
    found = inverse_percentile(values, x)
    return found if isinstance(found, str) else rounded(found, 1)


def _my_assumptions(results: dict, price, eps0, override: dict | None, current_snapshot_id: str) -> dict | None:
    if override is None:
        return None
    base = _base_rows(results)
    rows = []
    for years in (5, 10):
        row = base.get(years)
        if row is None or row.get("status") != "available" or eps0 is None or eps0 <= 0:
            rows.append({"horizon": years, **unavailable((row or {}).get("reason", {}).get("code", "scenario_unavailable"))})
            continue
        growth = number(override["growth"]) if override.get("growth") is not None else _median(row, "g")
        pe = number(override["exitPE"]) if override.get("exitPE") is not None else _median(row, "exitPE")
        payout = number(override["payout"]) if override.get("payout") is not None else _median(row, "payout")
        irr = scenario_irr(price, eps0, growth, pe, payout, years)
        rows.append({"horizon": years, "status": "available", "g": rounded(growth, 4), "exitPE": rounded(pe, 2),
                     "payout": rounded(payout, 4),
                     "inherited": {"g": override.get("growth") is None, "exitPE": override.get("exitPE") is None,
                                   "payout": override.get("payout") is None},
                     **({"irr": rounded(irr, 4), "irrRange": None} if isinstance(irr, Decimal) else {"irr": None, "irrRange": irr})})
    return {"overrideId": override["overrideId"], "basedOnSnapshotId": override["basedOnSnapshotId"],
            "basedOnCurrentSnapshot": override["basedOnSnapshotId"] == current_snapshot_id, "rows": rows}


def project(snapshot: dict, criteria: dict | None = None, override: dict | None = None, reviews=(), *, today: dt.date) -> dict:
    """Pure read: judgement, required-return inversions, my assumptions, re-check flags, age."""
    results, inputs = snapshot["results"], snapshot["inputs"]
    price = inputs["price"]["value"]
    eps0 = number(results["base"]["eps0"]) if (results.get("base") or {}).get("status") == "available" else None
    required = _percent_to_fraction(criteria.get("requiredReturn")) if criteria else None
    minimum = _percent_to_fraction(criteria.get("minMarginOfSafety")) if criteria else None
    years = criteria.get("holdingYears") if criteria else None
    age = (today - dt.date.fromisoformat(inputs["asOf"])).days
    notices = (["snapshot_old"] if age > SNAPSHOT_OLD_DAYS else [])
    return {
        "snapshotId": snapshot["snapshotId"], "asOf": inputs["asOf"], "ageDays": age, "notices": notices,
        "criteria": None if criteria is None else {"revisionId": criteria["revisionId"], "holdingYears": years,
                                                    "requiredReturn": criteria.get("requiredReturn"),
                                                    "minMarginOfSafety": criteria.get("minMarginOfSafety")},
        "verdict": {"return": _return_verdict(results, required, years), "marginOfSafety": _margin_verdict(results, price, minimum)},
        "requirement": _requirement(results, price, eps0, required),
        "myAssumptions": _my_assumptions(results, price, eps0, override, snapshot["snapshotId"]),
        "reviewNeeded": [dict(row) for row in reviews],
    }
