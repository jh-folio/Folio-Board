"""Company analysis service — scoring, context building, report management, charts."""
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from features.common.dataframe_ops import sort_records
from features.common.canonical_identity import ReportKind
from features.common.canonical_report_state import load_report
from features.common.canonical_report_types import WriteKind
from features.common.canonical_reports import commit_sync, prepare
from features.common.change_intelligence.service import decorate_candidate, project_committed_report
from features.common.utils import normalize, now_iso, read_json, write_json
from features.company_analysis import financial_engine
from features.company_analysis.dart_client import build_dart_summary
from features.company_analysis.filing_items import select_analysis_items, select_filing_keyword_excerpts
from features.company_analysis.depth_policy import render_length_contract
from features.company_analysis.report_contract import render_quality_requirements, render_source_contract
from features.company_analysis.style import analysis_prompt_path, read_analysis_prompt
from features.company_analysis.report_rules import (
    _fcf_series,
    _latest_metric_value,
    build_financial_quality_analysis,
    build_financial_table,
    build_valuation_metrics,
    fetch_market_valuation_data,
)
from features.company_analysis.sec_companyfacts import build_companyfacts_summary
from features.company_analysis.sec_filings import (
    ranked_10k_paragraphs,
    ranked_paragraphs_to_markdown,
    ranked_quarterly_report_paragraphs,
)
from features.llm_settings.client import (
    request_claude,
    request_gemini,
    request_openai,
    selected_llm_config,
    strip_llm_citation_markers,
    use_llm_analysis,
    use_web_search_for_analysis,
)
from features.common.quality_generation.prompt_hints import render_prompt_hints
from features.common.quality_generation.preflight_enrichment import build_preflight_evidence_context
from features.common.quality_generation.quality_targets import render_quality_target_context
from features.common.quality_generation.telemetry import normalize_token_usage
from features.common.web_search_scope import load_source_scope, render_scope_instruction
from features.market_memory.snapshot import render_market_memory_context
from features.common.generation_engine import engine_detail, engine_label
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = data_dir()
FEATURES_DIR = ROOT / "features"
ANALYSIS_REPORTS_DIR = DATA_DIR / "company-analysis"
SEC_CACHE_DIR = DATA_DIR / "sec-cache"
DART_CACHE_DIR = DATA_DIR / "dart-cache"
COMPANY_ANALYSIS_PROMPT_PATH = FEATURES_DIR / "company_analysis" / "prompt.md"
FINANCIAL_QUALITY_PROMPT_PATH = FEATURES_DIR / "company_analysis" / "financial_quality_prompt.md"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"

TRUSTED_SOURCES = {
    "Reuters": 10,
    "Bloomberg": 10,
    "WSJ": 10,
    "Barron's": 10,
    "Financial Times": 10,
    "CNBC": 8,
    "MarketWatch": 7,
    "한국경제": 9,
    "매일경제": 9,
    "연합인포맥스": 9,
    "User Archive": 5,
}

KR_DOMESTIC_SOURCES = {"한국경제", "매일경제", "연합인포맥스", "연합뉴스"}

COMPANY_ANALYSIS_BUCKETS = {
    "financial": ["revenue", "sales", "earnings", "income", "margin", "profit", "eps", "cash flow", "free cash flow", "capex", "debt", "liquidity", "balance sheet", "guidance", "실적", "매출", "이익", "마진", "현금흐름", "부채", "가이던스"],
    "business": ["business", "segment", "product", "service", "customer", "platform", "market share", "pricing", "backlog", "order", "사업", "제품", "서비스", "고객", "점유율", "수주"],
    "growth": ["growth", "strategy", "expansion", "investment", "ai", "automation", "international", "partnership", "capacity", "demand", "성장", "전략", "투자", "확장", "수요", "파트너십"],
    "risk": ["risk", "regulation", "lawsuit", "competition", "tariff", "supply chain", "cybersecurity", "inflation", "rate", "geopolitical", "리스크", "규제", "소송", "경쟁", "관세", "공급망", "금리"],
    "valuation": ["valuation", "multiple", "target price", "buyback", "repurchase", "dividend", "capital allocation", "shareholder", "m&a", "free cash flow yield", "wacc", "dcf", "밸류에이션", "목표주가", "자사주", "배당", "주주환원", "인수"],
}

IR_EARNINGS_TERMS = ["investor relations", "ir deck", "presentation", "earnings call", "transcript", "prepared remarks", "shareholder letter", "guidance", "outlook", "실적발표", "컨퍼런스콜", "ir", "프레젠테이션", "가이던스"]

OFFICIAL_FILING_TERMS = [
    "10-k", "10 k", "annual report", "form 10-k",
    "10-q", "10 q", "quarterly report", "form 10-q",
    "20-f", "40-f", "8-k", "6-k",
    "s-1", "s 1", "form s-1", "f-1", "form f-1",
    "424b", "prospectus", "registration statement",
    "def 14a", "proxy statement",
    "사업보고서", "분기보고서", "반기보고서", "증권신고서", "투자설명서",
]



def _source_weight(source):
    return TRUSTED_SOURCES.get(source, 5)


def _doc_markets(doc):
    raw = doc.get("markets")
    if isinstance(raw, list):
        return {str(item).strip().upper() for item in raw if str(item).strip()}
    raw = doc.get("market") or ""
    return {token.strip().upper() for token in str(raw).split(",") if token.strip()}


def _is_us_company(company):
    return str((company or {}).get("market") or "").upper() == "US"


def term_in_text(term, hay):
    token = str(term or "").lower()
    if not token:
        return False
    if re.fullmatch(r"[a-z0-9]+", token):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", hay))
    return token in hay


def company_terms(company):
    return [company.get("name", ""), company.get("ticker", ""), *company.get("aliases", [])]


def company_term_matches(term, hay):
    token = str(term or "").strip()
    if not token:
        return False
    lower = token.lower()
    common_words = {"apple", "meta", "alphabet", "kia", "cat", "snow", "coin", "on"}
    if lower in common_words:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(lower)}(?![a-z0-9])", hay))
    return term_in_text(token, hay)


def company_matches_query(company, query):
    hay = normalize(query).lower()
    if not hay:
        return False
    return any(company_term_matches(term, hay) or hay == str(term or "").lower() for term in company_terms(company))


def clean_brief_text(text, limit=420):
    text = normalize(text)
    text = re.sub(r"Original link:\s*https?://\S+", " ", text, flags=re.I)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"(^|\s)#\s*", " ", text)
    text = re.sub(r"\s+-\s+Reuters\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -")
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "..."


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def read_company_analysis_prompt(analysis_style="beginner"):
    try:
        prompt = read_analysis_prompt(analysis_style)
        if FINANCIAL_QUALITY_PROMPT_PATH.exists():
            prompt += "\n\n---\n\n" + FINANCIAL_QUALITY_PROMPT_PATH.read_text(encoding="utf-8")
        return prompt
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Document scoring and prioritisation
# ---------------------------------------------------------------------------

def company_doc_priority(doc):
    rel = str(doc.get("path", "")).replace("\\", "/").lower()
    if rel.startswith("research-inbox/filings/") or doc.get("type") == "filing":
        return 0
    if rel.startswith("research-inbox/reports/") or doc.get("type") == "report":
        return 1
    if rel.startswith("research-inbox/articles/"):
        return 2
    if rel.startswith("research-inbox/rss/"):
        return 3
    return 4


