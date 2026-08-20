"""Scope-aware issue clustering and publisher-normalized briefing selection."""

from __future__ import annotations

from features.common.text.tokenize import tokens as shared_tokens
import hashlib
import re
from collections import Counter, defaultdict

from features.common.market_calendar import doc_analysis_priority, infer_doc_market, infer_doc_markets
from features.common.research_library.indexing.research_index import cosine, embed_text
from features.common.utils import normalize
from features.daily_briefing.schema import (
    AGGREGATE_SCOPES,
    briefing_session_mode,
    normalize_market_scope,
)
from features.daily_briefing.selection import briefing_doc_score, market_connection_score


FOREIGN_CORE = frozenset({"Reuters", "WSJ", "Financial Times", "Bloomberg"})
FOREIGN_SUPPORT = frozenset({"CNBC", "MarketWatch", "Barron's", "Dow Jones"})
DOMESTIC_PUBLISHERS = frozenset({"연합인포맥스", "한국경제", "연합뉴스", "매일경제"})

# 매체별 권위와 **시장별 전문성**. 네 시장 모두에 값을 준다 — 예전에는 `us`/`kr` 둘뿐이라
# 유럽·일본 브리핑에서 `profile.get("europe")`가 없어 fallback(`sourceWeight`)으로 떨어졌고,
# 매체 권위 점수가 사실상 무작동이었다. 유럽·일본 매체는 표에 아예 없었다.
#
# `region`은 **한국장 교차 확인 판정 전용**이다(`domestic_count`). 유럽·일본 매체에
# `domestic`을 주면 KR 이슈가 아닌 곳에서 교차 확인 보너스가 붙으므로 `regional`로 둔다.
# 교차 확인 판정을 유럽·일본까지 일반화하는 것은 이번 범위가 아니다.
SOURCE_PROFILES = {
    "Reuters": {"authority": 10.0, "region": "foreign", "us": 10.0, "kr": 7.0, "europe": 9.5, "jp": 8.5},
    "WSJ": {"authority": 10.0, "region": "foreign", "us": 10.0, "kr": 6.5, "europe": 8.5, "jp": 7.5},
    "Financial Times": {"authority": 10.0, "region": "foreign", "us": 9.5, "kr": 7.0, "europe": 10.0, "jp": 8.0},
    "Bloomberg": {"authority": 10.0, "region": "foreign", "us": 9.5, "kr": 7.0, "europe": 9.0, "jp": 8.0},
    "Dow Jones": {"authority": 9.0, "region": "foreign", "us": 9.0, "kr": 5.5, "europe": 7.0, "jp": 6.0},
    "CNBC": {"authority": 8.0, "region": "foreign", "us": 8.0, "kr": 5.0, "europe": 6.0, "jp": 5.5},
    "MarketWatch": {"authority": 7.0, "region": "foreign", "us": 7.0, "kr": 4.5, "europe": 5.0, "jp": 4.5},
    "Barron's": {"authority": 8.0, "region": "foreign", "us": 8.0, "kr": 4.5, "europe": 5.0, "jp": 4.5},
    # 재전송 집계 매체. `only_publishers`가 원 발행처로 다시 태그하지만 남는 행이 있어
    # 자체 값을 준다 — 없으면 fallback이 원 매체와 같은 무게를 준다.
    "Yahoo Finance": {"authority": 6.0, "region": "foreign", "us": 6.0, "kr": 3.5, "europe": 4.0, "jp": 3.5},
    "연합인포맥스": {"authority": 8.5, "region": "domestic", "us": 3.2, "kr": 10.0, "europe": 2.5, "jp": 3.0},
    "연합뉴스": {"authority": 8.5, "region": "domestic", "us": 2.8, "kr": 8.5, "europe": 2.3, "jp": 3.2},
    "한국경제": {"authority": 7.5, "region": "domestic", "us": 2.7, "kr": 8.0, "europe": 2.2, "jp": 2.8},
    "매일경제": {"authority": 7.5, "region": "domestic", "us": 2.7, "kr": 8.0, "europe": 2.2, "jp": 2.8},
    # 유럽 — 현재 수집 중인 매체(config/rss_feeds.yaml)에서 실제로 들어오는 것만 적는다.
    "Handelsblatt": {"authority": 8.5, "region": "regional", "us": 3.0, "kr": 2.0, "europe": 9.5, "jp": 2.5},
    "Het Financieele Dagblad": {"authority": 8.0, "region": "regional", "us": 2.8, "kr": 1.8, "europe": 9.0, "jp": 2.0},
    "manager magazin": {"authority": 7.0, "region": "regional", "us": 2.5, "kr": 1.8, "europe": 8.0, "jp": 2.0},
    "La Tribune": {"authority": 7.0, "region": "regional", "us": 2.5, "kr": 1.8, "europe": 8.0, "jp": 2.0},
    "Expansion": {"authority": 7.0, "region": "regional", "us": 2.5, "kr": 1.8, "europe": 8.0, "jp": 2.0},
    "BFM Business": {"authority": 6.5, "region": "regional", "us": 2.3, "kr": 1.6, "europe": 7.5, "jp": 1.8},
    "la Repubblica Economia": {"authority": 6.5, "region": "regional", "us": 2.3, "kr": 1.6, "europe": 7.5, "jp": 1.8},
    "ANSA Economia": {"authority": 6.5, "region": "regional", "us": 2.3, "kr": 1.6, "europe": 7.5, "jp": 1.8},
    "NU.nl Economie": {"authority": 6.0, "region": "regional", "us": 2.0, "kr": 1.5, "europe": 7.0, "jp": 1.6},
    "Euronews Business": {"authority": 6.0, "region": "regional", "us": 2.5, "kr": 1.8, "europe": 7.0, "jp": 2.0},
    # 영국 매체는 유럽 전문성과 함께 국제 보도 범위가 넓어 미국·일본 값도 낮지 않다.
    "BBC": {"authority": 8.0, "region": "regional", "us": 5.0, "kr": 3.0, "europe": 8.0, "jp": 3.5},
    "The Guardian": {"authority": 7.5, "region": "regional", "us": 4.5, "kr": 2.5, "europe": 8.0, "jp": 3.0},
    # 일본
    "日本経済新聞": {"authority": 9.0, "region": "regional", "us": 3.5, "kr": 3.5, "europe": 3.0, "jp": 10.0},
    "NHK Business": {"authority": 8.0, "region": "regional", "us": 2.8, "kr": 2.8, "europe": 2.5, "jp": 9.0},
    "Asahi Shimbun Business": {"authority": 7.0, "region": "regional", "us": 2.5, "kr": 2.5, "europe": 2.3, "jp": 8.0},
}

