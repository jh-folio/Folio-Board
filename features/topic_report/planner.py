"""Topic Planner — 자유 입력 주제를 해석해 TopicPlan을 만든다 (설계 04 §3~5).

규칙 기반 해석이 기본이고, LLM이 켜져 있으면 계획을 정제한다.
LLM 결과는 topic_schema의 enum/정규화를 통과해야 하며, 실패 시 규칙 계획을 쓴다.
userContext는 질문 의도 파악에만 쓰고 사실/근거로 다루지 않는다.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy

from features.topic_report.topic_schema import (
    DEEP_MAX_QUESTIONS,
    DEEP_MAX_ROUND_1_QUESTIONS,
    DEEP_MAX_ROUND_2_QUESTIONS,
    EXPECTED_SECTIONS_V2,
    LEGACY_REPORT_TYPE_MAP,
    REPORT_TYPE_LABELS,
    normalize_report_type,
    compose_sections,
    normalize_topic_plan,
)

# ---------------------------------------------------------------------------
# 규칙 기반 분류
# ---------------------------------------------------------------------------

# (report_type, 가중치, 키워드) — 라벨에서 매칭된 가중치 합이 가장 큰 유형 선택
_TYPE_RULES: list[tuple[str, int, tuple[str, ...]]] = [
    ("supply_chain_theme", 3, ("공급망", "병목", "밸류체인", "supply chain", "bottleneck", "hbm", "수직계열")),
    ("policy_regulation", 3, ("규제", "정책", "법안", "관세", "보조금", "regulation", "policy", "tariff", "subsidy", "ira", "chips act")),
    ("geopolitical_risk", 3, ("지정학", "전쟁", "분쟁", "제재", "중동", "대만 리스크", "미중", "geopolit", "sanction", "war")),
    ("earnings_theme", 3, ("실적", "어닝", "가이던스", "eps", "earnings", "guidance", "컨센서스")),
    ("factor_style", 3, ("성장주", "가치주", "퀄리티", "배당주", "소형주", "모멘텀", "팩터", "스타일", "factor", "value stock", "growth stock", "high roic", "고roic")),
    ("company_basket", 2, ("수혜주", "관련주", "비교", "승자", "패자", "기업군", "바스켓", "basket", "누가 가장", "어떤 기업")),
    ("cross_asset_analysis", 2, ("환율과", "금리가", "달러와", "원화와", "엔화와", "주식에 미치는", "증시에 미치는", "채권에 미치는", "미치는 영향")),
    ("macro_analysis", 2, ("금리", "물가", "인플레이션", "환율", "중앙은행", "연준", "한국은행", "boj", "fed", "fomc", "경기", "침체", "유동성")),
    ("industry_theme", 2, ("산업", "섹터", "업종", "테마", "반도체", "전력 인프라", "데이터센터", "방산", "헬스케어", "에너지", "조선", "이차전지", "로봇")),
    ("country_market", 1, ("일본 시장", "중국 시장", "인도 시장", "한국 시장", "신흥국", "국가 시장")),
]

_REGION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Korea", ("한국", "korea", "원화", "krw", "코스피", "kospi", "한은", "삼성", "하이닉스", "국내")),
    ("US", ("미국", "us ", "u.s", "달러", "dollar", "연준", "fed", "nasdaq", "s&p", "장기금리")),
    ("Japan", ("일본", "japan", "엔화", "jpy", "boj", "닛케이", "nikkei", "종합상사")),
    ("China", ("중국", "china", "위안", "cny", "항셍")),
    ("Europe", ("유럽", "europe", "ecb", "유로", "euro")),
    ("Global", ("글로벌", "global", "세계")),
]

_ASSET_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("FX", ("환율", "원화", "엔화", "달러", "위안", "fx", "krw", "jpy", "usd")),
    ("rates", ("금리", "국채", "채권", "수익률", "yield", "rates", "장기금리")),
    ("equities", ("주식", "증시", "수혜주", "성장주", "기업", "주가", "코스피", "나스닥", "금융주", "반도체주", "수출주")),
    ("commodities", ("유가", "원유", "구리", "금 가격", "원자재", "commodity", "wti", "천연가스")),
    ("credit", ("회사채", "크레딧", "신용", "스프레드", "credit")),
]

# 키워드 → (ticker, 표시명). 라벨에서 발견되면 candidateTickers에 추가
_TICKER_HINTS: list[tuple[tuple[str, ...], str, str]] = [
    (("원화", "krw", "환율", "한국"), "USDKRW=X", "USD/KRW"),
    (("엔화", "jpy", "일본 금리", "boj"), "USDJPY=X", "USD/JPY"),
    (("달러", "dxy", "dollar"), "DX-Y.NYB", "DXY"),
    (("금리", "장기금리", "국채", "10년"), "^TNX", "미국 10년물 금리"),
    (("코스피", "한국 주식", "한국 증시", "수출주", "한국 금융주"), "^KS11", "KOSPI"),
    (("나스닥", "성장주", "기술주"), "QQQ", "Nasdaq 100"),
    (("s&p", "미국 증시", "미국 주식"), "SPY", "S&P 500"),
    (("닛케이", "일본 주식", "일본 증시", "종합상사"), "^N225", "Nikkei 225"),
    (("반도체", "hbm", "메모리"), "SOXX", "반도체 ETF"),
    (("전력", "유틸리티", "데이터센터"), "XLU", "유틸리티 섹터"),
    (("유가", "원유", "wti", "에너지"), "CL=F", "WTI 원유"),
    (("구리", "전선", "copper"), "HG=F", "구리 선물"),
    (("금 ", "gold", "안전자산"), "GC=F", "금"),
    (("장기채", "tlt"), "TLT", "미 장기채 ETF"),
    (("변동성", "vix", "리스크"), "^VIX", "VIX"),
    (("중국", "항셍"), "^HSI", "항셍지수"),
]

# FRED 시리즈 힌트 (requiredMacroData)
_MACRO_HINTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("금리", "연준", "fed", "rates", "국채"), ("FEDFUNDS", "DGS10", "DGS2", "T10Y2Y")),
    (("물가", "인플레이션", "cpi"), ("CPIAUCSL",)),
    (("고용", "실업"), ("UNRATE", "PAYEMS")),
    (("경기", "침체", "산업생산"), ("INDPRO",)),
    (("환율", "원화", "달러"), ("DGS10", "FEDFUNDS")),
]

# report_type별 필수 분석 축 (설계 §8)
_TYPE_AXES: dict[str, list[tuple[str, str]]] = {
    "macro_analysis": [
        ("policy_path", "정책금리 경로와 중앙은행 커뮤니케이션"),
        ("inflation_real_rates", "인플레이션과 실질금리"),
        ("fx_flows", "환율과 자본흐름"),
        ("risk_appetite", "위험선호/위험회피 환경"),
    ],
    "cross_asset_analysis": [
        ("equity_reaction", "주식시장 반응"),
        ("rates_reaction", "채권금리 반응"),
        ("fx_reaction", "환율 반응"),
        ("flows_volatility", "자금흐름과 변동성"),
    ],
    "industry_theme": [
        ("demand_drivers", "수요 증가 요인"),
        ("supply_pricing", "공급 병목과 가격/마진 구조"),
        ("value_chain", "밸류체인과 수혜/피해 기업"),
        ("capex_policy", "capex 사이클과 정책/규제"),
        ("valuation", "밸류에이션 반영 정도"),
    ],
    "supply_chain_theme": [
        ("final_demand", "최종 수요"),
        ("bottleneck", "병목 구간과 공급 확대 가능성"),
        ("pricing_power", "가격 결정력과 대체 가능성"),
        ("beneficiaries", "수혜 기업군과 리스크 요인"),
    ],
    "policy_regulation": [
        ("policy_content", "정책 내용과 시행 가능성·시점"),
        ("direct_impact", "직접 수혜/피해 산업"),
        ("second_order", "2차 파급효과"),
        ("priced_in", "시장 반영 정도와 정치적 지속 가능성"),
    ],
    "geopolitical_risk": [
        ("supply_shock", "공급 충격과 원자재 가격"),
        ("logistics", "운송/물류 영향"),
        ("sector_impact", "방산/에너지/소재 영향과 안전자산 흐름"),
        ("tail_risk", "tail risk와 리스크 완화 조건"),
    ],
    "earnings_theme": [
        ("earnings_trend", "실적 추세와 컨센서스 대비"),
        ("guidance", "가이던스와 이익 추정 방향"),
        ("sector_dispersion", "업종별 차별화"),
        ("valuation", "밸류에이션 반영 정도"),
    ],
    "factor_style": [
        ("factor_performance", "팩터/스타일 성과와 금리 민감도"),
        ("regime_fit", "현재 거시 환경과의 적합성"),
        ("valuation_spread", "밸류에이션 스프레드"),
        ("rotation_signal", "로테이션 신호와 체크포인트"),
    ],
    "company_basket": [
        ("exposure", "관련 기업 목록과 기업별 노출도"),
        ("sensitivity", "실적 민감도"),
        ("quality_valuation", "밸류에이션 부담과 재무 체력"),
        ("winners_losers", "승자/패자 구분과 확인할 지표"),
    ],
    "country_market": [
        ("macro_backdrop", "거시 환경과 정책"),
        ("market_structure", "시장 구조와 주도 업종"),
        ("flows", "외국인/기관 자금흐름"),
        ("valuation_risk", "밸류에이션과 리스크"),
    ],
    "portfolio_implication": [
        ("exposure_map", "포트폴리오 노출도"),
        ("scenario_impact", "시나리오별 영향"),
    ],
    "custom_research": [
        ("current_state", "현재 상황과 주요 사실"),
        ("drivers", "핵심 동인과 작동 경로"),
        ("market_link", "시장(주식·금리·환율)과의 연결"),
        ("risks", "반론과 리스크"),
    ],
}

_STOPWORDS = {
    "영향", "분석", "전망", "관련", "대한", "대해", "어떻게", "무엇", "정말", "주는", "미치는",
    "있는", "있나", "인가", "에서", "에게", "와", "과", "의", "이", "가", "은", "는", "을", "를",
    "the", "and", "for", "what", "how", "impact", "analysis",
    # 질문 문장에서 흔히 딸려오는 서술어. 검색어가 되면 아무 기사나 물어온다.
    "존재함", "가능성", "무엇인지", "파악해볼", "검토해서", "바라보는", "맞으면서", "자라고",
    "오르던", "최근", "이번", "여러", "다수", "가장", "내내", "대로", "반대로", "때문",
    # 접속·지시어. FTS가 토큰을 OR로 풀기 때문에 검색어에 남으면 아무 문서나 걸린다.
    "또는", "그리고", "하지만", "가운데", "위해", "따라", "통해", "각각", "어떤", "이런", "그런",
    # 사건을 가리키는 껍데기 말. 축 라벨에서 그대로 검색어가 되면 아무 기사나 걸린다
    # (실측: "기대 심리 사례" → 조폐공사·SK하이닉스 심리).
    "사례", "국면", "시기", "상황", "경우", "관점", "측면", "요인",
}

# 조사. `의`가 빠져 있어 `반도체의`가 검색어로 살아남았다.
_PARTICLES = "이가은는을를와과에의로서도만"


def _label_keywords(label: str, limit: int = 8) -> list[str]:
    """라벨에서 의미 있는 키워드 추출 — 기존 label.split()의 개선판."""
    tokens = re.findall(r"[A-Za-z가-힣0-9&=^.\-]{2,}", str(label or ""))
    out: list[str] = []
    for token in tokens:
        clean = token.strip(".,?!")
        if len(clean) < 2 or clean.lower() in _STOPWORDS:
            continue
        if len(clean) >= 3 and clean[-1] in _PARTICLES:
            clean = clean[:-1]
        if clean.lower() in _STOPWORDS:
            continue
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


# 질문 문단에서 주제어를 끊어낼 자리. 사람이 "주제: 배경 - 배경" 순으로 쓴다.
_SUBJECT_SPLIT = re.compile(r"[:：\n\r]|\s[-–—]\s|(?<=[.?!])\s")
_SUBJECT_MAX = 40


def topic_subject(label: str) -> str:
    """긴 질문에서 짧은 주제어를 뽑는다.

    사용자는 질문칸에 배경까지 한 문단으로 적는다. 그 240자를 `주제 라벨`로 쓰면
    축 질문도 검색어도 전부 같은 문단이 되고, 검색은 토큰이 OR로 풀려 아무 기사나
    물어온다. 계획이 흐린 게 아니라 근거가 흐려진다.

    첫 구획(콜론·줄바꿈·` - `·문장 끝 앞)을 주제로 보고, 그래도 길면 키워드로 줄인다.
    """
    text = str(label or "").strip()
    if not text:
        return ""
    head = _SUBJECT_SPLIT.split(text, maxsplit=1)[0].strip(" -–—·,")
    if head and len(head) <= _SUBJECT_MAX:
        return head
    # 첫 구획도 길면 앞쪽 키워드 몇 개로 압축한다.
    words = _label_keywords(head or text, limit=4)
    if words:
        subject = " ".join(words)
        return subject[:_SUBJECT_MAX].strip()
    return text[:_SUBJECT_MAX].strip()


def _detect_report_type(text: str) -> str:
    lower = text.lower()
    scores: dict[str, int] = {}
    for rtype, weight, keywords in _TYPE_RULES:
        hit = sum(1 for kw in keywords if kw in lower)
        if hit:
            scores[rtype] = scores.get(rtype, 0) + hit * weight
    if not scores:
        return "custom_research"
    # cross_asset은 "X가 Y에 미치는 영향" 패턴에서 macro와 경합 — 자산군 2개 이상이면 cross 우선
    best = max(scores.items(), key=lambda kv: kv[1])[0]
    if best == "macro_analysis" and scores.get("cross_asset_analysis"):
        asset_hits = sum(1 for _, kws in _ASSET_RULES if any(k in lower for k in kws))
        if asset_hits >= 2:
            return "cross_asset_analysis"
    return best


def _detect_listed(text: str, rules: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    lower = text.lower()
    return [name for name, keywords in rules if any(kw in lower for kw in keywords)]


def _explicit_tickers(label: str) -> dict[str, str]:
    """라벨 안의 명시적 티커(GEV, ETN, VRT 같은 2~5자 대문자)를 추출.

    'VRT에'처럼 한글 조사가 붙으면 \\b 경계가 성립하지 않으므로
    라틴 문자 기준 경계((?<![A-Za-z]) ... (?![A-Za-z]))로 잡는다."""
    out: dict[str, str] = {}
    for token in re.findall(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])", str(label or "")):
        if token in {"AI", "US", "EU", "ETF", "IPO", "CEO", "GDP", "CPI", "PER", "ROE", "ROIC", "FED", "BOJ", "BOK", "KRW", "JPY", "USD", "CNY", "HBM"}:
            continue
        out[token] = token
    return out


def _candidate_tickers(text: str, label: str) -> dict[str, str]:
    lower = text.lower()
    out = _explicit_tickers(label)
    for keywords, ticker, name in _TICKER_HINTS:
        if any(kw in lower for kw in keywords) and ticker not in out:
            out[ticker] = name
        if len(out) >= 12:
            break
    return out


def _required_macro(text: str) -> list[str]:
    lower = text.lower()
    out: list[str] = []
    for keywords, series in _MACRO_HINTS:
        if any(kw in lower for kw in keywords):
            for s in series:
                if s not in out:
                    out.append(s)
    return out


_QUERY_MAX = 40


def _josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """받침에 맞는 조사를 고른다. `요인은(는)`처럼 둘 다 적어두지 않는다."""
    text = str(word or "").strip()
    if not text:
        return without_batchim
    last = text[-1]
    if "가" <= last <= "힣":
        return with_batchim if (ord(last) - 0xAC00) % 28 else without_batchim
    # 숫자·라틴 문자는 읽는 사람마다 갈리므로 받침 없는 쪽으로 통일한다.
    return without_batchim


def _term(word: str) -> str:
    """축 이름에서 뽑은 낱말의 꼬리 조사를 떼어낸다(`병목과` → `병목`)."""
    clean = str(word or "").strip()
    if len(clean) >= 3 and clean[-1] in _PARTICLES:
        clean = clean[:-1]
    return clean


# 벌거벗은 숫자 토큰. `2021`, `2022`, `2021~2022`처럼 단위 없는 숫자만으로 이뤄진 말이다.
_BARE_NUMBER = re.compile(r"^[0-9]+(?:[~\-–][0-9]+)?$")


def _drop_bare_numbers(text: str) -> str:
    """검색어에서 단위 없는 숫자를 뺀다. 남는 말이 없으면 원문을 그대로 둔다."""
    tokens = str(text or "").split()
    kept = [token for token in tokens if not _BARE_NUMBER.fullmatch(token.strip(".,"))]
    # 숫자를 빼고 나면 검색할 말이 없는 질의(예: "2021 2022")는 손대지 않는다 —
    # 어차피 아래 `_usable_query`가 걸러낸다.
    return " ".join(kept) if len(kept) >= 2 else str(text or "")


def _usable_query(text: str) -> str:
    """검색어로 쓸 만한 형태인가.

    한 단어짜리(`피크`)와 질문 전문은 버린다. 전자는 전력망 기사를, 후자는 토큰이
    OR로 풀려 그날 시장 기사 아무거나 물어온다. 둘 다 실제로 확인한 결과다.
    """
    clean = " ".join(_drop_bare_numbers(str(text or "")).split())
    if not clean or len(clean) > _QUERY_MAX:
        return ""
    return clean if len(clean.split()) >= 2 else ""


def _clean_queries(queries, fallback) -> list[str]:
    """질문 전문과 한 단어짜리를 걸러낸다. 전부 걸리면 규칙 질의로 되돌린다."""
    out: list[str] = []
    for item in queries or []:
        query = _usable_query(item)
        if query and query not in out:
            out.append(query)
    return out[:12] or [q for q in (fallback or []) if q][:4]


def _axis_queries(subject: str, axis_label: str, keywords: list[str]) -> list[str]:
    """축 검색어 = 주제어 + 그 축을 가리키는 말 하나."""
    axis_terms = [
        term for term in (_term(w) for w in re.findall(r"[A-Za-z가-힣]{2,}", axis_label))
        if term and term not in _STOPWORDS
    ][:2]
    base = _drop_bare_numbers(subject or " ".join(keywords[:2]))
    queries = []
    for term in axis_terms[:2]:
        query = _usable_query(f"{base} {term}")
        if query and query not in queries:
            queries.append(query)
    if not queries:
        fallback = _usable_query(base)
        if fallback:
            queries.append(fallback)
    return queries[:3]


# 사용자가 질문에서 직접 나열한 항목. 줄머리 기호나 번호로 적은 것들이다.
_QUESTION_PART = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s*(.+?)\s*$", re.MULTILINE)
_PART_MAX_LENGTH = 60


def question_parts(topic: str, limit: int = 6) -> list[str]:
    """사용자가 질문에 직접 적어 준 사례·구간 목록.

    "- 2021~2022 인플레이션 사례" 처럼 나열한 것은 **이 보고서가 다뤄야 할 대상**이지
    참고 사항이 아니다. 실측으로 이걸 무시했더니 플래너가 표준 거시 축으로 갈아치웠고,
    2021~2022 사례가 보고서에서 통째로 사라졌다(본문에 '2021' 0회).
    """
    parts: list[str] = []
    for raw in _QUESTION_PART.findall(str(topic or "")):
        text = " ".join(str(raw).split()).strip(" .·")
        if not text or len(text) > _PART_MAX_LENGTH:
            continue
        if len(_label_keywords(text, limit=2)) < 1 or text in parts:
            continue
        parts.append(text)
        if len(parts) >= limit:
            break
    return parts


def _covers(part: str, axes: list[dict]) -> bool:
    """이 항목이 이미 어떤 축으로 들어가 있는가.

    연도·사건명처럼 그 항목을 구별짓는 말이 축 라벨에 들어 있으면 덮인 것으로 본다.
    """
    tokens = [token for token in _label_keywords(part, limit=6) if len(token) >= 2]
    if not tokens:
        return True
    for axis in axes:
        label = str((axis or {}).get("label") or "")
        hits = sum(1 for token in tokens if token in label)
        if hits >= min(2, len(tokens)):
            return True
    return False


def ensure_question_axes(plan: dict, topic: str, *, limit: int = 6) -> dict:
    """질문이 명시한 항목을 분석축으로 올린다. 축은 곧 본문 섹션이다."""
    out = dict(plan or {})
    parts = question_parts(topic)
    if not parts:
        return out
    axes = [dict(axis) for axis in out.get("analysisAxes") or []]
    subject = topic_subject(topic) or str(out.get("topicLabel") or "")
    keywords = _label_keywords(topic, limit=6)
    added: list[dict] = []
    for index, part in enumerate(parts):
        if _covers(part, axes + added):
            continue
        added.append({
            "key": f"asked_{index + 1}",
            "label": part[:60],
            "questions": [f"{part}에서 무엇이 확인되며, 그것이 이 질문에 어떤 답을 주는가?"],
            "searchQueries": _axis_queries(subject, part, keywords),
        })
    if not added:
        return out
    # 사용자가 든 사례를 앞에 둔다. 뒤로 밀면 상한에 잘려 사라진다.
    out["analysisAxes"] = (added + axes)[:limit]
    return out


def _data_gaps(report_type: str, regions: list[str]) -> list[str]:
    gaps = []
    if report_type in {"company_basket", "earnings_theme"}:
        gaps.append("개별 기업 컨센서스/이익 추정치는 로컬 자료에 없을 수 있어 웹 검색 보완이 필요합니다.")
    if report_type in {"macro_analysis", "cross_asset_analysis"}:
        gaps.append("외국인/기관 수급 상세 데이터는 제공되지 않아 가격·뉴스 기반 추정에 의존합니다.")
    if report_type in {"policy_regulation", "geopolitical_risk"}:
        gaps.append("최신 정책 발표/사건 전개는 로컬 자료 시차가 있어 웹 검색 보완이 필요할 수 있습니다.")
    if "Korea" in regions:
        gaps.append("한국 종목 단위 재무 상세는 SEC 기반 파이프라인 범위 밖일 수 있습니다.")
    if not gaps:
        gaps.append("주제 특화 데이터가 부족하면 보고서에 데이터 한계를 명시합니다.")
    return gaps


def build_rule_plan(topic: str, *, user_context: str = "") -> dict:
    """규칙 기반 TopicPlan. LLM 없이 항상 동작해야 한다 (절대 규칙 4)."""
    label = str(topic or "").strip()
    # 분류는 질문 전문을 본다(단서가 배경 문단에 있다). 파생물은 주제어 위에 세운다.
    subject = topic_subject(label)
    # userContext는 의도 파악 보조로만 — 분류 텍스트에 합치되 근거로는 쓰지 않음
    intent_text = f"{label} {str(user_context or '')[:300]}"
    report_type = _detect_report_type(intent_text)
    keywords = _label_keywords(label)
    regions = _detect_listed(intent_text, _REGION_RULES)
    assets = _detect_listed(intent_text, _ASSET_RULES)
    tickers = _candidate_tickers(intent_text, label)

    axes = []
    for i, (key, axis_label) in enumerate(_TYPE_AXES.get(report_type, _TYPE_AXES["custom_research"])):
        axes.append({
            "key": key,
            "label": axis_label,
            "questions": [f"{subject} 관점에서 {axis_label}{_josa(axis_label, '은', '는')} 어떤 상태인가?"],
            "requiredData": list(tickers.keys())[:4],
            "searchQueries": _axis_queries(subject, axis_label, keywords),
        })
        if i >= 5:
            break

    search_queries = []
    for candidate in (subject, " ".join(keywords[:3])):
        query = _usable_query(candidate)
        if query and query not in search_queries:
            search_queries.append(query)
    for axis in axes:
        for q in axis["searchQueries"]:
            if q not in search_queries:
                search_queries.append(q)

    plan = {
        "topic": label,
        # 목록과 보고서 제목에 쓰이는 이름. 240자 문단을 제목으로 달지 않는다.
        "topicLabel": subject or label,
        "reportType": report_type,
        "regions": regions,
        "assetClasses": assets,
        "userIntent": "investment implication",
        "researchQuestions": [
            f"{subject}의 현재 상황과 핵심 동인은 무엇인가?",
            f"{subject}{_josa(subject, '이', '가')} 시장 가격·실적·수급에 어떤 경로로 작동하는가?",
            "이 판단이 틀릴 수 있는 반대 근거는 무엇인가?",
        ],
        "analysisAxes": axes,
        "requiredMarketData": list(tickers.keys()),
        "requiredMacroData": _required_macro(intent_text),
        "searchQueries": search_queries,
        "memoryQueries": [k.lower() for k in keywords],
        "candidateTickers": tickers,
        # 본문 섹션은 분석축이 정한다. 축이 곧 이 보고서가 답해야 할 것들이므로,
        # 그것을 가중치 15%짜리 섹션 하나에 밀어 넣지 않고 각각 자기 자리를 준다.
        "expectedSections": compose_sections(axis["label"] for axis in axes),
        "dataGapsLikely": _data_gaps(report_type, regions),
    }
    return normalize_topic_plan(ensure_question_axes(plan, label), topic=label, topic_label=subject or label)


def _question_queries(
    question: str,
    *,
    subject: str,
    base_queries: list[str],
    index: int,
    used_heads: set[str] | None = None,
) -> list[str]:
    """하위 질문의 검색어. 질문마다 달라야 한다.

    예전에는 연구질문 전부에 `base_queries[:2]`를 그대로 줬다. 같은 질의 + 전역
    중복 제거라 앞 질문이 결과를 다 먹고 뒤 질문은 0건이 됐고, 그 0건이 "이 질문은
    로컬 근거가 부족합니다"라는 데이터 갭으로 보고서에 실렸다 — 자료가 없어서가
    아니라 같은 검색을 반복해서 생긴 0건이다.
    """
    keywords = _label_keywords(question, limit=6)
    out: list[str] = []
    for size in (3, 2):
        own = _usable_query(" ".join(keywords[:size]))
        if own:
            out.append(own)
            break
    if subject and keywords:
        paired = _usable_query(f"{subject} {keywords[0]}")
        if paired and paired not in out:
            out.append(paired)
    usable_base = [q for q in (base_queries or []) if q]
    if usable_base:
        offset = index % len(usable_base)
        for query in usable_base[offset:] + usable_base[:offset]:
            if query not in out:
                out.append(query)
            if len(out) >= 4:
                break
    # 규칙 계획의 연구질문은 "{주제}의 현재 상황은?", "{주제}가 시장에 작동하는
    # 경로는?"처럼 주제어가 지배해서 뽑히는 키워드가 같다. 앞선 질문이 이미 쓴
    # 검색어가 선두면 뒤로 미뤄, 첫 질의만이라도 서로 다르게 만든다.
    taken = used_heads or set()
    if len(out) > 1 and out[0] in taken:
        for position, query in enumerate(out):
            if query not in taken:
                out = [query] + out[:position] + out[position + 1:]
                break
    return out[:4]


def apply_deep_research_plan(plan: dict, *, max_rounds: int = 2, max_questions: int = DEEP_MAX_QUESTIONS) -> dict:
    """Attach bounded deep-research subquestions to a normalized TopicPlan.

    The base TopicPlan remains compatible with existing consumers. Deep metadata
    is opt-in and keeps the loop finite: round 1 covers core/axis questions,
    round 2 only probes gaps and falsification.
    """
    out = deepcopy(plan if isinstance(plan, dict) else {})
    max_rounds = max(1, min(2, int(max_rounds or 2)))
    max_questions = max(3, min(DEEP_MAX_QUESTIONS, int(max_questions or DEEP_MAX_QUESTIONS)))
    axes = out.get("analysisAxes") or []
    base_queries = list(out.get("searchQueries") or [])[:3]
    subject = str(out.get("topicLabel") or "").strip()
    round_caps = {1: DEEP_MAX_ROUND_1_QUESTIONS, 2: DEEP_MAX_ROUND_2_QUESTIONS}

    subquestions: list[dict] = []

    def add_question(question: str, *, axis_key: str = "", round_no: int = 1, queries: list[str] | None = None) -> None:
        text = str(question or "").strip()
        normalized_round = max(1, min(max_rounds, int(round_no or 1)))
        if not text or len(subquestions) >= max_questions:
            return
        if sum(int(row.get("round") or 1) == normalized_round for row in subquestions) >= round_caps.get(normalized_round, 6):
            return
        if any(q["question"] == text for q in subquestions):
            return
        qid = f"dq_{len(subquestions) + 1:02d}"
        search_queries = [q for q in (queries or []) if str(q or "").strip()]
        if not search_queries:
            search_queries = base_queries[:2]
        subquestions.append({
            "id": qid,
            "question": text[:240],
            "axisKey": axis_key,
            "round": normalized_round,
            "searchQueries": search_queries[:4],
        })

    used_heads: set[str] = set()
    for index, question in enumerate(out.get("researchQuestions") or []):
        queries = _question_queries(
            question,
            subject=subject,
            base_queries=base_queries,
            index=index,
            used_heads=used_heads,
        )
        if queries:
            used_heads.add(queries[0])
        add_question(question, round_no=1, queries=queries)

    # 축은 너비 우선으로 채운다. 축 하나씩 두 질문을 다 넣으면 앞 축이 상한을 먹고
    # 뒤 축은 질문을 하나도 못 받는다 — 실제로 축 5개 중 1~2개만 검색됐다.
    for slot in (0, 1):
        for axis in axes:
            axis_key = axis.get("key", "")
            queries = list(axis.get("searchQueries") or []) or base_queries
            questions = axis.get("questions") or [f"{axis.get('label', '')}에 대한 핵심 근거는 무엇인가?"]
            if slot < len(questions[:2]):
                add_question(questions[slot], axis_key=axis_key, round_no=1, queries=queries)

    if max_rounds >= 2:
        topic = out.get("topicLabel") or out.get("topic") or "이 주제"
        add_question(
            f"{topic}에 대한 현재 결론을 약화시키는 반대 근거는 무엇인가?",
            round_no=2,
            queries=(base_queries + ["리스크 반론 downside risk"])[:4],
        )
        add_question(
            f"{topic} 판단을 바꿔야 하는 정량 조건은 무엇인가?",
            round_no=2,
            queries=(base_queries + ["falsification trigger data"])[:4],
        )

    if len(subquestions) < 3:
        topic = out.get("topicLabel") or out.get("topic") or "이 주제"
        add_question(f"{topic}의 현재 상황을 보여주는 가장 중요한 데이터는 무엇인가?", round_no=1, queries=base_queries)
        add_question(f"{topic}이 시장 가격에 작동하는 경로는 무엇인가?", round_no=1, queries=base_queries)
        add_question(f"{topic} 분석이 틀릴 수 있는 조건은 무엇인가?", round_no=min(2, max_rounds), queries=base_queries)

    out["deepResearch"] = {
        "enabled": True,
        "maxRounds": max_rounds,
        "subQuestions": subquestions[:max_questions],
        "falsificationTriggers": [
            "핵심 가격·지표가 보고서의 기본 시나리오와 반대로 2회 이상 확인된다.",
            "주요 수혜/피해 기업의 실적·가이던스가 예상 작동 경로와 반대로 나온다.",
            "정책·금리·환율 전제가 바뀌어 기존 인과 경로가 더 이상 성립하지 않는다.",
        ],
        "requiredOutputs": [
            "scenario_table",
            "counter_arguments",
            "falsification_triggers",
            "quantitative_evidence_table",
        ],
    }
    return out


def plan_from_preset(config: dict) -> dict:
    """기존 프리셋 설정 → TopicPlan (backward compatible 경로)."""
    label = config.get("label", "")
    axes = []
    for i, axis_label in enumerate(config.get("theme_axes", [])):
        axes.append({
            "key": f"axis_{i + 1}",
            "label": axis_label,
            "questions": [],
            "requiredData": list(config.get("tickers", {}).keys())[:4],
            "searchQueries": [" ".join(config.get("search_keywords", [])[:3])],
        })
    plan = {
        "topic": label,
        "topicLabel": label,
        "reportType": LEGACY_REPORT_TYPE_MAP.get(config.get("report_type", ""), "custom_research"),
        "regions": [],
        "assetClasses": [],
        "researchQuestions": [],
        "analysisAxes": axes,
        "requiredMarketData": list(config.get("tickers", {}).keys()),
        "requiredMacroData": list(config.get("fred_series", [])),
        "searchQueries": config.get("search_keywords", [])[:12],
        "memoryQueries": config.get("memory_keywords", [])[:10],
        "candidateTickers": dict(config.get("tickers", {})),
        "expectedSections": config.get("report_sections", []) or list(EXPECTED_SECTIONS_V2),
        "dataGapsLikely": [],
    }
    return normalize_topic_plan(plan, topic=label, topic_label=label)


# ---------------------------------------------------------------------------
# LLM 정제 (선택)
# ---------------------------------------------------------------------------

_PLANNER_PROMPT = """당신은 투자 리서치 플래너입니다. 사용자의 리서치 주제를 해석해 아래 JSON 스키마의 TopicPlan을 작성하세요.