def company_specificity_score(doc, company, query=""):
    title = normalize(doc.get("title", ""))
    content = normalize(doc.get("content", "") or doc.get("summary", ""))
    path = normalize(doc.get("path", ""))
    url = normalize(doc.get("url", ""))
    full = f"{title}\n{content}\n{path}\n{url}"
    hay = full.lower()
    title_hay = title.lower()
    query_hay = normalize(query).lower()
    score = 0
    reasons = []
    name = normalize(company.get("name", ""))
    ticker = normalize(company.get("ticker", "")).upper().lstrip("$")
    aliases = [normalize(a) for a in company.get("aliases", []) if normalize(a)]
    terms = [name, ticker, *aliases]
    terms = [t for t in terms if t]

    query_is_ticker = ticker and query_hay == ticker.lower()
    if query_hay and not query_is_ticker and len(query_hay) >= 4 and (term_in_text(query_hay, title_hay) or term_in_text(query_hay, hay)):
        score += 10
        reasons.append("검색어 일치")
    if name and len(name) >= 4 and name.lower() in title_hay:
        score += 34
        reasons.append("제목에 회사명")
    elif name and len(name) >= 4 and name.lower() in hay:
        score += 22
        reasons.append("본문에 회사명")

    if ticker:
        ticker_pattern = rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])"
        if re.search(ticker_pattern, title):
            score += 32
            reasons.append("제목에 티커")
        elif re.search(ticker_pattern, full):
            score += 18
            reasons.append("본문에 티커")

    for alias in aliases:
        lower = alias.lower()
        if len(lower) < 4 or lower in {ticker.lower(), name.lower()}:
            continue
        if lower in title_hay:
            score += 18
            reasons.append("제목에 별칭")
            break
        if lower in hay:
            score += 10
            reasons.append("본문에 별칭")
            break

    doc_companies = doc.get("companies", []) or []
    for c in doc_companies:
        if any(company_term_matches(term, normalize(f"{c.get('name', '')} {c.get('ticker', '')}").lower()) for term in terms):
            score += 22
            reasons.append("인덱스 기업 태그 일치")
            break

    if score == 0 and query_hay and len(query_hay) >= 4 and term_in_text(query_hay, hay):
        score += 8
        reasons.append("본문 검색어 약한 일치")
    return score, reasons


def company_analysis_bucket_for_doc(doc):
    hay = normalize(" ".join([
        doc.get("title", ""),
        doc.get("summary", ""),
        doc.get("content", "")[:3500],
        " ".join(doc.get("sectors", [])),
        " ".join(doc.get("impactTags", [])),
    ])).lower()
    bucket_scores = {}
    for bucket, terms in COMPANY_ANALYSIS_BUCKETS.items():
        bucket_scores[bucket] = sum(1 for term in terms if term.lower() in hay)
    bucket, score = max(bucket_scores.items(), key=lambda item: item[1])
    return bucket if score else "general"


def company_analysis_doc_score(doc, company, query=""):
    priority = company_doc_priority(doc)
    score = {0: 42, 1: 34, 2: 18, 3: 12}.get(priority, 8)
    reasons = []
    if priority == 0:
        reasons.append("공식 공시")
    elif priority == 1:
        reasons.append("리포트/IR")
    elif priority in {2, 3}:
        reasons.append("뉴스/RSS")
    else:
        reasons.append("기타 로컬 자료")

    direct_score, direct_reasons = company_specificity_score(doc, company, query)
    score += direct_score
    reasons.extend(direct_reasons)

    words = int(doc.get("wordCount", 0) or 0)
    content = normalize(doc.get("content", "") or doc.get("summary", ""))
    hay = normalize(" ".join([doc.get("title", ""), doc.get("summary", ""), content[:5000], doc.get("path", ""), doc.get("url", "")])).lower()
    if not words:
        words = len(content.split())
    if words >= 3000:
        score += 22
        reasons.append("본문 충분")
    elif words >= 1000:
        score += 15
        reasons.append("본문 보통")
    elif words >= 250:
        score += 6
        reasons.append("본문 짧음")
    else:
        score -= 12
        reasons.append("본문 부족")

    source = doc.get("source", "") or "Unknown"
    score += min(int(doc.get("sourceWeight", 0) or _source_weight(source)), 30)
    markets = _doc_markets(doc)
    if _is_us_company(company) and priority in {2, 3}:
        if markets == {"KR"}:
            score -= 24
            reasons.append("미국 기업 분석에서 KR 전용 뉴스 감점")
        elif source in KR_DOMESTIC_SOURCES and "US" not in markets:
            score -= 14
            reasons.append("미국 기업 분석에서 국내 매체 보정")
    bucket = company_analysis_bucket_for_doc(doc)
    if bucket != "general":
        score += 8
        reasons.append(f"{bucket} 근거")
    if any(term.lower() in hay for term in IR_EARNINGS_TERMS):
        score += 18
        reasons.append("IR/실적발표 자료")
    if doc.get("url") or doc.get("path"):
        score += 3
    if "no summary available" in content.lower() or "original link:" in content.lower():
        score -= 10
        reasons.append("본문 정제 필요")
    if direct_score <= 8 and priority in {2, 3, 4}:
        score -= 18
        reasons.append("회사 직접성 낮음")
    return {
        **doc,
        "analysisScore": max(score, 0),
        "analysisBucket": bucket,
        "analysisReasons": list(dict.fromkeys(reasons))[:8],
    }


def company_direct_relevance(doc, company, query=""):
    score, reasons = company_specificity_score(doc, company, query)
    return score, reasons


def is_sec_filing_doc(doc):
    if company_doc_priority(doc) != 0:
        return False
    hay = normalize(" ".join([doc.get("title", ""), doc.get("path", ""), doc.get("content", "")[:2000]])).lower()
    if any(term in hay for term in OFFICIAL_FILING_TERMS):
        return True
    return str(doc.get("type") or "").lower() == "filing" and int(doc.get("wordCount", 0) or 0) >= 250


def filing_form_type(doc):
    hay = normalize(f"{doc.get('title', '')} {doc.get('path', '')} {doc.get('content', '')[:1200]}").lower()
    if any(term in hay for term in ["10-k", "10 k", "annual report", "form 10-k"]):
        return "10-K"
    if any(term in hay for term in ["10-q", "10 q", "quarterly report", "form 10-q"]):
        return "10-Q"
    if any(term in hay for term in ["20-f", "annual report on form 20-f"]):
        return "20-F"
    if any(term in hay for term in ["s-1", "s 1", "form s-1", "registration statement"]):
        return "S-1"
    if any(term in hay for term in ["f-1", "form f-1"]):
        return "F-1"
    if any(term in hay for term in ["8-k", "form 8-k", "current report"]):
        return "8-K"
    if any(term in hay for term in ["6-k", "form 6-k"]):
        return "6-K"
    if any(term in hay for term in ["424b", "prospectus", "투자설명서"]):
        return "Prospectus"
    if any(term in hay for term in ["def 14a", "proxy statement"]):
        return "Proxy"
    if "증권신고서" in hay:
        return "Securities Registration"
    return "filing"


def _filing_sort_rank(doc):
    form_type = filing_form_type(doc)
    ranks = {
        "10-K": 0,
        "20-F": 0,
        "10-Q": 1,
        "S-1": 2,
        "F-1": 2,
        "Securities Registration": 2,
        "Prospectus": 3,
        "8-K": 4,
        "6-K": 4,
        "Proxy": 5,
    }
    return ranks.get(form_type, 6)


def _excerpt_keywords(item: dict) -> list[str]:
    explicit = [str(k).lower() for k in item.get("keywords", []) if str(k).strip()]
    if explicit:
        return explicit[:8]
    text = normalize(item.get("text", "")).lower()
    keywords = []
    for keyword in [
        "business", "platform", "segment", "customer", "product", "service",
        "competition", "scale", "network", "technology", "brand",
        "risk", "regulation", "liquidity", "legal",
        "growth", "strategy", "investment", "margin", "cash flow", "ai",
        "revenue",
    ]:
        if keyword in text:
            keywords.append(keyword)
    return keywords[:8]


def _filing_paragraph_from_item(doc, form_type: str, item: dict) -> dict:
    return {
        "item": item.get("item") or item.get("label") or form_type,
        "text": item.get("text", ""),
        "keywords": _excerpt_keywords(item),
        "score": item.get("score", 70 if form_type in {"10-K", "10-Q", "20-F"} else 55),
        "source": doc.get("path") or doc.get("url") or doc.get("title", ""),
        "form": form_type,
    }


