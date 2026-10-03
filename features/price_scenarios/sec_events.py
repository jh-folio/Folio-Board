"""Reconcile SEC same-period filing pairs against supplied share events.

Pure source adjudication: an empty provider packet needs financial evidence
before it can become none_confirmed. Ordinary restatements remain history.
"""
from __future__ import annotations

from copy import deepcopy
import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from itertools import combinations

from .decimal_ops import number
from .events import EVENT_KINDS, _product


def _observations(history: dict) -> list[dict]:
    facts = {}
    for row in history.get("rows", []):
        if row["metric"] not in {"EPS Diluted", "Shares Diluted"}:
            continue
        if row.get("derived"):
            continue  # a quotient is never independent filing evidence of a split
        period = (row["period"].get("start"), row["period"]["end"])
        for fact in [*row.get("priorValues", []), row]:
            key = (*period, fact["filed"], fact.get("accession", ""))
            entry = facts.setdefault(key, {"period": dict(row["period"]), "filed": fact["filed"],
                                           "accession": fact.get("accession", "")})
            metric = row["metric"]
            value = number(fact["value"])
            if metric in entry and number(entry[metric]) != value:
                raise ValueError("ambiguous_same_filing_fact")
            entry[metric] = str(value)
    return sorted([row for row in facts.values() if "EPS Diluted" in row and "Shares Diluted" in row],
                  key=lambda row: (row["period"]["end"], row["filed"], row["accession"]))


def reconcile_sec_events(history: dict, events: list[dict], *, source_state: str,
                         session_date: str, security_kind: str,
                         latest_annual_filed: str | None = None) -> dict:
    """Check every same-period filing pair; retain the inputs used for proof.

    `source_state=received` means the event collection itself succeeded, even
    when empty. `latest_annual_filed` is mandatory for ADS identification so
    missing tags in a newer 20-F cannot move its boundary backwards.
    """
    result = {"state": "unknown", "reason": None, "events": deepcopy(events), "filingPairChecks": []}
    if source_state != "received":
        return {**result, "reason": "event_source_unavailable"}
    if security_kind not in {"common_share", "ads"}:
        return {**result, "reason": "listed_security_unknown"}
    try:
        dt.date.fromisoformat(session_date)
        if latest_annual_filed is not None:
            dt.date.fromisoformat(latest_annual_filed)
            if latest_annual_filed > session_date:
                raise ValueError("future_annual_filing")
        for event in events:
            dt.date.fromisoformat(event["eventDate"])
            if (event["eventDate"] > session_date or number(event["ratio"]) <= 0
                    or event["kind"] not in EVENT_KINDS):
                raise ValueError("invalid_share_event")
        if len({event["eventDate"] for event in events}) != len(events):
            raise ValueError("ambiguous_event_match")
        observations = _observations(history)
        if any(row["filed"] > session_date or row["period"]["end"] > session_date
               or number(row["Shares Diluted"]) <= 0 for row in observations):
            raise ValueError("invalid_filing_observation")
    except (ValueError, KeyError, TypeError) as exc:
        return {**result, "reason": str(exc)}
    if not observations:
        return {**result, "reason": "filing_evidence_unavailable"}
    if security_kind == "ads" and latest_annual_filed is None:
        return {**result, "reason": "latest_annual_filing_unavailable"}

    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        covered, spanned = set(), set()
        for old, new in combinations(observations, 2):
            if old["period"] != new["period"]:
                continue
            interval = [event for event in events if old["filed"] < event["eventDate"] <= new["filed"]]
            spanned.update(event["eventDate"] for event in interval)
            ratio = number(new["Shares Diluted"]) / number(old["Shares Diluted"])
            eps_old, eps_new = number(old["EPS Diluted"]), number(new["EPS Diluted"])
            trace = (abs(ratio - 1) > Decimal("0.05") and eps_old != 0
                     and abs(eps_new / eps_old * ratio - 1) <= Decimal("0.01"))
            product = _product(interval)
            matched = trace and abs(product / ratio - 1) <= Decimal("0.01")
            result["filingPairChecks"].append({"before": old, "after": new, "sharesRatio": str(ratio),
                                              "trace": trace, "eventProduct": str(product),
                                              "matched": matched if trace else None,
                                              "eventDates": [event["eventDate"] for event in interval]})
            if trace and not matched:
                result["reason"] = "unmatched_common_share_trace"
                return result
            if matched:
                covered.update(event["eventDate"] for event in interval)
        for event in result["events"]:
            if security_kind == "ads" and event.get("providerEvent"):
                if event["eventDate"] > latest_annual_filed:
                    return {**result, "reason": "ads_event_after_latest_annual"}
                if event["eventDate"] not in covered:
                    event["kind"] = "ads_ratio_change"
            elif (abs(number(event["ratio"]) - 1) > Decimal("0.05")
                  and event["eventDate"] in spanned and event["eventDate"] not in covered):
                return {**result, "reason": "expected_share_trace_missing"}
    result.update(state="present" if events else "none_confirmed", reason=None)
    return result
