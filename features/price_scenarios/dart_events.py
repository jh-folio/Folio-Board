"""Measured DART bonus-decision and dated equity-change fields.

No broad date/text guesses. Unrecognized changes or absent source fields keep
the input unconfirmed. Price effectiveness and share-count membership differ.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .decimal_ops import number, source_number


def dart_date(value) -> str | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})\s*일?", text)
    if not match:
        return None
    try:
        return dt.date(*(int(part) for part in match.groups())).isoformat()
    except ValueError:
        return None


def bonus_decisions(packet: dict, *, corp_code: str, trading_dates: list[str], as_of: str) -> dict:
    """fricDecsn ratios are *new shares per old share*, not split multipliers.

    The measured API has no ex-date. Follow the frozen fallback: trading day
    immediately before the record date. The scheduled listing date owns
    shareDate; its scheduled nature remains explicit in the source basis.
    """
    dt.date.fromisoformat(as_of)
    if packet.get("status") not in {"000", "013"}:
        return {"state": "unknown", "reason": "bonus_decision_source_unavailable", "events": []}
    if packet.get("status") == "013":
        return {"state": "received", "events": [], "reason": None}  # Only this event class was queried.
    events, seen = [], set()
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for row in packet.get("list", []):
            accession = str(row.get("rcept_no") or "")
            try:
                filed = dt.date.fromisoformat(f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}").isoformat()
            except ValueError:
                return {"state": "unknown", "reason": "invalid_decision_accession", "events": []}
            if filed > as_of:
                continue
            ratio_raw = source_number(row.get("nstk_ascnt_ps_ostk"))
            record, listing = dart_date(row.get("nstk_asstd")), dart_date(row.get("nstk_lstprd"))
            ex_date = max((day for day in trading_dates if record and day < record), default=None)
            coverage_end = max(trading_dates, default="")
            if (row.get("corp_code") != corp_code or ratio_raw is None or number(ratio_raw) <= 0
                    or not record or not listing or not ex_date or listing < record or ex_date < filed
                    or coverage_end < min(record, as_of)):
                return {"state": "unknown", "reason": "bonus_decision_fields_unconfirmed", "events": []}
            if ex_date > as_of:
                continue
            if record in seen:
                return {"state": "unknown", "reason": "ambiguous_bonus_revision", "events": []}
            seen.add(record)
            events.append({"kind": "bonus_issue", "eventDate": ex_date, "shareDate": listing,
                           "ratio": str(Decimal(1) + number(ratio_raw)), "exDateBasis": "record_date_minus_1",
                           "shareDateBasis": "scheduled_listing_date", "sources": [{
                               "provider": "dart_fricDecsn", "accession": accession, "corpCode": corp_code,
                               "filed": filed, "recordDate": record, "scheduledListingDate": listing,
                               "newSharesPerOldShare": ratio_raw, "ratioField": "nstk_ascnt_ps_ostk"}]})
    return {"state": "received", "reason": None, "events": sorted(events, key=lambda event: event["eventDate"])}


def dated_share_changes(packet: dict, *, corp_code: str, as_of: str) -> dict:
    """One annual irdsSttus ledger, not a concatenation of repeated annual lists.

    Bonus/split/dividend rows belong to the event ledger and are not E_i.
    A fully blank placeholder is explicit source evidence; status 013 alone
    still does not prove that the complete equity-change ledger is empty.
    """
    if packet.get("status") != "000" or not packet.get("list"):
        return {"state": "unknown", "reason": "share_change_source_unavailable", "changes": []}
    dt.date.fromisoformat(as_of)
    changes, seen = [], set()
    placeholders = 0
    for row in packet["list"]:
        if row.get("corp_code") != corp_code:
            return {"state": "unknown", "reason": "share_change_identity_mismatch", "changes": []}
        date, kind, security, raw = (row.get(key) for key in
            ("isu_dcrs_de", "isu_dcrs_stle", "isu_dcrs_stock_knd", "isu_dcrs_qy"))
        if all(value == "-" for value in (date, kind, security, raw)):
            placeholders += 1
            continue
        if security != "보통주":
            if security and "우선" in security:
                continue
            return {"state": "unknown", "reason": "share_change_security_unconfirmed", "changes": []}
        if kind in {"무상증자", "주식배당", "주식분할", "주식병합"}:
            continue
        if kind == "-" and dart_date(date) is not None and source_number(raw) is not None and number(source_number(raw)) >= 0:
            continue  # a dated change whose reason cell is blank explains nothing; the residual tolerance decides (spec §2.4)
        sign = (1 if kind and (kind.startswith("유상증자") or kind in
                    {"전환권행사", "신주인수권행사", "주식매수선택권행사"})
                else -1 if kind and kind.startswith("감자") else None)
        day, value = dart_date(date), source_number(raw)
        if sign is None or day is None or value is None or number(value) < 0:
            return {"state": "unknown", "reason": "share_change_fields_unconfirmed", "changes": []}
        if day > as_of:
            continue
        key = (day, kind, value)
        if key in seen:
            return {"state": "unknown", "reason": "ambiguous_share_change", "changes": []}
        seen.add(key)
        changes.append({"date": day, "delta": str(number(value) * sign), "kind": kind,
                        "source": {"provider": "dart_irdsSttus", "accession": row.get("rcept_no"),
                                   "quantity": value, "quantityField": "isu_dcrs_qy"}})
    if placeholders and (changes or len(packet["list"]) != placeholders):
        return {"state": "unknown", "reason": "ambiguous_empty_share_ledger", "changes": []}
    return {"state": "received", "reason": None, "changes": sorted(changes, key=lambda row: row["date"])}