def _doc_context_text(doc, min_content_chars: int = 1000, max_file_chars: int = 2_000_000) -> str:
    content = str(doc.get("content") or "")
    if len(content) >= min_content_chars:
        return content
    raw_path = doc.get("absolutePath") or doc.get("path") or ""
    if not raw_path:
        return content or str(doc.get("summary") or "")
    try:
        # `documents.path`는 **자료 폴더 기준** 상대 경로다(`indexing/service.py::
        # workspace_relative()`). 여기만 앱 폴더(`ROOT`)를 기준으로 이어 붙이고 경계까지
        # 앱 폴더로 재던, `FOLIO_HOME`이 체크아웃 밖일 때 저장된 원문을 한 건도 못 읽는다.
        # `except Exception`이 삼켜서 터지지는 않지만, 10-K 원문 대신 스니펫·요약으로
        # 조용히 내려앉아 보고서가 얇아진다 — 실패했다는 사실이 어디에도 안 남는다.
        # 기본값에서는 자료 폴더가 곧 앱 폴더라 동작이 같다.
        from features.common.workspace import workspace_root

        base = workspace_root()
        path = Path(raw_path)
        if not path.is_absolute():
            path = base / path
        resolved = path.resolve()
        for root in (base.resolve(), ROOT.resolve()):
            try:
                resolved.relative_to(root)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"document path is outside the workspace: {resolved}")
        if not resolved.exists() or not resolved.is_file():
            return content or str(doc.get("summary") or "")
        if resolved.stat().st_size > max_file_chars * 4:
            # Large saved SEC HTML can be noisy. Read a bounded prefix; keyword
            # fallback still gets the registration header and major early risk sections.
            data = resolved.read_bytes()[: max_file_chars * 2]
            return data.decode("utf-8", errors="replace")
        return resolved.read_text(encoding="utf-8", errors="replace")[:max_file_chars]
    except Exception:
        return content or str(doc.get("summary") or "")


def build_filing_item_context(filing_docs, max_filings=2):
    lines = []
    used = []
    paragraphs = []
    # 같은 form 등급 안에서는 최신 공시가 먼저다. 오래된 것이 앞서면 max_filings에
    # 잘려 최신 공시가 통째로 빠지고 metadata.filingDate도 옛 공시를 가리킨다.
    # 날짜 없는 문서는 reverse 정렬에서 뒤로 밀린다.
    by_recent = sorted(filing_docs, key=lambda d: str(d.get("date", "")), reverse=True)
    for doc in sorted(by_recent, key=_filing_sort_rank)[:max_filings]:
        form_type = filing_form_type(doc)
        wanted = ["1", "1A", "7", "7A", "8"] if form_type in {"10-K", "20-F", "S-1", "F-1", "Securities Registration"} else ["1A", "7", "8"]
        context_text = _doc_context_text(doc)
        items = select_analysis_items(context_text, wanted=wanted)
        item_source = "item"
        if not items:
            items = select_filing_keyword_excerpts(context_text)
            item_source = "keyword_excerpt"
        if not items:
            continue
        used.append(doc)
        lines.append(
            f"### {form_type} Item excerpts: {doc.get('title', '')}\n"
            f"- Source file: {doc.get('path', '')}\n"
            f"- Date: {doc.get('date', '')}\n"
            f"- Extraction: {item_source}\n"
            f"- Rule: 아래 로컬 공식자료 발췌는 SEC/DART 구조화 숫자와 SEC 연차보고서 HTML 문단이 부족할 때 보조 공식자료로 사용하세요. 숫자는 SEC companyfacts/DART 또는 웹 검색 공식자료로 교차검증하세요.\n"
        )
        for item in items:
            paragraphs.append(_filing_paragraph_from_item(doc, form_type, item))
            lines.append(
                f"#### {item['label']} (excerpt, {len(item['text'])}/{item['availableChars']} chars)\n"
                f"{clean_brief_text(item['text'], len(item['text']))}\n"
            )
    return "\n".join(lines), used, paragraphs


def build_supporting_doc_context(docs, company=None, query="", max_reports=4, max_articles=6, max_other=2):
    company = company or {}
    scored = [company_analysis_doc_score(d, company, query) for d in docs]
    scored = sort_records(scored, ["analysisScore", "sourceWeight", "date"], descending=True)
    quotas = {
        "financial": 3,
        "business": 3,
        "growth": 3,
        "risk": 3,
        "valuation": 2,
        "general": 2,
    }
    type_limits = {1: max_reports, 2: max_articles, 3: max_articles, 4: max_other}
    type_counts = {}
    bucket_counts = {}
    selected = []
    seen = set()
    for d in scored:
        priority = company_doc_priority(d)
        if priority == 0:
            continue
        key = d.get("url") or d.get("path") or d.get("title")
        if not key or key in seen:
            continue
        if d.get("analysisScore", 0) < 30 and priority in {2, 3, 4}:
            continue
        if type_counts.get(priority, 0) >= type_limits.get(priority, max_other):
            continue
        bucket = d.get("analysisBucket", "general")
        if bucket_counts.get(bucket, 0) >= quotas.get(bucket, 2):
            continue
        selected.append(d)
        seen.add(key)
        type_counts[priority] = type_counts.get(priority, 0) + 1
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(selected) >= max_reports + max_articles + max_other:
            break
    if len(selected) < 4:
        for d in scored:
            key = d.get("url") or d.get("path") or d.get("title")
            if key and key not in seen and company_doc_priority(d) != 0 and d.get("analysisScore", 0) >= 30:
                selected.append(d)
                seen.add(key)
            if len(selected) >= 4:
                break
    if not selected:
        return "", []
    lines = ["## 보조 자료: 리포트/IR/기사/RSS"]
    for i, d in enumerate(selected, 1):
        limit = 1000 if company_doc_priority(d) == 1 else 650
        content = clean_brief_text(d.get("content") or d.get("summary") or "", limit)
        tags = ", ".join((d.get("sectors", []) + d.get("impactTags", []))[:10]) or "없음"
        reasons = ", ".join(d.get("analysisReasons", [])[:5]) or "선별 점수 기준"
        lines.append(
            f"[{i}] 유형: {d.get('type', '')} | 출처: {d.get('source', 'Unknown')} | 날짜: {d.get('date', '')} | 태그: {tags}\n"
            f"선별: score={d.get('analysisScore', 0)} | bucket={d.get('analysisBucket', 'general')} | 이유: {reasons}\n"
            f"제목: {clean_brief_text(d.get('title', ''), 220)}\n"
            f"요약/발췌: {content}\n"
            f"근거 위치: {d.get('url') or d.get('path', '')}\n"
        )
    return "\n".join(lines), selected


