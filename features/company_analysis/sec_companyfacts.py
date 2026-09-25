#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import urllib.request
from pathlib import Path

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

METRIC_CANDIDATES = {
    "Revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "Gross Profit": ["GrossProfit"],
    "Operating Income": ["OperatingIncomeLoss"],
    "Net Income": ["NetIncomeLoss", "ProfitLoss"],
    "EPS Diluted": ["EarningsPerShareDiluted"],
    "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "CashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesNetOfAcquisitionsAndDispositions"],
    "Capital Expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets", "PaymentsToAcquirePropertyPlantAndEquipmentIntangibleAssetsAndOtherAssets", "CapitalExpenditures", "CapitalExpenditure", "PaymentsForCapitalImprovements"],
    "Cash & Equivalents": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "Total Assets": ["Assets"],
    "Total Liabilities": ["Liabilities"],
    "Long-Term Debt": ["LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"],
    # 장기부채만 보면 유동성 차입이 많은 회사의 부채가 통째로 사라진다. 순부채는
    # 장기+단기-현금이다.
    "Short-Term Debt": ["ShortTermBorrowings", "LongTermDebtCurrent", "DebtCurrent", "OtherShortTermBorrowings"],
    "Current Assets": ["AssetsCurrent"],
    "Current Liabilities": ["LiabilitiesCurrent"],
    "Inventory": ["InventoryNet"],
    "Accounts Receivable": ["AccountsReceivableNetCurrent", "AccountsReceivableNet"],
    "Accounts Payable": ["AccountsPayableCurrent", "AccountsPayable"],
    "Shares Diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfShareDiluted"],
    "EBITDA": ["EarningsBeforeInterestTaxesDepreciationAndAmortization", "EarningsBeforeInterestTaxesDepreciationAmortization"],
    "Depreciation & Amortization": ["DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationExpense", "DepreciationAndAmortization"],
    "Pretax Income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"],
    "Income Tax": ["IncomeTaxExpenseBenefit"],
    # 총이자비용 계열만 둔다. 태그 이름은 대소문자까지 같아야 잡힌다 — 예전 후보
    # `InterestExpenseNonOperating`은 실제 태그(`…Nonoperating`)와 달라 한 번도 잡히지
    # 않았고, HWM은 2023년 `InterestExpense`가 최신 값으로 남았다(실측 2026-09-25).
    # `InterestAndDebtExpense`는 차입 관련 비용을 포함한 총액이다. 순이자
    # (`InterestIncomeExpense…Net`)는 이자수익을 뺀 다른 정의라 섞지 않는다.
    "Interest Expense": ["InterestExpenseNonoperating", "InterestExpense", "InterestAndDebtExpense"],
    "Share Repurchases": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
    # 자사주 매입의 **질**은 금액만으로 보이지 않는다. 주식보상이 매입을 얼마나
    # 상쇄하는지, 주식 수가 실제로 줄었는지가 함께 있어야 판단이 된다.
    "Stock-Based Compensation": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "Shares Repurchased": ["TreasuryStockSharesAcquired"],
    # `PaymentsOfOrdinaryDividends`는 보통주 배당 지급의 현재 태그다. 없으면 2015년까지만
    # 있는 옛 태그가 최신 배당으로 쓰였다(HWM 실측: $223M(2015) vs 실제 $181M(2025)).
    "Dividends Paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends"],
}

