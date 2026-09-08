"""일일 브리핑 전용 자료 선별/시장 동인 그룹화.

기존 `marketRelevance`(인덱싱용)와 `group_docs()`(회사/섹터 묶음)는 그대로 두고,
브리핑 품질 개선을 위한 다음 로직을 분리해 담는다.

- `briefing_doc_score()`     : "이 자료가 오늘 브리핑에서 얼마나 쓸 만한가" 전용 점수
- `infer_drivers()`          : 문서가 어떤 시장 동인에 속하는지 추론
- `derive_market_drivers()`  : 문서들을 금리/환율/반도체 등 시장 동인으로 묶음
- `briefing_doc_excerpt()`   : driver/group/support tier에 따라 발췌 길이를 차등

service.py / app.py 는 이 모듈을 얇게 호출한다.
"""
import re

from features.common.company_lookup import term_in_text
from features.common.utils import normalize, clean_embedded_sections
from features.common.market_calendar import (
    doc_analysis_priority,
    doc_market_bucket,
    previous_trading_day,
    parse_iso_date,
)


# ---------------------------------------------------------------------------
# 시장 거래일(marketSessionDate) 추론
# ---------------------------------------------------------------------------
# 한국 언론의 '뉴욕증시 마감/브리핑' 류 기사는 한국시간 D일에 발행돼도 보통 미국
# D-1 정규장 마감 결과를 다룬다. 발행일을 그대로 미국장 거래일로 쓰면 전 거래일
# 결과를 당일 결과로 오인하므로, 이런 기사는 발행일 직전 미국 거래일로 보정한다.
_KO_US_CLOSE_TERMS = [
    "뉴욕증시", "뉴욕 증시", "미국증시", "미국 증시", "미 증시", "美 증시", "美증시",
    "뉴욕 마감", "뉴욕증시 브리핑", "월가",
]
_HANGUL_RE = re.compile(r"[가-힣]")


def is_us_market_close_article(doc):
    """한국 언론의 '뉴욕증시 마감/브리핑' 류 기사인지 추정한다.

    한글 제목/매체(=한국 언론)이면서 미국 증시 마감을 가리키는 표현이 있으면 True.
    이런 기사는 발행일(KST)이 실제 미국 정규장 거래일보다 하루 앞설 수 있다.
    """
    blob = f"{doc.get('title', '')} {doc.get('source', '')}"
    if not _HANGUL_RE.search(blob):  # 한국 언론에 한정
        return False
    hay = blob.lower()
    return any(term.lower() in hay for term in _KO_US_CLOSE_TERMS)


def infer_market_session_date(doc, market_windows=None):
    """자료가 실제로 다루는 '시장 거래일'을 추정한다.

    - 명시적 `marketSessionDate`가 있으면 그것을 사용.
    - 한국 언론의 미국 증시 마감 기사: 발행일(KST) 직전 미국 거래일(= 미국 D-1)을 사용.
    - 그 외 자료: 발행일(doc.date)을 그대로 사용.

    발행일만 보고 미국장 거래일을 단정하지 않기 위한 보정이다.
    """
    explicit = doc.get("marketSessionDate")
    if explicit:
        return explicit
    date_str = str(doc.get("date", ""))[:10]
    if not date_str:
        return date_str
    if is_us_market_close_article(doc):
        try:
            return previous_trading_day(parse_iso_date(date_str), "US").isoformat()
        except Exception:
            return date_str
    return date_str


def session_doc_counts(docs, market_windows):
    """브리핑 후보 자료를 세션 버킷별로 센다(디버그/데이터 부족 진단용).

    krCurrentIntradayDocCount가 0이면 한국 D 장중이 약한 이유가 코드가 아니라
    자료 부족임을 바로 알 수 있다.
    """
    counts = {
        "krCurrentIntradayDocCount": 0,
        "usPrevRegularDocCount": 0,
        "krPrevRegularDocCount": 0,
    }
    for d in docs:
        bucket = doc_market_bucket(d, market_windows)
        if bucket == "KR 당일 개장/장중":
            counts["krCurrentIntradayDocCount"] += 1
        elif bucket == "US 전일 정규장":
            counts["usPrevRegularDocCount"] += 1
        elif bucket == "KR 전일 정규장":
            counts["krPrevRegularDocCount"] += 1
    return counts


