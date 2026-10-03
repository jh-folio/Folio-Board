"""Why a new snapshot differs from an earlier one, and which earlier ones need a re-check (spec §4.3).

Pure. Both sides are compared as raw inputs after applying the NEW snapshot's
share-event list to each row by that row's own `filed` date, so a split that is
simply new never reads as a restatement. Differences inside the disclosed
precision are not restatements. This explains differences; it does not attribute
the result to them.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .decimal_ops import canonical, number

PER_SHARE = {"EPS Diluted", "DPS"}
SHARES = "Shares Diluted"
RELATIVE_TOLERANCE = Decimal("0.005")
DCF_ASSUMPTIONS = ("beta", "riskFree", "equityRiskPremium", "terminalGrowth", "projectionYears")
PRICE_KEYS = ("value", "sessionDate", "currency", "provider", "providerSymbol")


def _events(snapshot: dict) -> list[dict]:
    return [event for event in (snapshot["results"].get("shareEvents") or {}).get("events", [])
            if event.get("kind") != "ads_ratio_change"]


def _event_date(event: dict) -> str:
    return event.get("eventDate") or event["date"]


def _factor(row: dict, events: list[dict], session: str) -> Decimal:
    value = Decimal(1)
    for event in events:
        if row["filed"] < _event_date(event) <= session:
            value *= number(event["ratio"])
    return value


def _ads(snapshot: dict) -> Decimal:
    ratio = ((snapshot["inputs"].get("classificationInputs") or {}).get("adsRatio") or {}).get("value")
    return number(ratio) if ratio is not None else Decimal(1)


def _adjusted(row: dict, events: list[dict], session: str, ads: Decimal):
    """(comparable value, resolution of one disclosed unit in those terms)."""
    value, factor = number(row["value"]), _factor(row, events, session)
    half = Decimal("0.5") * Decimal(10) ** -int(row.get("precision", 0))
    if row["metric"] == SHARES:
        return value * factor / ads, half * factor / ads
    if row["metric"] in PER_SHARE:
        return value / factor * ads, half / factor * ads
    return value, half


def _by_key(inputs: dict) -> dict:
    return {(row["metric"], int(row["fiscalYear"])): row for row in inputs["history"]["rows"]}


def _actual_sources(inputs):
    """Compare real issuer facts by scope; a calculated EPS is never a restatement."""
    history = inputs['history']
    candidates = list(history['rows']) + list(history.get('existingSourceRows', []))
    for row in history['rows']:
        candidates.extend(row.get('sourceRows', []))
        validation = row.get('classValidation') or {}
        candidates.extend(validation[k] for k in ('netIncome', 'shares', 'eps') if validation.get(k))
    output = {}
    for row in candidates:
        if row.get('derived') or row.get('fiscalYear') is None or row.get('value') is None:
            continue
        period = row.get('period') or {}
        key = (row['metric'], int(row['fiscalYear']), period.get('start'), period.get('end'),
               row.get('unit'), row.get('scope') or 'company_consolidated', row.get('classBasis'))
        if key not in output or (row.get('filed', ''), row.get('accession', '')) > (output[key].get('filed', ''), output[key].get('accession', '')):
            output[key] = row
    return output


def _lineage(inputs, years):
    return sorted((r['metric'], int(r['fiscalYear']), r.get('derived', ''), r.get('source', 'companyfacts'), r.get('classBasis') or '')
                  for r in inputs['history']['rows'] if int(r['fiscalYear']) in years)


def restated_items(old: dict, new: dict) -> list[dict]:
    """Values for the same metric and fiscal year that really changed between two snapshots."""
    events, session, ads = _events(new), new["inputs"]["asOf"], _ads(new)
    before, after = _actual_sources(old["inputs"]), _actual_sources(new["inputs"])
    out = []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for key in sorted(set(before) & set(after), key=repr):
            if key[0] == "Stock-Based Compensation" and {old["inputs"]["methodVersion"], new["inputs"]["methodVersion"]} == {"price-scenario-3", "price-scenario-4"}:
                continue  # IFRS tag precedence changed, not necessarily the issuer's disclosed value.
            old_value, old_res = _adjusted(before[key], events, session, ads)
            new_value, new_res = _adjusted(after[key], events, session, ads)
            tolerance = max(abs(new_value) * RELATIVE_TOLERANCE, old_res, new_res)
            if abs(old_value - new_value) > tolerance:
                item = {"metric": key[0], "fiscalYear": key[1], "from": str(old_value), "to": str(new_value)}
                if item not in out:
                    out.append(item)
    return out


def _event_keys(snapshot: dict) -> set:
    return {(_event_date(event), str(number(event["ratio"]))) for event in _events(snapshot)}


def change_reasons(previous: dict, new: dict) -> list[dict]:
    """Ordered, deterministic reasons; a method change makes direct comparison unavailable."""
    old_in, new_in = previous["inputs"], new["inputs"]
    from . import SPEC4_REVISION0_SHA256
    def sha(inputs):
        return inputs.get("specSha256") or (SPEC4_REVISION0_SHA256 if inputs["methodVersion"] == "price-scenario-4" else None)
    if (old_in["methodVersion"], old_in["specVersion"], sha(old_in)) != (new_in["methodVersion"], new_in["specVersion"], sha(new_in)):
        return [{"code": "method_changed", "from": old_in["methodVersion"], "to": new_in["methodVersion"],
                 "fromSpecSha256": sha(old_in), "toSpecSha256": sha(new_in)}]
    reasons = []
    if any(old_in["price"].get(key) != new_in["price"].get(key) for key in PRICE_KEYS):
        reasons.append({"code": "price_moved"})
    old_years = {key[1] for key in _by_key(old_in)}
    for year in sorted({key[1] for key in _by_key(new_in)} - old_years):
        reasons.append({"code": "new_fiscal_year", "fiscalYear": year})
    for item in restated_items(previous, new):
        reasons.append({"code": "restated", **item})
    if _lineage(old_in, old_years) != _lineage(new_in, old_years):
        reasons.append({"code": "input_changed", "path": "history"})
    added = _event_keys(new) - _event_keys(previous)
    for date, ratio in sorted(added):
        reasons.append({"code": "share_event_added", "date": date, "ratio": ratio})
    old_dcf, new_dcf = old_in.get("dcfInputs") or {}, new_in.get("dcfInputs") or {}
    for field in DCF_ASSUMPTIONS:
        if canonical(old_dcf.get(field)) != canonical(new_dcf.get(field)):
            reasons.append({"code": "dcf_assumption_changed", "field": field})
    for path in ("identity", "classificationInputs"):
        if canonical(old_in.get(path)) != canonical(new_in.get(path)):
            reasons.append({"code": "input_changed", "path": path})
    old_prices = {row["fiscalYear"]: row for row in old_in.get("fiscalYearPrices", [])}
    if any(canonical(old_prices[row["fiscalYear"]]) != canonical(row)
           for row in new_in.get("fiscalYearPrices", []) if row["fiscalYear"] in old_prices):
        reasons.append({"code": "input_changed", "path": "fiscalYearPrices"})
    old_checks = {row["eventDate"]: row for row in old_in.get("eventPriceChecks", [])}
    if any(canonical(old_checks[row["eventDate"]]) != canonical(row)
           for row in new_in.get("eventPriceChecks", []) if row["eventDate"] in old_checks):
        reasons.append({"code": "input_changed", "path": "eventPriceChecks"})
    if not added and canonical(old_in.get("shareEventSources")) != canonical(new_in.get("shareEventSources")):
        reasons.append({"code": "input_changed", "path": "shareEventSources"})
    return reasons


def review_rows(earlier: list[dict], new: dict) -> list[dict]:
    """One row per earlier snapshot of the instrument that used a value the new one corrects."""
    rows = []
    for snapshot in earlier:
        from . import method_at_least
        same = (snapshot["inputs"]["methodVersion"], snapshot["inputs"]["specVersion"]) == (
            new["inputs"]["methodVersion"], new["inputs"]["specVersion"])
        compatible = all(method_at_least(s["inputs"]["methodVersion"], 3) for s in (snapshot, new))
        if not same and not compatible:
            continue
        for item in restated_items(snapshot, new):
            rows.append({"snapshotId": snapshot["snapshotId"], "reason": "restated", "metric": item["metric"],
                         "fiscalYear": item["fiscalYear"], "detectedBySnapshotId": new["snapshotId"]})
    return rows