CONCEPT_ALIASES = {
    "fed": ("fed", "federal reserve", "연준"),
    "rates": ("rate", "rates", "yield", "treasury", "bond", "금리", "국채", "채권", "점도표"),
    "nvidia": ("nvidia", "엔비디아"),
    "ai_chips": ("ai chip", "accelerator", "gpu", "data-center spending", "forecast", "outlook", "ai 수요", "수요 지속", "반도체"),
    "oil": ("oil", "crude", "유가", "원유"),
    "middle_east": ("middle east", "regional conflict", "supply disruption", "supply risk", "중동", "공급 우려"),
    "korea_chips": ("korea chip", "korean memory", "한국 반도체", "반도체 수출", "메모리 수출"),
    "exports": ("export", "shipment", "수출", "무역수지"),
    "kr_fx": ("won", "원화", "원달러", "원·달러", "환율"),
    "foreign_flow": ("foreign selling", "foreign buying", "외국인", "순매도", "순매수", "선물 매도"),
    "banks": ("bank", "banks", "lender", "은행", "금융주"),
    "bank_capital": ("bank capital", "capital requirement", "capital plan", "자본규제", "은행 규제"),
    "china_property": ("china", "beijing", "중국"),
    "property_support": ("property support", "housing market", "stimulus", "부동산 부양", "경기부양"),
    "apple": ("apple", "애플"),
    "earnings": ("earnings", "results", "guidance", "sales", "services growth", "실적", "가이던스", "매출"),
    "korea_auto": ("korean automaker", "korean carmaker", "한국 자동차", "현대차", "자동차 업계", "자동차"),
    "tariff": ("tariff", "trade barrier", "관세"),
    "biotech": ("biotech", "drugmaker", "바이오", "신약"),
    "clinical_trial": ("trial", "study", "endpoint", "임상", "평가지표"),
}