def build_company_analysis_materials(query, docs, company=None):
    company = company or {}
    scored_docs = [company_analysis_doc_score(d, company, query) for d in docs]
    for d in scored_docs:
        d["companyDocPriority"] = company_doc_priority(d)
        d["analysisScoreDesc"] = -float(d.get("analysisScore", 0) or 0)
    sorted_docs = sort_records(scored_docs, ["companyDocPriority", "analysisScoreDesc", "date"], descending=[False, False, True])
    filing_docs = [d for d in sorted_docs if is_sec_filing_doc(d) and company_direct_relevance(d, company, query)[0] >= 15]
    local_filing_context, local_filing_used, local_filing_paragraphs = build_filing_item_context(filing_docs)
    is_kr_company = company.get("market") == "KR" or bool(re.fullmatch(r"\d{6}", str(company.get("ticker") or "")))
    dart_facts = build_dart_summary(company, DART_CACHE_DIR) if is_kr_company else {}
    sec_facts = dart_facts if is_kr_company else build_companyfacts_summary(company, SEC_CACHE_DIR)
    ranked_filing = {"ok": False, "reason": "dart_company", "metadata": {}, "paragraphs": []} if is_kr_company else ranked_10k_paragraphs(company, SEC_CACHE_DIR, max_paragraphs=14)
    # 연차보고서만 읽으면 8월에 만든 보고서가 1월에 끝난 회계연도 서술로 회사를
    # 설명한다. 그 사이 분기의 MD&A를 함께 읽는다. 연차를 대체하지 않고 덧붙인다.
    quarterly_filing = (
        {"ok": False, "reason": "dart_company", "metadata": {}, "paragraphs": []}
        if is_kr_company
        else ranked_quarterly_report_paragraphs(company, SEC_CACHE_DIR, max_paragraphs=8)
    )
    sic_description = (ranked_filing.get("metadata", {}) or {}).get("sicDescription", "")
    if sic_description and (not company.get("sector") or company.get("sector") == "Unclassified"):
        company = {**company, "sector": sic_description}
    filing_context = local_filing_context
    filing_used = local_filing_used
    if ranked_filing.get("ok"):
        filing_context = ranked_paragraphs_to_markdown(ranked_filing)
        filing_used = []
    elif local_filing_paragraphs:
        ranked_filing = {
            "ok": True,
            "reason": "local_official_filing_fallback",
            "metadata": {
                "form": filing_form_type(local_filing_used[0]) if local_filing_used else "local filing",
                "title": (local_filing_used[0] or {}).get("title", "") if local_filing_used else "",
                "path": (local_filing_used[0] or {}).get("path", "") if local_filing_used else "",
                "filingDate": (local_filing_used[0] or {}).get("date", "") if local_filing_used else "",
                "source": "local_filings",
                "localFallback": True,
            },
            "paragraphs": local_filing_paragraphs,
        }
    filing_used_keys = {d.get("url") or d.get("path") or d.get("title") for d in filing_used}
    support_context, support_used = build_supporting_doc_context(
        [d for d in sorted_docs if (d.get("url") or d.get("path") or d.get("title")) not in filing_used_keys],
        company=company,
        query=query,
    )
    selected = filing_used + support_used
    market_financial_data = fetch_market_valuation_data(company)
    computed_financial_table = build_financial_table(sec_facts, market_financial_data)
    computed_financial_quality = build_financial_quality_analysis(sec_facts, market_financial_data)
    computed_valuation = build_valuation_metrics(company, sec_facts, market_financial_data)
    counts = {
        "filings": sum(1 for d in docs if company_doc_priority(d) == 0),
        "reports": sum(1 for d in docs if company_doc_priority(d) == 1),
        "articles": sum(1 for d in docs if company_doc_priority(d) in {2, 3}),
        "other": sum(1 for d in docs if company_doc_priority(d) == 4),
    }
    local_ir_count = sum(1 for d in support_used if any(reason == "IR/실적발표 자료" for reason in d.get("analysisReasons", [])))
    market_memory_context = render_market_memory_context(MARKET_MEMORY_DB_PATH)
    lines = [
        f"분석 대상: {query}",
        f"추정 기업: {company.get('name', '')} ({company.get('ticker', '')}) | market={company.get('market', '')} | CIK={company.get('cik', '') or sec_facts.get('cik', '') or '미확인'} | DART corp_code={company.get('corpCode') or sec_facts.get('corpCode') or '미확인'}",
        f"사용 가능한 자료 수: {len(docs)}",
        f"자료 우선순위별 개수: filings={counts['filings']}, reports={counts['reports']}, articles/rss={counts['articles']}, other={counts['other']}, local_ir_earnings={local_ir_count}",
        "",
        "컨텍스트 구성 방식:",
        "1. SEC 등록기업은 companyfacts 숫자와 SEC 연차보고서(국내 제출사 10-K, 외국 민간 발행인 20-F) 공시 문단을, 국내 기업은 DART 재무제표 숫자와 DART 공시 목록을 1차 공식 자료로 사용합니다.",
        "2. SEC 연차보고서 HTML은 기업 섹터/GICS 프로필에 따라 문단 단위로 점수화합니다. 20-F는 Item 번호 체계가 10-K와 달라(사업 개요 4, 위험 3.D, 경영진 논의 5, 시장위험 11, 재무제표 18) 발췌의 Item 표기는 그 보고서 체계를 따릅니다. 국내 기업은 DART 사업보고서/분기보고서 및 로컬 filings 자료로 보완합니다.",
        "3. 상위 공식자료가 부족하면 로컬 filings의 10-K/10-Q/S-1/20-F/8-K/prospectus/proxy 등 직접 관련 공식자료 발췌를 보조 공식자료로 사용합니다.",
        "4. 로컬 reports/articles/rss에 기업 IR, 실적발표, 컨퍼런스콜, 증권사 리포트, 관련 기사가 있으면 반드시 보조 근거로 사용합니다.",
        "5. 웹 검색이 허용되어 있고 로컬 공식자료나 IR/실적발표/리포트 자료의 수치 정확성 검증이 필요하면 회사 IR, SEC/EDGAR, DART, earnings release, transcript, 신뢰 가능한 금융 기사와 리포트로 교차검증하세요.",
        "",
        market_memory_context,
        "",
        "## 앱 계산 재무 요약",
        "아래 표는 SEC companyfacts 또는 DART 구조화 재무 데이터를 연도별 제목행으로 정리한 것입니다. LLM 출력의 Financial Summary 표는 이 구조를 우선 따라야 하며, 날짜를 각 셀에 반복하지 마세요.",
        computed_financial_table,
        "",
        "## 앱 계산 재무 품질 분석",
        "아래 내용은 SEC companyfacts 또는 DART 재무제표에서 계산 가능한 대용 지표를 사용한 예비 재무 품질 분석입니다. 값이 계산되어 있으면 LLM 출력에서 같은 항목을 '추가 확인 필요'로 되돌리지 말고, 계산값의 한계를 설명하세요.",
        computed_financial_quality,
        "",
        "## 앱 계산 Valuation 및 DCF",
        "아래 내용은 SEC/DART 재무 데이터와 yfinance 시장 데이터를 사용한 예비 밸류에이션 계산입니다. P/E, P/S, EV/EBITDA, FCF Yield, DCF 시나리오가 계산되어 있으면 LLM 출력에서 해당 항목을 '추가 확인 필요'로 쓰지 말고 계산값과 가정을 설명하세요.",
        computed_valuation,
        "",
        "## 공식 숫자 데이터",
        sec_facts.get("markdown", "Official financial data unavailable."),
        "",
        "## 최근 분기 공시 서술 (10-Q MD&A)",
        (
            ranked_paragraphs_to_markdown(quarterly_filing)
            if quarterly_filing.get("ok")
            else "최근 분기보고서 서술을 확보하지 못했습니다. 연차보고서 기준 서술만 사용하세요."
        ),
        "",
        "## 공식 공시 상위 문단 또는 Item 발췌",
        filing_context or ("DART 공시 본문 문단 추출은 아직 연결되지 않았습니다. 로컬 filings의 사업보고서/분기보고서 원문 또는 웹 검색 공식 공시로 보완하세요." if is_kr_company else "선별 가능한 SEC 연차보고서 HTML 문단/Item 발췌가 없습니다. 로컬 filings 원문 또는 웹 검색 공식 공시로 보완하세요."),
        "",
        support_context or "보조 리포트/기사 자료가 없습니다.",
    ]
    # 웹 검색 허용 목록과 산업 맥락 질의가 회사 도메인·업종을 필요로 한다.
    market_meta = market_financial_data if isinstance(market_financial_data, dict) else {}
    company = {
        **company,
        "website": company.get("website") or market_meta.get("website") or "",
        "sector": company.get("sector") or market_meta.get("sector") or "",
        "industry": company.get("industry") or market_meta.get("industry") or "",
    }
    return {
        "company": company,
        "docs": docs,
        "selectedDocs": selected,
        "supportDocs": support_used,
        "filingDocs": filing_used,
        "selection": [
            {
                "title": d.get("title", ""),
                "source": d.get("source", ""),
                "score": d.get("analysisScore", 0),
                "bucket": d.get("analysisBucket", "general"),
                "reasons": d.get("analysisReasons", []),
            }
            for d in selected
        ],
        "secFacts": sec_facts,
        "rankedFiling": ranked_filing,
        "rankedQuarterlyFiling": quarterly_filing,
        "dartFacts": dart_facts,
        "computedFinancialTable": computed_financial_table,
        "computedFinancialQuality": computed_financial_quality,
        "computedValuation": computed_valuation,
        "marketFinancialData": market_financial_data,
        "context": "\n".join(lines),
        "counts": counts,
        "localIrEarningsCount": local_ir_count,
    }


