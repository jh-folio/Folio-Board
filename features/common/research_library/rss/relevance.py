"""Market-relevance gating for Evidence Intake RSS items.

A boolean gate that complements ``policy.calculate_relevance_score`` (numeric):
it drops vendor stock-quote pages, raw ticker-symbol headlines, and Korean
lifestyle/noise items that slip through generic feeds, so only market-relevant
news enters the archive. This is intentionally separate from the numeric score
so the threshold and the hard exclusions can evolve independently.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from features.common.research_library.rss.article import normalize_text
from features.common.research_library.rss.policy import keyword_gate_applies
from features.common.utils import url_host_matches

NOISY_TITLE_PATTERNS = [
    r"\bStock Price\s*&\s*Latest News\b",
    r"\bStock Analysis Prediction, Earnings, Dividend\b",
    r"^About .+\bETF\b",
    r"^[A-Z0-9.%-]{2,12}\s+-?\s*$",
    r"^\([A-Z0-9.%-]{2,12}\)\s+Stock Price",
    r"^\[포토\]",
    r"\b프라이스&\b",
    r"\b권 기자의 장바구니\b",
    r"\b바이어 생생노트\b",
]

MARKET_RELEVANCE_TERMS = [
    "주가", "증시", "코스피", "코스닥", "상장", "공시", "실적", "영업이익", "매출", "가이던스",
    "투자", "투자자", "외국인", "기관", "수급", "반도체", "ai", "인공지능", "데이터센터",
    "배터리", "2차전지", "자동차", "전기차", "방산", "금리", "환율", "유가", "관세", "규제",
    "정책", "정부", "국회", "산업", "공급망", "수출", "수입", "목표주가", "밸류에이션",
    "revenue", "earnings", "guidance", "shares", "stocks", "market", "semiconductor",
]

STRONG_MARKET_TERMS = [
    "주가", "증시", "코스피", "코스닥", "상장", "공시", "실적", "영업이익", "가이던스",
    "기관", "수급", "순매수", "순매도", "반도체", "배터리", "전기차", "방산", "금리",
    "환율", "유가", "관세", "규제", "정책", "목표주가", "밸류에이션",
]

MARKET_COMPANY_HINTS = [
    "삼성", "하이닉스", "현대차", "기아", "lg", "sk", "네이버", "카카오", "셀트리온",
    "두산", "한화", "포스코", "롯데", "cj", "hd현대", "엔비디아", "테슬라", "애플",
    "마이크로소프트", "구글", "메타", "아마존", "브로드컴", "델",
]

KOREAN_NOISE_TERMS = [
    "맛집", "외식", "랍스터", "홈다이닝", "여행", "여객", "패션", "뷰티", "화장품",
    "액세서리", "다이소", "빵덕후", "쇼핑백", "포토", "연예", "스포츠", "날씨",
    "할인", "세일", "가성비", "장바구니", "프라이스", "새벽배송", "선물세트",
]

_KOREAN_MEDIA_DOMAINS = ("hankyung.com", "mk.co.kr", "einfomax.co.kr")
_VENDOR_TICKER_RE = re.compile(r"\b[A-Z0-9]{2,8}\.(?:OQ|N|PK|HA|BO|NS|SG|TO|F|Z)\b")
_REUTERS_COMPANY_RE = re.compile(r"/markets/companies/[^/]+/?$", re.IGNORECASE)


def canonical_media(media: str, url: str = "", title: str = "") -> str:
    """Map known outlets to a stable display name from any URL/title hint."""
    title_hay = str(title or "").lower()
    if url_host_matches(url, "barrons.com") or "barron's" in title_hay or "barrons" in title_hay:
        return "Barron's"
    if url_host_matches(url, "wsj.com") or "wall street journal" in title_hay:
        return "WSJ"
    if url_host_matches(url, "marketwatch.com") or "marketwatch" in title_hay:
        return "MarketWatch"
    if url_host_matches(url, "cnbc.com") or "cnbc" in title_hay:
        return "CNBC"
    if url_host_matches(url, "einfomax.co.kr") or "연합인포맥스" in title_hay:
        return "연합인포맥스"
    return media


def is_korean_media_link(link: str) -> bool:
    return url_host_matches(link, *_KOREAN_MEDIA_DOMAINS)


def is_market_relevant_item(title: str, description: str, link: str) -> bool:
    text = normalize_text(f"{title} {description} {link}").lower()
    relevant = sum(1 for term in MARKET_RELEVANCE_TERMS if term.lower() in text)
    strong = sum(1 for term in STRONG_MARKET_TERMS if term.lower() in text)
    company = any(term.lower() in text for term in MARKET_COMPANY_HINTS)
    noise = sum(1 for term in KOREAN_NOISE_TERMS if term.lower() in text)
    if is_korean_media_link(link):
        if re.search(r"^\s*\[포토\]", title or ""):
            return False
        if noise >= 2 and strong < 2:
            return False
        return relevant >= 1 or company
    return relevant >= 1 or company


def should_archive_item(title: str, description: str, link: str, feed: dict | None = None) -> bool:
    """Hard gate: reject vendor pages, raw ticker headlines, and off-topic noise.

    The keyword gate below is written in Korean and English. Applying it to a
    German or Japanese headline does not measure relevance — it measures whether
    a Latin substring happened to collide, which is why probe pass rates ranged
    from 4% (Japanese) to 95% (French, where ``ai`` hides inside ``vrai`` and
    ``aider``) with no relation to what the articles were about. So feeds in a
    language it cannot read skip it; the structural filters above still apply to
    every feed.

    Skipping leans on the feed being a business or economy section, and that
    assumption has failed before: `kyodo.co.jp/feed/` turned out to be a press
    release wire and `diamond.jp/list/feed/rss/dol` the whole magazine, so
    shopping reviews and self-help arrived with nothing to stop them. The fix is
    the feed list, not a wider gate — a keyword table in six more languages would
    be guessing at relevance in languages nobody here can check.
    """
    for pattern in NOISY_TITLE_PATTERNS:
        if re.search(pattern, title or "", re.IGNORECASE):
            return False
    if url_host_matches(link, "reuters.com") and _REUTERS_COMPANY_RE.search(link or ""):
        return False
    if _VENDOR_TICKER_RE.search(title or ""):
        return False
    if not url_section_allowed(link, feed):
        return False
    if not keyword_gate_applies(feed):
        return True
    return is_market_relevant_item(title, description, link)


def url_section_allowed(link: str, feed: dict | None = None) -> bool:
    """기사 URL의 섹션으로 거른다. 언어를 읽지 않는 **구조적** 필터다.

    종합 헤드라인 피드는 투자와 무관한 면을 그대로 실어 온다. 실측으로 Handelsblatt
    1,260건이 politik 421 · finanzen 279 · unternehmen 178 · technik 154 · karriere 68 ·
    video 31이었고, 쾰른 아이스크림 창업자 기사와 우크라이나 전황이 브리핑 자료로
    들어왔다. 그 기사들은 본문 장식에서 미국 대형주를 주워 `US` 시장으로까지 찍혔다.

    키워드 표를 독일어·프랑스어·이탈리아어로 늘리는 것은 이 저장소가 이미 거부한 길이다
    (§should_archive_item — "읽을 수 없는 언어에서 관련성을 추측하는 것"). 섹션 경로는
    매체가 스스로 붙인 분류라 번역이 필요 없고 눈으로 확인할 수 있다.

    섹션 피드가 따로 있으면 그쪽을 구독하는 것이 먼저다. 이 필터는 한 피드에 여러 면이
    섞여 오는 매체(Het Financieele Dagblad 등)를 위한 것이다.
    """
    rules = (feed or {}).get("url_sections") or {}
    if not rules:
        return True
    path = urlsplit(str(link or "")).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        # 섹션을 읽을 수 없으면 거르지 않는다. 구조 신호가 없다고 기사를 버리면
        # 경로 형태를 바꾼 매체의 자료가 통째로 사라진다.
        return True
    section = segments[0].lower()
    allow = rules.get("allow")
    if allow and section not in allow:
        return False
    return section not in (rules.get("deny") or [])