EVENT_CONCEPTS = frozenset({
    "rates", "ai_chips", "middle_east", "exports", "foreign_flow", "bank_capital",
    "property_support", "earnings", "tariff", "clinical_trial",
})


def _text(doc):
    return normalize(" ".join([
        str(doc.get("title") or ""),
        str(doc.get("summary") or ""),
        str(doc.get("content") or "")[:1200],
    ])).lower()


def _doc_key(doc):
    return str(doc.get("url") or doc.get("path") or doc.get("id") or doc.get("title") or "")


def body_availability(doc):
    status = str(doc.get("collectionStatus") or doc.get("collection_status") or "").lower()
    words = int(doc.get("wordCount") or 0)
    if status == "full_text" and words >= 120:
        return "full"
    if status in {"summary_only", "full_text"} or words >= 60:
        return "summary_only"
    return "headline_only"


def canonical_publisher(doc):
    source = str(doc.get("source") or "Unknown")
    text = _text(doc)
    if source != "Reuters" and re.search(r"\(로이터\)|\breuters?\b|로이터통신", text, re.I):
        return "Reuters"
    if source != "연합뉴스" and re.search(r"\(연합뉴스\)|연합뉴스 제공|yna\.co\.kr", text, re.I):
        return "연합뉴스"
    return source


def source_profile(doc, target_market):
    publisher = canonical_publisher(doc)
    profile = SOURCE_PROFILES.get(publisher, {})
    fallback = min(float(doc.get("sourceWeight") or 5), 10.0)
    authority = float(profile.get("authority", fallback))
    expertise = float(profile.get(str(target_market or "").lower(), fallback))
    availability = body_availability(doc)
    content_gate = {"full": 1.0, "summary_only": 0.78, "headline_only": 0.38}[availability]
    return {
        "publisher": publisher,
        "authority": authority,
        "marketExpertise": expertise,
        "region": profile.get("region", "unknown"),
        "coreForeign": publisher in FOREIGN_CORE,
        "bodyAvailability": availability,
        "contentGate": content_gate,
    }


def concepts_for_doc(doc):
    text = _text(doc)
    concepts = {name for name, aliases in CONCEPT_ALIASES.items() if any(alias in text for alias in aliases)}
    for company in doc.get("companies", []) or []:
        ticker = str(company.get("ticker") or "").upper().strip()
        name = normalize(str(company.get("name") or "")).lower()
        if ticker:
            concepts.add(f"ticker:{ticker}")
        if name:
            concepts.add(f"company:{name}")
    return concepts


def _event_date(doc):
    return str(doc.get("marketSessionDate") or doc.get("date") or "unknown")[:10]


def _tokens(text):
    return {
        token for token in shared_tokens(normalize(text).lower())
        if token not in {"the", "and", "after", "with", "from", "대한", "관련", "전망", "시장"}
    }


def _doc_features(doc):
    """비교에 쓰는 값 중 **문서 하나만으로 정해지는 것**을 미리 계산한다.

    예전에는 `_similarity`가 쌍마다 이것을 전부 다시 만들었다 — concepts, event date,
    제목 토큰, 그리고 **임베딩까지**. 비교는 O(n²)이므로 문서 900건이면 임베딩을 900번이
    아니라 80만 번 계산했고, 브리핑 생성이 15분 타임아웃을 넘겨 `internal_error`로 끝났다.
    수집량이 늘면서 드러난 문제다(실측 15,041건 색인, 2일 창에 1,831건).

    값 자체는 그대로이므로 클러스터 결과는 바뀌지 않는다.
    """
    tokens = _tokens(doc.get("title") or "")
    return {
        "concepts": concepts_for_doc(doc),
        "eventDate": _event_date(doc),
        "tokens": tokens,
        "embedding": embed_text(" ".join(sorted(tokens))),
    }


