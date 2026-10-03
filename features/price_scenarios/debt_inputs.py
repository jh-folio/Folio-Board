"""Same-fiscal-end debt/cash observations, with exact source definitions.

Missing components remain missing. The selected position follows the existing
SEC complete-first ordering; no quarterly or cross-date balance is injected.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from features.company_analysis import sec_companyfacts as sec
from .decimal_ops import number, source_number


def _fact(row, concept, value, end, *, unit, accession, filed, form):
    return {"concept": concept, "value": value, "periodEnd": end, "unit": unit,
            "accession": accession, "filed": filed, "form": form}


def _position(end, basis, complete, components, cash):
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        total = sum((number(row["value"]) for row in components), Decimal(0))
        cash_value = number(cash["value"])
        if total < 0 or cash_value < 0:
            return {"ok": False, "reason": "invalid_debt_balance", "asOf": end}
        return {"ok": True, "asOf": end, "basis": basis, "complete": complete,
                "totalDebt": str(total), "cash": cash["value"], "netDebt": str(total - cash_value),
                "components": {row["concept"]: row["value"] for row in components},
                "cashConcept": cash["concept"], "sources": [*components, cash]}


def sec_debt_inputs(data: dict, history: dict, *, as_of: str, borrowings_definition: dict | None = None) -> dict:
    """Capture all required US-GAAP debt tags at confirmed annual endpoints."""
    dt.date.fromisoformat(as_of)
    taxonomy, concepts, _ = sec.select_taxonomy(data)
    if taxonomy == "us-gaap":
        cash_names, bases = sec.DEBT_POSITION_CASH, sec.DEBT_POSITION_BASES
    elif (taxonomy == "ifrs-full" and borrowings_definition
          and borrowings_definition.get("basis") == "includes_current_maturities_excludes_shortterm"
          and borrowings_definition.get("source") and borrowings_definition.get("accession")):
        # Measured NVS annual debt note: Borrowings includes the current portion
        # of non-current debt, while ShorttermBorrowings is reported separately.
        cash_names = ("CashAndCashEquivalents",)
        bases = (("ifrs_borrowings_plus_shortterm", ("Borrowings", "ShorttermBorrowings"), True),
                 ("ifrs_borrowings_only", ("Borrowings",), False))
    else:
        return {"ok": False, "reason": "debt_taxonomy_unconfirmed", "observations": []}
    ends = {row["period"]["end"] for row in history["rows"] if row["period"].get("start")}
    currency = history["currency"]
    names = set(cash_names) | {name for _, tags, _ in bases for name in tags}
    observations = defaultdict(dict)
    ambiguous = set()
    for name in sorted(names):
        for row in ((concepts.get(name) or {}).get("units") or {}).get(currency, []):
            end, filed = row.get("end"), row.get("filed")
            value = source_number(row.get("val"))
            if (end not in ends or not filed or filed > as_of or end > as_of or value is None
                    or row.get("start") or str(row.get("form", "")).removesuffix("/A") not in {"10-K", "20-F"}):
                continue
            fact = _fact(row, name, value, end, unit=currency, accession=row.get("accn", ""), filed=filed, form=row["form"])
            prior = observations[end].get(name)
            if prior is None or (filed, fact["accession"]) > (prior["filed"], prior["accession"]):
                observations[end][name] = fact
                ambiguous.discard((end, name))
            elif (filed, fact["accession"]) == (prior["filed"], prior["accession"]) and fact["value"] != prior["value"]:
                ambiguous.add((end, name))
    positions = []
    for end, facts in sorted(observations.items(), reverse=True):
        if any(period == end for period, _ in ambiguous):
            continue
        cash = next((facts[name] for name in cash_names if name in facts), None)
        if not cash:
            continue
        for basis, names, complete in bases:
            if all(name in facts for name in names):
                positions.append(_position(end, basis, complete, [facts[name] for name in names], cash))
    valid = [row for row in positions if row["ok"]]
    chosen = next((row for complete in (True, False) for row in valid if row["complete"] == complete), None)
    # Match net_debt_from's annual-end guard: a very old complete position
    # cannot override the latest reported long-term balance. Use a known
    # same-date partial position instead; never add missing balances as zero.
    annual_end = max((row["period"]["end"] for row in history["rows"] if row.get("metric") == "Long-Term Debt"), default="")
    if chosen and chosen["asOf"] < annual_end:
        chosen = next((row for row in valid if row["asOf"] >= annual_end), None)
    if chosen and taxonomy == "ifrs-full":
        chosen["borrowingsDefinition"] = dict(borrowings_definition)
    return {"ok": chosen is not None, "reason": None if chosen else "same_period_debt_unavailable",
            "position": chosen, "ambiguousPeriodEnds": sorted({end for end, _ in ambiguous}),
            "observations": [row for end in sorted(observations) for _, row in sorted(observations[end].items())]}


# Exact standard account IDs and measured whole names for nonstandard rows.
# No finance costs, financial liabilities or cash-flow borrowings enter here.
_DART_BUCKETS = {
    "long_total": {"ifrs-full_LongtermBorrowings", "ifrs_LongtermBorrowings"},
    "long_loans": {"ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "ifrs_NoncurrentPortionOfNoncurrentLoansReceived"},
    "long_bonds": {"ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "ifrs_NoncurrentPortionOfNoncurrentBondsIssued"},
    "short": {"ifrs-full_ShorttermBorrowings", "ifrs_ShorttermBorrowings"},
    "current_long": {"ifrs-full_CurrentPortionOfNoncurrentLoansReceived", "ifrs_CurrentPortionOfNoncurrentLoansReceived"},
    "current_bonds": {"ifrs-full_CurrentPortionOfNoncurrentBondsIssued", "ifrs_CurrentPortionOfNoncurrentBondsIssued",
                      "dart_CurrentPortionOfConvertibleBonds"},
    "cash": {"ifrs-full_CashAndCashEquivalents", "ifrs_CashAndCashEquivalents"},
}
_DART_NAMES = {"단기차입금": "short", "유동성장기차입금": "current_long", "비유동 전환사채": "long_bonds"}


def dart_debt_inputs(batches: list[dict], history: dict, *, as_of: str) -> dict:
    dt.date.fromisoformat(as_of)
    ends = {row["period"]["end"] for row in history["rows"]}
    observations = defaultdict(dict)
    ambiguous = set()
    for batch in batches:
        if batch.get("basis") != history.get("basis"):
            continue
        finish = dt.date.fromisoformat(batch["periodEnd"])
        for row in batch.get("rows", []):
            if row.get("sj_div") != "BS" or row.get("currency") != "KRW" or row.get("reprt_code", "11011") != "11011":
                continue
            account = row.get("account_id")
            bucket = next((bucket for bucket, names in _DART_BUCKETS.items() if account in names), None)
            if account == "-표준계정코드 미사용-":
                bucket = _DART_NAMES.get(row.get("account_nm"))
            if not bucket:
                continue
            accession = str(row.get("rcept_no") or "")
            filed = f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}"
            try:
                dt.date.fromisoformat(filed)
            except ValueError:
                continue
            if filed > as_of:
                continue
            concept = f"{account}:{row.get('account_nm')}"
            for offset, column in enumerate(("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")):
                try:
                    end = finish.replace(year=finish.year - offset).isoformat()
                except ValueError:  # Leap-day comparative cannot be guessed.
                    continue
                value = source_number(row.get(column))
                if end not in ends or end > as_of or value is None:
                    continue
                fact = _fact(row, concept, value, end, unit="KRW", accession=accession, filed=filed, form="DART_11011")
                fact.update(bucket=bucket, amountField=column, accountId=account, accountName=row.get("account_nm"))
                key = (bucket, concept)
                prior = observations[end].get(key)
                if prior and prior["accession"] == accession and prior["value"] != value:
                    ambiguous.add(end)
                elif prior is None or accession > prior["accession"]:
                    observations[end][key] = fact
    positions = []
    for end, facts in sorted(observations.items(), reverse=True):
        by_bucket = defaultdict(list)
        for fact in facts.values():
            by_bucket[fact["bucket"]].append(fact)
        if end in ambiguous or any(len(rows) > 1 for rows in by_bucket.values()) or not by_bucket["cash"]:
            continue
        if by_bucket["long_total"]:
            long = by_bucket["long_total"]
        else:
            long = by_bucket["long_loans"] + by_bucket["long_bonds"]
        if not long and not by_bucket["short"] and not by_bucket["current_bonds"]:
            continue  # No debt account != debt-free.
        components = long + by_bucket["short"] + by_bucket["current_long"] + by_bucket["current_bonds"]
        complete = bool(long and by_bucket["short"])
        positions.append(_position(end, "dart_same_period_accounts", complete, components, by_bucket["cash"][0]))
    valid = [row for row in positions if row["ok"]]
    chosen = next((row for complete in (True, False) for row in valid if row["complete"] == complete), None)
    return {"ok": chosen is not None, "reason": None if chosen else "same_period_debt_unavailable", "position": chosen,
            "ambiguousPeriodEnds": sorted(ambiguous),
            "observations": [row for end in sorted(observations) for _, row in sorted(observations[end].items())]}