# ---------------------------------------------------------------------------
# 시장 동인(term) 매핑
# ---------------------------------------------------------------------------
# 시장 동인 어휘표. **브리핑 동인 선정과 대시보드 이야기 비중이 이 표를 공유한다** —
# 한쪽을 고치면 다른 쪽도 같이 움직이므로 측정 없이 손대지 않는다.
#
# 한글 토큰은 `term_in_text`에서 단어 경계 없이 부분일치한다(영문·숫자만 경계를 갖는다).
# 그래서 짧은 한글 어휘는 다른 낱말 안에 숨어 있는 것까지 잡는다 — 실측으로 `금` 하나가
# 문서의 24.5%를 물었고 그중 실제 매칭은 금리 2,712 · 금융 1,052 · 기준금리 320 · 자금 ·
# 세금 · 연금 · 임금이었다. 금값 기사는 거의 없었다. 한 글자 한글 어휘를 새로 넣지 않는다.
DRIVER_TERMS = {
    "금리": [
        "fed", "fomc", "treasury", "yield", "rate", "bond",
        "금리", "연준", "국채", "채권", "수익률",
    ],
    "환율/달러": [
        "dollar", "dxy", "currency", "fx", "won", "yen",
        "환율", "원달러", "달러", "원화", "엔화", "강달러",
    ],
    "반도체/AI": [
        "nvidia", "hbm", "gpu", "semiconductor", "chip", "ai", "data center",
        "엔비디아", "반도체", "gpu", "인공지능", "데이터센터",
    ],
    "원자재/유가": [
        "oil", "crude", "wti", "brent", "energy", "gas", "gold",
        # `금` 한 글자는 금리·금융·자금·세금·연금·임금을 전부 물어 이 동인을 부풀렸다
        # (실측: 문서의 14.8%가 그 한 어휘만으로 여기 들어왔고 대부분 금리 기사였다).
        # 금값을 가리키는 표기만 남긴다. 영문은 `gold`가 이미 경계를 갖는다.
        "유가", "원유", "브렌트", "천연가스", "원자재", "금값", "금 가격", "금시세", "귀금속",
    ],
    "수급": [
        "foreign buying", "foreign selling", "institution", "retail", "volume",
        "외국인", "기관", "개인", "순매수", "순매도", "거래대금", "수급",
    ],
    "정책/규제": [
        "policy", "regulation", "tariff", "sanction", "subsidy", "tax",
        "정책", "규제", "관세", "제재", "보조금", "세제", "정부",
    ],
    "실적/가이던스": [
        "earnings", "guidance", "revenue", "margin", "profit", "sales",
        "실적", "가이던스", "매출", "영업이익", "마진", "이익",
    ],
    "중국/글로벌 경기": [
        "china", "pmi", "manufacturing", "export", "global growth",
        "중국", "제조업", "수출", "경기", "글로벌 경기",
    ],
    "지정학": [
        "geopolitical", "war", "conflict", "middle east", "taiwan",
        "지정학", "전쟁", "분쟁", "중동", "대만",
    ],
    # 2026 시장 보도에서 독립된 이야기인데 표에 없었다. 실측 334건(1.8%)이 걸리고
    # 그중 80건은 어느 동인에도 속하지 못해 `그 외`로 빠져 있었다.
    "크립토": [
        "bitcoin", "ethereum", "crypto", "stablecoin", "digital asset",
        "비트코인", "이더리움", "가상자산", "암호화폐", "스테이블코인",
    ],
}


def _doc_text(doc, content_limit=3000):
    companies = doc.get("companies", []) or []
    return normalize(" ".join([
        doc.get("title", "") or "",
        doc.get("summary", "") or "",
        (doc.get("content", "") or "")[:content_limit],
        " ".join(doc.get("sectors", []) or []),
        " ".join(doc.get("impactTags", []) or []),
        " ".join(c.get("name", "") for c in companies),
        " ".join(c.get("ticker", "") for c in companies),
    ])).lower()


def infer_drivers(doc):
    """문서가 어떤 시장 동인에 속하는지 추론한다. 0개 이상 반환."""
    hay = _doc_text(doc)
    drivers = []
    for driver, terms in DRIVER_TERMS.items():
        if any(term_in_text(term, hay) for term in terms):
            drivers.append(driver)
    return drivers


# ---------------------------------------------------------------------------
# 브리핑 전용 자료 점수
# ---------------------------------------------------------------------------
def _is_article(path):
    return str(path).replace("\\", "/").lower().startswith("research-inbox/articles")