def _similarity_features(a, b):
    shared = a["concepts"] & b["concepts"]
    shared_events = shared & EVENT_CONCEPTS
    shared_subjects = shared - EVENT_CONCEPTS
    if a["eventDate"] != b["eventDate"] and "unknown" not in {a["eventDate"], b["eventDate"]}:
        return 0.0
    if shared_events and shared_subjects:
        return min(0.98, 0.72 + 0.08 * len(shared))
    at, bt = a["tokens"], b["tokens"]
    jaccard = len(at & bt) / max(1, len(at | bt))
    embedding = cosine(a["embedding"], b["embedding"])
    if jaccard >= 0.62 and embedding >= 0.68:
        return min(0.9, (jaccard + embedding) / 2)
    return 0.0


def _similarity(a, b):
    """문서 두 개의 유사도. 호출부가 하나뿐이면 이 경로를 쓴다."""
    return _similarity_features(_doc_features(a), _doc_features(b))


def cluster_documents(docs):
    docs = [
        {**doc, "bodyAvailability": body_availability(doc)}
        for doc in docs or [] if isinstance(doc, dict)
    ]
    parent = list(range(len(docs)))
    confidence = defaultdict(list)

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right, score):
        lroot, rroot = find(left), find(right)
        if lroot == rroot:
            return
        parent[rroot] = lroot
        confidence[lroot].append(score)
        confidence[lroot].extend(confidence.pop(rroot, []))

    # 문서별 값을 먼저 만든다. 쌍마다 다시 만들면 임베딩 계산이 O(n²)로 붙는다.
    features = [_doc_features(doc) for doc in docs]
    # 서로 다른 확정 이벤트 날짜는 항상 0점이다(`_similarity_features` 첫 규칙). 그
    # 문서들을 애초에 비교하지 않으면 결과를 바꾸지 않고 비교 수를 줄인다.
    unknown_dates = [i for i, row in enumerate(features) if row["eventDate"] == "unknown"]
    by_date = defaultdict(list)
    for index, row in enumerate(features):
        if row["eventDate"] != "unknown":
            by_date[row["eventDate"]].append(index)
    blocks = [*by_date.values(), unknown_dates]
    for block in blocks:
        for position, left in enumerate(block):
            for right in block[position + 1:]:
                score = _similarity_features(features[left], features[right])
                if score >= 0.72:
                    union(left, right, score)
    # `unknown`은 어느 날짜와도 비교 대상이다. 위 블록에서 빠진 조합만 추가로 본다.
    for left in unknown_dates:
        for right in range(len(features)):
            if right == left or features[right]["eventDate"] == "unknown":
                continue
            score = _similarity_features(features[left], features[right])
            if score >= 0.72:
                union(left, right, score)

    grouped = defaultdict(list)
    for index, doc in enumerate(docs):
        grouped[find(index)].append(doc)

    clusters = []
    for root, members in grouped.items():
        keys = sorted(_doc_key(doc) for doc in members)
        issue_id = hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:16]
        scores = confidence.get(find(root), [])
        cluster_confidence = sum(scores) / len(scores) if scores else 1.0
        clusters.append({
            "issueId": issue_id,
            "clusterConfidence": round(cluster_confidence, 4),
            "docs": members,
        })
    return clusters


def _priority_score(doc, target_market, market_windows):
    profile = source_profile(doc, target_market)
    session = {"primary": 10.0, "secondary": 7.0, "off_session_news": 6.0, "background": 3.0}.get(
        doc_analysis_priority(doc, market_windows), 3.0
    )
    return (
        briefing_doc_score(doc, market_windows)
        + profile["authority"] * 2.0
        + profile["marketExpertise"] * 2.0
        + session
    ) * profile["contentGate"]