규칙:
- reportType은 다음 중 하나만: {report_types}
- 사용자 컨텍스트는 관심 방향 파악에만 쓰고, 그 전제를 사실로 간주하지 마세요.
- **사용자가 질문에서 직접 든 사례·구간·항목(연도, 사건, 국면)은 반드시 각각 하나의 분석축이 된다.**
  표준 거시 축으로 갈아치우지 마라. 축이 곧 보고서의 본문 섹션이므로, 축에서 빠지면 보고서에서 사라진다.
- 질문이 "A는 B에 어떤 영향을 주고 C에 어떤 어려움을 주는가" 형태면 B와 C 각각이 축이 되어야 한다.
- analysisAxes는 3~5개. 각 축에 key(영문 snake_case), label(한국어), questions(1~2개), searchQueries(1~3개, 한국어+영어 혼합)를 넣으세요.
- topicLabel은 40자 이내의 짧은 주제어입니다. 질문 문단을 그대로 옮기지 마세요.
- searchQueries는 로컬 뉴스 검색용 2~5어절 구문입니다. 질문 전문이나 한 단어짜리는 넣지 마세요.
- candidateTickers는 yfinance 형식 심볼로.
- dataGapsLikely에는 로컬 자료만으로 부족할 법한 데이터를 적으세요.
- JSON 객체 하나만 출력하세요. 다른 텍스트 금지.

