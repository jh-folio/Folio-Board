#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from features.common.workspace import data_dir
from features.company_analysis import financial_engine
from features.company_analysis.dcf import (
    PROJECTION_YEARS,
    assumption_row_label,
    build_dcf,
    dcf_value,
    net_debt_from,
    sensitivity_band_collapsed,
)
from features.company_analysis.risk_free import current_risk_free
from features.company_analysis.style import analysis_style_label, normalize_analysis_style
from features.company_analysis.valuation_basis import (
    build_valuation_basis,
    market_cashflow_is_compatible,
    normalize_currency,
)

try:
    from jinja2 import Template
except Exception:  # pragma: no cover - fallback for first run before dependency install
    Template = None


REPORT_TEMPLATE = """# ✅ {{ company.name }} ({{ company.ticker }})

## 1. 기업 개요

- **기업명**: {{ company.name }}
- **Ticker**: {{ company.ticker }}
- **섹터 / 산업**: {{ company.sector }}
- **상장 시장**: {{ company.market or "확인 필요" }}
- **공시 식별자**: {% if company.market == "KR" %}DART corp_code {{ company.corpCode or "확인 필요" }}{% else %}CIK {{ company.cik or "확인 필요" }}{% endif %}

{{ overview }}

## 2. 재무 요약

{{ financial_table }}

{{ financial_commentary }}

{{ financial_quality }}

## 3. 밸류에이션 지표

{{ valuation_metrics }}

## 4. 경쟁력 분석

{{ competitive_analysis }}

## 5. 리스크 요인

{{ risk_table }}

{{ risk_commentary }}

## 6. 성장 전망과 전략

{{ growth_outlook }}

## 7. 종합 판단

- **가격 대비 내재가치**: Valuation Metrics의 DCF 시나리오 참고
- **장기 투자 적합도**: {{ suitability }}
- **투자 의견**: 관심종목

{{ conclusion }}

## 8. 사용 자료

{% for source in sources -%}
- {{ source }}
{% endfor -%}
"""


def _fmt(value) -> str:
    return str(value or "").strip()


def _metric_row(sec_rows: list[dict], metric: str) -> dict:
    for row in sec_rows:
        if row.get("metric") == metric:
            return row
    return {"metric": metric, "annual": [], "quarterly": []}


METRIC_LABELS = {
    "Revenue": "매출",
    "Gross Profit": "매출총이익",
    "Operating Income": "영업이익",
    "Net Income": "순이익",
    "EPS Diluted": "희석 EPS",
    "Operating Cash Flow": "영업현금흐름",
    "Capital Expenditure": "설비투자",
    "Cash & Equivalents": "현금성자산",
    "Total Assets": "총자산",
    "Total Liabilities": "총부채",
    "Long-Term Debt": "장기부채",
    "Current Assets": "유동자산",
    "Current Liabilities": "유동부채",
    "Inventory": "재고",
    "Accounts Receivable": "매출채권",
    "Accounts Payable": "매입채무",
    "Shares Diluted": "희석주식수",
    "EBITDA": "EBITDA",
    "Depreciation & Amortization": "감가상각비",
    "Pretax Income": "세전이익",
    "Income Tax": "법인세",
    "Interest Expense": "이자비용",
    "Share Repurchases": "자사주 매입",
    "Dividends Paid": "배당 지급",
}

KEYWORD_LABELS = {
    "business": "사업 구조",
    "platform": "플랫폼",
    "segment": "사업부",
    "customer": "고객",
    "customers": "고객",
    "product": "제품",
    "service": "서비스",
    "competition": "경쟁",
    "scale": "규모",
    "network": "네트워크 효과",
    "technology": "기술",
    "data": "데이터",
    "brand": "브랜드",
    "risk": "리스크",
    "regulation": "규제",
    "liquidity": "유동성",
    "cybersecurity": "사이버보안",
    "insurance": "보험 비용",
    "legal": "법률 이슈",
    "growth": "성장",
    "strategy": "전략",
    "investment": "투자",
    "margin": "마진",
    "cash flow": "현금흐름",
    "ai": "AI",
    "international": "해외 확장",
    "new products": "신제품",
    "revenue": "매출",
    "margin": "마진",
    "cash flow": "현금흐름",
}


def _year(item: dict) -> str:
    return str(str(item.get("end", ""))[:4] or item.get("fy") or "확인 필요")


def _reporting_currency(sec_summary: dict) -> str:
    """The currency the filer reports in, or USD for reports saved before 0.5."""
    return str((sec_summary or {}).get("currency") or "USD")


def _format_fact(item: dict, metric: str, currency: str = "USD") -> str:
    from features.company_analysis.sec_companyfacts import format_value

    if not item:
        return "확인되지 않음"
    return format_value(item.get("val"), metric, currency)


def _annual_items(sec_summary: dict, metric: str) -> list[dict]:
    return _metric_row(sec_summary.get("rows", []), metric).get("annual", [])


def _latest_number(sec_summary: dict, metric: str, offset: int = 0) -> float | None:
    return financial_engine.latest_value(sec_summary, metric, offset)


def _annual_numbers(sec_summary: dict, metric: str, limit: int = 5) -> list[float]:
    return financial_engine.annual_values(sec_summary, metric, limit)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    try:
        return numerator / denominator
    except Exception:
        return None


def _pct(value: float | None) -> str:
    if value is None:
        return "확인 필요"
    return f"{value * 100:.1f}%"


def _money(value: float | None, currency: str = "USD") -> str:
    if value is None:
        return "확인 필요"
    return _format_fact({"val": value}, "Revenue", currency)


def _money_with_currency_status(value: float | None, currency: str | None) -> str:
    """Format a valuation amount without labelling an unknown currency as USD."""
    if value is None:
        return "확인 필요"
    code = normalize_currency(currency)
    if code:
        # GBp/GBX are pence units.  Passing them through `format_value` would
        # uppercase GBp to GBP and print a pound symbol without converting the
        # numeric value, which is a silent 100x labelling error.
        if code in {"GBp", "GBX"}:
            return f"{code} {_plain_number(value)}"
        return _money(value, code)
    return f"{_plain_number(value)} (통화 확인 필요)"


def _plain_number(value: float | None) -> str:
    if value is None:
        return "확인 필요"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,.0f}"


def _multiple(value: float | None) -> str:
    if value is None:
        return "확인 필요"
    return f"{value:.1f}x"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def _market_cache_dir() -> Path:
    return data_dir() / "company-analysis" / "market-cache"


# 캐시에 담는 항목이 늘면 올린다. 옛 파일은 신선해도 다시 받는다.
MARKET_CACHE_SHAPE = 4  # 4: quote/financial currency provenance for valuation eligibility.