def evaluate_issue_cluster(cluster, target_market, market_windows, publisher_issue_shares=None):
    docs = cluster.get("docs", [])
    by_publisher = defaultdict(list)
    for doc in docs:
        by_publisher[canonical_publisher(doc)].append(doc)
    representatives = []
    for publisher_docs in by_publisher.values():
        representatives.append(max(publisher_docs, key=lambda d: _priority_score(d, target_market, market_windows)))
    representatives.sort(key=lambda d: _priority_score(d, target_market, market_windows), reverse=True)

    profiles = [source_profile(doc, target_market) for doc in representatives]
    publisher_count = len(profiles)
    article_counts = Counter(canonical_publisher(doc) for doc in docs)
    total_articles = max(1, sum(article_counts.values()))
    concentration = sum((count / total_articles) ** 2 for count in article_counts.values())
    authority_sum = sum(profile["authority"] for profile in profiles)
    breadth = min(1.0, authority_sum / 35.0)
    expertise = sum(profile["marketExpertise"] for profile in profiles) / max(1, publisher_count)
    foreign_core_count = sum(1 for profile in profiles if profile["coreForeign"])
    domestic_count = sum(1 for profile in profiles if profile["region"] == "domestic")
    market_impact_raw = max((market_connection_score(doc) for doc in docs), default=0.0)
    impact_status = "measured" if market_impact_raw > 0 else "unavailable"
    market_impact_score = min(100.0, market_impact_raw * 2.5) if market_impact_raw > 0 else None
    cross_region = "domestic_only"
    cross_bonus = 0.0
    if str(target_market).upper() == "KR" and foreign_core_count >= 2:
        cross_region, cross_bonus = "cross_confirmed", 10.0
    elif str(target_market).upper() == "KR" and foreign_core_count >= 1 and market_impact_score is not None:
        cross_region, cross_bonus = "market_confirmed_international", 7.0
    elif foreign_core_count and domestic_count:
        cross_region, cross_bonus = "cross_region_covered", 4.0
    elif foreign_core_count:
        cross_region = "foreign_only"

    bias_penalty = 0.0
    for publisher in by_publisher:
        share = float((publisher_issue_shares or {}).get(publisher, 0.0) or 0.0)
        bias_penalty += max(0.0, share - 0.25) * 8.0
    syndication_count = sum(max(0, len(rows) - 1) for rows in by_publisher.values())
    content_gate = max((profile["contentGate"] for profile in profiles), default=0.38)
    impact_component = (market_impact_score or 0.0) * 0.24 if market_impact_score is not None else 0.0
    base_without_impact = (
        breadth * 30.0
        + min(publisher_count, 5) / 5.0 * 16.0
        + expertise * 1.4
        + cross_bonus
        - concentration * 10.0
        - min(syndication_count, 5) * 1.5
        - bias_penalty
    )
    issue_score = impact_component + base_without_impact
    if content_gate < 0.5 and market_impact_score is None:
        issue_score *= 0.55

    market = str(target_market).upper()
    warnings = []
    if impact_status == "unavailable":
        warnings.append("market impact data unavailable; ranked by breadth and authority")
    return {
        "issueId": cluster.get("issueId"),
        "market": market,
        "publisherCount": publisher_count,
        "weightedPublisherBreadth": round(breadth, 4),
        "foreignCorePublisherCount": foreign_core_count,
        "domesticPublisherCount": domestic_count,
        "sourceConcentration": round(concentration, 4),
        "clusterConfidence": cluster.get("clusterConfidence", 1.0),
        "syndicatedCopies": syndication_count,
        "bodyAvailabilityMix": dict(Counter(profile["bodyAvailability"] for profile in profiles)),
        "crossRegionStatus": cross_region,
        "internationalSalience": round(cross_bonus, 1),
        "marketImpactStatus": impact_status,
        "marketImpactScore": round(market_impact_score, 1) if market_impact_score is not None else None,
        "issueScore": round(max(0.0, issue_score), 2),
        "representativeDocs": representatives,
        "docs": docs,
        "warnings": warnings,
    }