def _is_rss(path):
    return str(path).replace("\\", "/").lower().startswith("research-inbox/rss/")


# 실제 시장 가격/지수/수급 반응과 연결되는지 판단하는 신호
_INDEX_TERMS = [
    "s&p", "나스닥", "nasdaq", "다우", "dow", "코스피", "kospi", "코스닥", "kosdaq",
    "russell", "러셀", "반도체지수", "sox", "필라델피아", "vix", "선물지수",
]
_MOVE_TERMS = [
    "급등", "급락", "반등", "되돌림", "사이드카", "서킷브레이커", "순매수", "순매도",
    "외국인", "기관", "거래대금", "강세", "약세", "%", "surge", "plunge", "rebound",
    "rally", "selloff", "sell-off", "soared", "tumbled",
]


def market_connection_score(doc):
    """이 자료가 실제 시장 가격/지수/수급 반응과 얼마나 직접 연결되는지.

    지수·등락·수급 신호가 있고 회사/섹터가 붙은 자료는 브리핑 핵심에 쓰일
    가능성이 높다. broad keyword(금리·채권·달러 등)만 스친 단발 기사(개별 채권
    발행, 펀드, trivia)는 이 점수가 0에 가깝다.
    """
    hay = _doc_text(doc, content_limit=1500)
    s = 0.0
    if any(t in hay for t in _INDEX_TERMS):
        s += 12
    if any(t in hay for t in _MOVE_TERMS):
        s += 10
    companies = doc.get("companies") or []
    if companies and doc.get("sectors"):
        s += 6
    if len(companies) >= 2:
        s += 4
    return s


def effective_market_relevance(doc):
    """직접 저장 article이 인덱싱 단계에서 marketRelevance=100으로 고정되는
    문제를 브리핑 선별 단계에서만 완화한다(인덱싱은 건드리지 않음).

    시장 신호(회사/섹터/영향 태그)가 거의 없는 article은 100점을 그대로
    신뢰하지 않고 보수적으로 낮춰, RSS보다는 우대하되 무조건 상단으로
    올라오지 않게 한다.
    """
    mr = float(doc.get("marketRelevance", 0) or 0)
    if _is_article(doc.get("path", "")) and mr >= 100:
        signal = (
            len(doc.get("companies", []) or [])
            + len(doc.get("sectors", []) or [])
            + len(doc.get("impactTags", []) or [])
        )
        if signal == 0:
            return 45.0
        if signal <= 2:
            return 70.0
    return mr


def briefing_doc_score(doc, market_windows):
    """"이 자료가 오늘 브리핑에서 얼마나 쓸 만한가"를 평가한다.

    출처 신뢰도, 시장 시간창 적합성, 시장 관련성, 본문 품질, 영향/섹터/회사
    태그, RSS 헤드라인 감점을 합산한다.
    """
    score = 0.0

    # 1. 출처 신뢰도
    source_weight = float(doc.get("sourceWeight", 5) or 5)
    score += min(source_weight, 10) * 3

    # 1-b. Evidence Intake 신뢰도 계층(reliability_tier) 보너스. Tier 1(공식자료)·
    #      Tier 2(주요 매체)는 소폭 우대한다. 단, 공식자료(source_type=official_*/
    #      macro_data)는 브리핑의 "직접 근거"로 쓰지 않는다는 Folio OS 원칙에 따라
    #      여기서 가산하지 않고, 브리핑 본문 근거 후보에서 강하게 내린다.
    source_type = str(doc.get("sourceType", "") or "")
    is_official = source_type.startswith("official_") or source_type == "macro_data"
    if is_official:
        score -= 40
    else:
        try:
            tier = int(doc.get("reliabilityTier") or 0)
        except (TypeError, ValueError):
            tier = 0
        if tier == 1:
            score += 6
        elif tier == 2:
            score += 3

    # 2. 분석 우선순위(브리핑 모드별 가중치). 평일은 미국 전일/한국 당일이 primary,
    #    주말·휴장 모드에서는 off_session_news(다음 거래일 영향 후보)의 비중이 커진다.
    priority = doc_analysis_priority(doc, market_windows)
    weekend_mode = bool(market_windows.get("weekendOrHolidayNewsMode"))
    if weekend_mode:
        if priority == "off_session_news":
            score += 38
        elif priority == "primary":
            score += 16
        elif priority == "secondary":
            score += 12
        else:  # background
            score += 5
    else:
        if priority == "primary":
            score += 28
        elif priority == "secondary":
            score += 16
        elif priority == "off_session_news":
            score += 4
        else:  # background
            score += 6

    # 3. 시장 관련성(article 과대평가는 effective_market_relevance로 완화)
    market_relevance = effective_market_relevance(doc)
    score += min(market_relevance, 100) * 0.4

    # 4. 본문 품질
    word_count = int(doc.get("wordCount", 0) or 0)
    if word_count >= 600:
        score += 20
    elif word_count >= 200:
        score += 10
    elif word_count >= 80:
        score += 3
    else:
        score -= 12

    # 5. 영향 태그
    impact_tags = doc.get("impactTags", []) or []
    score += min(len(impact_tags), 4) * 6

    # 6. 회사/섹터 태그
    companies = doc.get("companies", []) or []
    sectors = doc.get("sectors", []) or []
    if companies:
        score += 8
    if sectors:
        score += 6

    # 7. 시장 가격/지수/수급 반응과의 연결성 (실제 브리핑 본문에 쓰일 자료 우대)
    connection = market_connection_score(doc)
    score += connection

    # 8. broad keyword만 스친 단발 기사 감점:
    #    동인 키워드는 걸렸지만 지수/등락/수급 신호가 전혀 없고 회사/섹터도 빈약한
    #    자료(개별 채권 발행, 펀드, trivia, 거시 단신)는 핵심에서 내린다.
    if connection == 0 and not sectors and len(companies) <= 1:
        score -= 15

    # 9. RSS headline-only 감점 (본문 품질이 낮은 RSS는 더 강하게)
    if _is_rss(doc.get("path", "")):
        if word_count < 80:
            score -= 18
        elif word_count < 200 and not impact_tags and not sectors:
            score -= 10

    return max(score, 0.0)


