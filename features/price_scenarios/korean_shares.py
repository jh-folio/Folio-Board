"""spec-2 Korean share reconciliation with proven cumulative denominations.

Pure calculation. A proof is a captured official-source observation, never
inferred by trying different units until a residual happens to match.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .decimal_ops import number, source_number
from .events import EVENT_KINDS, _product

COMPONENTS = ("profitCancellation", "redemption")
PROOF_SOURCES = {"dart_report", "issuer_disclosure"}


def _day(value):
    return dt.date.fromisoformat(value)


def _proof(proof, as_of):
    if not isinstance(proof, dict) or proof.get("source") not in PROOF_SOURCES:
        return False
    if any(not isinstance(proof.get(key), str) or not proof[key].strip()
           for key in ("accession", "filed", "locator", "statement")):
        return False
    return _day(proof["filed"]) <= _day(as_of)


def _unknown(reason):
    return {"state": "unknown", "reason": reason}


def dart_observation(packet: dict, *, corp_code: str, as_of: str, unit_bases: dict | None = None) -> dict:
    """Keep official common-count cells, including a missing redemption cell.

    Unit proofs are supplied by the official document reader. An API dash is
    never converted to zero. Only a literal numeric zero carries explicit-zero
    proof without a denomination-specific document note.
    """
    try:
        if (not isinstance(packet, dict) or not isinstance(packet.get("list", []), list)
                or any(not isinstance(row, dict) for row in packet.get("list", []))
                or (unit_bases is not None and not isinstance(unit_bases, dict))):
            return _unknown("invalid_share_count_source")
        if packet.get("status") != "000":
            return _unknown("share_count_source_unavailable")
        rows = [row for row in packet.get("list", []) if row.get("corp_code") == corp_code and row.get("se") == "보통주"]
        if len(rows) != 1:
            return _unknown("share_count_identity_unconfirmed")
        row = rows[0]
        end, accession = row["stlm_dt"], row["rcept_no"]
        filed = f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}"
        if not _day(end) <= _day(as_of) or _day(filed) > _day(as_of):
            return _unknown("future_share_count_source")
        shares = source_number(row.get("istc_totqy"))
        if shares is None or number(shares) <= 0:
            return _unknown("invalid_ending_shares")
        decreases = {}
        for key, field in (("profitCancellation", "profit_incnr"), ("redemption", "rdmstk_repy")):
            value = source_number(row.get(field))
            basis = (unit_bases or {}).get(key) or {}
            if not isinstance(basis, dict):
                return _unknown("invalid_share_count_source")
            unit_date, unit_proof = basis.get("unitDate"), basis.get("unitProof")
            if value is not None and number(value) == 0:
                unit_date = end
                unit_proof = {"source": "dart_report", "accession": accession, "filed": filed,
                              "locator": f"stockTotqySttus[se=보통주].{field}", "statement": "explicit_zero",
                              "sameDayBasis": "post_event"}
            decreases[key] = {"value": value, "rawCell": row.get(field), "unitDate": unit_date, "unitProof": unit_proof}
        return {"state": "received", "observation": {"periodEnd": end, "shares": shares,
                "source": {"provider": "dart_stockTotqySttus", "accession": accession, "filed": filed,
                           "corpCode": corp_code, "locator": "se=보통주; istc_totqy"}, "decreases": decreases}}
    except (ValueError, KeyError, TypeError):
        return _unknown("invalid_share_count_source")


def reconcile(previous: dict, current: dict, events: list[dict], changes: list[dict],
              *, coverage: dict, as_of: str) -> dict:
    """All raw values/proofs/coverage belong to inputs; results exclude hash.

    Same-day cumulative units include/exclude the event according to the
    official pre/post proof. Dated E_i retains the post-event same-day rule.
    """
    if (not all(isinstance(value, dict) for value in (previous, current, coverage))
            or not all(isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
                       for rows in (events, changes))):
        return _unknown("invalid_share_input")
    try:
        with localcontext() as context:
            context.prec, context.rounding = 28, ROUND_HALF_EVEN
            return _reconcile(previous, current, events, changes, coverage, as_of)
    except (ValueError, KeyError, TypeError):
        return _unknown("invalid_share_input")


def _reconcile(previous, current, events, changes, coverage, as_of):
    start, end = previous["periodEnd"], current["periodEnd"]
    if not _day(start) < _day(end) <= _day(as_of):
        return _unknown("invalid_share_interval")
    ns, ne = number(previous["shares"]), number(current["shares"])
    if min(ns, ne) <= 0:
        return _unknown("invalid_ending_shares")
    for observation in (previous, current):
        source = observation.get("source") or {}
        if not isinstance(source, dict) or not all(isinstance(source.get(key), str) and source[key].strip() for key in ("provider", "accession", "locator")):
            return _unknown("share_count_source_unconfirmed")
    if previous.get("restated") or current.get("restated"):
        if (not previous.get("revisionBasis") or previous.get("revisionBasis") != current.get("revisionBasis")
                or not all(_proof(row.get("revisionProof"), as_of) for row in (previous, current))):
            return _unknown("cumulative_revision_unconfirmed")

    ledger, seen = [], set()
    for event in events:
        date = event.get("shareDate", event["eventDate"])
        _day(date)
        if event["kind"] not in EVENT_KINDS or number(event["ratio"]) <= 0:
            return _unknown("invalid_share_event")
        key = (event["eventDate"], date, event["kind"], event["ratio"])
        if key in seen:
            return _unknown("ambiguous_share_event")
        seen.add(key)
        if event["kind"] != "ads_ratio_change":
            ledger.append({**event, "shareDate": date})
    # Stable source order cannot change Decimal multiplication/rounding.
    ledger.sort(key=lambda row: (row["shareDate"], row["eventDate"], row["kind"], row["ratio"]))
    unit_dates, converted = [start], []
    totals = {"previous": {}, "current": {}}
    for side, observation in (("previous", previous), ("current", current)):
        for component in COMPONENTS:
            decreases = observation.get("decreases") or {}
            if not isinstance(decreases, dict):
                return _unknown("cumulative_unit_unconfirmed")
            entry = decreases.get(component) or {}
            if not isinstance(entry, dict) or entry.get("value") is None or not _proof(entry.get("unitProof"), as_of):
                return _unknown("cumulative_unit_unconfirmed")
            raw = number(entry["value"])
            if entry["unitProof"]["statement"] == "explicit_zero" and raw != 0:
                return _unknown("cumulative_unit_unconfirmed")
            unit_date = entry.get("unitDate")
            if raw < 0 or not unit_date or _day(unit_date) > _day(observation["periodEnd"]):
                return _unknown("cumulative_unit_unconfirmed")
            unit_dates.append(unit_date)
            same_day = [event for event in ledger if event["shareDate"] == unit_date]
            phase = entry["unitProof"].get("sameDayBasis")
            if same_day and phase not in {"pre_event", "post_event"}:
                return _unknown("cumulative_unit_unconfirmed")
            chosen = [event for event in ledger if unit_date < event["shareDate"] <= end
                      or (event["shareDate"] == unit_date <= end and phase == "pre_event")]
            factor = _product(chosen)
            totals[side][component] = raw * factor
            converted.append({"side": side, "component": component, "rawValue": entry["value"],
                              "unitDate": unit_date, "factor": str(factor), "valueEnd": str(raw * factor)})
    if (coverage.get("state") != "confirmed" or _day(coverage["start"]) > _day(min(unit_dates))
            or not _day(end) <= _day(coverage["end"]) <= _day(as_of)):
        return _unknown("event_coverage_unconfirmed")
    interval = [event for event in ledger if start < event["shareDate"] <= end]
    p = _product(interval)
    delta = Decimal(0)
    for change in sorted(changes, key=lambda row: (row["date"], str(row["delta"]))):
        _day(change["date"])
        if not start < change["date"] <= end:
            continue
        if any(event["shareDate"] == change["date"] for event in interval) and change.get("sameDayBasis") != "post_event":
            return _unknown("dated_change_unit_unconfirmed")
        after = [event for event in interval if event["shareDate"] > change["date"]]
        delta += number(change["delta"]) * _product(after)
    decreases = {key: totals["current"][key] - totals["previous"][key] for key in COMPONENTS}
    if any(value < 0 for value in decreases.values()):
        return _unknown("cumulative_decrease_unconfirmed")
    decrease = sum(decreases.values(), Decimal(0))
    numerator, denominator = ne - delta + decrease, ns * p
    if min(numerator, denominator) <= 0:
        return _unknown("invalid_share_residual")
    rho = abs((numerator / denominator).ln())
    matched = rho <= Decimal("1.05").ln()
    return {"state": "matched" if matched else "unknown",
            "reason": None if matched else "unexplained_share_change", "eventProduct": str(p),
            "datedDeltaAdjusted": str(delta), "decreaseEnd": str(decrease),
            "decreasesEnd": {key: str(value) for key, value in decreases.items()},
            "unitConversions": converted, "residual": str(rho)}