def build_company_analysis_context(query, docs, company=None):
    materials = build_company_analysis_materials(query, docs, company)
    return materials["context"], materials["selectedDocs"]


def company_external_search_context(materials):
    company = materials.get("company", {}) or {}
    name = company.get("name", "")
    ticker = company.get("ticker", "")
    market = company.get("market", "")
    local_ir_count = materials.get("localIrEarningsCount", 0)
    return "\n".join([
        "## 웹 검색 보완 지시",
        "웹 검색이 허용되어 있습니다. 로컬 자료와 앱 계산 자료를 먼저 사용하되, 아래 항목이 부족하면 외부 검색으로 보완하세요.",
        f"- 대상 기업: {name} ({ticker}) | market={market}",
        f"- 로컬 IR/실적발표 자료 감지 수: {local_ir_count}",
        "- 항상 사용해야 할 기초 자료: SEC 등록기업은 companyfacts와 연차보고서(10-K 또는 20-F)·10-Q, 국내 기업은 DART 재무제표/사업보고서/분기보고서, 그리고 yfinance/Yahoo Finance 시장 데이터.",
        "- 로컬 자료에 IR presentation, earnings release, shareholder letter, transcript, investor day, 증권사 리포트, 관련 기사가 있으면 반드시 같이 반영하세요.",
        "- 로컬 IR/실적발표/리포트가 부족하면 공식 회사 IR 사이트, earnings release, earnings presentation, conference call transcript, SEC/EDGAR 또는 DART, Reuters/Bloomberg/WSJ/FT/AP/연합인포맥스/한국경제 등 신뢰 가능한 금융 기사 또는 리포트를 검색하세요.",
        "- 검색 결과는 보고서 본문에서 필요한 부분에만 사용하고, `Sources Used`에는 로컬 자료, SEC/yfinance, 웹 검색 자료를 구분해 URL과 함께 남기세요.",
        "- 웹에서 확인되지 않은 수치나 목표주가를 추정해서 만들지 마세요. 확인된 자료가 없으면 왜 확인되지 않는지만 짧게 쓰세요.",
        "",
        "권장 검색 질의 예시:",
        f"- {name} {ticker} investor relations earnings presentation",
        f"- {name} {ticker} DART 사업보고서 분기보고서",
        f"- {name} {ticker} latest earnings release guidance",
        f"- {name} {ticker} conference call transcript",
        f"- {name} {ticker} analyst report Reuters Bloomberg WSJ FT",
        "",
        render_scope_instruction(load_source_scope(company), company),
        "",
        _context_search_instruction(company),
    ])


def _context_search_instruction(company: dict) -> str:
    """산업·정책 맥락 질의와 그 결과를 다루는 규칙.

    회사 공시만으로는 경쟁우위·리스크·성장 전망이 반쪽이다. 그렇다고 산업 기사를
    회사 근거와 섞으면 안 된다 — 실제로 NVDA 보고서에 LATAM 항공 실적이 근거로
    올라온 적이 있다. Market Memory와 같은 경계를 쓴다: 배경으로만 쓰고 회사 고유
    사실의 근거로는 쓰지 않는다.
    """
    industry = str(company.get("industry") or "").strip()
    sector = str(company.get("sector") or "").strip()
    subject = industry or sector
    lines = [
        "## 산업·정책 맥락 검색",
        "회사 자료만으로는 경쟁우위·리스크·성장 전망을 판단하기 어렵습니다. 아래 두 갈래를 함께 찾으세요.",
    ]
    if subject:
        lines += [
            f"- 산업: {subject} 수요 전망, 공급 구조, 가격, 주요 경쟁사 동향",
            f"- 정책·거시: {subject} 관련 규제, 관세, 수출 통제, 보조금, 금리·환율 영향",
        ]
    else:
        lines.append("- 업종을 확인하지 못했습니다. 회사 공시에서 사업 영역을 먼저 읽고 그 영역으로 검색하세요.")
    lines += [
        "",
        "**이 결과는 배경입니다.**",
        "- 회사의 매출·이익·가이던스·제품 같은 고유 사실의 근거로 인용하지 마세요. 그 숫자는 회사 자료에서만 옵니다.",
        "- 4번(경쟁우위), 5번(리스크), 6번(성장 전망)의 판단 배경으로 쓰고, 회사에 어떻게 연결되는지 직접 밝히세요.",
        "- `Sources Used`에 `회사 / 산업 / 정책`을 구분해 남기세요. 산업 기사 수가 많다고 회사 근거가 충분한 것은 아닙니다.",
    ]
    return "\n".join(lines)


def generate_llm_company_analysis(
    query, docs, web_search_override=None, llm_override=None, materials=None,
    quality_preflight=None, analysis_style="beginner", *, depth_policy=None, source_ledger=None,
    web_facts="",
):
    cfg = selected_llm_config()
    llm_on = use_llm_analysis() if llm_override is None else bool(llm_override)
    if not llm_on:
        return None, "disabled"
    if not cfg["apiKey"]:
        return None, f"missing_{cfg['provider']}_api_key"
    prompt = read_company_analysis_prompt(analysis_style)
    if not prompt:
        return None, "missing_prompt"
    if not docs and not (materials or {}).get("context"):
        return None, "no_documents"
    if materials is None:
        materials = build_company_analysis_materials(query, docs)
    context = materials["context"]
    used_docs = materials["selectedDocs"]
    target_block = render_quality_target_context(
        "company_analysis",
        preflight=quality_preflight,
        context={"extraRoutes": [
            f"현재 로컬 filings/reports/articles/rss 개수: {materials.get('counts', {})}",
            f"로컬 IR/실적발표 감지 수: {materials.get('localIrEarningsCount', 0)}",
            "공식 숫자가 없으면 웹 검색보다 먼저 dataGap으로 남기고, 웹 검색 사용 시 공식 IR·SEC·DART를 우선한다.",
        ]},
    )
    context = "\n\n".join([context, target_block])
    context = "\n\n".join([
        context,
        build_preflight_evidence_context(
            "company_analysis",
            preflight=quality_preflight,
            artifact={
                "sources": used_docs,
                "analysisInputs": {
                    "secFactsOk": bool((materials.get("secFacts") or {}).get("ok")),
                    "rankedFilingOk": bool((materials.get("rankedFiling") or {}).get("ok")),
                },
                "dataGaps": [],
            },
        ),
    ])
    hint_block = render_prompt_hints(quality_preflight)
    if hint_block:
        context = "\n\n".join([context, hint_block])
    # 분량과 근거 인용은 프롬프트가 아니라 **이 요청의 숫자와 목록**으로 준다.
    # 원칙은 안 움직이고 숫자로 된 과제만 움직인다(딥 리서치에서 세 번 확인).
    for block in (
        render_length_contract(depth_policy or {}),
        render_quality_requirements(),
        render_source_contract(source_ledger),
        web_facts,
    ):
        if block:
            context = "\n\n".join([context, block])
    web_search = use_web_search_for_analysis() if web_search_override is None else bool(web_search_override)
    if web_search:
        context = "\n\n".join([context, company_external_search_context(materials)])
    web_status = "web_search" if web_search else "local_only"
    try:
        max_tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "7000")))
        if cfg["provider"] == "gemini":
            text, response_id, usage = request_gemini(cfg, prompt, context, web_search=web_search, include_usage=True)
        elif cfg["provider"] == "claude":
            text, response_id, usage = request_claude(cfg, prompt, context, web_search=web_search, include_usage=True)
        else:
            text, response_id, usage = request_openai(cfg, prompt, context, web_search=web_search, include_usage=True)
        if not text:
            return None, "empty_response"
        text = strip_llm_citation_markers(text)
        return {
            "markdown": text,
            "provider": cfg["provider"],
            "model": cfg["model"],
            "usedDocs": used_docs,
            "promptPath": str(analysis_prompt_path(analysis_style)),
            "responseId": response_id,
            "webSearch": web_search,
            "tokenUsage": normalize_token_usage(usage, prompt=prompt, context=context, output=text, max_output_tokens=max_tokens),
        }, f"ok_{web_status}"
    except Exception:
        return None, "generation_failed"