# ---------------------------------------------------------------------------
# 시장 동인 그룹화
# ---------------------------------------------------------------------------
def _doc_key(doc):
    return doc.get("url") or doc.get("path") or doc.get("title")


def derive_market_drivers(docs, market_windows, limit=4):
    """문서들을 금리/환율/반도체 등 시장 동인 기준으로 묶는다.

    자료 수가 많은 동인이 곧 중요한 동인은 아니므로, 점수에는 출처 다양성과
    미국·한국 양쪽 시간대에 걸친 동인 여부를 가산한다.
    """
    groups = {}
    for doc in docs:
        drivers = infer_drivers(doc) or ["시장 전반"]
        doc_score = briefing_doc_score(doc, market_windows)
        bucket = doc_market_bucket(doc, market_windows)
        enriched = {**doc, "briefingDocScore": doc_score, "marketBucket": bucket}

        for driver in drivers:
            g = groups.setdefault(driver, {
                "driver": driver,
                "docs": [],
                "score": 0.0,
                "sources": set(),
                "markets": set(),
                "impactTags": set(),
                "sectors": set(),
            })
            g["docs"].append(enriched)
            g["score"] += doc_score
            g["sources"].add(doc.get("source", ""))
            g["markets"].add(bucket)
            for tag in doc.get("impactTags", []) or []:
                g["impactTags"].add(tag)
            for sector in doc.get("sectors", []) or []:
                g["sectors"].add(sector)

    out = []
    for g in groups.values():
        # 여러 출처에서 반복 확인되면 가산
        g["score"] += min(len(g["sources"]), 4) * 8
        # 미국장/한국장 양쪽 시간대에 걸친 동인이면 가산
        if any("US" in m for m in g["markets"]) and any("KR" in m for m in g["markets"]):
            g["score"] += 15
        if market_windows.get("weekendOrHolidayNewsMode"):
            off_docs = [d for d in g["docs"] if doc_analysis_priority(d, market_windows) == "off_session_news"]
            if off_docs:
                # 주말/휴장 브리핑의 핵심 변수는 정규장 복기보다 휴장 중 새 재료를
                # 우선한다. 가격 반응은 다음 거래일 확인 대상으로 남긴다.
                g["score"] += 35 + min(len(off_docs), 4) * 8
        # docs는 표시용 상위 5건으로 자르지만, 실제 몇 건이 이 동인에 속했는지는
        # docTotal로 보존한다 (모든 동인이 "기사 5건"으로 보이는 문제 방지).
        g["docTotal"] = len(g["docs"])
        g["docs"] = sorted(
            g["docs"], key=lambda d: d.get("briefingDocScore", 0), reverse=True
        )[:5]
        out.append({
            **g,
            "sources": sorted(s for s in g["sources"] if s),
            "markets": sorted(m for m in g["markets"] if m),
            "impactTags": sorted(g["impactTags"]),
            "sectors": sorted(g["sectors"]),
        })

    # "시장 전반"은 분류 실패 묶음이므로 동순위면 뒤로 민다.
    out.sort(key=lambda g: (g["score"], g["driver"] != "시장 전반"), reverse=True)
    return out[:limit]


