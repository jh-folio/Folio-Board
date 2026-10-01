"""Share-event reconciliation and adjustment. Pure, replayable Decimal inputs."""
from __future__ import annotations

from copy import deepcopy
import datetime as dt
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from .decimal_ops import number

EVENT_KINDS = {"split", "reverse_split", "bonus_issue", "stock_dividend", "ads_ratio_change", "unspecified"}
PER_SHARE = {"EPS Diluted", "DPS"}


def _product(events):
    value = Decimal(1)
    for event in events:
        ratio = number(event["ratio"])
        if ratio <= 0:
            raise ValueError("invalid_event_ratio")
        value *= ratio
    return value


def merge_events(provider: list[dict], official: list[dict]) -> dict:
    """Only unique, date/ratio-compatible observations may be merged once."""
    def validate(event):
        dt.date.fromisoformat(event["eventDate"])
        if number(event["ratio"]) <= 0 or event["kind"] not in EVENT_KINDS:
            raise ValueError("invalid_share_event")
    try:
        for event in provider + official:
            validate(event)
    except (ValueError, KeyError, TypeError):
        return {"state": "unknown", "reason": "invalid_share_event", "events": []}
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        used, merged = set(), []
        for event in official:
            close = []
            for index, supplied in enumerate(provider):
                days = abs((dt.date.fromisoformat(event["eventDate"]) - dt.date.fromisoformat(supplied["eventDate"])).days)
                same_ratio = abs(number(supplied["ratio"]) / number(event["ratio"]) - 1) <= Decimal("0.01")
                if days <= 10:
                    if not same_ratio or (event["kind"] != "unspecified" and supplied["kind"] not in {"unspecified", event["kind"]}):
                        return {"state": "unknown", "reason": "conflicting_event_sources", "events": []}
                    close.append(index)
                elif days <= 60 and same_ratio:
                    return {"state": "unknown", "reason": "ambiguous_event_date", "events": []}
            if len(close) > 1 or any(index in used for index in close):
                return {"state": "unknown", "reason": "ambiguous_event_match", "events": []}
            row = deepcopy(event)
            if close:
                index = close[0]
                used.add(index)
                row["sources"] = row.get("sources", []) + deepcopy(provider[index].get("sources", []))
            row["providerEvent"] = bool(close)
            merged.append(row)
        merged.extend({**deepcopy(event), "providerEvent": True} for index, event in enumerate(provider) if index not in used)
        # Duplicate observations from one source cannot multiply adjustment.
        dates = [event["eventDate"] for event in merged]
        if len(dates) != len(set(dates)):
            return {"state": "unknown", "reason": "ambiguous_event_match", "events": []}
        return {"state": "merged", "events": sorted(merged, key=lambda event: event["eventDate"])}


def price_check(ratio, before_close, after_close, *, provider_event: bool) -> str:
    try:
        r, before, after = map(number, (ratio, before_close, after_close))
    except ValueError:
        return "unknown"
    if min(r, before, after) <= 0:
        return "unknown"
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        q, threshold = before / after, Decimal("1.15").ln()
        distance_one, distance_ratio = abs(q.ln()), abs((q / r).ln())
        if distance_one <= threshold and distance_ratio > threshold:
            return "reflected"
        if distance_ratio <= threshold and distance_one > threshold:
            return "not_reflected"
        if distance_one <= threshold and distance_ratio <= threshold:
            return "assumed_by_provider_event" if provider_event else "assumed_not_reflected"
        return "unknown"


def event_price_checks(events: list[dict], closes: list[dict], fiscal_prices: list[dict]) -> tuple[list[dict], list[dict]]:
    """Capture the actual adjacent closes used, instead of recomputing later."""
    checked, inputs = [], []
    first = min((row["priceDate"] for row in fiscal_prices), default=None)
    by_date = {row["date"]: row["close"] for row in closes}
    for event in events:
        row = deepcopy(event)
        day = row["eventDate"]
        if first and day < first:
            row["priceCheck"] = "not_needed"
        else:
            before_date = max((date for date in by_date if date < day), default=None)
            before, after = by_date.get(before_date), by_date.get(day)
            inputs.append({"eventDate": day, "beforeDate": before_date, "beforeClose": before,
                           "afterDate": day if after is not None else None, "afterClose": after})
            row["priceCheck"] = price_check(row["ratio"], before, after, provider_event=row.get("providerEvent", False))
        checked.append(row)
    return checked, inputs