def publisher_issue_concentration(docs):
    """Estimate each publisher's dominant-topic share in the available window."""
    totals = Counter()
    concept_counts = defaultdict(Counter)
    for doc in docs or []:
        publisher = canonical_publisher(doc)
        concepts = concepts_for_doc(doc) & EVENT_CONCEPTS
        if not concepts:
            continue
        totals[publisher] += 1
        for concept in concepts:
            concept_counts[publisher][concept] += 1
    result = {}
    for publisher, total in totals.items():
        # Do not infer a stable editorial tendency from a tiny sample.
        result[publisher] = max(concept_counts[publisher].values()) / total if total >= 5 else 0.0
    return result


def build_issue_coverage(docs, target_market, market_windows, limit=10, publisher_issue_shares=None):
    scoped = [doc for doc in docs or [] if infer_doc_market(doc) in {str(target_market).upper(), "BOTH", "GLOBAL"}]
    if publisher_issue_shares is None:
        publisher_issue_shares = publisher_issue_concentration(scoped)
    evaluated = [
        evaluate_issue_cluster(cluster, target_market, market_windows, publisher_issue_shares)
        for cluster in cluster_documents(scoped)
    ]
    evaluated.sort(key=lambda issue: (issue["issueScore"], issue["publisherCount"]), reverse=True)
    return evaluated[:limit]


_TITLE_MARKET_PRODUCTS = frozenset({"US", "KR", "EUROPE", "JP"})


def title_claims_other_market(doc, target: str) -> bool:
    """Whether the headline names a different market and never the target.

    Body text cannot decide a document's home market: every Korean market wrap
    opens with a sentence about the overnight New York close, which made
    "코스피 1.6% 반등 마감" a BOTH document and put it in a US briefing's
    참고자료. The headline states what the article is actually about, so a
    title that names only another market keeps the document out of this scope.
    A title with no market signal at all decides nothing — the full-document
    inference below still governs.
    """
    title = str(doc.get("title") or "").strip()
    if not title:
        return False
    title_markets = set(infer_doc_markets({"title": title}))
    named = title_markets & _TITLE_MARKET_PRODUCTS
    if target in named:
        return False
    # **`GLOBAL`이 통행증이 되면 안 된다.** 예전에는 제목에 유가·중동 같은 GLOBAL 토큰이
    # 하나라도 있으면 다른 시장을 명시한 제목도 통과시켰다. 그 근거는 "주시장 판정이 이미
    # 거른다"였는데, 주시장이 `GLOBAL`이나 `BOTH`로 나온 문서에는 그 판정이 걸리지 않는다
    # — `documents_for_scope`가 그런 문서를 **모든** 시장 풀에 넣기 때문이다.
    #
    # 그래서 "코스피, 美 CPI 경계·유가 상승에도 반도체 호조" 같은 제목이 유럽장·일본장
    # 브리핑의 참고자료로 올라왔다(실측). 제목이 다른 시장을 지목했으면 이 시장 기사가
    # 아니다. 시장 신호가 없거나 GLOBAL뿐인 제목은 여전히 아무것도 배제하지 않는다.
    return bool(named)


def documents_for_scope(docs, market_scope):
    """Narrow the candidate pool to one market, keeping global evidence.

    Aggregate scopes keep everything: each market leg narrows again on its own,
    and dropping a document here would remove it from every leg at once.
    """
    scope = normalize_market_scope(market_scope)
    if scope in AGGREGATE_SCOPES:
        return list(docs or [])
    target = scope.upper()
    # 유가·달러·공급망 기사는 특정 시장 소유가 아니라 어느 시장에도 근거가 된다.
    #
    # **`BOTH`는 "US+KR"이다.** `infer_doc_market`의 docstring이 그렇게 못박고 있는데,
    # 이 필터가 그것을 모든 시장에 통과시켰다. 그래서 미국+한국 기사가 유럽장·일본장
    # 풀을 채웠다 — 실측으로 일본장 풀 1,272건 중 825건(65%)이 `BOTH`였고, 그 결과
    # 일본장 브리핑 참고자료가 한국 기사로 찼다.
    #
    # 복수형(`infer_doc_markets`)으로 바꾸는 것은 답이 아니다. 그 값은 문서가 **스치듯
    # 언급한** 시장까지 담아서 오히려 풀이 넓어진다(실측 일본장 1,272 -> 2,054).
    allowed = {target, "GLOBAL"}
    if target in {"US", "KR"}:
        allowed.add("BOTH")
    return [
        doc for doc in docs or []
        if infer_doc_market(doc) in allowed
        and not title_claims_other_market(doc, target)
    ]