def group_ticker(group):
    """묶음 회사의 티커. 회사 태그(name+ticker)를 단 문서에서 읽는다 — 이름 매칭으로
    대형주 목록과 잇는 것은 표기가 달라 신뢰할 수 없다(정식명 vs 기사 표기)."""
    name = str(group.get("company") or "")
    if not name:
        return ""
    for doc in group.get("docs", []):
        for company in doc.get("companies", []) or []:
            if str(company.get("name") or "") == name and company.get("ticker"):
                return str(company["ticker"]).upper()
    return ""


def _ticker_forms(symbol):
    """provider 심볼과 기사 태그가 같은 종목을 다른 표기로 부른다 — 둘 다 담는다.

    대형주 목록은 provider 심볼(`005930.KS`, `7203.T`, `ASML.AS`)인데 기사 회사 태그는
    bare 코드(`005930`)나 SEC 표기(`ASML`)다. 접미사만 떼면 두 표기가 만난다. 이걸 안
    하면 `isMajor`가 미국 밖에서 한 번도 참이 되지 않아, 니치가 두 자리를 차지하는
    바로 그 문제(cf2128f가 고친 것)가 KR·유럽·일본에서 그대로 남는다(실측: 색인의
    삼성전자 태그는 `005930`).
    """
    upper = str(symbol or "").upper()
    if not upper:
        return ()
    root = upper.split(".", 1)[0]
    return (upper,) if root == upper else (upper, root)


def major_ticker_set(market_scope):
    """그 범위의 시총 상위 구성종목 티커(표기 변형 포함). 못 읽으면 빈 집합.

    종합 범위(`both`/`multi`/`all`)는 선택된 시장들의 **합집합**이다 — 예약 기본값이
    미국+한국인데 종합이라는 이유로 빈 집합을 주면, 가장 흔한 구성에서 가중이 없다.
    """
    try:
        from features.common.market_data.major_companies import major_company_symbols
        from features.daily_briefing.schema import normalize_market_selection
        from features.common.markets import MarketCode

        markets = normalize_market_selection(market_scope)
        codes = [MarketCode(market.upper()) for market in markets]
        if not codes:
            return frozenset()
        return frozenset(
            form for symbol in major_company_symbols(codes) for form in _ticker_forms(symbol)
        )
    except Exception:  # noqa: BLE001 - 가중일 뿐 브리핑을 막지 않는다
        return frozenset()


# 시장 영향력 축의 무게 — 시총 상위 구성종목은 **그날 최고 이야기 점수의 이 비율**을
# 영향력 점수로 받는다. 종합은 곱이 아니라 **합**이다(2026-08-22 사용자 결정) — 곱은
# 이야기 점수가 0인 대형주를 통째로 소멸시킨다. 고정 상수 대신 그날 최고점 기준으로
# 스케일을 맞춘다 — 이야기 점수는 날마다 수십~수백으로 널뛴다.
MAJOR_IMPACT_WEIGHT = 0.5


