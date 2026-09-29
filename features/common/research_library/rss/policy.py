"""Evidence intake policy helpers for RSS collection."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 키워드 게이트가 실제로 판단할 수 있는 언어. 표가 한국어와 영어로 쓰여 있기 때문이다.
# 이 모듈에 두는 이유는 두 가지다. 숫자 점수(`calculate_relevance_score`)와 boolean 게이트가
# 같은 기준을 써야 하고, `relevance.py`는 `article.py`를 거쳐 이 모듈에 의존하므로
# 반대로 import하면 순환이 된다.
KEYWORD_GATE_LANGUAGES = frozenset({"ko", "en"})


def keyword_gate_applies(feed: dict | None) -> bool:
    """Whether the Korean/English keyword lists can judge this feed at all.

    예전 조건은 "country와 language를 둘 다 선언했는가"였다. country를 없애면서 그대로
    language 유무로 바꿀 수 없다 — 모든 피드가 언어를 선언하게 되었으므로, 있는지만 보면
    한국·영어 피드까지 게이트를 건너뛴다. 그러면 한국어 잡음 필터(`[포토]`·장바구니·맛집)가
    꺼진다. 원래 주석이 진짜 기준을 이미 적어두고 있었고(*"The keyword gate below is written
    in Korean and English"*), 그것을 그대로 조건으로 쓴다.

    언어를 모르면 게이트를 적용한다. 판단할 수 없는 자료를 그냥 들이는 것보다 낫고,
    country/language가 없던 피드가 전부 게이트를 지나던 예전 동작과도 같다.
    """
    if not isinstance(feed, dict):
        return True
    language = str(feed.get("language") or "").strip().lower()
    return language in KEYWORD_GATE_LANGUAGES or not language


STRONG_MARKET_TERMS = {
    "주가",
    "증시",
    "코스피",
    "코스닥",
    "공시",
    "실적",
    "영업이익",
    "가이던스",
    "반도체",
    "전기차",
    "금리",
    "환율",
    "유가",
    "관세",
    "revenue",
    "earnings",
    "guidance",
}
GENERAL_MARKET_TERMS = {
    "market",
    "stock",
    "stocks",
    "shares",
    "demand",
    "supply",
    "sales",
    "investment",
    "ai",
    "semiconductor",
    "data center",
    "fed",
    "yield",
    "매출",
    "투자",
    "수급",
    "공급망",
    "수출",
    "정책",
}
COMPANY_HINTS = {
    "삼성",
    "하이닉스",
    "현대차",
    "기아",
    "lg",
    "sk",
    "네이버",
    "카카오",
    "엔비디아",
    "테슬라",
    "애플",
    "마이크로소프트",
    "브로드컴",
}
NOISE_TERMS = {
    "맛집",
    "여행",
    "패션",
    "뷰티",
    "스포츠",
    "연예",
    "날씨",
    "할인",
    "세일",
}
# Gate phrases only. Bare words like "구독"/"로그인" appear in the footer of
# virtually every Korean news page (newsletter buttons) and caused free
# articles (연합뉴스/매경/한경) to be misclassified as paywalled.
PAYWALL_TERMS = {
    "subscribe to continue",
    "sign in to continue",
    "register to continue",
    "already a subscriber",
    "subscription required",
    "this article is for subscribers",
    "구독 후 이용",
    "구독자 전용",
    "유료 회원 전용",
    "유료회원 전용",
    "로그인 후 이용",
    "로그인 후 계속",
}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "cmpid",
    "ref",
    "smid",
}


# Dow Jones 매체는 같은 기사를 피드마다 다른 `?mod=`(유입 위치 태그)로 내보낸다
# (`rss_markets_main` / `pls_whats_news_us_business_f` / `rss_Technology`). 기사 식별과
# 무관하지만 URL 문자열이 달라 같은 기사가 두 번 저장됐다. `mod`는 다른 사이트에서
# 다른 뜻일 수 있어 이 호스트에서만 추적 파라미터로 본다.
MOD_TRACKING_HOSTS = ("wsj.com", "barrons.com", "marketwatch.com")
# Financial Times 신디케이션 링크의 `?syn-<해시>=1`. 키 이름 자체가 바뀌므로 접두로 거른다.
SYNDICATION_QUERY_PREFIX = "syn-"


def _host_in(netloc: str, hosts) -> bool:
    return any(netloc == host or netloc.endswith("." + host) for host in hosts)


def normalize_url(url: str) -> str:
    """Return a stable URL key for dedupe without changing the original URL."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or parts.path
    drop_mod = _host_in(netloc, MOD_TRACKING_HOSTS)
    query_rows = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith("utm_") or low in TRACKING_QUERY_KEYS:
            continue
        if low.startswith(SYNDICATION_QUERY_PREFIX) or (drop_mod and low == "mod"):
            continue
        query_rows.append((key, value))
    query = urlencode(sorted(query_rows), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def should_store_full_text(save_full_text: bool, public_mode: bool = False) -> bool:
    return bool(save_full_text) and not bool(public_mode)


def should_retry_existing_item(existing_status: str, *, retry_failed: bool = False, retry_summary_only: bool = False) -> bool:
    status = str(existing_status or "").strip().lower()
    if status == "fetch_failed":
        return bool(retry_failed)
    if status in {"summary_only", "needs_manual_save", "legacy_rss"}:
        return bool(retry_summary_only)
    return False


def calculate_relevance_score(item: dict, feed: dict | None = None, *, baseline: float = 1.0) -> float:
    """Score an item's market relevance from its text.

    The term lists are Korean and English, so a German or Japanese item scores
    near zero regardless of what it is about. For a feed in a language the lists
    cannot read, the feed's editorial scope is the relevance signal, so the score
    floors at ``baseline`` instead of failing the archive threshold. Items that
    also match terms still score above the floor, so ranking between them is
    preserved.

    The condition is the feed's language, not "does it declare metadata": every
    feed declares a language now, and reading it as a floor signal would hand the
    floor to Korean and English feeds too — exactly the ones these lists judge.
    """
    text = " ".join(str(item.get(key) or "") for key in ("title", "description", "summary", "url", "link")).lower()
    score = 0.0
    score += sum(2 for term in STRONG_MARKET_TERMS if term.lower() in text)
    score += sum(1 for term in GENERAL_MARKET_TERMS if term.lower() in text)
    if any(term.lower() in text for term in COMPANY_HINTS):
        score += 2
    score -= sum(2 for term in NOISE_TERMS if term.lower() in text)
    if str(item.get("source_type") or "").startswith("official"):
        score += 3
    if not keyword_gate_applies(feed):
        score = max(score, baseline)
    return score


def looks_paywalled(text: str) -> bool:
    hay = str(text or "").lower()
    return any(term in hay for term in PAYWALL_TERMS)
