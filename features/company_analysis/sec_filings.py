#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import CancelledError

from features.common.utils import strip_html_text
from features.company_analysis.sec_companyfacts import normalize_cik, sec_user_agent

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
# 연차보고서 form. 국내 제출사는 10-K, 외국 민간 발행인은 20-F를 낸다.
ANNUAL_REPORT_FORMS = ("10-K", "20-F")

SECTOR_KEYWORDS = {
    "Semiconductors": {
        "items": ["1", "1A", "7", "7A"],
        "keywords": ["data center", "gpu", "semiconductor", "ai", "accelerated computing", "supply", "inventory", "customer", "margin", "export control"],
    },
    "Internet": {
        "items": ["1", "1A", "7"],
        "keywords": ["advertising", "cloud", "ai", "users", "engagement", "traffic", "regulation", "privacy", "margin", "capex"],
    },
    "Software": {
        "items": ["1", "1A", "7"],
        "keywords": ["cloud", "subscription", "arr", "retention", "ai", "security", "enterprise", "margin", "revenue"],
    },
    "Mobility": {
        "items": ["1", "1A", "7", "7A"],
        "keywords": ["mobility", "delivery", "freight", "driver", "consumer", "marketplace", "gross bookings", "take rate", "insurance", "regulation"],
    },
    "Healthcare": {
        "items": ["1", "1A", "7"],
        "keywords": ["reimbursement", "pharmaceutical", "distribution", "customer", "margin", "regulation", "opioid", "working capital"],
    },
    "Industrials": {
        "items": ["1", "1A", "7", "7A"],
        "keywords": ["machinery", "equipment", "construction", "mining", "energy", "transportation", "dealer", "manufacturing", "backlog", "inventory", "services", "margin", "cyclical"],
    },
    "Machinery": {
        "items": ["1", "1A", "7", "7A"],
        "keywords": ["machinery", "equipment", "construction", "mining", "energy", "transportation", "dealer", "manufacturing", "backlog", "inventory", "services", "margin", "cyclical"],
    },
}

DEFAULT_PROFILE = {
    "items": ["1", "1A", "7", "7A", "8"],
    "keywords": ["revenue", "margin", "growth", "risk", "competition", "customer", "cash flow", "liquidity", "regulation", "strategy"],
}

VALUATION_KEYWORDS = [
    "free cash flow", "operating cash flow", "capital expenditures", "capex", "depreciation",
    "amortization", "working capital", "interest expense", "tax rate", "effective tax",
    "share repurchase", "repurchases", "dividend", "capital allocation", "debt", "liquidity",
    "segment", "backlog", "pricing", "guidance", "outlook", "demand", "inventory",
]


def read_json(path: Path, fallback=None):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class SourceFetchError(str):
    """String-compatible public diagnostic; no URL, secret or exception text."""
    def __new__(cls, message, code="source_request_failed", http_status=None):
        instance = super().__new__(cls, message)
        instance.code, instance.http_status = code, http_status
        return instance


def source_failure(error: Exception) -> dict:
    status = error.code if isinstance(error, urllib.error.HTTPError) else None
    if status in {404, 410}:
        code = "source_not_found"
    elif status in {401, 403}:
        code = "source_access_denied"
    elif status in {408, 429} or status is not None and 500 <= status <= 599:
        code = "provider_error"
    elif isinstance(error, (TimeoutError, ConnectionError, urllib.error.URLError)) and status is None:
        code = "provider_error"
    else:
        code = "source_request_failed"
    return {"code": code, "httpStatus": status}