def _kr_session_is_still_open(market_windows) -> bool:
    """생성 시각 기준으로 한국장이 아직 진행 중인가.

    analysisMode는 "그날이 거래일인가"만 본다. 그것만으로 장중이라고 하면 지난
    날짜로 생성한 브리핑도 "장중"이 되어, 이미 끝난 장을 진행 중이라고 말한다.
    한국장은 CLAUDE.md 계약대로 생성 시각으로 가른다.
    """
    import datetime as dt

    session_date = str((market_windows or {}).get("krCurrentSessionDate") or "").strip()
    if not session_date:
        return False
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    today = now.date().isoformat()
    if session_date < today:
        return False
    if session_date > today:
        # 아직 오지 않은 세션은 장중이 아니다. 개장 전 상태는 별도 mode가 없어
        # 마감과 같은 취급을 하되 제목이 사실과 어긋나지 않게 한다.
        return False
    # 한국 정규장 09:00~15:30 KST. 종료 후 생성분은 마감으로 본다.
    return dt.time(9, 0) <= now.time() < dt.time(15, 30)


def session_modes_from_windows(market_windows):
    mode = str((market_windows or {}).get("analysisMode") or "")
    # 저장된 세션 단계가 있으면 그게 권위다. 그 값은 생성 시각(`as_of`)으로
    # 계산돼 제목·기준일과 같은 출처를 쓴다. 없으면 벽시계로 판정한다 —
    # 단계 없이 만들어진 window도 지난 세션을 "장중"이라 말하면 안 되기 때문이다.
    kr_phase = str((market_windows or {}).get("krSessionPhase") or "")
    if kr_phase == "intraday":
        kr_mode = "kr_intraday"
    elif kr_phase in {"pre_open", "closed"}:
        kr_mode = "kr_close"
    elif kr_phase == "holiday":
        kr_mode = "kr_holiday"
    else:
        kr_mode = "kr_intraday" if _kr_session_is_still_open(market_windows) else ""

    if mode == "weekend":
        legacy = {"us": "us_off_session", "kr": "kr_off_session"}
    elif mode == "both_holiday":
        legacy = {"us": "us_holiday", "kr": kr_mode or "kr_holiday"}
    elif mode.startswith("us_holiday_kr_open"):
        legacy = {"us": "us_holiday", "kr": kr_mode or "kr_close"}
    elif mode.startswith("us_holiday_kr_"):
        legacy = {"us": "us_holiday", "kr": kr_mode or "kr_close"}
    elif mode == "kr_holiday":
        legacy = {"us": "us_close", "kr": kr_mode or "kr_holiday"}
    elif kr_mode:
        legacy = {"us": "us_close", "kr": kr_mode}
    elif mode == "weekday_kr_open":
        # 단계도 없고 장중도 아니면 이미 끝난 세션이다. 거래일이라는 것만으로
        # 장중이라고 하면 두 달 전 브리핑도 "진행 중"이 된다.
        legacy = {"us": "us_close", "kr": "kr_close"}
    else:
        legacy = {"us": "us_close", "kr": "kr_off_session"}
    # 유럽·일본은 analysisMode가 다루지 않는다. 세션 기술자에서 직접 읽는다.
    for scope in ("europe", "jp"):
        resolved_mode = briefing_session_mode(scope, "", market_windows or {})
        if resolved_mode:
            legacy[scope] = resolved_mode
    return legacy