# 순차입금은 **한 기준일의 잔액**이다. 후보 태그를 섞어 가장 최근 값을 각각 고르면
# 장기부채는 연말, 단기차입은 3년 전, 현금은 분기말이 되어 어느 날의 재무 상태도 아니게
# 된다. 같은 날짜에 모두 있는 조합만 쓰고, 위에서부터 정의가 넓은 순서로 고른다.
# `LongTermDebt`는 유동성 장기부채를 포함한 값이라 `LongTermDebtCurrent`와 더하지 않는다.
DEBT_POSITION_BASES = (
    ("total_debt", ("DebtLongtermAndShorttermCombinedAmount",), True),
    ("noncurrent_plus_current", ("LongTermDebtNoncurrent", "DebtCurrent"), True),
    ("noncurrent_current_short", ("LongTermDebtNoncurrent", "LongTermDebtCurrent", "ShortTermBorrowings"), True),
    ("long_term_plus_short", ("LongTermDebt", "ShortTermBorrowings"), True),
    # 단기차입이 그 날짜에 보고되지 않았다. 0으로 채우지 않고 불완전하다고 표시한다.
    ("noncurrent_plus_current_ltd", ("LongTermDebtNoncurrent", "LongTermDebtCurrent"), False),
    ("long_term_only", ("LongTermDebt",), False),
    ("long_term_and_leases_only", ("LongTermDebtAndFinanceLeaseObligations",), False),
)
# 현금은 제한성 현금을 뺀 값을 먼저 쓴다. 포함 값만 있으면 그 사실을 함께 남긴다.
DEBT_POSITION_CASH = ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")

# IFRS concept 후보. us-gaap과 이름 체계가 달라 기존 표를 재사용할 수 없다.
# 실측(2026-08-06, SAP·도요타 companyfacts)으로 확인한 이름만 넣는다.
IFRS_METRIC_CANDIDATES = {
    "Revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "Gross Profit": ["GrossProfit"],
    "Operating Income": ["ProfitLossFromOperatingActivities"],
    "Net Income": ["ProfitLoss", "ProfitLossAttributableToOwnersOfParent"],
    "EPS Diluted": ["DilutedEarningsLossPerShare"],
    "Operating Cash Flow": [
        "CashFlowsFromUsedInOperatingActivities",
        "CashFlowsFromUsedInOperatingActivitiesContinuingOperations",
    ],
    "Capital Expenditure": [
        "PurchaseOfPropertyPlantAndEquipment",
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNonFinancialAssets",
    ],
    "Cash & Equivalents": ["CashAndCashEquivalents"],
    "Total Assets": ["Assets"],
    "Total Liabilities": ["Liabilities"],
    "Long-Term Debt": ["NoncurrentPortionOfNoncurrentBorrowings", "Borrowings"],
    "Short-Term Debt": ["CurrentPortionOfNoncurrentBorrowings", "ShorttermBorrowings"],
    "Current Assets": ["CurrentAssets"],
    "Current Liabilities": ["CurrentLiabilities"],
    "Inventory": ["Inventories"],
    "Accounts Receivable": ["TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"],
    "Accounts Payable": ["TradeAndOtherCurrentPayables", "CurrentTradePayables"],
    "Shares Diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "Stock-Based Compensation": ["ShareBasedPayments", "ExpenseFromShareBasedPaymentTransactions"],
    "Depreciation & Amortization": ["DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"],
    "Pretax Income": ["ProfitLossBeforeTax"],
    "Income Tax": ["IncomeTaxExpenseContinuingOperations"],
    "Interest Expense": ["InterestExpense", "FinanceCosts"],
    "Dividends Paid": ["DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid"],
    "Equity": ["Equity"],
}
# 연간 보고서 form. 20-F는 외국 민간 발행인의 연차보고서이고 10-K와 같은 자리를 차지한다.
ANNUAL_FORMS = ("10-K", "20-F")
QUARTERLY_FORMS = ("10-Q",)

POINT_IN_TIME_METRICS = {"Cash & Equivalents", "Total Assets", "Total Liabilities", "Long-Term Debt", "Current Assets", "Current Liabilities", "Inventory", "Accounts Receivable", "Accounts Payable", "Equity"}
PER_SHARE_METRICS = {"EPS Diluted"}
SHARE_COUNT_METRICS = {"Shares Diluted"}


def normalize_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper().replace(".", "-")


def normalize_cik(cik: str | int) -> str:
    digits = re.sub(r"\D", "", str(cik or ""))
    return digits.zfill(10) if digits else ""