스키마 키: topic, topicLabel, reportType, regions, assetClasses, timeHorizon, userIntent,
researchQuestions, analysisAxes, requiredMarketData, requiredMacroData, searchQueries,
memoryQueries, candidateTickers, dataGapsLikely"""


def _plan_via_cli(prompt: str, context: str) -> str:
    """Agent CLI로 계획을 받아온다.

    이 설치의 Agent는 API 키가 아니라 CLI(Codex/Claude)로 돈다. 플래너만 직접 API
    경로를 보고 있어서, 보고서를 쓰는 엔진이 멀쩡히 있는데도 계획은 늘 규칙으로
    떨어졌다. 켤 설정이 없는 게 아니라 플래너가 그 엔진을 몰랐던 것이다.
    """
    try:
        from features.agent_mode.bridge import bridge_status, run_agent_prompt
    except Exception:
        return ""
    if not bridge_status().get("available"):
        return ""
    timeout = max(30, int(os.environ.get("TOPIC_PLANNER_TIMEOUT_SECONDS", "120")))
    result = run_agent_prompt(f"{prompt}\n\n---\n\n{context}", timeout=timeout)
    return str(result.get("output") or "")


def refine_plan_with_llm(
    rule_plan: dict,
    topic: str,
    user_context: str = "",
    *,
    current_plan: dict | None = None,
    instruction: str = "",
) -> tuple[dict, str]:
    """LLM으로 계획을 쓴다. 실패하면 (rule_plan, 사유) 반환.

    `instruction`이 있으면 처음부터 쓰지 않고 `current_plan`을 그 요청대로 고친다.
    사용자는 칸을 하나씩 고치기보다 "축 하나 빼고 검색어를 한국어로"처럼 말한다.
    """
    try:
        from features.llm_settings.client import (
            extract_json_object,
            request_llm_text,
            selected_llm_config,
            use_llm_analysis,
        )
    except Exception:
        return rule_plan, "llm_unavailable"
    if not use_llm_analysis():
        return rule_plan, "llm_disabled"
    try:
        cfg = selected_llm_config()
    except Exception:
        # 이 함수의 계약은 "실패하면 rule_plan"이다. `selected_llm_config()`는
        # 설정값(예: 지원 안 되는 `AI_AGENT_REASONING_EFFORT`)이 안 맞으면 예외를
        # 던지는데, 이 줄만 두 try 블록 사이에 안 감싸여 있어 그 예외가 그대로
        # 새 나갔다 — 계획을 아예 못 만드는 대신 규칙 계획으로 내려가야 한다.
        return rule_plan, "llm_config_invalid"
    prompt = _PLANNER_PROMPT.format(report_types=", ".join(sorted(REPORT_TYPE_LABELS)))
    context_lines = [f"리서치 주제: {topic}"]
    if user_context.strip():
        context_lines.append(f"사용자 컨텍스트(관심 방향, 사실 아님): {user_context.strip()[:500]}")
    # 수정 요청이 있으면 지금 계획을 고친다. 규칙 계획에서 다시 시작하면 사용자가
    # 앞서 받아 든 계획이 통째로 사라져 무엇이 반영됐는지 알 수 없다.
    base_plan = current_plan if (instruction.strip() and current_plan) else rule_plan
    context_lines.append(f"현재 계획(수정 대상):\n{json.dumps(base_plan, ensure_ascii=False, indent=1)[:3500]}")
    if instruction.strip():
        context_lines.append(
            "사용자 수정 요청 — 이 요청만 반영하고 나머지는 그대로 두세요:\n"
            + instruction.strip()[:1000]
        )
    context = "\n\n".join(context_lines)
    try:
        if cfg.get("apiKey"):
            text, _rid = request_llm_text(cfg, prompt, context, json_mode=True, max_output_tokens=2500)
        else:
            text = _plan_via_cli(prompt, context)
            if not text.strip():
                return rule_plan, "no_engine"
        raw = extract_json_object(text)
        if not isinstance(raw, dict):
            return rule_plan, "parse_failed"
        refined = normalize_topic_plan(
            ensure_question_axes(raw, topic), topic=topic, topic_label=topic_subject(topic) or topic
        )
        # LLM이 비워버린 핵심 필드는 규칙 계획으로 보강 (계획이 후퇴하지 않게)
        for key in ("searchQueries", "memoryQueries", "candidateTickers", "analysisAxes", "dataGapsLikely"):
            if not refined.get(key):
                refined[key] = rule_plan.get(key, refined.get(key))
        # 검색어 위생은 코드가 정한다. 프롬프트로 부탁한 것과 지킨 것은 다르고,
        # 여기서 새는 질의는 곧 근거 품질이다(§5 원칙 4).
        refined["searchQueries"] = _clean_queries(refined.get("searchQueries"), rule_plan.get("searchQueries"))
        for axis in refined.get("analysisAxes") or []:
            axis["searchQueries"] = _clean_queries(axis.get("searchQueries"), refined["searchQueries"][:2])
        return refined, "llm"
    except Exception:
        return rule_plan, "llm_generation_failed"


def build_topic_plan(
    topic_key: str,
    custom_label: str = "",
    user_context: str = "",
    *,
    llm_override=None,
    preset_config: dict | None = None,
    current_plan: dict | None = None,
    instruction: str = "",
) -> dict:
    """진입점. 프리셋이면 설정 기반 plan, custom이면 규칙 해석(+선택 LLM 정제)."""
    if topic_key != "custom":
        if preset_config is None:
            from features.topic_report.topic_config import get_topic_config
            preset_config = get_topic_config(topic_key)
        plan = plan_from_preset(preset_config)
        plan["plannerMode"] = "preset"
        return plan
    label = (custom_label or "커스텀 주제").strip()
    rule_plan = build_rule_plan(label, user_context=user_context)
    use_llm = True if llm_override is None else bool(llm_override)
    if use_llm:
        plan, mode = refine_plan_with_llm(
            rule_plan, label, user_context, current_plan=current_plan, instruction=instruction
        )
    else:
        plan, mode = rule_plan, "rules"
    plan["plannerMode"] = "llm" if mode == "llm" else "rules"
    return plan