def fetch_market_valuation_data(company: dict, ttl_hours: int = 6) -> dict:
    ticker = str(company.get("ticker") or "").strip().upper()
    if not ticker:
        return {"ok": False, "reason": "market_price_unavailable_for_ticker"}
    yf_symbol = f"{ticker}.KS" if company.get("market") == "KR" and re.fullmatch(r"\d{6}", ticker) else ticker
    cache_path = _market_cache_dir() / f"{yf_symbol.replace('.', '_')}.json"
    cached = _read_json(cache_path, None)
    if cached and cached.get("fetchedAt"):
        try:
            fetched = dt.datetime.fromisoformat(cached["fetchedAt"])
            cached_data = cached.get("data", cached)
            cache_is_fresh = dt.datetime.now(dt.timezone.utc) - fetched < dt.timedelta(hours=ttl_hours)
            # 캐시에 담기는 항목이 늘면 옛 파일은 그 항목 없이 신선한 상태로 남는다.
            # cashflowRows 때 한 번 겪었고 website·업종을 더하며 또 겪었다. 형태에
            # 번호를 붙여 두면 항목이 늘 때마다 특별 취급을 새로 쓰지 않아도 된다.
            same_shape = int(cached_data.get("shape") or 0) >= MARKET_CACHE_SHAPE
            if cache_is_fresh and same_shape and (cached_data.get("cashflowRows") or not cached_data.get("ok")):
                return cached_data
        except Exception:
            pass
    try:
        import yfinance as yf

        stock = yf.Ticker(yf_symbol)
        fast = getattr(stock, "fast_info", {}) or {}
        info = {}
        try:
            info = stock.get_info() or {}
        except Exception:
            try:
                info = stock.info or {}
            except Exception:
                info = {}

        def pick(*names):
            for name in names:
                value = None
                try:
                    if hasattr(fast, name):
                        value = getattr(fast, name)
                    elif isinstance(fast, dict):
                        value = fast.get(name)
                except Exception:
                    value = None
                if value is None:
                    value = info.get(name)
                try:
                    if value is not None:
                        return float(value)
                except Exception:
                    continue
            return None

        def cashflow_rows():
            try:
                frame = stock.cashflow
                if frame is None or getattr(frame, "empty", True):
                    try:
                        frame = stock.get_cash_flow(freq="yearly")
                    except Exception:
                        frame = None
                if frame is None or getattr(frame, "empty", True):
                    return []
                rows = []
                wanted = {
                    "Operating Cash Flow": ["Operating Cash Flow", "Total Cash From Operating Activities", "Net Cash Provided By Operating Activities"],
                    "Capital Expenditure": ["Capital Expenditure", "Capital Expenditures", "Capital Spending"],
                    "Free Cash Flow": ["Free Cash Flow"],
                }
                index_labels = {str(label).strip().lower(): label for label in getattr(frame, "index", [])}
                for column in list(getattr(frame, "columns", []))[:4]:
                    year = str(column)[:4]
                    if not re.fullmatch(r"\d{4}", year):
                        continue
                    row = {
                        "year": year,
                        "end": str(column)[:10],
                        "source": "yfinance cashflow",
                        "currency": info.get("financialCurrency") or None,
                    }
                    for metric, labels in wanted.items():
                        value = None
                        for label in labels:
                            actual = index_labels.get(label.lower())
                            if actual is None:
                                continue
                            try:
                                raw_value = frame.loc[actual, column]
                                if raw_value is not None:
                                    value = float(raw_value)
                                    break
                            except Exception:
                                continue
                        if metric == "Capital Expenditure" and value is not None:
                            value = abs(value)
                        row[metric] = value
                    cfo = row.get("Operating Cash Flow")
                    capex = row.get("Capital Expenditure")
                    if row.get("Free Cash Flow") is None and cfo is not None and capex is not None:
                        row["Free Cash Flow"] = cfo - capex
                    if any(row.get(metric) is not None for metric in wanted):
                        rows.append(row)
                rows.sort(key=lambda item: item.get("year", ""), reverse=True)
                return rows
            except Exception:
                return []

        data = {
            "ok": True,
            "ticker": yf_symbol,
            "price": pick("last_price", "lastPrice", "currentPrice", "regularMarketPrice", "previousClose"),
            "marketCap": pick("market_cap", "marketCap"),
            "enterpriseValue": pick("enterprise_value", "enterpriseValue"),
            "sharesOutstanding": pick("shares", "sharesOutstanding", "impliedSharesOutstanding"),
            "ebitda": pick("ebitda", "trailingEbitda"),
            # 할인율을 회사별로 만들려면 베타가 필요하다. 없으면 DCF가 고정
            # 할인율로 내려가고 그 사실을 보고서가 밝힌다.
            "beta": pick("beta"),
            # `currency` is retained as the legacy quote-currency field, but it
            # is never defaulted to USD: an absent provider value must remain
            # unknown to the valuation policy.  Financial-statement/cash-flow
            # currency is a distinct provider field and is not inferred from
            # the quote currency.
            "currency": info.get("currency") or "",
            "quoteCurrency": info.get("currency") or None,
            "currencyKnown": bool(normalize_currency(info.get("currency"))),
            "financialCurrency": info.get("financialCurrency") or None,
            "financialCurrencyKnown": bool(normalize_currency(info.get("financialCurrency"))),
            "marketValueCurrency": info.get("marketValueCurrency") or info.get("marketCapCurrency") or None,
            "marketValueCurrencyKnown": bool(
                normalize_currency(info.get("marketValueCurrency") or info.get("marketCapCurrency"))
            ),
            # Preserve explicit provider share metadata when available.  The
            # policy only treats a declared ratio/unit/class mismatch as a
            # mismatch; ticker/exchange heuristics are intentionally absent.
            "shareRatio": info.get("shareRatio") or info.get("adrRatio") or info.get("sharesPerAdr"),
            "shareUnit": info.get("shareUnit") or info.get("sharesUnit") or info.get("shareCountUnit"),
            "shareClass": info.get("shareClass"),
            "shareClassMismatch": info.get("shareClassMismatch"),
            # 회사 공식 도메인. 웹 검색 허용 목록이 이 회사 사이트만 열어 두는 데 쓴다.
            "website": info.get("website") or "",
            "sector": info.get("sector") or "",
            "industry": info.get("industry") or "",
            "source": "yfinance",
            "shape": MARKET_CACHE_SHAPE,
            "cashflowRows": cashflow_rows(),
        }
        _write_json(cache_path, {"fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "data": data})
        return data
    except Exception:
        fallback = cached.get("data") if cached else None
        if fallback:
            fallback = dict(fallback)
            # Older cache shapes used `currency: USD` as a display fallback and
            # therefore cannot prove that USD was the provider quote currency.
            # Do not let a provider outage turn that legacy label into an
            # eligible valuation input.
            if int(fallback.get("shape") or 0) < MARKET_CACHE_SHAPE:
                fallback["currencyKnown"] = False
                fallback["quoteCurrency"] = None
                fallback["financialCurrencyKnown"] = False
                fallback["financialCurrency"] = None
                fallback["marketValueCurrencyKnown"] = False
                fallback["marketValueCurrency"] = None
            fallback["warning"] = "using cached market data after provider error"
            return fallback
        return {"ok": False, "reason": "market_data_provider_unavailable"}


def _judge(value: float | None, good: float, okay: float, reverse: bool = False) -> str:
    if value is None:
        return "확인 필요"
    if reverse:
        if value <= good:
            return "양호"
        if value <= okay:
            return "보통"
        return "취약"
    if value >= good:
        return "양호"
    if value >= okay:
        return "보통"
    return "취약"


def _clean_sentence(text: str, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"Table of Contents", "", text, flags=re.I).strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(parts[:2]).strip() or text
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."
    return out


def _keyword_text(row: dict, limit: int = 5) -> str:
    labels = [KEYWORD_LABELS.get(str(k).lower(), str(k)) for k in row.get("keywords", [])[:limit]]
    return ", ".join(dict.fromkeys(labels)) or "핵심 키워드"


def _market_cashflow_by_year(
    market_data: dict | None,
    metric: str,
    *,
    reporting_currency: str | None = None,
) -> dict[str, dict]:
    out = {}
    market = market_data or {}
    market_currency = normalize_currency(market.get("financialCurrency"))
    if market.get("financialCurrencyKnown") is False:
        market_currency = None
    # yfinance cash-flow values are financial-statement values, not quote
    # values.  When the SEC/DART reporting currency, provider currency, or
    # their equality is unknown, keep the SEC/DART series but do not splice an
    # unlabelled foreign series into it.
    if not reporting_currency or not market_currency or normalize_currency(reporting_currency) != market_currency:
        return out
    for row in (market_data or {}).get("cashflowRows", []) or []:
        year = str(row.get("year") or str(row.get("end", ""))[:4])
        if not re.fullmatch(r"\d{4}", year):
            continue
        value = row.get(metric)
        try:
            value = float(value) if value is not None else None
        except Exception:
            value = None
        if value is not None:
            out[year] = {
                "val": value,
                "end": row.get("end") or year,
                "source": row.get("source") or "yfinance cashflow",
                "currency": market_currency,
            }
    return out


def _annual_value_map(sec_summary: dict, metric: str) -> dict[str, dict]:
    row = _metric_row(sec_summary.get("rows", []), metric)
    out = {}
    for item in row.get("annual", []) or []:
        year = _year(item)
        if re.fullmatch(r"\d{4}", year):
            out.setdefault(year, item)
    return out


def _derived_fcf_by_year(sec_summary: dict, market_data: dict | None = None) -> tuple[dict[str, dict], str]:
    cfo = _annual_value_map(sec_summary, "Operating Cash Flow")
    capex = _annual_value_map(sec_summary, "Capital Expenditure")
    fcf = {}
    for year in sorted(set(cfo) & set(capex), reverse=True):
        try:
            fcf[year] = {"val": float(cfo[year].get("val")) - float(capex[year].get("val")), "end": cfo[year].get("end") or capex[year].get("end") or year, "source": "SEC CFO - SEC CapEx"}
        except Exception:
            continue
    source = "SEC CFO - SEC CapEx" if fcf else ""
    if not fcf:
        y_fcf = _market_cashflow_by_year(
            market_data,
            "Free Cash Flow",
            reporting_currency=normalize_currency(sec_summary.get("currency")),
        )
        if y_fcf:
            fcf = y_fcf
            source = "yfinance cashflow FCF"
    return fcf, source


def _latest_metric_value(sec_summary: dict, market_data: dict | None, metric: str, offset: int = 0) -> float | None:
    if metric == "Free Cash Flow":
        values, _ = _derived_fcf_by_year(sec_summary, market_data)
        ordered = [values[year].get("val") for year in sorted(values, reverse=True)]
    else:
        ordered = [item.get("val") for _, item in sorted(_annual_value_map(sec_summary, metric).items(), reverse=True)]
        if not ordered and metric in {"Operating Cash Flow", "Capital Expenditure"}:
            fallback = _market_cashflow_by_year(
                market_data,
                metric,
                reporting_currency=normalize_currency(sec_summary.get("currency")),
            )
            ordered = [fallback[year].get("val") for year in sorted(fallback, reverse=True)]
    try:
        return float(ordered[offset]) if len(ordered) > offset and ordered[offset] is not None else None
    except Exception:
        return None


def _latest_metric_entry(sec_summary: dict, market_data: dict | None, metric: str) -> tuple[float | None, str]:
    """최신 값과 그 값의 연도. 연도가 다른 CFO와 CapEx를 빼면 어느 해의 것도 아닌 FCF가 된다."""
    entries = sorted(_annual_value_map(sec_summary, metric).items(), reverse=True)
    if not entries and metric in {"Operating Cash Flow", "Capital Expenditure"}:
        entries = sorted(
            _market_cashflow_by_year(
                market_data,
                metric,
                reporting_currency=normalize_currency(sec_summary.get("currency")),
            ).items(),
            reverse=True,
        )
    if not entries:
        return None, ""
    year, item = entries[0]
    try:
        return float(item.get("val")), str(year)
    except Exception:
        return None, ""


def _fcf_series_with_fallback(sec_summary: dict, market_data: dict | None = None, limit: int = 5) -> list[float]:
    values, _ = _derived_fcf_by_year(sec_summary, market_data)
    out = []
    for year in sorted(values, reverse=True)[:limit]:
        try:
            out.append(float(values[year].get("val")))
        except Exception:
            pass
    return out


def build_financial_table(sec_summary: dict, market_data: dict | None = None) -> str:
    currency = _reporting_currency(sec_summary)
    rows = sec_summary.get("rows", []) if sec_summary.get("ok") else []
    metrics = [
        "Revenue",
        "Gross Profit",
        "Operating Income",
        "Net Income",
        "EPS Diluted",
        "Operating Cash Flow",
        "Capital Expenditure",
        "Free Cash Flow",
        "Cash & Equivalents",
        "Total Liabilities",
        "Long-Term Debt",
    ]
    years = set()
    for row in rows:
        for item in row.get("annual", []):
            year = _year(item)
            if re.fullmatch(r"\d{4}", year):
                years.add(year)
    for row in (market_data or {}).get("cashflowRows", []) or []:
        year = str(row.get("year") or str(row.get("end", ""))[:4])
        if re.fullmatch(r"\d{4}", year):
            years.add(year)
    years = sorted(years, reverse=True)[:3]
    while len(years) < 3:
        years.append("확인 필요")
    lines = [f"| 항목 | {years[0]} | {years[1]} | {years[2]} | 비고 |", "| --- | --- | --- | --- | --- |"]
    fcf_by_year, fcf_source = _derived_fcf_by_year(sec_summary, market_data)
    for metric in metrics:
        row = _metric_row(rows, metric)
        values_by_year = {}
        source_note = row.get("concept") or ""
        if metric == "Free Cash Flow":
            values_by_year = {year: _money(item.get("val"), currency) for year, item in fcf_by_year.items()}
            source_note = fcf_source or "CFO/CapEx 확인 필요"
        else:
            for item in row.get("annual", []) or []:
                year = _year(item)
                values_by_year.setdefault(year, _format_fact(item, metric, currency))
            if metric in {"Operating Cash Flow", "Capital Expenditure"}:
                fallback = _market_cashflow_by_year(
                    market_data,
                    metric,
                    reporting_currency=normalize_currency(sec_summary.get("currency")),
                )
                for year, item in fallback.items():
                    if year not in values_by_year:
                        values_by_year[year] = _money(item.get("val"), currency)
                if fallback and not source_note:
                    source_note = "yfinance cashflow fallback"
        lines.append(
            f"| {METRIC_LABELS.get(metric, metric)} | {values_by_year.get(years[0], '확인되지 않음')} | "
            f"{values_by_year.get(years[1], '확인되지 않음')} | "
            f"{values_by_year.get(years[2], '확인되지 않음')} | {source_note} |"
        )
    return "\n".join(lines)

def build_financial_quality_analysis(sec_summary: dict, market_data: dict | None = None) -> str:
    currency = _reporting_currency(sec_summary)
    revenue = _latest_number(sec_summary, "Revenue")
    revenue_prior = _latest_number(sec_summary, "Revenue", 1)
    operating_income = _latest_number(sec_summary, "Operating Income")
    operating_income_prior = _latest_number(sec_summary, "Operating Income", 1)
    net_income = _latest_number(sec_summary, "Net Income")
    cfo = _latest_metric_value(sec_summary, market_data, "Operating Cash Flow")
    cfo_prior = _latest_metric_value(sec_summary, market_data, "Operating Cash Flow", 1)
    capex = _latest_metric_value(sec_summary, market_data, "Capital Expenditure")
    cash = _latest_number(sec_summary, "Cash & Equivalents")
    assets = _latest_number(sec_summary, "Total Assets")
    liabilities = _latest_number(sec_summary, "Total Liabilities")
    long_term_debt = _latest_number(sec_summary, "Long-Term Debt")
    derived = financial_engine.derived_financials(sec_summary)
    buybacks = _latest_number(sec_summary, "Share Repurchases")
    dividends = _latest_number(sec_summary, "Dividends Paid")

    fcf = _latest_metric_value(sec_summary, market_data, "Free Cash Flow")
    if fcf is None:
        # 같은 해일 때만 뺀다. 연도가 갈리면 FCF를 만들지 않고 결측으로 남긴다.
        # 밸류에이션 표는 "확인 필요"인데 품질 표만 연도 섞인 FCF로 판단을 내면 안 된다.
        cfo_value, cfo_year = _latest_metric_entry(sec_summary, market_data, "Operating Cash Flow")
        capex_value, capex_year = _latest_metric_entry(sec_summary, market_data, "Capital Expenditure")
        if cfo_value is not None and capex_value is not None and cfo_year and cfo_year == capex_year:
            fcf = cfo_value - capex_value
    fcf_margin = _ratio(fcf, revenue)
    cfo_to_operating_income = _ratio(cfo, operating_income)
    cfo_to_net_income = _ratio(cfo, net_income)
    capex_to_cfo = _ratio(capex, cfo)
    operating_income_to_assets = _ratio(operating_income, assets)
    liabilities_to_cash = _ratio(liabilities, cash)
    debt_to_cfo = _ratio(long_term_debt, cfo)

    revenue_growth = _ratio(revenue - revenue_prior, revenue_prior) if revenue is not None and revenue_prior not in {None, 0} else None
    operating_growth = _ratio(operating_income - operating_income_prior, operating_income_prior) if operating_income is not None and operating_income_prior not in {None, 0} else None
    cfo_growth = _ratio(cfo - cfo_prior, cfo_prior) if cfo is not None and cfo_prior not in {None, 0} else None

    cash_conversion_judgment = _judge(cfo_to_operating_income, 0.9, 0.6)
    fcf_judgment = "확인 필요" if fcf is None else ("양호" if fcf > 0 and (fcf_margin or 0) >= 0.08 else "보통" if fcf > 0 else "취약")
    growth_quality = "확인 필요"
    if revenue_growth is not None and operating_growth is not None:
        if revenue_growth >= 0 and operating_growth >= revenue_growth * 0.7:
            growth_quality = "양호"
        elif revenue_growth >= 0 or operating_growth >= 0:
            growth_quality = "보통"
        else:
            growth_quality = "취약"

    stability_judgment = "확인 필요"
    if debt_to_cfo is not None:
        stability_judgment = _judge(debt_to_cfo, 1.5, 3.0, reverse=True)
    elif liabilities_to_cash is not None:
        stability_judgment = _judge(liabilities_to_cash, 4.0, 8.0, reverse=True)

    capital_allocation = "확인 필요"
    if capex_to_cfo is not None and fcf is not None:
        if 0.05 <= capex_to_cfo <= 0.45 and fcf > 0:
            capital_allocation = "양호"
        elif fcf > 0:
            capital_allocation = "보통"
        else:
            capital_allocation = "취약"

    rows = [
        (
            "자본수익성",
            _judge(operating_income_to_assets, 0.10, 0.05),
            f"영업이익/총자산 대용 지표는 {_pct(operating_income_to_assets)}입니다.",
            "ROIC, WACC, 투하자본 세부 구성",
        ),
        (
            "현금전환",
            cash_conversion_judgment,
            f"영업현금흐름/영업이익은 {_pct(cfo_to_operating_income)}, 영업현금흐름/순이익은 {_pct(cfo_to_net_income)}입니다.",
            "EBITDA, 운전자본 변화",
        ),
        (
            "자유현금흐름",
            fcf_judgment,
            f"영업현금흐름 {_money(cfo, currency)}에서 설비투자 {_money(capex, currency)}를 차감한 단순 FCF는 {_money(fcf, currency)}이며, FCF/매출은 {_pct(fcf_margin)}입니다.",
            "리스, 일회성 현금흐름, 유지/성장 CapEx 구분",
        ),
        (
            "성장의 질",
            growth_quality,
            f"매출 성장률은 {_pct(revenue_growth)}, 영업이익 성장률은 {_pct(operating_growth)}, 영업현금흐름 성장률은 {_pct(cfo_growth)}입니다.",
            "세그먼트별 성장, 가격/물량 효과",
        ),
        (
            "재무 안정성",
            stability_judgment,
            f"현금성자산은 {_money(cash, currency)}, 총부채는 {_money(liabilities, currency)}, 장기부채/영업현금흐름은 {_pct(debt_to_cfo)}, 유동비율은 {_multiple(derived.get('currentRatio'))}입니다.",
            "순부채, 만기 구조",
        ),
        (
            "자본배분",
            capital_allocation,
            f"설비투자/영업현금흐름은 {_pct(capex_to_cfo)}이며, 자사주 매입은 {_money(buybacks, currency)}, 배당 지급은 {_money(dividends, currency)}로 확인됩니다.",
            "M&A 수익률, 유지/성장 CapEx 구분",
        ),
    ]

    table = [
        "### 재무 품질 분석",
        "",
        "| 항목 | 예비 판단 | 근거 | 추가 확인 포인트 |",
        "| --- | --- | --- | --- |",
        *[f"| {name} | {judgment} | {basis} | {needed} |" for name, judgment, basis, needed in rows],
        "",
    ]
    commentary = []
    if cash_conversion_judgment in {"양호", "보통"} and fcf_judgment in {"양호", "보통"}:
        commentary.append("현재 확인 가능한 수치 기준으로 이익의 현금 전환은 일정 수준 이상 유지되고 있습니다.")
    elif cash_conversion_judgment == "취약" or fcf_judgment == "취약":
        commentary.append("현재 확인 가능한 수치 기준으로 회계상 이익과 실제 현금흐름 사이의 괴리를 추가로 점검해야 합니다.")
    else:
        commentary.append("현금전환 품질은 EBITDA, 운전자본, 일회성 현금흐름 자료가 추가로 있어야 더 정확히 판단할 수 있습니다.")
    if growth_quality == "양호":
        commentary.append("성장 과정에서 수익성과 현금흐름이 함께 뒷받침되는지 계속 확인하면 됩니다.")
    elif growth_quality == "취약":
        commentary.append("외형 성장보다 수익성 또는 현금흐름이 약해지는지 확인하는 것이 더 중요합니다.")
    if stability_judgment == "취약":
        commentary.append("부채와 유동성 지표는 단순 잔액보다 만기 구조와 이자비용을 함께 봐야 합니다.")
    if derived.get("taxRate") is not None or derived.get("debtCost") is not None:
        commentary.append(f"세율은 {_pct(derived.get('taxRate'))}, 이자비용/장기부채 대용 지표는 {_pct(derived.get('debtCost'))}로 추정됩니다.")
    commentary.append("이 평가는 가격 매력도가 아니라 기업의 재무 체력을 보기 위한 예비 점검입니다.")
    return "\n".join(table + [" ".join(commentary)])


def _fcf_series(sec_summary: dict, market_data: dict | None = None) -> list[float]:
    values = _fcf_series_with_fallback(sec_summary, market_data, 5)
    return values or financial_engine.fcf_series(sec_summary, 5)


def _growth_rate(values: list[float], fallback: float = 0.04) -> float:
    return financial_engine.growth_rate(values, fallback)


def _dcf_value(base_fcf: float, net_debt: float, shares: float, near_growth: float, discount_rate: float, terminal_growth: float, years: int | None = None) -> dict:
    """민감도 표도 시나리오 표와 **같은 모델**을 쓴다. 예전에는 여기만 5년 평탄
    모델이라 같은 할인율에서 두 표가 다른 값을 말했다."""
    return dcf_value(base_fcf, net_debt, shares, near_growth, discount_rate, terminal_growth,
                     years if years is not None else PROJECTION_YEARS)


def build_valuation_metrics(company: dict, sec_summary: dict, market_data: dict | None = None) -> str:
    currency = _reporting_currency(sec_summary)
    reporting_currency = normalize_currency((sec_summary or {}).get("currency"))
    market = market_data or fetch_market_valuation_data(company)
    revenue = _latest_number(sec_summary, "Revenue")
    eps = _latest_number(sec_summary, "EPS Diluted")
    cfo = _latest_metric_value(sec_summary, market, "Operating Cash Flow")
    capex = _latest_metric_value(sec_summary, market, "Capital Expenditure")
    cash = _latest_number(sec_summary, "Cash & Equivalents") or 0.0
    debt = _latest_number(sec_summary, "Long-Term Debt")
    liabilities = _latest_number(sec_summary, "Total Liabilities")
    ebitda = market.get("ebitda") if market.get("ok") else None
    # 제공자(yfinance) EBITDA가 매출을 넘으면 통화 문제가 아니라 원본 데이터
    # 오류로 본다 — 정상 영업기업의 EBITDA 마진은 100%를 넘지 않는다(실측:
    # 000660.KS의 yfinance EBITDA가 매출의 약 11배로 나와 EV/EBITDA 1.2배라는
    # 터무니없는 값을 냈다). 아래 통화 재확인(financialCurrency)은 같은 통화
    # 라벨(KRW=KRW) 안의 크기 오류는 못 잡는다. 억지로 쓰지 않고 없는 값으로
    # 되돌려 SEC/DART 값이나 "확인 안 됨"으로 내려가게 한다.
    if ebitda is not None and revenue and ebitda > revenue:
        ebitda = None
    if ebitda is None:
        ebitda = _latest_number(sec_summary, "EBITDA")
    shares = market.get("sharesOutstanding") if market.get("ok") else None
    if shares is None:
        shares = _latest_number(sec_summary, "Shares Diluted")
    price = market.get("price") if market.get("ok") else None
    market_cap = market.get("marketCap") if market.get("ok") else None
    valuation_basis = build_valuation_basis(sec_summary, market, share_count=shares)
    eligibility = valuation_basis.get("eligibility") or {}
    price_eligible = bool((eligibility.get("per") or {}).get("eligible"))
    market_value_eligible = bool((eligibility.get("marketMultiples") or {}).get("eligible"))
    # A provider marketCap with unknown/mismatched financial currency is not
    # safe to divide by SEC revenue.  A cap derived from same-currency price ×
    # shares is safe and is explicitly marked as derived in the basis.
    raw_market_cap = market_cap
    market_cap_derived = False
    if valuation_basis.get("marketValueCurrencyStatus") != "same":
        market_cap = (
            price * shares
            if valuation_basis.get("marketValueDerivedSafe") and price is not None and shares is not None
            else None
        )
        market_cap_derived = market_cap is not None
    elif (
        market_cap is None
        and price is not None
        and shares is not None
        # Keep the same proof required by the branch above.  A provider
        # market-value currency can be known and reporting-compatible while
        # the quote itself is foreign; in that case price * shares would be
        # denominated in the quote currency and cannot be paired with SEC
        # revenue/FCF.
        and valuation_basis.get("marketValueDerivedSafe")
    ):
        market_cap = price * shares
        market_cap_derived = True
    # **순부채는 한 값이다.** 예전에는 여기서 `장기부채 - 현금`으로 계산해 `순부채` 행과
    # 민감도 표에 쓰고, 바로 아래 시나리오 표는 `dcf_model`(단기차입 포함)을 읽었다 —
    # 한 섹션 안에서 세 표가 서로 다른 레버리지를 말했다. 단기차입이 많은 회사에서는
    # 그 차이가 그대로 주당 가치로 간다. `dcf.net_debt_from()`이 단일 출처다.
    net_debt = float(net_debt_from(sec_summary).get("netDebt") or 0.0)
    enterprise_value = market.get("enterpriseValue") if market.get("ok") else None
    if valuation_basis.get("marketValueCurrencyStatus") != "same":
        enterprise_value = None
    if enterprise_value is None and market_cap is not None and market_value_eligible:
        enterprise_value = market_cap + net_debt

    fcf = _latest_metric_value(sec_summary, market, "Free Cash Flow")
    if fcf is None:
        # 같은 해일 때만 뺀다. 연도가 갈리면 FCF를 만들지 않고 결측으로 남긴다.
        cfo_value, cfo_year = _latest_metric_entry(sec_summary, market, "Operating Cash Flow")
        capex_value, capex_year = _latest_metric_entry(sec_summary, market, "Capital Expenditure")
        if cfo_value is not None and capex_value is not None and cfo_year and cfo_year == capex_year:
            fcf = cfo_value - capex_value
    psr = _ratio(market_cap, revenue) if market_value_eligible else None
    per = _ratio(price, eps) if price_eligible and eps and eps > 0 else None
    # Provider EBITDA has its own unit provenance.  SEC EBITDA is already in
    # reporting currency and can be paired with a safe derived market value.
    provider_ebitda = market.get("ebitda") if market.get("ok") else None
    if provider_ebitda is not None and normalize_currency(valuation_basis.get("financialCurrency")) != reporting_currency:
        ebitda = _latest_number(sec_summary, "EBITDA")
    ev_ebitda = _ratio(enterprise_value, ebitda) if market_value_eligible and ebitda and ebitda > 0 else None
    fcf_yield = _ratio(fcf, market_cap) if market_value_eligible else None
    fcf_margin = _ratio(fcf, revenue)

    # **규칙 보고서도 같은 DCF를 쓴다.** 여기서 따로 계산하면 규칙 보고서와 LLM
    # 보고서가 같은 회사에 다른 내재가치를 말한다 — PER 시나리오에서 이미 겪었다.
    dcf_eligibility = eligibility.get("dcf") or {}
    if dcf_eligibility.get("eligible"):
        dcf_model = build_dcf(
            sec_summary,
            price=price if price_eligible else None,
            shares=shares,
            # Unknown provider market value is omitted; build_dcf then uses
            # its documented fixed-rate fallback rather than mixing units.
            market_cap=market_cap if market_value_eligible else None,
            beta=market.get("beta") if market.get("ok") and market_value_eligible else None,
            currency=currency,
            risk_free=current_risk_free(currency),
        )
    else:
        dcf_reason = dcf_eligibility.get("reason") or "필요한 단위 정보를 확인하지 못했습니다."
        dcf_model = {
            "ok": False,
            "status": "unavailable",
            "reason": dcf_reason,
            "unavailableReason": dcf_reason,
            "reasonCodes": dcf_eligibility.get("reasonCodes", []),
            "currency": reporting_currency,
        }
    near_growth = dcf_model.get("growth", {}).get("rate", 0.04)
    discount_rate = dcf_model.get("discountRate", {}).get("rate", 0.09)
    terminal_growth = dcf_model.get("terminalGrowth", 0.025)
    scenarios = dcf_model.get("scenarios") or []
    dcf = next((row for row in scenarios if row.get("name") == "기준"), {"ok": False})
    base_fcf = (dcf_model.get("baseFcf") or {}).get("value")

    # 주가는 상장 통화, 재무는 신고 통화다. ASML은 나스닥 ADR이 달러인데 재무는
    # 유로라, 두 통화가 다르면 시가총액/매출 같은 배수는 서로 다른 단위를 나눈
    # 값이라 의미가 없다. 환산하지 않고 그 사실을 밝힌다.
    market_currency = normalize_currency(market.get("quoteCurrency") or market.get("currency"))
    mixed_currency = valuation_basis.get("priceCurrencyStatus") == "mismatch"
    market_value_currency = valuation_basis.get("marketValueCurrency")
    market_cap_display = market_cap if market_cap_derived else raw_market_cap
    market_cap_source = (
        "앱 계산: 주가 × 주식수 (공급자 marketCap 미사용)"
        if market_cap_derived
        else "yfinance marketCap (시장가치 통화 확인 필요)"
    )
    table = [
        "| 지표 | 계산값 | 사용 입력/계산식 |",
        "| --- | ---: | --- |",
        f"| 현재 주가 | {_money_with_currency_status(price, market_currency)} | yfinance {market.get('ticker', company.get('ticker', ''))} |",
        f"| 시가총액 | {_money_with_currency_status(market_cap_display, reporting_currency if market_cap_derived else market_value_currency)} | {market_cap_source} |",
        f"| 순부채 | {_money_with_currency_status(net_debt, reporting_currency)} | 장기부채 + 단기차입 - 현금 {_money_with_currency_status(cash, reporting_currency)} |",
        f"| PER | {_multiple(per)} | 주가 / 희석 EPS {_plain_number(eps)} |",
        f"| PSR | {_multiple(psr)} | 시가총액 / 매출 {_money_with_currency_status(revenue, reporting_currency)} |",
        f"| EV/EBITDA | {_multiple(ev_ebitda)} | 기업가치 / EBITDA {_money_with_currency_status(ebitda, reporting_currency)} |",
        f"| FCF Yield | {_pct(fcf_yield)} | FCF {_money_with_currency_status(fcf, reporting_currency)} / 시가총액 |",
        f"| FCF Margin | {_pct(fcf_margin)} | FCF / 매출 |",
    ]

    lines = ["### Valuation Metrics", "", *table, ""]
    if dcf.get("ok"):
        basis = (dcf_model.get("growth") or {}).get("basis", "")
        basis_label = {"revenue_cagr": "매출 CAGR", "fcf_cagr": "FCF CAGR"}.get(basis, "기본값")
        lines += [
            "### DCF 기반 내재가치",
            "",
            f"초기 성장률은 {basis_label}에서 왔고, {len(dcf_model.get('fadePath') or [])}년에 걸쳐 "
            f"영구성장률 {_pct(terminal_growth)}까지 감쇠시켰습니다. 시나리오는 성장률만 흔들고 "
            "할인율·영구성장률은 아래 민감도 표가 맡습니다.",
            "",
            "| 시나리오 | 초기 성장률 | 할인율 | 영구성장률 | 자기자본가치 | 내재가치/주 | 현재가 대비 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for scenario in scenarios:
            if scenario.get("ok"):
                upside = _ratio(scenario["perShare"] - price, price) if price else None
                lines.append(
                    f"| {scenario['name']} | {_pct(scenario['growth'])} | {_pct(scenario['discount'])} | {_pct(scenario['terminal'])} | "
                    f"{_money(scenario['equityValue'], currency)} | {_money(scenario['perShare'], currency)} | {_pct(upside)} |"
                )
            else:
                lines.append(f"| {scenario['name']} | {_pct(scenario['growth'])} | {_pct(scenario['discount'])} | {_pct(scenario['terminal'])} | 계산 불가 | 계산 불가 | 계산 불가 |")
        base = dcf_model.get("baseFcf") or {}
        discount = dcf_model.get("discountRate") or {}
        deviation = base.get("deviationFromRecent")
        lines += [
            "",
            "| 항목 | 값 |",
            "| --- | ---: |",
            f"| 기준 FCF (정상화) | {_money(base_fcf, currency)} |",
            f"| 최근 연도 실제 FCF | {_money(base.get('recent'), currency)}"
            + (f" ({_pct(deviation)} 차이)" if deviation is not None else "")
            + " |",
            f"| 할인율 | {_pct(discount_rate)}"
            + (f" (WACC, 조정베타 {discount.get('adjustedBeta')})" if discount.get("method") == "wacc"
               else " (회사별 계산 실패로 고정값)")
            + " |",
            f"| 순부채 | {_money(net_debt, currency)} |",
            f"| 순부채 차감 후 자기자본가치 | {_money(dcf['equityValue'], currency)} |",
            f"| DCF 내재가치/주 | {_money(dcf['perShare'], currency)} |",
        ]
        # **터미널 비중을 숨기지 않는다.** 가치의 절반 이상이 명시 예측 기간 이후
        # 가정에서 오는데 그 사실이 없으면 독자는 정밀한 현금흐름 모델을 봤다고 생각한다.
        fade_years = len(dcf_model.get("fadePath") or []) or PROJECTION_YEARS
        share = dcf.get("terminalShare")
        if share is not None:
            lines.append(
                f"| 터미널 비중 | {_pct(share)} (명시 예측 기간 {fade_years}년 이후"
                " 영구성장 가정에서 오는 가치) |"
            )
        implied = dcf_model.get("impliedGrowth") or {}
        if implied.get("status") == "solved":
            lines.append(
                f"| 역산 성장률 | {_pct(implied['growth'])} (현재가를 정당화하는 1년차 FCF"
                f" 성장률 — 이후 {fade_years}년간 영구성장률까지 감쇠) |"
            )
        lines += [
            "",
            "| 민감도: 내재가치/주 | 영구성장 2.0% | 영구성장 2.5% | 영구성장 3.0% |",
            "| --- | ---: | ---: | ---: |",
        ]
        # 시나리오는 사업 가정(성장률)만 흔들고, 평가 가정(할인율·영구성장)은 이 표가 맡는다.
        for dr in [discount_rate - 0.01, discount_rate, discount_rate + 0.01]:
            cells = []
            for tg in [0.02, 0.025, 0.03]:
                case = _dcf_value(base_fcf or 0.0, net_debt, shares or 0.0, near_growth, dr, tg)
                # 통화를 명시한다 — 기본값 USD로 두면 바로 아래 가정 감도표와 같은
                # 수치가 다른 통화 기호로 나란히 찍힌다(KRW/EUR 신고 기업).
                cells.append(_money(case.get("perShare") if case.get("ok") else None, currency))
            lines.append(f"| 할인율 {_pct(dr)} | {cells[0]} | {cells[1]} | {cells[2]} |")
        # 할인율의 두 입력(무위험·ERP)이 답을 얼마나 지배하는지의 감도. 실측 ERP 4~6%가
        # 내재가치를 37% 흔드는데 그 폭이 하나의 숫자에 눌려 보이지 않았다(§9.4).
        assumption_rows = dcf_model.get("assumptionSensitivity") or []
        if assumption_rows:
            lines += [
                "",
                "| 가정 감도 | 할인율 | 내재가치/주 | 역산 성장률 |",
                "| --- | ---: | ---: | ---: |",
            ]
            for row in assumption_rows:
                implied_cell = _pct(row.get("impliedGrowth")) if row.get("impliedGrowth") is not None else "—"
                lines.append(
                    f"| {assumption_row_label(row)} | {_pct(row.get('discountRate'))} | {_money(row.get('perShare'), currency)} | {implied_cell} |"
                )
            if sensitivity_band_collapsed(assumption_rows):
                lines.append(
                    "\n모든 행의 할인율이 모델의 상·하한에 물려 같습니다. 이 표에서 두 가정의 "
                    "영향을 읽을 수 없다는 뜻이지, 가정이 무관하다는 뜻이 아닙니다."
                )
            else:
                lines.append(
                    "\n무위험수익률과 위험프리미엄은 가정입니다. 내재가치는 하나의 값이 아니라 위 범위로 "
                    "읽으세요 — 범위가 현재가를 걸치면 그 사실 자체가 판단 재료입니다."
                )
        lines += [
            "",
            "DCF는 예비 모델입니다. 기준 FCF는 FCF 마진 중앙값으로 정상화했고 성장률은 "
            "예측 기간에 걸쳐 영구성장률까지 감쇠시켰습니다. 무위험수익률과 위험프리미엄은 "
            "가정이며, 유지/성장 CapEx 구분, 운전자본 정상화, 경기 사이클은 별도 검증이 필요합니다. "
            "**내재가치와 현재가의 차이를 고평가·저평가로 단정하지 마세요** — 위 가정이 바뀌면 결과도 바뀝니다.",
        ]
    else:
        if dcf_model.get("status") == "unavailable":
            lines += [
                "### DCF 기반 내재가치",
                "",
                f"**DCF 계산 불가:** {dcf_model.get('reason') or '필요한 단위 정보를 확인하지 못했습니다.'}",
            ]
        else:
            missing = []
            if not base_fcf or base_fcf <= 0:
                missing.append("양의 기준 FCF")
            if not shares:
                missing.append("희석주식수")
            if price is None:
                missing.append("현재 주가")
            if not missing:
                missing.append("할인율/성장률 조건")
            lines += [
                "### DCF 기반 내재가치",
                "",
                f"DCF 계산에는 {', '.join(missing)}가 필요합니다. 현재 확인 가능한 SEC/companyfacts와 시장가격 데이터만으로는 신뢰할 수 있는 내재가치를 산출하지 않았습니다.",
            ]
    if not market.get("ok"):
        lines.append(f"\n시장가격 데이터 참고: yfinance 데이터를 가져오지 못했습니다({market.get('reason', 'unknown')}). SEC 기반 재무 지표만 표시했습니다.")
    elif market.get("warning"):
        lines.append(f"\n시장가격 데이터 참고: {market['warning']}")
    if mixed_currency:
        lines.append(
            f"\n**통화 주의 — 밸류에이션 계산 불가:** 주가는 {market_currency or '확인 필요'}, 재무는 {currency or '확인 필요'} 기준입니다. "
            "환산 근거가 없어 주가와 주당 재무 수치를 비교하는 PER·DCF·PER 시나리오와 시장가치 배수를 산출하지 않았습니다."
        )
    unavailable = [
        (label, item)
        for key, label in (("per", "PER"), ("marketMultiples", "PSR·EV/EBITDA"), ("fcfYield", "FCF Yield"))
        for item in [eligibility.get(key) or {}]
        if not item.get("eligible")
    ]
    if unavailable and not mixed_currency:
        lines.append(
            "\n**밸류에이션 계산 불가:** "
            + "; ".join(f"{label} — {item.get('reason') or '필요한 단위 정보를 확인하지 못했습니다.'}" for label, item in unavailable)
        )
    return "\n".join(lines)


def _growth_phrase(sec_summary: dict, metric: str) -> str:
    row = _metric_row(sec_summary.get("rows", []), metric)
    annual = row.get("annual", [])
    if len(annual) < 2:
        label = METRIC_LABELS.get(metric, metric)
        return f"{label} 추세는 추가 확인이 필요합니다."
    try:
        recent = float(annual[0]["val"])
        prior = float(annual[1]["val"])
        if prior == 0:
            return f"{METRIC_LABELS.get(metric, metric)}은 최근 연도 기준 확인되지만 증가율 계산은 어렵습니다."
        rate = (recent / prior - 1) * 100
        direction = "증가" if rate >= 0 else "감소"
        return f"{METRIC_LABELS.get(metric, metric)}은 최근 연도에 전년 대비 약 {abs(rate):.1f}% {direction}했습니다."
    except Exception:
        return f"{METRIC_LABELS.get(metric, metric)} 추세는 추가 확인이 필요합니다."


def paragraphs_by_theme(paragraphs: list[dict], keywords: list[str], limit: int = 3) -> list[dict]:
    wanted = [kw.lower() for kw in keywords]
    rows = []
    for row in paragraphs:
        blob = f"{row.get('text', '')} {' '.join(row.get('keywords', []))}".lower()
        score = sum(1 for kw in wanted if kw in blob) + int(row.get("score", 0)) / 20
        if score > 0:
            rows.append((score, row))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows[:limit]]


def summarize_paragraphs(rows: list[dict], fallback: str) -> str:
    if not rows:
        return fallback
    out = []
    for row in rows:
        keyword_text = _keyword_text(row)
        item = row.get("item") or "공시"
        snippet = _clean_sentence(row.get("text", ""))
        if snippet:
            out.append(f"- **Item {item}**: {snippet} 핵심 논점은 {keyword_text}입니다.")
        else:
            out.append(f"- **Item {item}**: 해당 공시 문단은 {keyword_text}와 관련된 내용을 포함합니다.")
    return "\n".join(out)


def render_report(context: dict) -> str:
    company = context["company"]
    sources = "\n".join(f"- {source}" for source in context.get("sources", []))
    filing_id = f"DART corp_code {company.get('corpCode') or '확인 필요'}" if company.get("market") == "KR" else f"CIK {company.get('cik') or '확인 필요'}"
    style_label = context.get("styleLabel") or "기업 분석"
    return f"""# ✅ {company.get("name", "")} ({company.get("ticker", "")})

> 분석 모드: {style_label}

## 1. 기업 개요

- **기업명**: {company.get("name", "")}
- **Ticker**: {company.get("ticker", "")}
- **섹터 / 산업**: {company.get("sector") or "확인 필요"}
- **상장 시장**: {company.get("market") or "확인 필요"}
- **공시 식별자**: {filing_id}

{context["overview"]}

## 2. 재무 요약

{context["financial_table"]}

{context["financial_commentary"]}

{context["financial_quality"]}

## 3. 밸류에이션 지표

{context["valuation_metrics"]}

## 4. 경쟁력 분석

{context["competitive_analysis"]}

## 5. 리스크 요인

{context["risk_table"]}

{context["risk_commentary"]}

## 6. 성장 전망과 전략

{context["growth_outlook"]}

## 7. 종합 판단

- **가격 대비 내재가치**: Valuation Metrics의 DCF 시나리오 참고
- **장기 투자 적합도**: {context["suitability"]}
- **투자 의견**: 관심종목

{context["conclusion"]}

## 8. 사용 자료

{sources}
"""


# 안내 문구에 쓸 (사업 개요, 위험 요소) Item 번호. 20-F는 체계가 다르다.
_ANNUAL_ITEM_HINTS = {
    "10-K": ("Item 1", "Item 1A"),
    "20-F": ("Item 4", "Item 3.D"),
}


def build_rule_report(analysis: dict, analysis_style: str = "beginner") -> str:
    style = normalize_analysis_style(analysis_style)
    company = analysis["company"]
    sec_summary = analysis.get("secFacts", {})
    ranked = analysis.get("rankedFiling", {})
    paragraphs = ranked.get("paragraphs", [])
    sources = []

    metadata = ranked.get("metadata", {}) or {}
    # 안내 문구도 실제 form을 따른다. 20-F 제출사에게 "10-K Item 1"을 보라고 하면
    # 존재하지 않는 구획을 가리킨다 — 그 회사의 사업 개요는 Item 4다.
    annual_form = str(metadata.get("form") or ranked.get("form") or "10-K").upper()
    overview_item, risk_item = _ANNUAL_ITEM_HINTS.get(annual_form, _ANNUAL_ITEM_HINTS["10-K"])
    if metadata.get("url"):
        sources.append(f"SEC {annual_form} HTML: {metadata.get('url')}")
    elif metadata.get("path"):
        sources.append(f"Local official filing fallback ({metadata.get('form', 'filing')}): {metadata.get('path')}")
    if analysis.get("dartFacts", {}).get("ok"):
        sources.append(f"DART Open API: corp_code {analysis['dartFacts'].get('corpCode')}")
    if sec_summary.get("ok"):
        if sec_summary.get("corpCode"):
            sources.append(f"DART financial statements: corp_code {sec_summary.get('corpCode')}")
        else:
            sources.append(f"SEC companyfacts: CIK {sec_summary.get('cik')}")
    for doc in analysis.get("filingDocs", [])[:4]:
        sources.append(f"Local filing · {doc.get('date')} · {doc.get('title')} · {doc.get('url') or doc.get('path')}")
    for doc in analysis.get("supportDocs", [])[:8]:
        sources.append(f"{doc.get('source')} · {doc.get('date')} · {doc.get('title')} · {doc.get('url') or doc.get('path')}")
    if not sources:
        sources.append("로컬 research-inbox 자료 및 사용 가능한 캐시")

    overview = summarize_paragraphs(
        paragraphs_by_theme(paragraphs, ["business", "platform", "segment", "customer", "product", "service"], 3),
        f"사업 개요 문단이 충분히 구조화되지 않았습니다. {annual_form} {overview_item} 또는 회사 IR 자료를 추가하면 보강할 수 있습니다.",
    )
    financial_commentary = " ".join(
        [
            _growth_phrase(sec_summary, "Revenue"),
            _growth_phrase(sec_summary, "Operating Income"),
            _growth_phrase(sec_summary, "Operating Cash Flow"),
            "CapEx와 현금/부채 항목은 현금흐름의 질과 재무 유연성을 판단하는 보조 지표로 확인해야 합니다.",
        ]
    )
    competitive_analysis = summarize_paragraphs(
        paragraphs_by_theme(paragraphs, ["competition", "scale", "network", "customer", "technology", "data", "brand"], 4),
        "경쟁우위 관련 문단이 제한적입니다. 규모, 네트워크 효과, 고객 전환비용, 기술/데이터 우위를 중심으로 추가 확인이 필요합니다.",
    )
    risks = paragraphs_by_theme(paragraphs, ["risk", "regulation", "competition", "liquidity", "cybersecurity", "insurance", "legal"], 5)
    risk_table = "\n".join(
        [
            "| 리스크 | 설명 | 영향도 |",
            "| --- | --- | --- |",
            *[
                f"| {', '.join(KEYWORD_LABELS.get(str(k).lower(), str(k)) for k in row.get('keywords', [])[:3]) or '리스크'} | Item {row.get('item') or '공시'}에서 해당 리스크 키워드가 반복적으로 감지되었습니다. | 중간 |"
                for row in risks[:5]
            ],
        ]
    )
    if len(risk_table.splitlines()) <= 2:
        risk_table += f"\n| 추가 확인 필요 | {annual_form} {risk_item} 발췌가 충분하지 않습니다. | 중간 |"
    risk_commentary = "규칙 기반 리스크 평가는 문단 키워드와 공식 공시 Item 출처를 기준으로 합니다. 실제 투자 판단 전에는 소송, 규제, 재무 레버리지, 경쟁 강도에 대한 최신 공시를 함께 확인해야 합니다."
    growth_outlook = summarize_paragraphs(
        paragraphs_by_theme(paragraphs, ["growth", "strategy", "investment", "margin", "cash flow", "ai", "international", "new products"], 4),
        "성장 전략 관련 문단이 충분하지 않습니다. 경영진 가이던스, 실적발표 transcript, IR deck를 추가하면 성장 전망을 더 정교하게 만들 수 있습니다.",
    )
    suitability = "보통" if sec_summary.get("ok") and paragraphs else "낮음"
    if style == "advanced":
        conclusion = (
            f"{company.get('name')} 분석은 SEC 또는 DART 공식 숫자 데이터와 핵심 공시 문단을 기반으로 구성했습니다. "
            "규칙 기반 고급 모드는 매출 성장, 마진, 현금전환, 밸류에이션 입력값, 리스크 문단의 존재 여부를 압축적으로 연결합니다. "
            "LLM 분석처럼 정성적 경쟁구도와 세그먼트별 민감도를 깊게 확장하지는 못하지만, 확인 가능한 근거와 미확인 gap을 분리해 판단의 출발점을 제공합니다. "
            "다음 단계에서는 최신 실적발표 자료, IR deck, transcript, 비교기업 valuation 자료를 함께 넣으면 risk/reward 판단이 더 정교해집니다."
        )
    else:
        conclusion = (
            f"{company.get('name')} 분석은 SEC 또는 DART 공식 숫자 데이터와 핵심 공시 문단을 기반으로 구성했습니다. "
            "규칙 기반 초심자 모드는 어려운 투자 용어보다 매출, 이익, 현금흐름, 리스크가 왜 중요한지 이해하는 데 초점을 둡니다. "
            "빈 보고서를 내는 대신, 확인 가능한 숫자와 공시 문단에 기반해 투자자가 다음에 확인해야 할 지점을 쉽게 정리합니다. "
            "다음 단계에서는 최신 실적발표 자료, IR deck, 주가/밸류에이션 데이터를 함께 넣으면 결론의 실전성이 높아집니다."
        )

    market_data = analysis.get("marketFinancialData") or fetch_market_valuation_data(company)
    context = {
        "company": company,
        "overview": overview,
        "financial_table": build_financial_table(sec_summary, market_data),
        "financial_commentary": financial_commentary,
        "financial_quality": build_financial_quality_analysis(sec_summary, market_data),
        "valuation_metrics": build_valuation_metrics(company, sec_summary, market_data),
        "competitive_analysis": competitive_analysis,
        "risk_table": risk_table,
        "risk_commentary": risk_commentary,
        "growth_outlook": growth_outlook,
        "suitability": suitability,
        "conclusion": conclusion,
        "sources": sources,
        "styleLabel": analysis_style_label(style),
    }
    return render_report(context)