def sec_user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT", "MarketResearchArchive/0.1 contact@example.com").strip()


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_json(url: str, cache_path: Path, ttl_hours: int = 24):
    cached = _read_json(cache_path, None)
    if cached and cached.get("fetchedAt") and cached.get("data") is not None:
        try:
            fetched = dt.datetime.fromisoformat(cached["fetchedAt"])
            if dt.datetime.now(dt.timezone.utc) - fetched < dt.timedelta(hours=ttl_hours):
                return cached.get("data"), cached.get("error", "")
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=int(os.environ.get("SEC_TIMEOUT_SECONDS", "30"))) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
        _write_json(cache_path, {"fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "data": data, "error": ""})
        return data, ""
    except Exception:
        if cached and cached.get("data"):
            return cached.get("data"), "using cached SEC data after fetch error"
        _write_json(cache_path, {"fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "data": None, "error": "SEC request failed"})
        return None, "SEC request failed"


def load_ticker_cik_map(cache_dir: Path) -> dict[str, str]:
    data, _ = fetch_json(SEC_TICKERS_URL, cache_dir / "company_tickers.json", ttl_hours=24 * 7)
    out = {}
    if isinstance(data, dict):
        rows = data.values()
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    for row in rows:
        ticker = normalize_ticker(row.get("ticker", ""))
        cik = normalize_cik(row.get("cik_str", ""))
        if ticker and cik:
            out[ticker] = cik
    return out


def resolve_cik(company: dict, cache_dir: Path) -> str:
    cik = normalize_cik(company.get("cik", ""))
    if cik:
        return cik
    ticker = normalize_ticker(company.get("ticker", ""))
    if not ticker or company.get("market") == "KR" or re.fullmatch(r"\d{6}", ticker):
        return ""
    return load_ticker_cik_map(cache_dir).get(ticker, "")


def reporting_currency(concepts: dict) -> str:
    """The currency this filer actually reports in, by weight of evidence.

    A 20-F filer reports in its own currency — ASML in EUR, Toyota in JPY —
    and some also publish a handful of USD convenience figures. Preferring USD
    would take those few rows for the metrics that have them and the local
    currency elsewhere, producing one table quietly mixing two currencies.
    """
    totals: dict[str, int] = {}
    for meta in concepts.values():
        for unit, rows in ((meta or {}).get("units") or {}).items():
            if unit in {"shares", "Shares", "pure"} or "/" in unit:
                continue
            totals[unit] = totals.get(unit, 0) + len(rows)
    if not totals:
        return ""
    return max(totals.items(), key=lambda row: (row[1], row[0]))[0]


def _unit_rows(units: dict, metric: str, currency: str) -> list[dict]:
    """Rows for one metric in the filer's reporting currency, or nothing."""
    if metric in SHARE_COUNT_METRICS:
        return units.get("shares") or units.get("Shares") or []
    if metric in PER_SHARE_METRICS:
        # 주당 단위는 `EUR/shares` 형태다. 통화가 같은 것만 받는다.
        return units.get(f"{currency}/shares") or []
    return units.get(currency) or []


def _facts_for_metric(concepts: dict, metric: str, *, currency: str = "USD", table=None) -> tuple[str, list[dict]]:
    candidates = []
    point_in_time = metric in POINT_IN_TIME_METRICS
    table = table if table is not None else METRIC_CANDIDATES
    for concept in table.get(metric, []):
        units = (concepts.get(concept) or {}).get("units", {})
        facts = _unit_rows(units, metric, currency)
        if not facts:
            continue
        annual = _best_rows(facts, ANNUAL_FORMS, point_in_time)
        quarterly = _best_rows(facts, QUARTERLY_FORMS, point_in_time)
        latest_end = max([r.get("end", "") for r in annual + quarterly] or [""])
        candidates.append((latest_end, len(annual), len(quarterly), concept, facts))
    if candidates:
        candidates.sort(reverse=True)
        _, _, _, concept, facts = candidates[0]
        return concept, facts
    # 신고 통화로 된 행이 없으면 결측으로 남긴다. 다른 통화 행을 끌어오면
    # 한 표 안에서 통화가 섞이고, 그 사실이 어디에도 드러나지 않는다.
    return "", []


def _duration_days(row: dict) -> int:
    try:
        start = dt.date.fromisoformat(row.get("start", ""))
        end = dt.date.fromisoformat(row.get("end", ""))
        return max(0, (end - start).days)
    except Exception:
        return 0


def _best_rows(rows: list[dict], forms, point_in_time: bool) -> list[dict]:
    """Rows for the given report forms, newest first, one per period end.

    ``forms`` is a set because the annual report is `10-K` for a domestic filer
    and `20-F` for a foreign private issuer; both occupy the same slot and are
    selected by the same annual duration rule.
    """
    if isinstance(forms, str):
        forms = (forms,)
    forms = tuple(forms)
    annual = any(form in ANNUAL_FORMS for form in forms)
    filtered = [r for r in rows if r.get("form") in forms and r.get("val") is not None and r.get("end")]
    if not point_in_time:
        if annual:
            filtered = [r for r in filtered if _duration_days(r) >= 250]
        else:
            filtered = [r for r in filtered if 45 <= _duration_days(r) <= 120]
    filtered.sort(key=lambda r: (r.get("end", ""), r.get("filed", "")), reverse=True)
    # 분기는 8개를 모은다. 4개만 모으면 전년 동기가 표에 아예 없어 계절성 비교가
    # 불가능하다(10-Q에는 Q4가 없어 4개는 1년치도 못 채운다).
    cap = 4 if annual else 8
    deduped = []
    seen = set()
    for row in filtered:
        key = row.get("end")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= cap:
            break
    return deduped


# 통화 기호가 있는 통화만 기호를 쓰고, 나머지는 코드를 앞에 붙인다. 없는 기호를
# 지어내는 것보다 "JPY 29.93T"가 정직하다.
_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "KRW": "₩"}


def currency_prefix(currency: str) -> str:
    code = str(currency or "USD").strip().upper()
    return _CURRENCY_SYMBOLS.get(code) or (f"{code} " if code else "$")


def format_value(value, metric: str, currency: str = "USD") -> str:
    try:
        num = float(value)
    except Exception:
        return str(value)
    if metric in PER_SHARE_METRICS:
        return f"{num:.2f}"
    if metric in SHARE_COUNT_METRICS:
        if num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.2f}B shares"
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M shares"
        return f"{num:,.0f} shares"
    sign = "-" if num < 0 else ""
    prefix = currency_prefix(currency)
    num = abs(num)
    if num >= 1_000_000_000_000:
        # 엔·원처럼 자릿수가 큰 통화는 조 단위가 있어야 읽힌다.
        return f"{sign}{prefix}{num / 1_000_000_000_000:.2f}T"
    if num >= 1_000_000_000:
        return f"{sign}{prefix}{num / 1_000_000_000:.2f}B"
    if num >= 1_000_000:
        return f"{sign}{prefix}{num / 1_000_000:.1f}M"
    return f"{sign}{prefix}{num:,.0f}"


def _instant_values(concepts: dict, concept: str, currency: str) -> dict[str, dict]:
    """날짜 → 그 날짜의 잔액 행(가장 늦게 신고된 것). 연차·분기 보고서의 시점 값만."""
    out: dict[str, dict] = {}
    rows = ((concepts.get(concept) or {}).get("units") or {}).get(currency) or []
    for row in rows:
        if row.get("start") or row.get("val") is None or not row.get("end"):
            continue
        if row.get("form") not in ANNUAL_FORMS + QUARTERLY_FORMS:
            continue
        end = str(row["end"])
        current = out.get(end)
        if current is None or str(row.get("filed") or "") > str(current.get("filed") or ""):
            out[end] = row
    return out


def debt_position(concepts: dict, currency: str = "USD") -> dict:
    """가장 최근 공통 기준일의 차입금·현금·순차입금.

    값과 함께 기준일·정의·태그를 돌려준다. 같은 날짜에 차입금 조합과 현금이 함께 없으면
    계산하지 않는다(`ok=False`). us-gaap 태그만 다룬다 — IFRS·DART는 기존 경로를 쓴다.
    """
    cash_by_concept = {name: _instant_values(concepts, name, currency) for name in DEBT_POSITION_CASH}
    dates = sorted({end for values in cash_by_concept.values() for end in values}, reverse=True)
    if not dates:
        return {"ok": False, "reason": "no_cash_balance"}
    needed = {concept for _, names, _ in DEBT_POSITION_BASES for concept in names}
    debt_by_concept = {name: _instant_values(concepts, name, currency) for name in needed}
    for end in dates:
        cash_concept = next((name for name in DEBT_POSITION_CASH if end in cash_by_concept[name]), "")
        cash_row = cash_by_concept[cash_concept][end]
        for basis, names, complete in DEBT_POSITION_BASES:
            if not all(end in debt_by_concept[name] for name in names):
                continue
            parts = {name: float(debt_by_concept[name][end]["val"]) for name in names}
            total = sum(parts.values())
            cash = float(cash_row["val"])
            return {
                "ok": True,
                "asOf": end,
                "basis": basis,
                "complete": complete,
                "totalDebt": total,
                "cash": cash,
                "netDebt": total - cash,
                "components": parts,
                "cashConcept": cash_concept,
                "cashIncludesRestricted": cash_concept != DEBT_POSITION_CASH[0],
                "form": str(cash_row.get("form") or ""),
            }
    return {"ok": False, "reason": "no_debt_on_cash_dates"}


def _latest_fact_end(concepts: dict) -> str:
    """The most recent period end anywhere in this taxonomy."""
    latest = ""
    for meta in concepts.values():
        for rows in ((meta or {}).get("units") or {}).values():
            for row in rows:
                end = str(row.get("end") or "")
                if end > latest:
                    latest = end
    return latest


def select_taxonomy(data: dict) -> tuple[str, dict, dict]:
    """Pick one taxonomy and never mix the two.

    A 20-F filer may report under either, and some carry both: Toyota and Sony
    publish `us-gaap` and `ifrs-full` side by side. Reading whichever concept
    matches first would take revenue from one standard and assets from the
    other, which is not a financial statement of anything. The taxonomy holding
    the most recent data wins — a filer that moved to IFRS keeps a larger but
    frozen us-gaap history, and counting concepts would serve that history as
    current. The choice travels with the numbers.
    """
    facts = data.get("facts") or {}
    options = [
        ("us-gaap", facts.get("us-gaap") or {}, METRIC_CANDIDATES),
        ("ifrs-full", facts.get("ifrs-full") or {}, IFRS_METRIC_CANDIDATES),
    ]
    ranked = []
    for name, concepts, table in options:
        if not concepts:
            continue
        # 최신성이 기준이다. 개념 수로 고르면 IFRS로 전환한 기업의 옛 us-gaap
        # 이력이 더 커서 5년 전 재무를 현재로 내놓는다(도요타 실측).
        ranked.append((_latest_fact_end(concepts), len(concepts), name, concepts, table))
    if not ranked:
        return "", {}, METRIC_CANDIDATES
    ranked.sort(reverse=True)
    _, _, name, concepts, table = ranked[0]
    return name, concepts, table


def build_companyfacts_summary(company: dict, cache_dir: Path) -> dict:
    cik = resolve_cik(company, cache_dir)
    if not cik:
        return {"ok": False, "reason": "no_cik", "company": company, "markdown": "SEC companyfacts: CIK를 찾지 못했습니다."}
    data, error = fetch_json(SEC_FACTS_URL.format(cik=cik), cache_dir / "companyfacts" / f"CIK{cik}.json", ttl_hours=12)
    if not data:
        return {"ok": False, "reason": "fetch_failed", "cik": cik, "error": error, "markdown": f"SEC companyfacts fetch failed: {error}"}
    taxonomy, concepts, table = select_taxonomy(data)
    currency = reporting_currency(concepts)
    rows = []
    for metric in table:
        concept, facts = _facts_for_metric(concepts, metric, currency=currency, table=table)
        annual = _best_rows(facts, ANNUAL_FORMS, metric in POINT_IN_TIME_METRICS)
        quarterly = _best_rows(facts, QUARTERLY_FORMS, metric in POINT_IN_TIME_METRICS)
        recent = annual[:3] if annual else quarterly[:3]
        rows.append(
            {
                "metric": metric,
                "concept": concept,
                "annual": annual[:3],
                # 전년 동기 비교를 하려면 8분기가 있어야 한다.
                "quarterly": quarterly[:8],
                "recent": recent,
            }
        )
    summary = {
        "ok": True, "cik": cik, "entityName": data.get("entityName", ""), "rows": rows,
        "warning": error,
        # 회계기준과 통화는 숫자와 함께 읽혀야 한다. 20-F 제출사의 매출을 USD로
        # 읽으면 자릿수가 통째로 틀린다.
        "taxonomy": taxonomy,
        "accountingStandard": "IFRS" if taxonomy == "ifrs-full" else "US-GAAP",
        "currency": currency,
    }
    if taxonomy == "us-gaap":
        summary["debtPosition"] = debt_position(concepts, currency)
    summary["markdown"] = companyfacts_to_markdown(summary)
    return summary


def _row_values(items: list[dict], metric: str, currency: str = "USD") -> str:
    if not items:
        return "확인되지 않음"
    return " / ".join(
        f"{item.get('end')}: {format_value(item.get('val'), metric, currency)}" for item in items[:3]
    )


def companyfacts_to_markdown(summary: dict) -> str:
    if not summary.get("ok"):
        return summary.get("markdown", "SEC companyfacts unavailable.")
    lines = [
        f"SEC companyfacts structured data: {summary.get('entityName') or ''} (CIK {summary.get('cik')})",
    ]
    # 회계기준과 통화가 숫자와 떨어지면 안 된다. 20-F 제출사의 매출을 달러로
    # 읽으면 자릿수가 통째로 틀리고, 표만 봐서는 알 길이 없다.
    standard = summary.get("accountingStandard") or ""
    currency = summary.get("currency") or ""
    if standard or currency:
        parts = [part for part in (standard, f"보고 통화 {currency}" if currency else "") if part]
        lines.append(f"회계기준·통화: {' · '.join(parts)}")
    if summary.get("warning"):
        lines.append(f"주의: {summary['warning']}")
    lines += [
        "",
        f"| Metric | Recent Annual / Point-in-time{f' ({currency})' if currency else ''} | Recent Quarter | SEC Concept |",
        "| --- | --- | --- | --- |",
    ]
    for row in summary.get("rows", []):
        metric = row["metric"]
        lines.append(
            f"| {metric} | {_row_values(row.get('annual', []), metric, currency)} | {_row_values(row.get('quarterly', []), metric, currency)} | {row.get('concept') or 'n/a'} |"
        )
    position = summary.get("debtPosition") or {}
    if position.get("ok"):
        money = lambda value: format_value(value, "Total Debt", currency or "USD")  # noqa: E731
        note = "" if position.get("complete") else " — 그 날짜의 단기차입 보고가 없어 차입금이 불완전할 수 있음"
        lines += [
            "",
            f"최신 차입금·현금 ({position['asOf']} 기준, 같은 날짜 잔액): 차입금 {money(position['totalDebt'])}"
            f" ({' + '.join(position.get('components') or {})}), 현금 {money(position['cash'])}"
            f" ({position.get('cashConcept')}), 순차입금 {money(position['netDebt'])}{note}",
        ]
    return "\n".join(lines)