def select_diverse_documents(issues, market_windows, limit=24, per_publisher=4, minimum_publishers=5):
    candidates = []
    seen = set()
    for issue in issues or []:
        for doc in issue.get("representativeDocs", [])[:3]:
            key = _doc_key(doc)
            if key and key not in seen:
                seen.add(key)
                candidates.append((issue.get("issueScore", 0.0), doc))
    candidates.sort(key=lambda item: (item[0], briefing_doc_score(item[1], market_windows)), reverse=True)
    selected, deferred = [], []
    counts = Counter()
    for _, doc in candidates:
        publisher = canonical_publisher(doc)
        if counts[publisher] >= per_publisher:
            deferred.append(doc)
            continue
        selected.append(doc)
        counts[publisher] += 1
        if len(selected) >= limit:
            break
    relaxed = False
    if len(selected) < min(limit, len(candidates)):
        relaxed = True
        for doc in deferred:
            if len(selected) >= limit:
                break
            selected.append(doc)
    warnings = []
    if relaxed:
        warnings.append("publisher soft cap relaxed because evidence lanes lacked enough documents")
    if len(counts) < minimum_publishers:
        warnings.append(f"source diversity below target: {len(counts)}/{minimum_publishers} publishers")
    return selected, warnings


def diversify_ranked_documents(docs, limit=24, per_publisher=4, minimum_publishers=5):
    """Apply a soft publisher cap to an already relevance-ranked document list."""
    selected, deferred, seen = [], [], set()
    counts = Counter()
    for doc in docs or []:
        key = _doc_key(doc)
        if not key or key in seen:
            continue
        seen.add(key)
        publisher = canonical_publisher(doc)
        if counts[publisher] >= per_publisher:
            deferred.append(doc)
            continue
        selected.append(doc)
        counts[publisher] += 1
        if len(selected) >= limit:
            break
    relaxed = False
    if len(selected) < min(limit, len(seen)):
        relaxed = True
        for doc in deferred:
            if len(selected) >= limit:
                break
            selected.append(doc)
    warnings = []
    if relaxed:
        warnings.append("publisher soft cap relaxed because the selected evidence pool was too small")
    final_publishers = {canonical_publisher(doc) for doc in selected}
    if len(final_publishers) < minimum_publishers:
        warnings.append(f"source diversity below target: {len(final_publishers)}/{minimum_publishers} publishers")
    return selected, warnings


def doc_ref(doc):
    """저장/비교용 가벼운 문서 참조. 본문은 담지 않는다."""
    return {
        "title": doc.get("title") or "",
        "source": doc.get("source") or "",
        "url": doc.get("url") or "",
        "path": doc.get("path") or "",
        "date": doc.get("date") or "",
    }


def public_issue_coverage(issues):
    """Remove article payloads before persisting issue diagnostics."""
    fields = (
        "issueId", "market", "publisherCount", "weightedPublisherBreadth",
        "foreignCorePublisherCount", "domesticPublisherCount", "sourceConcentration",
        "clusterConfidence", "syndicatedCopies", "bodyAvailabilityMix",
        "crossRegionStatus", "marketImpactStatus", "marketImpactScore", "issueScore", "warnings",
        "internationalSalience",
    )
    rows = []
    for issue in issues or []:
        row = {field: issue.get(field) for field in fields}
        # 대표 제목·상위 자료가 없으면 저장된 이슈가 해시 id로만 남아
        # 변화 비교/화면 어디에서도 무슨 이슈인지 알 수 없다.
        representatives = issue.get("representativeDocs") or []
        row["title"] = str((representatives[0] or {}).get("title") or "") if representatives else ""
        row["topDocs"] = [doc_ref(doc) for doc in representatives[:3]]
        rows.append(row)
    return rows


def pairwise_cluster_metrics(items, predicted_cluster_by_id):
    tp = fp = fn = 0
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            expected_same = items[left].get("expectedCluster") == items[right].get("expectedCluster")
            predicted_same = predicted_cluster_by_id.get(items[left].get("id")) == predicted_cluster_by_id.get(items[right].get("id"))
            if predicted_same and expected_same:
                tp += 1
            elif predicted_same and not expected_same:
                fp += 1
            elif expected_same and not predicted_same:
                fn += 1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {"precision": round(precision, 4), "recall": round(recall, 4), "tp": tp, "fp": fp, "fn": fn}