def analysis_status_message(generation):
    status = generation.get("status", "")
    provider = generation.get("provider", "")
    if generation.get("mode") == "llm":
        suffix = " · 웹 검색 보완 사용" if generation.get("webSearch") else " · 로컬 자료만 사용"
        return f"LLM 기업분석 생성 완료: {provider} / {generation.get('model', '')}{suffix}"
    if status == "disabled":
        return "LLM 사용이 꺼져 있어 규칙 기반 기업분석으로 생성했습니다."
    if status == "no_documents":
        return "분석에 사용할 자료가 충분하지 않습니다."
    if status.startswith("missing_"):
        return f"{provider} API 키가 없어 규칙 기반 기업분석으로 생성했습니다."
    if "429" in status or "Too Many Requests" in status:
        return f"{provider} API 사용량 제한 또는 요청 한도 때문에 규칙 기반 기업분석으로 대체했습니다."
    if status.startswith("error:"):
        return f"{provider} LLM 호출 실패로 규칙 기반 기업분석으로 대체했습니다. 상세: {status[7:240]}"
    return "규칙 기반 기업분석으로 생성했습니다."


# ---------------------------------------------------------------------------
# Analysis report management
# ---------------------------------------------------------------------------

def _report_date_key(generated_at):
    """생성 시각의 KST 날짜.

    `generated_at`은 UTC(`now_iso()`)라 앞 10자를 그대로 쓰면 KST 00~09시에 만든
    보고서가 전날로 묶인다. 그 시간대의 재분석은 덮어쓰기가 아니라 파일 하나를
    더 만든다. 앱의 사용자 노출 날짜 기준은 KST다.
    """
    text = str(generated_at or "")
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return text[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")


def analysis_report_id(company, generated_at):
    # 날짜 단위로 id를 안정화한다 — 같은 기업을 같은 날 재분석하면 최신본으로 덮어쓰고,
    # 자동 저장이 파일을 무한정 쌓지 않게 한다(시간 단위 timestamp 대신 날짜).
    key = f"{company.get('ticker') or company.get('name')}:{_report_date_key(generated_at)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def save_analysis_report(report):
    ANALYSIS_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = dict(report or {})
    report["savedAt"] = report.get("savedAt") or now_iso()
    rid = analysis_report_id(report.get("company", {}), report.get("generatedAt", now_iso()))
    report["id"] = report.get("id") or rid
    report["saved"] = True
    path = ANALYSIS_REPORTS_DIR / f"{report['id']}.json"
    # Manual POSTs without generation provenance/ChangeBasis remain ordinary
    # canonical saves and do not emit a synthetic change event.
    if isinstance(report.get("changeBasis"), dict):
        report["changeBasis"] = {**report["changeBasis"], "artifactId": report["id"]}
        report.pop("changeSummary", None)
        report = decorate_candidate("company_analysis", report, data_dir=DATA_DIR, generation_provenance=True)
    prepared = prepare(
        report_kind=ReportKind.COMPANY_ANALYSIS,
        exact_path=path,
        write_kind=WriteKind.CANONICAL,
        candidate=report,
    )
    commit_sync(prepared)
    projection = project_committed_report(MARKET_MEMORY_DB_PATH, path) if report.get("changeSummary") else {"status": "skipped"}
    committed = load_report(path)
    if committed is None:
        raise RuntimeError("canonical company report commit did not persist the report")
    if report.get("changeSummary"):
        committed["changeIntelligence"] = {**(committed.get("changeIntelligence") or {}), "projectionStatus": projection.get("status"), "invalidationToken": projection.get("invalidationToken") or (committed.get("changeIntelligence") or {}).get("invalidationToken")}
    return committed


def delete_analysis_report(report_id):
    from features.agent_mode.report_delete import DeleteRequest, execute_report_delete
    from features.common.canonical_reports import (
        CanonicalIdentityError,
        CanonicalNotFoundError,
        ReportKind,
        resolve_exact_report_path,
    )

    safe_id = str(report_id or "")
    try:
        path = resolve_exact_report_path(ANALYSIS_REPORTS_DIR.parent, ReportKind.COMPANY_ANALYSIS, safe_id)
    except CanonicalNotFoundError:
        return {"deleted": False, "error": "Analysis report not found"}
    except CanonicalIdentityError as exc:
        raise ValueError("analysis report identifier is invalid") from exc
    outcome = execute_report_delete(DeleteRequest(
        root=ANALYSIS_REPORTS_DIR,
        identity=f"company:{safe_id}",
        primary_names=(path.name,),
        target_names=(path.name,),
    ))
    if not outcome.deleted:
        return {"deleted": False, "error": "Analysis report not found"}
    return {"deleted": True, "id": safe_id}


def list_analysis_reports():
    ANALYSIS_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(ANALYSIS_REPORTS_DIR.glob("*.json"), reverse=True):
        report = read_json(path, None)
        if not report:
            continue
        company = report.get("company", {})
        data_gaps = report.get("dataGaps") or {}
        data_gap_summary = data_gaps.get("summary", {}) if isinstance(data_gaps, dict) else {}
        rows.append(
            {
                "id": report.get("id") or path.stem,
                "generatedAt": report.get("generatedAt", ""),
                "query": report.get("query", ""),
                "title": report.get("headline", ""),
                "company": company,
                "mode": (report.get("generation") or {}).get("mode", ""),
                "provider": (report.get("generation") or {}).get("provider", ""),
                # 목록 카드가 "LLM"이라고만 적으면 어느 모델이 썼는지 알 수 없다.
                "engine": engine_label(report.get("generation")),
                "engineDetail": engine_detail(report.get("generation")),
                "analysisStyle": report.get("analysisStyle", ""),
                "dataGapSummary": data_gap_summary,
            }
        )
    return rows


def get_analysis_report(report_id):
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(report_id or ""))
    if not safe_id:
        return None
    return read_json(ANALYSIS_REPORTS_DIR / f"{safe_id}.json", None)


