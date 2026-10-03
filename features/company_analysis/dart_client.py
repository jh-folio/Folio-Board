from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from features.common.atomic_replace import write_bytes_atomic


DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_FINANCIAL_ALL_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
DART_DISCLOSURE_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"

DART_REPORT_CODES = {
    "annual": "11011",
    "q1": "11013",
    "half": "11012",
    "q3": "11014",
}

ACCOUNT_PATTERNS = {
    "Revenue": ["매출액", "영업수익", "수익(매출액)", "revenue"],
    "Gross Profit": ["매출총이익", "gross profit"],
    "Operating Income": ["영업이익", "operating income"],
    "Net Income": ["당기순이익", "분기순이익", "반기순이익", "profit loss", "net income"],
    "Operating Cash Flow": ["영업활동 현금흐름", "영업활동으로 인한 현금흐름", "cash flows from operating"],
    "Capital Expenditure": ["유형자산의 취득", "유형자산 취득", "property plant and equipment"],
    "Cash & Equivalents": ["현금및현금성자산", "현금 및 현금성자산", "cash and cash equivalents"],
    "Total Assets": ["자산총계", "total assets"],
    "Total Liabilities": ["부채총계", "total liabilities"],
    "Long-Term Debt": ["장기차입금", "사채", "long-term borrowings", "long term debt"],
    "Current Assets": ["유동자산", "current assets"],
    "Current Liabilities": ["유동부채", "current liabilities"],
    "Inventory": ["재고자산", "inventories"],
    "Accounts Receivable": ["매출채권", "trade receivables"],
    "Accounts Payable": ["매입채무", "trade payables"],
    "EPS Diluted": ["희석주당이익", "diluted earnings per share"],
}

# 표준계정코드 정확 일치 표. SEC 경로(sec_companyfacts)가 개념명을 정확 일치로 고르는 것과
# 같은 원칙이다 — account_id를 부분문자열로 이름 패턴에 섞으면 ProfitLossBeforeTax(세전이익)·
# ShareOfProfitLoss...(지분법이익)가 "profit loss" 패턴에 걸려 손익계산서에서 먼저 나오는
# 그 행이 Net Income 슬롯을 차지한다(실측: 삼성전자 순이익 15.49T가 887.55B로 저장).
ACCOUNT_ID_METRICS = {
    "ifrs-full_revenue": "Revenue",
    "ifrs_revenue": "Revenue",
    "ifrs-full_grossprofit": "Gross Profit",
    "ifrs_grossprofit": "Gross Profit",
    "dart_operatingincomeloss": "Operating Income",
    "ifrs-full_profitloss": "Net Income",
    "ifrs_profitloss": "Net Income",
    "ifrs-full_cashflowsfromusedinoperatingactivities": "Operating Cash Flow",
    "ifrs_cashflowsfromusedinoperatingactivities": "Operating Cash Flow",
    "ifrs-full_cashandcashequivalents": "Cash & Equivalents",
    "ifrs_cashandcashequivalents": "Cash & Equivalents",
    "ifrs-full_assets": "Total Assets",
    "ifrs_assets": "Total Assets",
    "ifrs-full_liabilities": "Total Liabilities",
    "ifrs_liabilities": "Total Liabilities",
    "ifrs-full_currentassets": "Current Assets",
    "ifrs_currentassets": "Current Assets",
    "ifrs-full_currentliabilities": "Current Liabilities",
    "ifrs_currentliabilities": "Current Liabilities",
    "ifrs-full_inventories": "Inventory",
    "ifrs_inventories": "Inventory",
    "ifrs-full_dilutedearningslosspershare": "EPS Diluted",
    "ifrs_dilutedearningslosspershare": "EPS Diluted",
}