def reconcile_korean_shares(previous: dict, current: dict, events: list[dict], changes: list[dict]) -> dict:
    """DART common ending shares; dated deltas and both cumulative-decrease units.

    `decreaseCumulative` is profit cancellations plus redemptions, not the
    cumulative column containing par splits. Event membership uses shareDate.
    """
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        start, end = previous["periodEnd"], current["periodEnd"]
        if dt.date.fromisoformat(start) >= dt.date.fromisoformat(end):
            raise ValueError("invalid_share_interval")
        ns, ne = number(previous["shares"]), number(current["shares"])
        interval = [event for event in events if start < event.get("shareDate", event["eventDate"]) <= end]
        p = _product(interval)
        delta = Decimal(0)
        for change in changes:
            if not start < change["date"] <= end:
                continue
            after = [event for event in interval if event.get("shareDate", event["eventDate"]) > change["date"]]
            delta += number(change["delta"]) * _product(after)
        decrease = number(current["decreaseCumulative"]) - number(previous["decreaseCumulative"])
        if ns <= 0 or ne <= 0:
            return {"state": "unknown", "reason": "invalid_ending_shares"}
        ua, ub = (ne - delta + decrease) / ns, (ne - delta + decrease * p) / ns
        if min(ua, ub) <= 0:
            return {"state": "unknown", "reason": "invalid_share_residual"}
        low, high = min(ua, ub), max(ua, ub)
        rho = Decimal(0) if low <= p <= high else min(abs((ua / p).ln()), abs((ub / p).ln()))
        return {"state": "matched" if rho <= Decimal("1.05").ln() else "unknown",
                "reason": None if rho <= Decimal("1.05").ln() else "unexplained_share_change",
                "eventProduct": str(p), "datedDeltaAdjusted": str(delta), "decrease": str(decrease),
                "unitInterval": [str(low), str(high)], "residual": str(rho)}


def adjust_history(history: dict, events: list[dict], *, session_date: str, state: str, ads_ratio: str | None = None) -> dict:
    """Apply events after each filing once, then convert verified ADS units."""
    if state not in {"present", "none_confirmed"}:
        raise ValueError("share_event_unknown")
    dt.date.fromisoformat(session_date)
    result = deepcopy(history)
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        ads = number(ads_ratio) if ads_ratio is not None else Decimal(1)
        if ads <= 0:
            raise ValueError("invalid_ads_ratio")
        for row in result["rows"]:
            if row["metric"] not in PER_SHARE | {"Shares Diluted"}:
                continue
            chosen = [event for event in events if row["filed"] < event["eventDate"] <= session_date and event["kind"] != "ads_ratio_change"]
            factor, value = _product(chosen), number(row["value"])
            row["rawValue"] = row["value"]
            row["value"] = str(value * factor / ads if row["metric"] == "Shares Diluted" else value / factor * ads)
            row["adjustment"] = {"eventProduct": str(factor), "adsRatio": str(ads), "events": [event["eventDate"] for event in chosen]}
    return result


def adjust_fiscal_prices(prices: list[dict], events: list[dict]) -> list[dict]:
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        result = deepcopy(prices)
        for row in result:
            relevant = [event for event in events if row["priceDate"] < event["eventDate"]]
            if any(event["priceCheck"] == "unknown" for event in relevant):
                raise ValueError("price_event_unverified")
            factor = _product([event for event in relevant if event["priceCheck"] in {"not_reflected", "assumed_not_reflected"}])
            row.update(rawClose=row["close"], close=str(number(row["close"]) / factor), eventProduct=str(factor))
        return result