def company_analysis_sources(materials, docs):
    sources = []
    seen = set()

    def add(source):
        key = source.get("url") or source.get("path") or source.get("title")
        if not key or key in seen:
            return
        seen.add(key)
        sources.append(source)

    ranked = materials.get("rankedFiling", {}) or {}
    metadata = ranked.get("metadata", {}) or {}
    if metadata.get("url"):
        add({
            # 출처 표기는 실제 form을 따른다. 20-F 제출사의 근거를 "10-K"로 적으면
            # source ledger가 존재하지 않는 문서를 가리킨다.
            "title": metadata.get("title") or f"SEC {metadata.get('form') or '10-K'} HTML",
            "source": "SEC EDGAR",
            "date": metadata.get("filingDate", ""),
            "url": metadata.get("url", ""),
            "path": "",
            "type": metadata.get("form") or "filing",
        })
    sec_facts = materials.get("secFacts", {}) or {}
    dart_facts = materials.get("dartFacts", {}) or {}
    if dart_facts.get("corpCode"):
        add({
            "title": f"DART financial statements corp_code {dart_facts.get('corpCode')}",
            "source": "DART Open API",
            "date": "",
            "url": "https://opendart.fss.or.kr/",
            "path": "",
            "type": "financials",
        })
        for disclosure in (dart_facts.get("disclosures") or [])[:4]:
            rcept_no = disclosure.get("rcept_no", "")
            add({
                "title": disclosure.get("report_nm") or "DART disclosure",
                "source": "DART",
                "date": disclosure.get("rcept_dt", ""),
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else "https://dart.fss.or.kr/",
                "path": "",
                "type": "filing",
            })
    if sec_facts.get("cik"):
        add({
            "title": f"SEC companyfacts CIK {sec_facts.get('cik')}",
            "source": "SEC companyfacts",
            "date": "",
            "url": f"https://data.sec.gov/submissions/CIK{sec_facts.get('cik')}.json",
            "path": "",
            "type": "financials",
        })
    company = materials.get("company", {}) or {}
    ticker = str(company.get("ticker") or "").strip().upper()
    if ticker:
        yf_symbol = ticker
        if company.get("market") == "KR" and re.fullmatch(r"\d{6}", ticker):
            yf_symbol = f"{ticker}.KS"
        add({
            "title": f"Market data for {yf_symbol}",
            "source": "yfinance / Yahoo Finance",
            "date": "",
            "url": f"https://finance.yahoo.com/quote/{yf_symbol}",
            "path": "",
            "type": "market data",
        })
    for d in docs:
        add({
            "title": d.get("title", ""),
            "source": d.get("source", ""),
            "date": d.get("date", ""),
            "url": d.get("url", ""),
            "path": d.get("path", ""),
            "type": d.get("type", ""),
        })
        if len(sources) >= 16:
            break
    return sources


# ---------------------------------------------------------------------------
# Chart data builders
# ---------------------------------------------------------------------------

def _finite_number(value):
    try:
        number = float(value)
    except Exception:
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _metric_quarterly_map(sec_summary, metric):
    """분기 값을 기간 라벨로 모은다. `2026-03-31` → `2026 Q1`.

    차트는 연간만 읽고 있었다. 8월에 만든 보고서가 1월 결산 회계연도만 그리면
    그 사이 두 분기가 그림에서 사라진다.
    """
    out = {}
    for row in sec_summary.get("rows", []) or []:
        if row.get("metric") != metric:
            continue
        for item in row.get("quarterly", []) or []:
            end = str(item.get("end", "") or "")
            value = _finite_number(item.get("val"))
            if len(end) >= 7 and value is not None:
                year, month = end[:4], int(end[5:7])
                out[f"{year} Q{(month - 1) // 3 + 1}"] = value
    return out


def _metric_annual_map(sec_summary, metric):
    out = {}
    for row in sec_summary.get("rows", []) or []:
        if row.get("metric") != metric:
            continue
        for item in row.get("annual", []) or []:
            year = str(item.get("end", "") or item.get("fy", ""))[:4]
            value = _finite_number(item.get("val"))
            if year and value is not None:
                out[year] = value
    return out


def _series_for_years(values, years):
    return [_finite_number(values.get(year)) for year in years]


def _ratio_series(numerators, denominators):
    rows = []
    for numerator, denominator in zip(numerators, denominators):
        if numerator is None or denominator in {None, 0}:
            rows.append(None)
        else:
            rows.append(numerator / denominator)
    return rows


def _has_any_number(rows):
    return any(value is not None for value in rows)