# 이름 패턴 부분 매칭의 오염 차단. "계속영업이익"은 "영업이익"을, "계속영업당기순이익"은
# "당기순이익"을 부분문자열로 포함해 진짜 행보다 먼저 슬롯을 차지한다.
ACCOUNT_EXCLUDES = {
    "Net Income": ["세전", "법인세비용차감전", "차감전", "지분법", "계속영업", "중단영업", "before tax", "share of", "continuing", "discontinued"],
    "Operating Income": ["계속영업", "중단영업", "영업외", "continuing", "discontinued", "non-operating"],
}


def dart_api_key() -> str:
    return os.environ.get("DART_API_KEY", "").strip()


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    write_bytes_atomic(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _fresh(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    return age < dt.timedelta(hours=ttl_hours)


def _request_json(url: str, params: dict, cache_path: Path, ttl_hours: int = 12) -> tuple[dict | None, str]:
    if _fresh(cache_path, ttl_hours):
        cached = _read_json(cache_path, None)
        if cached is not None:
            return cached, ""
    query = urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "MarketResearchArchive/0.1"})
        with urllib.request.urlopen(req, timeout=int(os.environ.get("DART_TIMEOUT_SECONDS", "30"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _write_json(cache_path, data)
        return data, ""
    except Exception:
        cached = _read_json(cache_path, None)
        if cached is not None:
            return cached, "using cached DART data after fetch error"
        return None, "DART request failed"


def load_corp_codes(cache_dir: Path, api_key: str | None = None) -> list[dict]:
    api_key = (api_key or dart_api_key()).strip()
    cache_path = cache_dir / "corp_codes.json"
    if _fresh(cache_path, ttl_hours=24 * 7):
        cached = _read_json(cache_path, [])
        if isinstance(cached, list):
            return cached
    if not api_key:
        return _read_json(cache_path, []) or []
    try:
        req = urllib.request.Request(
            f"{DART_CORP_CODE_URL}?{urllib.parse.urlencode({'crtfc_key': api_key})}",
            headers={"User-Agent": "MarketResearchArchive/0.1"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("DART_TIMEOUT_SECONDS", "30"))) as resp:
            payload = resp.read()
        with zipfile.ZipFile(BytesIO(payload)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
        root = ET.fromstring(xml_bytes)
        rows = []
        for item in root.findall("list"):
            row = {child.tag: (child.text or "").strip() for child in item}
            if row.get("corp_code") and row.get("corp_name"):
                rows.append(row)
        _write_json(cache_path, rows)
        return rows
    except Exception:
        return _read_json(cache_path, []) or []


def resolve_dart_company(query: str, cache_dir: Path, api_key: str | None = None) -> dict | None:
    token = str(query or "").strip()
    if not token:
        return None
    token_upper = token.upper().replace(".KS", "").replace(".KQ", "")
    token_norm = re.sub(r"\s+", "", token).lower()
    exact_stock = None
    exact_name = None
    contains_name = None
    for row in load_corp_codes(cache_dir, api_key):
        stock_code = str(row.get("stock_code") or "").strip()
        corp_name = str(row.get("corp_name") or "").strip()
        corp_code = str(row.get("corp_code") or "").strip()
        if not stock_code or not corp_name or not corp_code:
            continue
        candidate = {
            "name": corp_name,
            "ticker": stock_code,
            "sector": "Unclassified",
            "market": "KR",
            "cik": "",
            "corpCode": corp_code,
            "aliases": [corp_name, stock_code, f"{stock_code}.KS", f"{stock_code}.KQ"],
        }
        if token_upper == stock_code:
            exact_stock = candidate
            break
        name_norm = re.sub(r"\s+", "", corp_name).lower()
        if token_norm == name_norm:
            exact_name = candidate
        elif len(token_norm) >= 2 and token_norm in name_norm and contains_name is None:
            contains_name = candidate
    return exact_stock or exact_name or contains_name


def fetch_company_profile(corp_code: str, cache_dir: Path, api_key: str | None = None) -> dict:
    """Official exchange/industry/fiscal-month metadata; never infer a suffix.

    A fresh official cache is usable without a credential. A fetch failure may
    return a prior official packet with an explicit warning, as other DART
    readers do. API errors and mismatched identities cannot confirm a market.
    """
    code = str(corp_code or "").strip()
    if not re.fullmatch(r"\d{8}", code):
        return {"ok": False, "reason": "invalid_corp_code"}
    cache_path = cache_dir / "companies" / f"{code}.json"
    key = (api_key or dart_api_key()).strip()
    if not key:
        if not _fresh(cache_path, ttl_hours=24):
            return {"ok": False, "reason": "missing_dart_api_key"}
        packet, warning = _read_json(cache_path), ""
    else:
        packet, warning = _request_json(DART_COMPANY_URL, {"crtfc_key": key, "corp_code": code},
                                        cache_path, ttl_hours=24)
    if not isinstance(packet, dict) or packet.get("status") != "000":
        return {"ok": False, "reason": "dart_company_unavailable",
                "status": packet.get("status") if isinstance(packet, dict) else None}
    if packet.get("corp_code") != code:
        return {"ok": False, "reason": "dart_company_identity_mismatch"}
    return {"ok": True, "profile": packet, "source": "dart_company", "warning": warning}


def _num(value) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "nan", "None"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text)
        return -number if negative else number
    except Exception:
        return None


def _account_matches(account: str, patterns: list[str]) -> bool:
    hay = re.sub(r"\s+", "", str(account or "")).lower()
    return any(re.sub(r"\s+", "", pattern).lower() in hay for pattern in patterns)


def _metric_for_account(account_name: str, account_id: str = "") -> str | None:
    norm_id = re.sub(r"\s+", "", str(account_id or "")).lower()
    exact = ACCOUNT_ID_METRICS.get(norm_id)
    if exact:
        return exact
    # 표준계정코드가 있는데 정확 일치 표에 없으면 다른 계정이다(세전이익·지분법이익 등).
    # 이름 매칭은 코드가 없거나("-표준계정코드 미사용-" 등) 비표준일 때만 대체 경로로 쓴다.
    for metric, patterns in ACCOUNT_PATTERNS.items():
        if not _account_matches(account_name, patterns):
            continue
        if _account_matches(account_name, ACCOUNT_EXCLUDES.get(metric, [])):
            continue
        return metric
    return None


def _select_statement_rows(rows: list[dict]) -> list[dict]:
    consolidated = [row for row in rows if row.get("fs_div") == "CFS"]
    return consolidated or rows


def fetch_financial_rows(corp_code: str, cache_dir: Path, api_key: str, years: list[int]) -> tuple[list[dict], list[str]]:
    warnings = []
    metric_rows: dict[str, dict] = {}
    for year in years:
        data, error = _request_json(
            DART_FINANCIAL_ALL_URL,
            {
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": DART_REPORT_CODES["annual"],
                "fs_div": "CFS",
            },
            cache_dir / "financials" / f"{corp_code}_{year}_annual.json",
            ttl_hours=12,
        )
        if error:
            warnings.append(error)
        if not data or data.get("status") not in {"000", "013"}:
            if data and data.get("message"):
                warnings.append(f"{year}: {data.get('message')}")
            continue
        for row in _select_statement_rows(data.get("list") or []):
            metric = _metric_for_account(row.get("account_nm", ""), row.get("account_id", ""))
            value = _num(row.get("thstrm_amount"))
            if not metric or value is None:
                continue
            item = {
                "val": value,
                "end": f"{year}-12-31",
                "fy": str(year),
                "form": "DART",
                "fp": "FY",
                "account": row.get("account_nm", ""),
            }
            metric_row = metric_rows.setdefault(metric, {"metric": metric, "concept": row.get("account_nm", ""), "annual": [], "quarterly": [], "recent": []})
            if not any(existing.get("fy") == str(year) for existing in metric_row["annual"]):
                metric_row["annual"].append(item)
    for row in metric_rows.values():
        row["annual"].sort(key=lambda item: item.get("end", ""), reverse=True)
        row["annual"] = row["annual"][:3]
        row["recent"] = row["annual"][:3]
    return list(metric_rows.values()), warnings


def recent_disclosures(corp_code: str, cache_dir: Path, api_key: str, limit: int = 5) -> tuple[list[dict], str]:
    today = dt.datetime.now().strftime("%Y%m%d")
    start = (dt.datetime.now() - dt.timedelta(days=365 * 2)).strftime("%Y%m%d")
    data, error = _request_json(
        DART_DISCLOSURE_LIST_URL,
        {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bgn_de": start,
            "end_de": today,
            "page_count": str(limit),
        },
        cache_dir / "disclosures" / f"{corp_code}_recent.json",
        ttl_hours=12,
    )
    if not data or data.get("status") not in {"000", "013"}:
        return [], error or (data or {}).get("message", "")
    return (data.get("list") or [])[:limit], error


def dart_summary_to_markdown(summary: dict) -> str:
    if not summary.get("ok"):
        return summary.get("markdown", "DART financials unavailable.")
    lines = [
        f"DART structured financial data: {summary.get('entityName') or ''} (corp_code {summary.get('corpCode')})",
    ]
    if summary.get("warning"):
        lines.append(f"주의: {summary['warning']}")
    lines += [
        "",
        "| Metric | Recent Annual | DART Account |",
        "| --- | --- | --- |",
    ]
    for row in summary.get("rows", []):
        values = " / ".join(f"{item.get('end')}: {item.get('val'):,.0f}" for item in row.get("annual", [])[:3])
        lines.append(f"| {row.get('metric')} | {values or '확인되지 않음'} | {row.get('concept') or ''} |")
    return "\n".join(lines)


def build_dart_summary(company: dict, cache_dir: Path, api_key: str | None = None) -> dict:
    api_key = (api_key or dart_api_key()).strip()
    # DART fnlttSinglAcntAll의 thstrm_amount는 원화다. currency가 비면 _reporting_currency()가
    # USD로 떨어져 국내 기업 재무 전액이 $로 표기되고 mixed_currency 오탐 경고까지 붙는다.
    # 실패 반환에도 넣는다 — is_kr_company면 이 dict이 그대로 sec_facts가 되기 때문이다.
    if not api_key:
        return {"ok": False, "reason": "missing_dart_api_key", "company": company, "currency": "KRW", "markdown": "DART: API 키가 설정되지 않았습니다."}
    corp_code = str(company.get("corpCode") or "").strip()
    resolved = None
    if not corp_code:
        resolved = resolve_dart_company(company.get("ticker") or company.get("name"), cache_dir, api_key)
        corp_code = str((resolved or {}).get("corpCode") or "").strip()
    if not corp_code:
        return {"ok": False, "reason": "no_corp_code", "company": company, "currency": "KRW", "markdown": "DART: corp_code를 찾지 못했습니다."}
    fiscal_year = dt.datetime.now().year - 1
    years = [fiscal_year - offset for offset in range(3)]
    rows, warnings = fetch_financial_rows(corp_code, cache_dir, api_key, years)
    disclosures, disclosure_warning = recent_disclosures(corp_code, cache_dir, api_key)
    if disclosure_warning:
        warnings.append(disclosure_warning)
    entity_name = company.get("name") or (resolved or {}).get("name") or ""
    summary = {
        "ok": bool(rows),
        "corpCode": corp_code,
        "entityName": entity_name,
        "rows": rows,
        "disclosures": disclosures,
        "warning": "; ".join(dict.fromkeys([w for w in warnings if w]))[:800],
        "source": "DART Open API",
        "currency": "KRW",
    }
    if not rows:
        summary["reason"] = "no_financial_rows"
        summary["markdown"] = f"DART: 재무제표 주요 계정을 찾지 못했습니다. {summary.get('warning', '')}".strip()
        return summary
    summary["markdown"] = dart_summary_to_markdown(summary)
    return summary

