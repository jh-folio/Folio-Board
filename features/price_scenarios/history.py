"""Ten-year raw financial history, without changing legacy report summaries.

No network, cache, or user-workspace access. Callers must supply the original
packets and explicit DART period ends from a filing/share-count observation.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from decimal import ROUND_HALF_EVEN, localcontext

from features.company_analysis import sec_companyfacts as sec
from .decimal_ops import number, source_number


def _date(value):
    try:
        return dt.date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _shift_months(date: dt.date, months: int) -> dt.date:
    total = date.year * 12 + date.month - 1 + months
    year, month = divmod(total, 12)
    return dt.date(year, month + 1, min(date.day, calendar.monthrange(year, month + 1)[1]))


MIN_ACCOUNTING_PERIOD_DAYS = 60


def _annual_period(start, end) -> bool:
    begin, finish = _date(start), _date(end)
    return bool(begin and finish and _shift_months(finish, -13) <= begin <= _shift_months(finish, -11))


def _precision(value: str) -> int:
    return max(0, -number(value).as_tuple().exponent)


def _limit(rows, exclusions, *, currency, basis, shares_basis, years):
    if not isinstance(years, int) or isinstance(years, bool) or not 1 <= years <= 10:
        raise ValueError("invalid_history_year_limit")
    selected = sorted({r["fiscalYear"] for r in rows}, reverse=True)[:years]
    annual_years = {r["fiscalYear"] for r in rows if r["period"].get("start")}
    rows = [r for r in rows if r["fiscalYear"] in selected]
    rows.sort(key=lambda r: (r["fiscalYear"], r["metric"], r["period"]["end"]))
    # Annual filings also carry quarterly facts. Reject those observations,
    # without labelling their valid full fiscal year a transition year.
    unique_exclusions = { (r["fiscalYear"], r["reason"]): r for r in exclusions
                          if r["reason"] != "non_annual_period" or r["fiscalYear"] not in annual_years }
    return {"rows": rows, "excludedYears": sorted(unique_exclusions.values(), key=lambda r: (r["fiscalYear"], r["reason"])),
            "currency": currency, "basis": basis, "sharesBasis": shares_basis}


def sec_history(data: dict, *, as_of: str | None = None, years=10) -> dict:
    cutoff = _date(as_of) if as_of is not None else None
    if as_of is not None and cutoff is None:
        raise ValueError("invalid_as_of")
    taxonomy, concepts, original_table = sec.select_taxonomy(data)
    table = dict(original_table)
    if taxonomy == "ifrs-full":
        table["Net Income"] = ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"]
        # Measured in the NVS 20-F EPS table: basic weighted shares + dilution.
        table["Shares Diluted"] = ["AdjustedWeightedAverageShares", *table["Shares Diluted"]]
        # NVS annual cash-flow statements use the standard investing-activity
        # PPE purchase tag. PPE additions from the balance note are not cash.
        table["Capital Expenditure"] = [
            "PurchaseOfPropertyPlantAndEquipment",
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            *table["Capital Expenditure"][1:],
        ]
    table["DPS"] = (["DividendsPerShare"] if taxonomy == "ifrs-full" else
                    ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"])
    currency = sec.reporting_currency(concepts) if concepts else ""
    output, exclusions = [], []
    for metric, candidates in table.items():
        unit = "shares" if metric == "Shares Diluted" else currency + "/shares" if metric in {"EPS Diluted", "DPS"} else currency
        by_end = defaultdict(dict)
        for priority, concept in enumerate(candidates):
            for fact in ((concepts.get(concept) or {}).get("units") or {}).get(unit, []):
                if str(fact.get("form", "")).removesuffix("/A") not in {"10-K", "20-F"}:
                    continue
                end, filed = _date(fact.get("end")), _date(fact.get("filed"))
                value = source_number(fact.get("val"))
                if not end or not filed or value is None or (cutoff and (end > cutoff or filed > cutoff)):
                    continue
                instant = metric in sec.POINT_IN_TIME_METRICS or metric == "Short-Term Debt"
                if not instant and not _annual_period(fact.get("start"), fact.get("end")):
                    begin = _date(fact.get("start"))
                    if begin is None or (end - begin).days >= MIN_ACCOUNTING_PERIOD_DAYS:
                        # A fiscal-year change is an accounting period; a one-or-two-day measurement (a post-year-end buyback
                        # fact in an annual filing) is not a fiscal year and must not displace the latest real year.
                        exclusions.append({"fiscalYear": end.year, "reason": "non_annual_period"})
                    continue
                by_end[end.isoformat()].setdefault(priority, []).append((concept, fact, value))
        for end, priorities in sorted(by_end.items()):
            # Tag preference is resolved separately for each period, never globally.
            observations = priorities[min(priorities)]
            observations.sort(key=lambda item: (item[1]["filed"], str(item[1].get("accn", "")), str(item[1].get("start", ""))))
            concept, fact, value = observations[-1]
            prior = []
            for _, old, old_value in observations[:-1]:
                item = {"value": old_value, "filed": old["filed"], "accession": old.get("accn", ""), "form": old["form"]}
                if item not in prior:
                    prior.append(item)
            output.append({"fiscalYear": int(end[:4]), "metric": metric, "value": value,
                           "period": {"start": fact.get("start"), "end": end}, "concept": taxonomy + ":" + concept,
                           "form": fact["form"], "filed": fact["filed"], "accession": fact.get("accn", ""),
                           "unit": unit, "precision": _precision(value), "priorValues": prior})
    # 10-K/20-F can include quarterly balance snapshots and opening balances.
    # Filing form alone does not make an instant a fiscal-year-end observation.
    annual_ends = {row["period"]["end"] for row in output if row["period"].get("start")}
    output = [row for row in output if row["period"].get("start") or row["period"]["end"] in annual_ends]
    return _limit(output, exclusions, currency=currency, basis=taxonomy, shares_basis="diluted_weighted_average", years=years)


_DART_METRICS = {
    "Revenue": ("ifrs-full_Revenue", "ifrs_Revenue"),
    "Operating Income": ("dart_OperatingIncomeLoss",),
    "Net Income": ("ifrs-full_ProfitLossAttributableToOwnersOfParent", "ifrs_ProfitLossAttributableToOwnersOfParent"),
    "EPS Diluted": ("ifrs-full_DilutedEarningsLossPerShare", "ifrs_DilutedEarningsLossPerShare"),
    "Operating Cash Flow": ("ifrs-full_CashFlowsFromUsedInOperatingActivities", "ifrs_CashFlowsFromUsedInOperatingActivities"),
    "Capital Expenditure": ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "ifrs_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "ifrs_PurchaseOfPropertyPlantAndEquipment"),
    "Cash & Equivalents": ("ifrs-full_CashAndCashEquivalents", "ifrs_CashAndCashEquivalents"),
    "Total Assets": ("ifrs-full_Assets", "ifrs_Assets"),
    "Total Liabilities": ("ifrs-full_Liabilities", "ifrs_Liabilities"),
    "Pretax Income": ("ifrs-full_ProfitLossBeforeTax", "ifrs_ProfitLossBeforeTax"),
    "Income Tax": ("ifrs-full_IncomeTaxExpenseContinuingOperations", "ifrs_IncomeTaxExpenseContinuingOperations"),
    "Interest Expense": ("ifrs-full_InterestExpense", "ifrs_InterestExpense"),
    "Dividends Paid": ("ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "ifrs_DividendsPaidClassifiedAsFinancingActivities"),
    "Share Repurchases": ("dart_AcquisitionOfTreasuryShares",),
    "Current Assets": ("ifrs-full_CurrentAssets", "ifrs_CurrentAssets"),
    "Current Liabilities": ("ifrs-full_CurrentLiabilities", "ifrs_CurrentLiabilities"),
}

_DART_INSTANT = {"Cash & Equivalents", "Total Assets", "Total Liabilities", "Current Assets", "Current Liabilities"}


def dart_history(batches: list[dict], *, as_of: str | None = None, years=10) -> dict:
    cutoff = _date(as_of) if as_of is not None else None
    if as_of is not None and cutoff is None:
        raise ValueError("invalid_as_of")
    # A company has one statement basis throughout the packet.
    basis = "CFS" if any(b.get("basis") == "CFS" and b.get("rows") for b in batches) else "OFS"
    metric_table = dict(_DART_METRICS)
    if basis == "OFS":
        metric_table["Net Income"] += ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss")
    candidates, exclusions = defaultdict(list), []
    for batch in batches:
        if batch.get("basis") != basis:
            continue
        finish = _date(batch.get("periodEnd"))
        if finish is None:
            raise ValueError("dart_period_end_requires_source")
        for row in batch.get("rows", []):
            if row.get("currency") != "KRW":
                continue
            if row.get("reprt_code", "11011") != "11011":
                continue
            accession = str(row.get("rcept_no", ""))
            filed = _date(f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}")
            if filed is None or (cutoff and filed > cutoff):
                continue
            detail = str(row.get("account_detail") or "")
            if "우선" in detail:
                continue
            for metric, accounts in metric_table.items():
                account = row.get("account_id")
                if account not in accounts:
                    continue
                for offset, field in enumerate(("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")):
                    value = source_number(row.get(field))
                    end = _shift_months(finish, -12 * offset)
                    if value is None or (cutoff and end > cutoff):
                        continue
                    start = None if metric in _DART_INSTANT else (_shift_months(end, -12) + dt.timedelta(days=1)).isoformat()
                    candidates[(end.isoformat(), metric)].append((accounts.index(account), {
                        "fiscalYear": end.year, "metric": metric, "value": value, "period": {"start": start, "end": end.isoformat()},
                        "concept": account, "form": "사업보고서", "filed": filed.isoformat(), "accession": accession,
                        "unit": "KRW/shares" if metric == "EPS Diluted" else "KRW", "precision": _precision(value),
                        "sourceField": field, "periodEndSource": batch.get("periodEndSource"), "priorValues": [],
                    }))
    output = []
    for _, observations in sorted(candidates.items()):
        # DART contract selects the latest filing, including comparative revisions.
        observations.sort(key=lambda pair: (pair[1]["accession"], -pair[0]))
        chosen = dict(observations[-1][1])
        if any(pair[1]["accession"] == chosen["accession"] and pair[0] == observations[-1][0]
               and pair[1]["value"] != chosen["value"] for pair in observations):
            exclusions.append({"fiscalYear": chosen["fiscalYear"], "reason": "ambiguous_common_share_fact"})
            continue
        for _, previous in observations[:-1]:
            old = {k: previous[k] for k in ("value", "filed", "accession", "form")}
            if old not in chosen["priorValues"]:
                chosen["priorValues"].append(old)
        output.append(chosen)
    by_year = defaultdict(dict)
    for row in output:
        by_year[row["fiscalYear"]][row["metric"]] = row
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        for fiscal_year, metrics in by_year.items():
            profit, eps = metrics.get("Net Income"), metrics.get("EPS Diluted")
            if not profit or not eps or number(eps["value"]) == 0 or profit["period"] != eps["period"]:
                continue
            shares = number(profit["value"]) / number(eps["value"])
            if shares <= 0:
                continue
            output.append({"fiscalYear": fiscal_year, "metric": "Shares Diluted", "value": str(shares), "period": dict(eps["period"]),
                           "concept": "shares_implied_from_eps", "formula": "parent_common_profit/diluted_common_eps",
                           "form": eps["form"], "filed": max(profit["filed"], eps["filed"]), "accession": eps["accession"],
                           "sourceAccessions": [profit["accession"], eps["accession"]], "unit": "shares",
                           "precision": _precision(str(shares)), "priorValues": []})
    return _limit(output, exclusions, currency="KRW" if output else "", basis=basis, shares_basis="shares_implied_from_eps", years=years)


def dart_dividend_history(packets: list[dict], *, as_of: str | None = None, years=10) -> dict:
    """Measured alotMatter common DPS, preserving missing dividends as missing."""
    cutoff = _date(as_of) if as_of is not None else None
    if as_of is not None and cutoff is None:
        raise ValueError("invalid_as_of")
    by_end = defaultdict(list)
    for packet in packets:
        if packet.get("status") != "000":
            continue
        for row in packet.get("list", []):
            if row.get("stock_knd") != "보통주" or row.get("se") != "주당 현금배당금(원)":
                continue
            end = _date(row.get("stlm_dt"))
            accession = str(row.get("rcept_no") or "")
            filed = _date(f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}")
            if not end or not filed or (cutoff and filed > cutoff):
                continue
            for offset, field in enumerate(("thstrm", "frmtrm", "lwfr")):
                value = source_number(row.get(field))
                finish = _shift_months(end, -12 * offset)
                if value is None or (cutoff and finish > cutoff):
                    continue
                by_end[finish].append({"fiscalYear": finish.year, "metric": "DPS", "value": value,
                    "period": {"start": (_shift_months(finish, -12) + dt.timedelta(days=1)).isoformat(), "end": finish.isoformat()},
                    "concept": "alotMatter:common_cash_dividend_per_share", "form": "사업보고서",
                    "filed": filed.isoformat(), "accession": accession, "unit": "KRW/shares", "precision": _precision(value),
                    "sourceField": field, "periodEndSource": "alotMatter:stlm_dt", "priorValues": []})
    rows, excluded = [], []
    for end, candidates in sorted(by_end.items()):
        candidates.sort(key=lambda row: row["accession"])
        selected = candidates[-1]
        if any(row["accession"] == selected["accession"] and row["value"] != selected["value"] for row in candidates):
            excluded.append({"fiscalYear": end.year, "reason": "ambiguous_common_share_fact"})
            continue
        for previous in candidates[:-1]:
            old = {k: previous[k] for k in ("value", "filed", "accession", "form")}
            if old not in selected["priorValues"]:
                selected["priorValues"].append(old)
        rows.append(selected)
    return _limit(rows, excluded, currency="KRW" if rows else "", basis="common_dividend", shares_basis="common_share", years=years)