def prioritize_briefing_groups(groups, market_windows, limit=None, market_scope=None):
    """주도 기업/섹터 그룹을 브리핑 모드에 맞게 재정렬한다.

    group_docs()는 일반 뉴스 검색용 점수라 주말에는 직전 정규장 자료가 계속
    상단을 차지할 수 있다. 주말/휴장 모드에서는 off_session_news 자료가 있는
    기업/섹터를 우선해 '다음 거래일 반영 후보' 중심으로 주도 기업 섹션을 만든다.

    `market_scope`를 주면 **이야기 점수 + 시장 영향력 점수**의 종합으로 정렬한다.
    보도량만으로 정렬하던 동안 니치 기업이 미국장 주도 기업 두 자리를 다 차지했다
    (실측 Nebius·CoreWeave). 합이라 이야기가 충분히 큰 니치는 여전히 이기고, 이야기가
    0인 대형주도 후보에서 소멸하지 않는다.
    """
    weekend_mode = bool(market_windows.get("weekendOrHolidayNewsMode"))
    majors = major_ticker_set(market_scope) if market_scope else frozenset()
    out = []
    for group in groups or []:
        docs = list(group.get("docs") or [])
        scored_docs = sorted(docs, key=lambda d: briefing_doc_score(d, market_windows), reverse=True)
        off_docs = [d for d in scored_docs if doc_analysis_priority(d, market_windows) == "off_session_news"]
        score = sum(briefing_doc_score(d, market_windows) for d in scored_docs[:5])
        if weekend_mode:
            score += sum(briefing_doc_score(d, market_windows) for d in off_docs[:4]) * 1.2
            score += len(off_docs[:4]) * 30
        is_major = bool(majors) and group_ticker(group) in majors
        out.append({
            **group,
            "docs": scored_docs,
            "briefingGroupScore": score,
            "isMajor": is_major,
            "offSessionDocCount": len(off_docs),
        })
    # 영향력 점수는 그날 최고 이야기 점수 기준으로 스케일을 맞춘 뒤 **더한다**.
    top_story = max((g["briefingGroupScore"] for g in out), default=0.0)
    for g in out:
        g["leaderScore"] = g["briefingGroupScore"] + (MAJOR_IMPACT_WEIGHT * top_story if g["isMajor"] else 0.0)
    out.sort(key=lambda g: (g.get("leaderScore", 0), g.get("briefingGroupScore", 0), g.get("score", 0)), reverse=True)
    return out[:limit] if limit else out


# ---------------------------------------------------------------------------
# tier별 발췌 길이
# ---------------------------------------------------------------------------
_TIER_LIMIT = {"driver": 1200, "group": 850, "support": 450}

# 기사 페이지에 함께 저장되는 네비게이션/추천/자동요약 문구는 evidence가 아니다.
# 너무 넓은 금칙어 목록은 정상적인 기사 내용을 잃게 하므로, 페이지 chrome을
# 가리키는 표현만 제한적으로 제거한다.
_EXCERPT_NOISE_RE = re.compile(
    r"(?:공유하기|카카오톡에 공유|페이스북에 공유|트위터에 공유|링크 복사|글자 크기|"
    r"관련기사|추천기사|많이 본 기사|다른 기사|인기 검색어|로그인|댓글 쓰기|"
    r"AI\s*(?:요약|자동 요약)|인공지능\s*요약|자동 생성 요약|본문과 관련 없는)",
    re.I,
)
# Keep decimal points inside numbers (``5.62%``) intact while still splitting
# ordinary prose sentences. Newline-separated snippets remain boundaries.
_EXCERPT_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[!?。！？])\s+|(?<!\d)\.(?=\s+|$)|\n+"
)
_EXCERPT_SIGNAL_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*%?|\d[\d,]*(?:\.\d+)?\s*(?:조|억|만|원|달러|%|bp|명|건)|"
    r"(?:상승|하락|급등|급락|반등|마감|순매수|순매도|전환|발표|공시|실적|가이던스|"
    r"전망|인수|계약|수주|가격|주가|지수|금리|환율|외국인|기관|투자자|대표|CEO|"
    r"according|reported|said|announced|earnings|guidance|price|shares))",
    re.I,
)


def _excerpt_parts(value):
    """Return embedded Summary/Full Text sections without collapsing them.

    Older index rows occasionally put the complete ``# Summary``/``# Full Text``
    document in one field.  ``clean_embedded_sections`` intentionally returns one
    section for legacy callers, but the briefing writer needs both so a number or
    event mentioned only later in Full Text is not silently lost.
    """
    text = str(value or "").strip()
    if not text:
        return {"summary": "", "full_text": ""}
    marker = re.compile(r"#{1,6}\s*(Summary|Full Text|Collection Notes)\b[:\s]*", re.I)
    matches = list(marker.finditer(text))
    if not matches:
        return {"summary": "", "full_text": text}
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        label = match.group(1).lower().replace(" ", "_")
        sections.setdefault(label, text[match.end():end].strip())
    full_text = sections.get("full_text", "")
    if "full text is not saved by default" in full_text.lower():
        full_text = ""
    return {
        "summary": sections.get("summary", ""),
        "full_text": full_text,
    }