def fetch_text(url: str, cache_path: Path, ttl_hours: int = 24) -> tuple[str, str]:
    cached = read_json(cache_path, None)
    if cached and cached.get("text") and cached.get("fetchedAt"):
        try:
            fetched = dt.datetime.fromisoformat(cached["fetchedAt"])
            if dt.datetime.now(dt.timezone.utc) - fetched < dt.timedelta(hours=ttl_hours):
                error = cached.get("error", "")
                diagnostic = cached.get("diagnostic") or {}
                return cached["text"], SourceFetchError(error, diagnostic.get("code", "source_request_failed"), diagnostic.get("httpStatus")) if error else ""
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": sec_user_agent(), "Accept": "text/html,application/json"})
    try:
        with urllib.request.urlopen(req, timeout=int(os.environ.get("SEC_TIMEOUT_SECONDS", "30"))) as resp:
            raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        write_json(cache_path, {"fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "url": url, "text": text, "error": ""})
        return text, ""
    except CancelledError:
        raise
    except Exception as error:
        diagnostic = source_failure(error)
        public_error = "SEC request failed"
        if cached and cached.get("text"):
            return cached["text"], SourceFetchError("using cached SEC filing after fetch error", diagnostic["code"], diagnostic["httpStatus"])
        # Only public SEC content and a stable failure code are cached.
        # codeql[py/clear-text-storage-sensitive-data]
        write_json(cache_path, {"fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "url": url, "text": "", "error": public_error, "diagnostic": diagnostic})
        return "", SourceFetchError(public_error, diagnostic["code"], diagnostic["httpStatus"])


def get_company_submissions(cik: str, cache_dir: Path) -> tuple[dict, str]:
    cik = normalize_cik(cik)
    if not cik:
        return {}, "missing CIK"
    text, error = fetch_text(SEC_SUBMISSIONS_URL.format(cik=cik), cache_dir / "submissions" / f"CIK{cik}.json", ttl_hours=12)
    if not text:
        return {}, error
    try:
        return json.loads(text), error
    except Exception:
        return {}, "SEC response parse failed"


def latest_annual_report_metadata(cik: str, cache_dir: Path, forms=None) -> dict:
    """Newest annual report of any accepted form.

    A foreign private issuer files 20-F where a domestic filer files 10-K. The
    old lookup matched `10-K` alone, so a 20-F filer had no document URL at all
    and its narrative came back empty with `no_10k` — the failure looked like a
    missing filing rather than an unsupported form.
    """
    accepted = tuple(forms or ANNUAL_REPORT_FORMS)
    data, error = get_company_submissions(cik, cache_dir)
    recent = data.get("filings", {}).get("recent", {}) if data else {}
    forms = recent.get("form", []) or []
    accessions = recent.get("accessionNumber", []) or []
    docs = recent.get("primaryDocument", []) or []
    dates = recent.get("filingDate", []) or []
    reports = recent.get("reportDate", []) or []
    for idx, form in enumerate(forms):
        if form in accepted and idx < len(accessions) and idx < len(docs):
            accession = accessions[idx]
            accession_plain = accession.replace("-", "")
            cik_plain = str(int(cik))
            url = f"{SEC_ARCHIVES_BASE}/{cik_plain}/{accession_plain}/{docs[idx]}"
            return {
                "ok": True,
                "cik": cik,
                "entityName": data.get("name", ""),
                "sic": data.get("sic", ""),
                "sicDescription": data.get("sicDescription", ""),
                "form": form,
                "accession": accession,
                "filingDate": dates[idx] if idx < len(dates) else "",
                "reportDate": reports[idx] if idx < len(reports) else "",
                "primaryDocument": docs[idx],
                "url": url,
                "error": error,
            }
    return {"ok": False, "cik": cik, "error": error or f"No recent {'/'.join(accepted)} found"}


def latest_10k_metadata(cik: str, cache_dir: Path) -> dict:
    """Back-compatible alias; existing callers keep the 10-K-only behaviour."""
    return latest_annual_report_metadata(cik, cache_dir, forms=("10-K",))


def _clean_lines(markup: str) -> list[str]:
    text = strip_html_text(markup, separator="\n")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]


def _is_paragraph(line: str) -> bool:
    return len(line) >= 80 and not re.fullmatch(r"[\d\s.,$%()/-]+", line)


def html_to_paragraphs(markup: str) -> list[str]:
    return [line for line in _clean_lines(markup) if _is_paragraph(line)]


def paragraphs_with_items(markup: str, form: str = "10-K"):
    """Yield ``(item, paragraph)`` with section headings read before filtering.

    Section headings are short by nature and the paragraph filter drops short
    lines, so looking for `ITEM 5.` only inside kept paragraphs finds it only
    when a filing happens to inline the heading with body text. ASML's 20-F puts
    each heading on its own line, so every paragraph came back `Unknown` and the
    section weighting never applied.
    """
    # Linked contents tables can have Item numbers that never appear in the
    # actual body. Do not carry the final contents entry into unlabeled prose.
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(markup, "html.parser")
    for table in list(soup.find_all("table")):
        if table.parent is None:
            continue
        labels = re.findall(r"\bItem\s+\d+[A-Z]?\b", table.get_text(" "), re.I)
        links = table.select('a[href^="#"]')
        if len(labels) >= 2 and len(links) >= 2:
            for row in table.find_all("tr"):
                label = re.search(_ITEM_PATTERNS.get(form, _ITEM_PATTERNS['10-K']), row.get_text(" "), re.I)
                link = row.select_one('a[href^="#"]')
                if label and link:
                    anchor = link['href'][1:]
                    target = soup.find(id=anchor) or soup.find('a', attrs={'name': anchor})
                    if target and table not in target.parents:
                        heading = soup.new_tag('div')
                        heading.string = 'ITEM ' + label.group(1)
                        target.insert_before(heading)
            table.decompose()
    if form == '10-K':
        for block in list(soup.find_all(['div', 'p', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])):
            # Only standalone body headings: exclude table contents, links,
            # and spans embedded in prose that happens to cite this title.
            title = re.sub(r'\s+', ' ', block.get_text(' ')).strip()
            section = ('8' if re.fullmatch(r'(?:Notes to (?:the )?)?Consolidated Financial Statements', title, re.I) else
                       '7' if re.fullmatch(r'Management[’\']s Discussion and Analysis of Financial Condition(?:s)? and Results of Operations', title, re.I) else '')
            if not section:
                continue
            table = block.find_parent('table')
            links = table.select('a[href]') if table else []
            running_header = bool(links) and len(table.get_text(' ', strip=True)) < 240 and all(
                re.fullmatch(r'(?:Financial )?Table of Contents', a.get_text(' ', strip=True), re.I) for a in links)
            if (table and not running_header) or block.find_parent('a') or block.find('a') or block.find(['div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                continue
            if section:
                heading = soup.new_tag('div')
                heading.string = 'ITEM ' + section
                block.insert_before(heading)
    # Inline cross-reference anchors are split onto their own lines by the
    # text reader. They must not reset the current section to their target.
    reference_marker = '__FOLIO_INLINE_REFERENCE__'
    for anchor in soup.select('a[href]'):
        label = re.sub(r'\s+', ' ', anchor.get_text(' ')).strip()
        block = anchor.find_parent(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        block_text = re.sub(r'\s+', ' ', block.get_text(' ')).strip() if block else ''
        semantic_heading = block is not None and block.name in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
        if re.match(r'Item\s+\d', label, re.I) and block_text != label and not semantic_heading:
            anchor.string = reference_marker + label
    markup = str(soup)
    current = ""
    for line in _clean_lines(markup):
        if line.startswith(reference_marker):
            line = line[len(reference_marker):]
        else:
            current = item_for_paragraph(line, current, form)
        if _is_paragraph(line):
            yield current, line


# 20-F는 10-K와 Item 번호 체계가 다르다. 같은 번호가 다른 내용을 가리키므로
# form을 모르고 읽으면 사업 개요 자리에서 위험 요소를 읽게 된다.
#   10-K: 1 사업 · 1A 위험 · 7 MD&A · 7A 시장위험 · 8 재무제표
#   20-F: 3.D 위험 · 4 회사 정보 · 5 경영진 논의 · 11 시장위험 · 18/19 재무제표
#   10-Q: Part I 1 재무제표 · 2 MD&A · 3 시장위험 / Part II 1A 위험
_ITEM_PATTERNS = {
    "10-K": r"\bITEM\s+(\d{1,2}[A-C]?)\b",
    "20-F": r"\bITEM\s+(3\.?D|3|4A|4|5|11|18|19)\b",
    "10-Q": r"\bITEM\s+(1A|1|2|3|4)\b",
}
FINANCIAL_DISCUSSION_ITEMS = {
    "10-K": {"7", "7A", "8"},
    "20-F": {"5", "11", "18"},
    # 분기보고서에서 서술의 무게는 MD&A(2)와 시장위험(3)에 있다.
    "10-Q": {"2", "3", "1"},
}
# 섹터 프로필의 `items`는 10-K 번호로 쓰여 있다. 20-F에 그대로 대면 사업 개요
# 자리(10-K의 1)가 20-F의 Item 1(제출사 신원)에 가산되고, 정작 MD&A인 Item 5는
# 아무 가산도 못 받는다. 같은 뜻의 구획끼리 옮긴다.
_ITEM_EQUIVALENTS = {
    "20-F": {"1": "4", "1A": "3D", "7": "5", "7A": "11", "8": "18"},
    # 10-Q에는 사업 개요(10-K의 1)에 해당하는 구획이 없다. MD&A로 옮긴다.
    "10-Q": {"1": "2", "7": "2", "7A": "3", "8": "1"},
}


def equivalent_items(items, form: str) -> set[str]:
    """Translate 10-K-numbered section lists into the given form's numbering."""
    mapping = _ITEM_EQUIVALENTS.get(str(form or "").upper())
    if not mapping:
        return {str(item).upper() for item in items or ()}
    return {mapping.get(str(item).upper(), str(item).upper()) for item in items or ()}


def item_for_paragraph(paragraph: str, current_item: str, form: str = "10-K") -> str:
    pattern = _ITEM_PATTERNS.get(str(form or "").upper(), _ITEM_PATTERNS["10-K"])
    # A prose cross-reference ("Refer to Item 1A") is not a section heading.
    match = re.match(r"^\s*(?:PART\s+[IVX]+[.\s:-]*)?" + pattern, paragraph, flags=re.I)
    if match:
        return match.group(1).upper().replace(".", "")
    return current_item


def profile_for_sector(sector: str) -> dict:
    label = str(sector or "").strip()
    if label in SECTOR_KEYWORDS:
        return SECTOR_KEYWORDS[label]
    lower = label.lower()
    if any(token in lower for token in ["machinery", "construction", "industrial", "equipment", "manufacturing"]):
        return SECTOR_KEYWORDS["Machinery"]
    return DEFAULT_PROFILE


def score_paragraph(paragraph: str, *, sector: str, item: str, form: str = "10-K") -> tuple[int, list[str]]:
    profile = profile_for_sector(sector)
    hay = paragraph.lower()
    hits = []
    score = 0
    if item in equivalent_items(profile["items"], form):
        score += 8
    for keyword in profile["keywords"]:
        if keyword.lower() in hay:
            hits.append(keyword)
            score += 5
    for keyword in ["revenue", "operating income", "cash flow", "margin", "risk", "competition", "regulation", "liquidity"]:
        if keyword in hay and keyword not in hits:
            hits.append(keyword)
            score += 2
    for keyword in VALUATION_KEYWORDS:
        if keyword in hay and keyword not in hits:
            hits.append(keyword)
            score += 3
    financial_items = FINANCIAL_DISCUSSION_ITEMS.get(str(form or "").upper(), FINANCIAL_DISCUSSION_ITEMS["10-K"])
    if item in financial_items and any(keyword in hay for keyword in VALUATION_KEYWORDS):
        score += 5
    if 180 <= len(paragraph) <= 1800:
        score += 2
    if len(paragraph) > 2600:
        score -= 3
    return score, hits


def ranked_annual_report_paragraphs(company: dict, cache_dir: Path, max_paragraphs: int = 14) -> dict:
    """Score the narrative sections of the newest 10-K or 20-F.

    CIK는 직접 해결한다. 예전에는 `company["cik"]`만 읽어서, 그 값을 채워주지 못한
    호출자에게는 조용히 빈 결과를 돌려줬다. 같은 company dict를 받는 companyfacts는
    티커로 CIK를 스스로 찾기 때문에, **숫자는 오는데 공시 서술만 빠지는** 보고서가
    나왔다. 두 경로가 같은 해결기를 쓰면 그 비대칭이 생기지 않는다.
    """
    return _ranked_filing_paragraphs(company, cache_dir, ANNUAL_REPORT_FORMS, "no_annual_report", max_paragraphs)


def ranked_quarterly_report_paragraphs(company: dict, cache_dir: Path, max_paragraphs: int = 8) -> dict:
    """가장 최근 10-Q의 서술 문단.

    연차보고서만 읽으면 8월에 만든 보고서가 1월에 끝난 회계연도의 서술로 회사를
    설명한다. 그 사이 두 분기에 무슨 일이 있었는지는 MD&A(Item 2)에 있다.
    연차보고서를 대체하지 않고 최근 분기를 덧붙이는 용도다.
    """
    return _ranked_filing_paragraphs(company, cache_dir, ("10-Q",), "no_quarterly_report", max_paragraphs)


def _ranked_filing_paragraphs(company: dict, cache_dir: Path, forms, missing_reason: str, max_paragraphs: int) -> dict:
    from features.company_analysis.sec_companyfacts import resolve_cik

    cik = resolve_cik(company, cache_dir)
    if not cik:
        return {"ok": False, "reason": "no_cik", "paragraphs": [], "metadata": {}}
    metadata = latest_annual_report_metadata(cik, cache_dir, forms=forms)
    if not metadata.get("ok"):
        return {"ok": False, "reason": missing_reason, "paragraphs": [], "metadata": metadata}
    form = str(metadata.get("form") or forms[0]).upper()
    # 캐시 키에 form을 넣는다. 같은 회사가 form을 바꾸면 예전 문서를 계속 읽는다.
    cache_name = f"{cik}_{form.replace('/', '-')}_{metadata['accession']}.json"
    html_text, error = fetch_text(metadata["url"], cache_dir / "html_10k" / cache_name, ttl_hours=24 * 30)
    if not html_text:
        metadata["error"] = error
        return {"ok": False, "reason": "fetch_failed", "paragraphs": [], "metadata": metadata}
    sector = company.get("sector", "")
    if not sector or sector == "Unclassified":
        sector = metadata.get("sicDescription", "")
    rows = []
    for current_item, para in paragraphs_with_items(html_text, form):
        score, hits = score_paragraph(para, sector=sector, item=current_item, form=form)
        if score <= 0:
            continue
        rows.append(
            {
                "item": current_item or "Unknown",
                "score": score,
                "keywords": hits[:8],
                "text": para[:1800],
            }
        )
    rows.sort(key=lambda row: (row["score"], len(row["keywords"])), reverse=True)
    return {
        "ok": True, "metadata": metadata, "form": form,
        "paragraphs": rows[:max_paragraphs], "count": len(rows),
    }


def ranked_10k_paragraphs(company: dict, cache_dir: Path, max_paragraphs: int = 14) -> dict:
    """Back-compatible alias. 20-F filers now resolve through the same path."""
    return ranked_annual_report_paragraphs(company, cache_dir, max_paragraphs=max_paragraphs)


def ranked_paragraphs_to_markdown(result: dict) -> str:
    metadata = result.get("metadata", {}) or {}
    # 이 함수는 연차(10-K/20-F)와 분기(10-Q) 발췌 모두를 렌더한다. 문구를 10-K로
    # 박아 두면 10-Q MD&A 발췌가 연차보고서 서술로 읽힌다.
    form = str(result.get("form") or metadata.get("form") or "").strip()
    doc_label = f"SEC {form}" if form else "SEC filing"
    if not result.get("ok"):
        return f"{doc_label} HTML paragraphs unavailable: {result.get('reason') or metadata.get('error') or 'unknown'}"
    lines = [
        f"{doc_label} HTML filing metadata",
        f"- Form: {metadata.get('form', '')}",
        f"- Filing date: {metadata.get('filingDate', '')}",
        f"- Report date: {metadata.get('reportDate', '')}",
        f"- Accession: {metadata.get('accession', '')}",
        f"- URL: {metadata.get('url', '')}",
        "",
        f"Top scored {form or 'filing'} paragraphs by sector/GICS profile",
    ]
    for idx, row in enumerate(result.get("paragraphs", []), 1):
        lines.append(
            f"[{idx}] Item {row.get('item')} | score={row.get('score')} | keywords={', '.join(row.get('keywords', []))}\n"
            f"{row.get('text', '')}\n"
        )
    return "\n".join(lines)