def _finite_series(node):
    """차트 payload의 non-finite 숫자를 `None`으로 내린다(값 없음과 같은 자리)."""
    if isinstance(node, dict):
        return {key: _finite_series(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_finite_series(item) for item in node]
    if isinstance(node, float):
        return _finite_number(node)
    return node


def _compute_price_returns(ticker: str) -> dict | None:
    """Return % vs SPY and QQQ over 1m/3m/6m/12m. Returns None on any failure."""
    if not ticker:
        return None
    try:
        import yfinance as yf
        benchmarks = ["SPY", "QQQ"]
        period_map = [("1개월", "1mo"), ("3개월", "3mo"), ("6개월", "6mo"), ("12개월", "1y")]
        labels = [label for label, _ in period_map]
        series: dict[str, list] = {}
        for sym in [ticker] + benchmarks:
            returns = []
            for _label, period in period_map:
                try:
                    hist = yf.Ticker(sym).history(period=period)
                    if hist is not None and not getattr(hist, "empty", True) and len(hist) >= 2:
                        # yfinance는 결측 행을 NaN으로 준다. `if start_price`는 0만 걸러내고
                        # NaN은 참이라 그대로 통과해, NaN 수익률 하나가 보고서 저장 단계에서
                        # canonical JSON에 걸려 100초짜리 CLI 결과를 통째로 버리게 했다.
                        start_price = _finite_number(hist["Close"].iloc[0])
                        end_price = _finite_number(hist["Close"].iloc[-1])
                        r = (
                            _finite_number(round((end_price / start_price - 1) * 100, 2))
                            if start_price and end_price is not None
                            else None
                        )
                    else:
                        r = None
                except Exception:
                    r = None
                returns.append(r)
            if any(v is not None for v in returns):
                series[sym] = returns
        if ticker not in series:
            return None
        return {"labels": labels, "series": series}
    except Exception:
        return None


def _present_subtitle(base: str, named: list[tuple[str, list]]) -> str:
    """실제로 값이 있는 계열만 부제에 적는다.

    "Gross, operating, and net margin"이라 적어 놓고 총이익률을 못 그린 적이 있다.
    공시에 없는 지표를 제목에서 약속하면 독자는 빠진 줄도 모른다.
    """
    present = [label for label, values in named if _has_any_number(values)]
    return f"{base} · {' · '.join(present)}" if present else base


def build_company_analysis_charts(materials):
    sec_summary = materials.get("secFacts", {}) or {}
    company = materials.get("company", {}) or {}
    if not sec_summary.get("ok"):
        return {"available": False, "reason": "sec_companyfacts_unavailable", "charts": []}

    metric_maps = {
        metric: _metric_annual_map(sec_summary, metric)
        for metric in [
            "Revenue",
            "Gross Profit",
            "Operating Income",
            "Net Income",
            "Operating Cash Flow",
            "Capital Expenditure",
        ]
    }
    market = materials.get("marketFinancialData") or fetch_market_valuation_data(company)
    # 재무 차트는 신고 통화, 주가 차트는 상장 통화다. 둘은 다를 수 있다
    # (ASML: 재무 EUR, 나스닥 ADR 주가 USD).
    reporting_currency = str(sec_summary.get("currency") or "USD")
    price_currency = str(market.get("currency") or reporting_currency) if market.get("ok") else reporting_currency
    for row in market.get("cashflowRows", []) if market.get("ok") else []:
        year = str(row.get("year") or str(row.get("end", ""))[:4])
        if not re.fullmatch(r"\d{4}", year):
            continue
        for metric in ["Operating Cash Flow", "Capital Expenditure"]:
            try:
                value = row.get(metric)
                if value is not None and year not in metric_maps[metric]:
                    metric_maps[metric][year] = abs(float(value)) if metric == "Capital Expenditure" else float(value)
            except Exception:
                pass
    years = sorted(set().union(*[set(values.keys()) for values in metric_maps.values()]))[-5:]

    charts = []
    if years:
        revenue = _series_for_years(metric_maps["Revenue"], years)
        gross_profit = _series_for_years(metric_maps["Gross Profit"], years)
        operating_income = _series_for_years(metric_maps["Operating Income"], years)
        net_income = _series_for_years(metric_maps["Net Income"], years)
        net_margin = _ratio_series(net_income, revenue)
        if _has_any_number(revenue) or _has_any_number(net_income):
            charts.append({
                "id": "performance",
                "title": "실적 추이",
                "subtitle": "SEC companyfacts 연간 보고 기준",
                "kind": "performance",
                "years": years,
                "revenue": revenue,
                "grossProfit": gross_profit,
                "operatingIncome": operating_income,
                "netIncome": net_income,
                "netMargin": net_margin,
                "currency": reporting_currency,
            })

        # 분기 흐름은 연간 추세와 다른 질문에 답한다. 둘 다 그린다.
        quarter_maps = {
            metric: _metric_quarterly_map(sec_summary, metric)
            for metric in ("Revenue", "Operating Income", "Net Income")
        }
        quarters = sorted({q for values in quarter_maps.values() for q in values})[-8:]
        if quarters:
            q_revenue = [_finite_number(quarter_maps["Revenue"].get(q)) for q in quarters]
            q_operating = [_finite_number(quarter_maps["Operating Income"].get(q)) for q in quarters]
            q_net = [_finite_number(quarter_maps["Net Income"].get(q)) for q in quarters]
            if _has_any_number(q_revenue) or _has_any_number(q_net):
                charts.append({
                    "id": "quarterly",
                    "title": "분기 흐름",
                    "subtitle": "SEC companyfacts 분기 보고 기준",
                    "kind": "quarterly",
                    "years": quarters,
                    "revenue": q_revenue,
                    "operatingIncome": q_operating,
                    "netIncome": q_net,
                    "netMargin": _ratio_series(q_net, q_revenue),
                    "currency": reporting_currency,
                    # 분기는 계절성이 있어 직전 분기가 아니라 전년 동기와 비교한다.
                    # 화면은 라벨(`2026 Q2`→`2025 Q2`)로 전년 동기를 찾는다 — 10-Q에는
                    # Q4가 없어 고정 오프셋 4는 전년 동기가 아니다. 이 값은 옛 저장
                    # 페이로드와의 호환으로만 남는다.
                    "compareOffset": 4,
                })

        cfo = _series_for_years(metric_maps["Operating Cash Flow"], years)
        capex_raw = _series_for_years(metric_maps["Capital Expenditure"], years)
        capex = [-abs(value) if value is not None else None for value in capex_raw]
        free_cash_flow = [
            (a - b) if a is not None and b is not None else None
            for a, b in zip(cfo, capex_raw)
        ]
        fcf_margin = _ratio_series(free_cash_flow, revenue)
        if _has_any_number(cfo) or _has_any_number(free_cash_flow):
            charts.append({
                "id": "cashflow",
                "title": "현금흐름",
                "subtitle": _present_subtitle(
                    "SEC companyfacts 연간 보고 기준",
                    [("영업활동", cfo), ("설비투자", capex), ("잉여현금흐름", free_cash_flow)],
                ),
                "kind": "cashflow",
                "years": years,
                "operatingCashFlow": cfo,
                "capitalExpenditure": capex,
                "freeCashFlow": free_cash_flow,
                "fcfMargin": fcf_margin,
                "currency": reporting_currency,
            })

        gross_margin = _ratio_series(gross_profit, revenue)
        operating_margin = _ratio_series(operating_income, revenue)
        if _has_any_number(gross_margin) or _has_any_number(operating_margin):
            charts.append({
                "id": "margins",
                "title": "마진 추이",
                "subtitle": _present_subtitle(
                    "매출 대비 비율",
                    [("매출총이익률", gross_margin), ("영업이익률", operating_margin), ("순이익률", net_margin)],
                ),
                "kind": "margins",
                "years": years,
                "grossMargin": gross_margin,
                "operatingMargin": operating_margin,
                "netMargin": net_margin,
            })

    fcf = _latest_metric_value(sec_summary, market, "Free Cash Flow")
    cash = financial_engine.latest_value(sec_summary, "Cash & Equivalents") or 0.0
    debt = financial_engine.latest_value(sec_summary, "Long-Term Debt") or 0.0
    shares = market.get("sharesOutstanding") if market.get("ok") else None
    if shares is None:
        shares = financial_engine.latest_value(sec_summary, "Shares Diluted")
    price = market.get("price") if market.get("ok") else None
    near_growth = financial_engine.growth_rate(_fcf_series(sec_summary, market))
    scenarios = financial_engine.dcf_scenarios(fcf or 0.0, debt - cash, shares or 0.0, near_growth)
    scenario_rows = [
        {
            "name": item.get("name"),
            "perShare": _finite_number(item.get("perShare")),
            "growth": _finite_number(item.get("growth")),
            "discount": _finite_number(item.get("discount")),
            "terminal": _finite_number(item.get("terminal")),
        }
        for item in scenarios
        if item.get("ok") and _finite_number(item.get("perShare")) is not None
    ]
    if scenario_rows:
        charts.append({
            "id": "dcf",
            "title": "DCF 시나리오",
            "subtitle": "보수·기본·낙관 가정별 주당 내재가치",
            "kind": "dcf",
            "scenarios": scenario_rows,
            "currentPrice": _finite_number(price),
            # 내재가치/주는 현재가와 나란히 읽히므로 주가 통화를 쓴다.
            "currency": price_currency,
        })

    # PER scenario price chart
    trailing_eps = financial_engine.latest_value(sec_summary, "EPS Diluted") or \
                   financial_engine.latest_value(sec_summary, "EPS Basic")
    if trailing_eps and price and trailing_eps > 0:
        current_pe = _finite_number(price / trailing_eps)
        forward_eps = _finite_number(trailing_eps * (1 + (near_growth or 0.05)))
        if current_pe and forward_eps:
            per_bear = _finite_number(current_pe * 0.75)
            per_base = current_pe
            per_bull = _finite_number(current_pe * 1.30)
            per_scenarios = [
                {"label": "나쁜 경우", "price": _finite_number(forward_eps * per_bear), "per": per_bear, "eps": forward_eps},
                {"label": "기본",     "price": _finite_number(forward_eps * per_base), "per": per_base, "eps": forward_eps},
                {"label": "좋은 경우","price": _finite_number(forward_eps * per_bull), "per": per_bull, "eps": forward_eps},
            ]
            valid_per_scenarios = [s for s in per_scenarios if s["price"] is not None]
            if valid_per_scenarios:
                charts.append({
                    "id": "scenario_price",
                    "title": "PER 시나리오 적정가",
                    "subtitle": f"Forward EPS 추정 × PER 범위 (현재 PER ×0.75 / ×1.0 / ×1.30)",
                    "kind": "scenario_price",
                    "scenarios": valid_per_scenarios,
                    "currentPrice": _finite_number(price),
                    "forwardEps": forward_eps,
                    "currency": price_currency,
                })

    # Price return vs benchmark chart
    yf_ticker = market.get("ticker") if market.get("ok") else (
        f"{company.get('ticker', '')}.KS"
        if company.get("market") == "KR" and re.fullmatch(r"\d{6}", company.get("ticker", ""))
        else company.get("ticker", "")
    )
    price_return_data = _compute_price_returns(yf_ticker)
    if price_return_data:
        charts.append({
            "id": "price_return",
            "title": "주가 수익률 비교",
            "subtitle": f"{company.get('ticker', '')} vs SPY vs QQQ",
            "kind": "price_return",
            "labels": price_return_data["labels"],
            "series": price_return_data["series"],
        })

    return {
        "available": bool(charts),
        "company": {"name": company.get("name", ""), "ticker": company.get("ticker", "")},
        "source": "SEC companyfacts + yfinance market data",
        # 차트 숫자는 전부 외부 provider에서 온다. 하나라도 NaN이면 보고서 저장이
        # canonical JSON에서 막혀 CLI가 만든 결과를 통째로 잃는다. 값 없음은 이미
        # None으로 표현하므로 여기서 같은 자리로 내린다.
        "charts": _finite_series(charts),
    }