def _clean_excerpt_sentences(text):
    sentences = []
    # Split the raw blocks first. ``normalize`` collapses newlines, which used
    # to join a valid fact to a neighbouring menu block before the noise filter
    # could remove the latter.
    for part in _EXCERPT_SENTENCE_SPLIT_RE.split(str(text or "")):
        sentence = normalize(part).strip(" -")
        if not sentence or _EXCERPT_NOISE_RE.search(sentence):
            continue
        # Drop isolated menu labels and tiny UI fragments while retaining short
        # numeric facts that may be useful to the market-flow section.
        if len(sentence) < 18 and not _EXCERPT_SIGNAL_RE.search(sentence):
            continue
        sentences.append(sentence)
    return sentences


def _bounded_summary_text(text, limit):
    """Clean summary blocks while retaining their original order."""
    # Summary prose can be a short but meaningful sentence without a numeric
    # signal. Keep it; only the explicit page-noise filter is authoritative in
    # this lane. Tiny standalone labels are still rejected.
    sentences = []
    for part in _EXCERPT_SENTENCE_SPLIT_RE.split(str(text or "")):
        sentence = normalize(part).strip(" -")
        if sentence and len(sentence) >= 8 and not _EXCERPT_NOISE_RE.search(sentence):
            sentences.append(sentence)
    chosen = []
    for sentence in sentences:
        candidate = " ".join([*chosen, sentence]).strip()
        if len(candidate) > limit:
            break
        chosen.append(sentence)
    return " ".join(chosen)


def _bounded_relevant_full_text(text, limit):
    sentences = _clean_excerpt_sentences(text)
    if not sentences:
        return ""
    # Prefer event/number/speaker/reaction sentences, then keep chronological
    # context. This is deliberately bounded and never inserts the whole article.
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (bool(_EXCERPT_SIGNAL_RE.search(item[1])), item[0]),
        reverse=True,
    )
    chosen_indices = []
    chosen = []
    for index, sentence in ranked:
        candidate = " ".join([*chosen, sentence]).strip()
        if len(candidate) > limit:
            continue
        chosen.append(sentence)
        chosen_indices.append(index)
    # Ranking decides which sentences fit the budget; source order keeps event
    # progression (for example a six-day flow reversal) readable.
    return " ".join(sentences[index] for index in sorted(chosen_indices))


def briefing_doc_excerpt(doc, clean_fn, tier="support"):
    """tier에 따라 발췌 길이를 차등한다.

    clean_fn 은 service.clean_brief_text 처럼 (text, limit) -> str 인 정리 함수.
    """
    limit = _TIER_LIMIT.get(tier, _TIER_LIMIT["support"])
    # Summary와 Full Text를 합치면 Full Text의 뒤쪽 사건/수치가 요약에 가려진다.
    # 두 필드를 분리한 뒤 Full Text는 관련 문장만 bounded하게 추가한다.
    raw_summary = str(doc.get("summary", "") or "")
    summary_parts = _excerpt_parts(raw_summary)
    content_parts = _excerpt_parts(doc.get("content", ""))
    structured_summary = bool(re.search(r"#{1,6}\s*(Summary|Full Text|Collection Notes)\b", raw_summary, re.I))
    summary = summary_parts["summary"] or ("" if structured_summary else summary_parts["full_text"])
    # A legacy Summary field can contain both sections while content is empty;
    # preserve its Full Text as the bounded full-text lane instead of dropping it.
    full_text = content_parts["full_text"] or (summary_parts["full_text"] if structured_summary else "")
    if not summary and content_parts["summary"]:
        summary = content_parts["summary"]
    summary = clean_fn(
        _bounded_summary_text(clean_embedded_sections(summary), min(limit, max(180, limit // 2))),
        min(limit, max(180, limit // 2)),
    )
    remaining = max(0, limit - len(summary) - 22)
    full_excerpt = clean_fn(_bounded_relevant_full_text(full_text, remaining), remaining)
    if summary and full_excerpt and full_excerpt.lower() != summary.lower():
        return f"Summary: {summary}\nFull Text excerpts: {full_excerpt}"
    evidence = summary or full_excerpt
    if evidence:
        return evidence
    # Some legacy headline/RSS rows store a useful title with only a terse
    # placeholder summary (for example ``요약``). Keep that headline as the
    # bounded writer evidence, while the same noise filter still rejects
    # recommendation/menu titles.
    return _bounded_summary_text(doc.get("title", ""), limit)
