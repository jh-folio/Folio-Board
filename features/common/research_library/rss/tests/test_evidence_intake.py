"""Evidence Intake RSS helper tests.

Run:
    py -3 features/common/research_library/rss/tests/test_evidence_intake.py
"""
from __future__ import annotations

import sys
import sqlite3
import tempfile
import datetime as dt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.research_library.indexing.service import canonical_news_source, parse_rssarchive_markdown
from features.common.research_library.rss.service import (
    RSS_CACHE_TABLE,
    _collection_created_count,
    _dedupe_rss_rows,
    _repair_cached_media,
    archive_item,
    ensure_rss_cache,
)
from features.common.research_library.rss import rss_archive
from features.common.research_library.rss import service as rss_service
from features.common.research_library.rss.collectors import (
    collect_official_items,
    load_simple_yaml,
)
from features.common.research_library.rss.feed_config import (
    FeedConfigError,
    feed_metadata_for_query,
    load_rss_feeds,
    normalize_feed,
)
from features.common.research_library.rss.article import collect_article_body
from features.common.research_library.rss.policy import calculate_relevance_score, looks_paywalled, normalize_url, should_retry_existing_item
from features.common.research_library.rss.parser import KST, parse_feed, parse_pub_date
from features.common.research_library.rss.normalizer import rss_item_to_evidence
from features.common.research_library.rss.store import save_evidence_item
from features.common.research_library.rss.writer import evidence_markdown, existing_file_needs_enrichment, load_archive_index
from features.common.market_calendar import infer_doc_markets
from features.common.research_library.indexing.research_index import (
    MANIFEST_METADATA_VERSION,
    hybrid_search,
    init_db,
    load_documents_from_db,
    read_manifest,
    sync_index,
    write_manifest,
)


def test_naive_rfc822_pubdate_is_treated_as_kst_not_utc():
    import datetime as dt
    # mk.co.kr sends RFC822 pubDate without a timezone offset; the real time is KST.
    parsed = parse_pub_date("Tue, 23 Jun 2026 15:37:14")
    assert parsed is not None
    # 15:37 KST == 06:37 UTC (not 15:37 UTC, which would push it +9h to the next day)
    assert parsed == dt.datetime(2026, 6, 23, 6, 37, 14, tzinfo=dt.timezone.utc)
    # explicit offsets are still respected
    explicit = parse_pub_date("Tue, 23 Jun 2026 15:37:14 +0900")
    assert explicit == dt.datetime(2026, 6, 23, 6, 37, 14, tzinfo=dt.timezone.utc)


def test_future_published_at_is_capped_at_collection_time():
    import datetime as dt
    collected = dt.datetime(2026, 6, 23, 10, 17, 25, tzinfo=dt.timezone.utc)
    future = dt.datetime(2026, 6, 23, 15, 37, 0, tzinfo=dt.timezone.utc)  # after collection
    item = rss_item_to_evidence(
        item={"title": "t", "link": "https://mk.co.kr/news/1", "published_at_utc": future},
        source="매일경제",
        collected_at_utc=collected,
    )
    assert item["published_at_utc"] == collected


def test_normalize_url_removes_tracking_query():
    url = "HTTPS://www.Example.com/path/?utm_source=x&b=2&a=1&fbclid=zzz#frag"
    assert normalize_url(url) == "https://example.com/path?a=1&b=2"


def test_normalize_url_ignores_dow_jones_mod_tag_and_ft_syndication_key():
    """같은 기사가 피드마다 다른 `?mod=`로 와서 두 번 저장되던 사례(WSJ 346건)."""
    base = "https://www.wsj.com/business/tech-media-telecom-roundup-market-talk-60e57249"
    assert normalize_url(f"{base}?mod=rss_markets_main") == normalize_url(f"{base}?mod=pls_whats_news_us_business_f")
    assert normalize_url(f"{base}?mod=rss_Technology") == normalize_url(base)
    ft = "https://www.ft.com/content/dabdeae3-9855-484b-9369-e74176352107"
    assert normalize_url(f"{ft}?syn-25a6b1a6=1") == normalize_url(ft)


def test_normalize_url_keeps_mod_and_article_ids_on_other_hosts():
    """`mod`는 다른 사이트에서 콘텐츠를 가를 수 있고, 인포맥스 `idxno`는 기사 번호다."""
    assert normalize_url("https://example.com/view?mod=1") != normalize_url("https://example.com/view?mod=2")
    a = "https://news.einfomax.co.kr/news/articleView.html?idxno=1"
    b = "https://news.einfomax.co.kr/news/articleView.html?idxno=2"
    assert normalize_url(a) != normalize_url(b)


def test_rss_list_dedupe_merges_rows_stored_before_the_mod_rule():
    base = "https://www.wsj.com/tech/ai/openai-chatgpt-model-release-cancel-safety-5a2f9f42"
    rows = [
        {"normalized_url": f"{base}?mod=rss_markets_main", "url": f"{base}?mod=rss_markets_main"},
        {"normalized_url": f"{base}?mod=pls_whats_news_us_business_f", "url": f"{base}?mod=pls_whats_news_us_business_f"},
    ]
    assert len(_dedupe_rss_rows(rows)) == 1


def test_shipped_configs_collect_the_wsj_technology_feed():
    from features.common.research_library.rss.feed_config import load_rss_feeds

    for relative in ("config/rss_feeds.yaml", "defaults/config/rss_feeds.yaml"):
        urls = {feed["url"] for feed in load_rss_feeds(ROOT / relative) if feed["media"] == "WSJ"}
        assert "https://feeds.content.dowjones.io/public/rss/RSSWSJD" in urls, relative


def test_retry_policy_defaults_to_no_repeated_fetch():
    assert should_retry_existing_item("full_text") is False
    assert should_retry_existing_item("summary_only") is False
    assert should_retry_existing_item("needs_manual_save") is False
    assert should_retry_existing_item("legacy_rss") is False
    assert should_retry_existing_item("fetch_failed") is False
    assert should_retry_existing_item("fetch_failed", retry_failed=True) is True
    assert should_retry_existing_item("summary_only", retry_summary_only=True) is True


def test_collection_created_count_uses_collector_summary():
    output = "Saved: article.md [full_text]\nDone. Created 3 file(s). Updated 1 file(s). Upgraded 0 legacy file(s). Status: {}"
    assert _collection_created_count(output) == 3
    assert _collection_created_count("RSS collection failed.") is None


def test_relevance_score_accepts_market_items_and_penalizes_noise():
    market = {"title": "Nvidia earnings guidance lifts AI semiconductor shares"}
    noise = {"title": "여행 맛집 할인 세일"}
    assert calculate_relevance_score(market) >= 3
    assert calculate_relevance_score(noise) < 0


def test_paywall_detection():
    assert looks_paywalled("Subscribe to continue reading this article")
    assert looks_paywalled("이 기사는 구독 후 이용 가능합니다")
    assert looks_paywalled("로그인 후 이용 가능한 기사입니다")
    assert not looks_paywalled("Markets rose after earnings guidance improved")
    # 한국 뉴스 페이지 공통 푸터(뉴스레터 구독/로그인 버튼)는 유료벽이 아니다.
    assert not looks_paywalled("(서울=연합뉴스) 기사 본문 ... 뉴스레터 구독 신청 로그인 회원가입")


def test_raw_item_strips_embedded_html_from_description():
    from features.common.research_library.rss.parser import strip_markup

    google_desc = (
        '<a href="https://news.google.com/rss/articles/x?oc=5" target="_blank">'
        "Oil drifts down after OPEC+ agrees to raise output targets</a>"
        '&nbsp;<font color="#6f6f6f">Reuters</font>'
    )
    import html as html_mod
    cleaned = strip_markup(html_mod.unescape(google_desc))
    assert "<" not in cleaned and "href" not in cleaned
    assert cleaned.startswith("Oil drifts down after OPEC+")


def test_infer_doc_markets_word_boundaries_and_company_master():
    # substring 오탐 제거: "downgrade"의 dow, "turmoil"의 oil이 매칭되면 안 된다.
    assert infer_doc_markets({"title": "Analysts downgrade several names amid turmoil"}) == ["UNKNOWN"]
    # 단어 경계 매칭: Dow/Fed는 온전한 단어일 때만 US 신호다.
    assert "US" in infer_doc_markets({"title": "Dow rises 300 points as Fed signals pause"})
    assert infer_doc_markets({"title": "Downgrade wave hits industrials outside market turmoil"}) == ["UNKNOWN"]
    assert infer_doc_markets({"title": "FedEx expands parcel network"}) == ["UNKNOWN"]
    assert "US" in infer_doc_markets({"title": "Earnings season starts with banks in focus"})
    assert "KR" in infer_doc_markets({"title": "실적 시즌 앞두고 국내 증시 관심 확대"})
    # 회사 마스터(config/company_master.json) 기반 시장 신호
    assert "US" in infer_doc_markets({"title": "엔비디아 데이터센터 매출 신기록"})
    assert "KR" in infer_doc_markets({"title": "삼성전자 파운드리 수주 확대"})
    # 한국 기사 관행인 [6자리 종목코드] 표기는 KR 신호다.
    assert "KR" in infer_doc_markets({"title": "한투증권, 셀트리온[068270] 목표가 하향"})
    # 명시적 UNKNOWN 태그는 신호가 아니므로 본문 기준으로 재추론한다.
    assert infer_doc_markets({"market": "UNKNOWN", "title": "Nasdaq futures climb"}) == ["US"]


def test_rss_item_to_evidence_feed_default_market_is_fallback_only():
    import datetime as dt
    published = dt.datetime(2026, 7, 6, 1, 0, 0, tzinfo=dt.timezone.utc)
    feed = {"url": "https://example.com/feed", "default_market": "US", "reliability_tier": 2}
    # 아무 시장 신호가 없으면 feed 기본 시장을 쓴다.
    plain = rss_item_to_evidence(
        item={"title": "Weekly roundup of new gadgets", "link": "https://example.com/a", "published_at_utc": published},
        source="CNBC", feed=feed,
    )
    assert plain["markets"] == ["US"]
    # 본문에 실제 신호가 있으면 feed 힌트는 절대 이기지 못한다.
    kr_item = rss_item_to_evidence(
        item={"title": "코스피 외국인 순매수 확대", "link": "https://example.com/b", "published_at_utc": published},
        source="CNBC", feed=feed,
    )
    assert "KR" in kr_item["markets"] and "US" not in kr_item["markets"]


def test_rss_item_to_evidence_preserves_feed_language():
    published = dt.datetime(2026, 8, 4, 10, 0, tzinfo=dt.timezone.utc)
    item = rss_item_to_evidence(
        item={"title": "日経平均が反発", "link": "https://example.com/jp", "published_at_utc": published},
        source="Google News JP",
        feed={
            "url": "https://example.com/jp.xml",
            "default_market": "JP",
            "language": "ja",
            "reliability_tier": 2,
        },
    )
    assert item["language"] == "ja"
    # country는 없앴다 — 태그된 피드에서 언어와 1:1이었고 국제 통신사에서는 정의가 안 됐다.
    assert "country" not in item


def test_rss_archive_skips_stale_dated_feed_items():
    import datetime as dt
    collected = dt.datetime(2026, 7, 6, 0, 0, 0, tzinfo=dt.timezone.utc)
    stale = {"title": "Old market story", "published_at_utc": dt.datetime(2025, 7, 6, 0, 0, 0, tzinfo=dt.timezone.utc)}
    recent = {"title": "Recent market story", "published_at_utc": dt.datetime(2026, 7, 1, 0, 0, 0, tzinfo=dt.timezone.utc)}
    undated = {"title": "No date market story"}
    assert rss_archive.item_within_recency_window(stale, collected_at_utc=collected, max_age_days=14) is False
    assert rss_archive.item_within_recency_window(recent, collected_at_utc=collected, max_age_days=14) is True
    assert rss_archive.item_within_recency_window(undated, collected_at_utc=collected, max_age_days=14) is True


def test_rss_feed_config_includes_cnbc_business_economy_finance_channels():
    feeds = load_rss_feeds(ROOT / "config" / "rss_feeds.yaml")
    cnbc_feeds = {
        feed.get("category"): feed
        for feed in feeds
        if feed.get("media") == "CNBC"
    }
    assert "100003114" in cnbc_feeds["top"].get("url", "")
    assert "10001147" in cnbc_feeds["business"].get("url", "")
    assert "10000664" in cnbc_feeds["finance"].get("url", "")
    assert "20910258" in cnbc_feeds["economy"].get("url", "")
    assert any(
        feed.get("media") == "CNBC"
        and feed.get("category") == "investing"
        and "15839069" in feed.get("url", "")
        for feed in feeds
    )


def test_load_archive_index_reads_new_format_front_matter_urls():
    # 신규 front matter 포맷 파일이 dedupe 인덱스에서 누락되면 매 수집마다
    # 같은 기사가 " (2)", " (3)" 파일로 복제된다.
    content = "\n".join([
        "---",
        'id: "rss_dedupe_test"',
        'title: "테스트 기사"',
        'source: "연합뉴스"',
        'url: "https://www.yna.co.kr/view/AKR_TEST_001"',
        'normalized_url: "https://yna.co.kr/view/AKR_TEST_001"',
        'collection_status: "needs_manual_save"',
        "---",
        "",
        "# 테스트 기사",
        "",
        "## Full Text",
        "",
        "Full text is not saved by default.",
        "",
        "## Collection Notes",
        "",
        "- Status: needs_manual_save",
    ])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "2026-07-06 08-00-00 - 연합뉴스 - 테스트 기사.md"
        path.write_text(content, encoding="utf-8")
        links, names, link_paths = load_archive_index(Path(tmp))
        assert "https://yna.co.kr/view/AKR_TEST_001" in links
        assert link_paths["https://yna.co.kr/view/AKR_TEST_001"] == path
        # 신규 포맷의 collection_status를 읽어야 매 실행 재수집(refetch)을 막는다.
        assert existing_file_needs_enrichment(path) is False
        assert existing_file_needs_enrichment(path, retry_summary_only=True) is True


def test_collect_article_body_skips_aggregator_redirect_urls():
    # Google News 링크는 JS 리다이렉트 stub이라 기사 HTML이 아니다.
    # RSS 요약을 유지해야 하며 Google 페이지의 meta description으로 덮어쓰면 안 된다.
    body = collect_article_body(
        "https://news.google.com/rss/articles/CBMiAbc?oc=5",
        "Prosecutor charges refiners with price collusion",
    )
    assert body["status"] == "summary_only"
    assert body["summary"] == "Prosecutor charges refiners with price collusion"
    assert body["full_text"] == ""
    empty = collect_article_body("https://news.google.com/rss/articles/CBMiAbc?oc=5", "")
    assert empty["status"] == "needs_manual_save"


def test_collect_article_body_trusts_long_public_body_over_footer_banner():
    import features.common.research_library.rss.article as article_mod

    paragraph = "<p>" + "시장 분석 본문 문단입니다. 지수와 수급 흐름을 설명합니다. " * 30 + "</p>"
    markup = (
        "<html><head><meta name=\"description\" content=\"기사 요약\"></head>"
        f"<body><article>{paragraph}</article>"
        "<footer>구독 후 이용 가능한 프리미엄 뉴스레터도 있습니다</footer></body></html>"
    )
    original = article_mod.fetch_url_text
    article_mod.fetch_url_text = lambda url, **kwargs: markup
    try:
        body = article_mod.collect_article_body("https://example.com/news/1", "rss desc")
    finally:
        article_mod.fetch_url_text = original
    # 본문이 충분히 추출됐으면 페이지 다른 곳의 구독 배너가 full_text를 막지 않는다.
    assert body["status"] == "full_text"
    assert len(body["full_text"]) >= 700


def test_frontmatter_markdown_parses_for_indexing():
    md = evidence_markdown(
        {
            "id": "rss_test",
            "collector": "rss",
            "source_type": "news",
            "source": "Reuters",
            "title": "AI grid bottleneck",
            "url": "https://example.com/a?utm_source=x",
            "normalized_url": "https://example.com/a",
            "published_at_utc": None,
            "collected_at_utc": None,
            "query": "https://feed.example/rss",
            "query_source": "rss_feed",
            "description": "Grid demand rises.",
            "summary": "Grid demand rises.",
            "full_text": "Longer body",
            "collection_status": "summary_only",
            "error": "",
            "relevance_score": 3,
            "search_score": None,
            "related_tickers": [],
            "related_themes": [],
            "markets": ["US", "GLOBAL"],
            "event_id": None,
            "narrative_ids": [],
            "reliability_tier": 2,
        }
    )
    meta, body = parse_rssarchive_markdown(md)
    assert meta["title"] == "AI grid bottleneck"
    assert meta["url"] == "https://example.com/a?utm_source=x"
    assert meta["normalizedUrl"] == "https://example.com/a"
    assert meta["collectionStatus"] == "summary_only"
    assert meta["markets"] == ["US", "GLOBAL"]
    assert "Grid demand rises" in body


def test_yonhap_rss_item_keeps_yonhap_source_in_feed():
    md = evidence_markdown({
        "id": "rss_yonhap",
        "collector": "rss",
        "source_type": "news",
        "source": "연합뉴스",
        "title": "코스피 외국인 순매수 확대",
        "url": "https://www.yna.co.kr/view/AKR20260623000100002",
        "normalized_url": "https://www.yna.co.kr/view/AKR20260623000100002",
        "published_at_utc": None,
        "collected_at_utc": None,
        "query": "https://www.yna.co.kr/rss/market.xml",
        "query_source": "rss_feed",
        "summary": "외국인 순매수가 확대됐다.",
        "collection_status": "summary_only",
        "error": "",
        "relevance_score": 4,
        "search_score": None,
        "related_tickers": [],
        "related_themes": [],
        "event_id": None,
        "narrative_ids": [],
        "reliability_tier": 2,
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "2026-06-23 09-00-00 - 연합뉴스 - 코스피.md"
        path.write_text(md, encoding="utf-8")
        assert archive_item(path)["media"] == "연합뉴스"
    assert canonical_news_source("연합뉴스", "", "") == "연합뉴스"


def test_archive_item_exposes_multi_market_tags():
    md = evidence_markdown({
        "id": "rss_cross_market",
        "collector": "rss",
        "source_type": "news",
        "source": "Reuters",
        "title": "Nasdaq rally lifts Korean chip exporters as KOSPI opens higher",
        "url": "https://example.com/cross",
        "normalized_url": "https://example.com/cross",
        "published_at_utc": None,
        "collected_at_utc": None,
        "query": "feed",
        "query_source": "rss_feed",
        "summary": "US AI chip gains and KOSPI semiconductor names move with global dollar and supply-chain signals.",
        "collection_status": "summary_only",
        "error": "",
        "relevance_score": 4,
        "search_score": None,
        "related_tickers": [],
        "related_themes": [],
        "event_id": None,
        "narrative_ids": [],
        "reliability_tier": 2,
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "2026-06-23 09-00-00 - Reuters - cross.md"
        path.write_text(md, encoding="utf-8")
        item = archive_item(path)
    assert item["markets"] == ["US", "KR", "GLOBAL"]
    assert item["market"] == "US,KR,GLOBAL"


def test_archive_item_unions_stored_tags_with_fresh_inference():
    """Stored tags are a floor, not an override.

    Feeding them back into `infer_doc_markets` put them on the top rung of the
    ladder, so a tag written by an older token table echoed forever and editing
    the tables never reached already-collected material. Dropping them instead
    would lose what collection-time inference read from the full article, so the
    two are unioned: nothing is lost and new tokens still land.
    """
    from features.common.research_library.rss.service import _merge_market_tags

    assert _merge_market_tags(["UNKNOWN"], ["US"]) == ["US"]
    assert _merge_market_tags(["JP"], ["UNKNOWN"]) == ["JP"]
    assert _merge_market_tags(["UNKNOWN"], ["UNKNOWN"]) == ["UNKNOWN"]
    assert _merge_market_tags([], []) == ["UNKNOWN"]
    # Canonical order, whichever side each tag came from.
    assert _merge_market_tags(["GLOBAL", "US"], ["KR"]) == ["US", "KR", "GLOBAL"]
    # A value outside the contract (older spelling, hand edit) is kept, not dropped.
    assert _merge_market_tags(["EUROPE"], ["BOTH"]) == ["EUROPE", "BOTH"]


def test_cache_rows_carry_the_tagger_version_that_wrote_them():
    """An unchanged file must still be re-read when the token tables change.

    The refresh loop skipped by size and mtime alone, so stored items kept their
    old tags no matter how often the cache was rebuilt. Rows now record the
    tagger version and a stale row is reparsed even though its file is identical.
    """
    import sqlite3

    from features.common.market_calendar import MARKET_TAGGER_VERSION
    from features.common.research_library.rss.service import RSS_CACHE_TABLE, ensure_rss_cache

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_rss_cache(conn)
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({RSS_CACHE_TABLE})")}
    assert "tagger_version" in columns
    # 0 means "written before the column existed", which must never match.
    assert MARKET_TAGGER_VERSION > 0


def test_archive_item_prefers_frontmatter_market_tags():
    md = evidence_markdown({
        "id": "rss_tagged_market",
        "collector": "rss",
        "source_type": "news",
        "source": "Reuters",
        "title": "Chip supply chain update",
        "url": "https://example.com/tagged",
        "normalized_url": "https://example.com/tagged",
        "published_at_utc": None,
        "collected_at_utc": None,
        "query": "feed",
        "query_source": "rss_feed",
        "summary": "A short market update.",
        "collection_status": "summary_only",
        "error": "",
        "relevance_score": 4,
        "search_score": None,
        "related_tickers": [],
        "related_themes": [],
        "markets": ["KR", "GLOBAL"],
        "event_id": None,
        "narrative_ids": [],
        "reliability_tier": 2,
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "2026-06-23 09-00-00 - Reuters - tagged.md"
        path.write_text(md, encoding="utf-8")
        item = archive_item(path)
    assert item["markets"] == ["KR", "GLOBAL"]
    assert infer_doc_markets({"market": "US,KR,GLOBAL"}) == ["US", "KR", "GLOBAL"]


def test_rss_cache_schema_includes_markets_column():
    with sqlite3.connect(":memory:") as conn:
        ensure_rss_cache(conn)
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({RSS_CACHE_TABLE})").fetchall()}
    assert {"markets", "language", "tagger_version"} <= cols
    assert "country" not in cols


def test_rss_cache_upgrade_preserves_pre_language_schema_rows():
    """0.5 can add language metadata without requiring a destructive cache reset."""
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            f"""CREATE TABLE {RSS_CACHE_TABLE} (
                filename TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                title TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                timestamp_sort TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT NOT NULL,
                media TEXT NOT NULL,
                normalized_url TEXT NOT NULL DEFAULT '',
                collector TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT '',
                collection_status TEXT NOT NULL DEFAULT '',
                reliability_tier TEXT NOT NULL DEFAULT '',
                markets TEXT NOT NULL DEFAULT '',
                visible INTEGER NOT NULL,
                parsed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            f"""INSERT INTO {RSS_CACHE_TABLE}
                (filename, path, size, mtime_ns, title, timestamp, timestamp_sort, url, description, media,
                 normalized_url, collector, source_type, collection_status, reliability_tier, markets, visible, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "legacy.md", "legacy.md", 1, 1, "Legacy headline", "2026-06-23 09:00:00",
                "2026-06-23T09:00:00", "https://example.com/legacy", "summary", "Reuters",
                "https://example.com/legacy", "rss", "news", "summary_only", "2", "US", 1,
                "2026-06-23T09:00:00",
            ),
        )

        ensure_rss_cache(conn)
        row = conn.execute(
            f"SELECT filename, title, markets, language, mtime_ns, visible FROM {RSS_CACHE_TABLE} WHERE filename = ?",
            ("legacy.md",),
        ).fetchone()

    assert row == ("legacy.md", "Legacy headline", "US", "", -1, 1)


def test_existing_yonhap_cache_row_is_repaired_without_file_change():
    with sqlite3.connect(":memory:") as conn:
        ensure_rss_cache(conn)
        conn.execute(
            f"""INSERT INTO {RSS_CACHE_TABLE}
                (filename, path, size, mtime_ns, title, timestamp, timestamp_sort, url, description, media,
                 normalized_url, collector, source_type, collection_status, reliability_tier, visible, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "2026-06-23 09-00-00 - 연합뉴스 - 코스피.md", "x.md", 1, 1,
                "코스피 외국인 순매수", "2026-06-23 09:00:00", "2026-06-23T09:00:00",
                "https://www.yna.co.kr/view/AKR1", "summary", "User Archive",
                "", "rss", "news", "summary_only", "2", 1, "2026-06-23T09:00:00",
            ),
        )
        assert _repair_cached_media(conn) == 1
        media = conn.execute(f"SELECT media FROM {RSS_CACHE_TABLE}").fetchone()[0]
        assert media == "연합뉴스"


def test_rss_feed_rows_are_deduped_by_normalized_url():
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        ensure_rss_cache(conn)
        for filename, title, url, normalized_url in [
            ("a.md", "AI chip rally", "https://example.com/a?utm_source=x", "https://example.com/a"),
            ("b.md", "AI chip rally duplicate", "https://example.com/a?utm_source=y", "https://example.com/a"),
            ("c.md", "Different article", "https://example.com/c", "https://example.com/c"),
        ]:
            conn.execute(
                f"""INSERT INTO {RSS_CACHE_TABLE}
                    (filename, path, size, mtime_ns, title, timestamp, timestamp_sort, url, description, media,
                     normalized_url, collector, source_type, collection_status, reliability_tier, markets, visible, parsed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    filename, filename, 1, 1, title, "2026-06-23 09:00:00", "2026-06-23T09:00:00",
                    url, "summary", "Reuters", normalized_url, "rss", "news", "summary_only", "2",
                    "US,GLOBAL", 1, "2026-06-23T09:00:00",
                ),
            )
        rows = conn.execute(f"SELECT * FROM {RSS_CACHE_TABLE} ORDER BY filename").fetchall()

    deduped = _dedupe_rss_rows(rows)
    assert [row["filename"] for row in deduped] == ["a.md", "c.md"]


def test_rss_feed_config_loads_default_feeds():
    feeds = load_rss_feeds(ROOT / "config" / "rss_feeds.yaml")
    assert feeds
    assert all(feed["url"] and feed["media"] for feed in feeds)


def test_rss_feed_config_has_complete_europe_japan_selection_records():
    feeds = load_rss_feeds(ROOT / "config" / "rss_feeds.yaml")
    target = [feed for feed in feeds if feed["default_market"] in {"EUROPE", "JP"}]
    assert {feed["language"] for feed in target} == {"en", "de", "fr", "nl", "it", "es", "ja"}
    assert all(feed["source_type"] == "news" for feed in target)
    assert all(feed["reliability_tier"] in {1, 2, 3} for feed in target)
    assert all(feed["freshness_item_count"] > 0 for feed in target)
    assert all(feed["freshness_checked_at"] and feed["freshness_latest_at"] for feed in target)

    packaged = load_rss_feeds(ROOT / "defaults" / "config" / "rss_feeds.yaml")
    packaged_target = [feed for feed in packaged if feed["default_market"] in {"EUROPE", "JP"}]
    selection = lambda rows: {
        (
            feed["url"], feed["default_market"], feed["language"],
            feed["source_type"], feed["reliability_tier"], feed["freshness_checked_at"],
            feed["freshness_latest_at"], feed["freshness_item_count"],
        )
        for feed in rows
    }
    assert selection(packaged_target) == selection(target)


def test_rss_feed_config_rejects_invalid_target_metadata():
    valid = {
        "media": "Example",
        "url": "https://example.com/rss",
        "default_market": "EUROPE",
        "language": "de",
        "freshness_checked_at": "2026-08-04T11:10:00Z",
        "freshness_latest_at": "2026-08-04T10:40:51Z",
        "freshness_item_count": 29,
    }
    assert normalize_feed(valid)["language"] == "de"

    invalid_rows = [
        {**valid, "default_market": "EU"},
        {**valid, "language": "pt"},
        # 언어는 이제 모든 피드가 선언한다. 빠지면 US 피드도 거부된다.
        {k: v for k, v in valid.items() if k != "language"},
        {"media": "Example", "url": "https://example.com/us.xml", "default_market": "US"},
        {**valid, "freshness_item_count": 0},
        {**valid, "freshness_latest_at": "2026-07-31T10:40:51Z"},
    ]
    for row in invalid_rows:
        try:
            normalize_feed(row)
        except FeedConfigError:
            continue
        raise AssertionError(f"invalid feed metadata was accepted: {row}")


def test_feed_metadata_inference_requires_exact_unambiguous_feed_url(tmp_path: Path):
    row = """\
  - media: "Example {suffix}"
    url: "https://example.com/shared.xml"
    default_market: "JP"
    language: "ja"
    freshness_checked_at: "2026-08-04T11:10:00Z"
    freshness_latest_at: "2026-08-04T11:05:00Z"
    freshness_item_count: 1
"""
    one = tmp_path / "one.yaml"
    one.write_text("feeds:\n" + row.format(suffix="one"), encoding="utf-8")
    assert feed_metadata_for_query("https://example.com/shared.xml", config_path=one) == {
        "language": "ja", "default_market": "JP",
    }
    assert feed_metadata_for_query("https://example.com/other.xml", config_path=one) == {}

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("feeds:\n" + row.format(suffix="one") + row.format(suffix="two"), encoding="utf-8")
    assert feed_metadata_for_query("https://example.com/shared.xml", config_path=duplicate) == {}


def test_us_and_kr_feeds_are_indexed_with_their_market(tmp_path: Path):
    """The index used to drop them, which is why re-tagging could never work.

    Only Europe and Japan feeds were allowed to declare a country or a language,
    and the index kept only rows that had one, so all 36 US/KR/GLOBAL feeds fell
    out of it. The RSS cache rebuild therefore had no feed hint for them and
    every legacy `UNKNOWN` item stayed `UNKNOWN` no matter how often it ran.
    """
    config = tmp_path / "feeds.yaml"
    config.write_text(
        'feeds:\n'
        '  - media: "Bloomberg"\n'
        '    url: "https://example.com/us.xml"\n'
        '    default_market: "US"\n'
        '    language: "en"\n',
        encoding="utf-8",
    )
    assert feed_metadata_for_query("https://example.com/us.xml", config_path=config) == {
        "language": "en", "default_market": "US",
    }


def test_outlet_market_lookup_refuses_to_guess_across_markets(tmp_path: Path):
    """83% of stored items carry no feed URL, so the outlet name is the fallback.

    An outlet whose feeds span several markets cannot be resolved this way — the
    stored item does not record which of its feeds it arrived through — so it
    returns nothing rather than picking one.
    """
    from features.common.research_library.rss.feed_config import feed_market_for_media

    config = tmp_path / "feeds.yaml"
    config.write_text(
        'feeds:\n'
        '  - media: "한국경제"\n    url: "https://example.com/kr.xml"\n    default_market: "KR"\n    language: "ko"\n'
        '  - media: "Reuters"\n    url: "https://example.com/r-us.xml"\n    default_market: "US"\n    language: "en"\n'
        '  - media: "Reuters"\n    url: "https://example.com/r-gl.xml"\n    default_market: "GLOBAL"\n    language: "en"\n',
        encoding="utf-8",
    )
    assert feed_market_for_media("한국경제", config_path=config) == "KR"
    assert feed_market_for_media("Reuters", config_path=config) == ""
    assert feed_market_for_media("Unknown Outlet", config_path=config) == ""


def test_rss_sample_parse():
    xml = b"""<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Sample Feed</title>
        <item>
          <title>Semiconductor exports rise</title>
          <link>https://example.com/chips</link>
          <description>Korean chip exports rebounded in May.</description>
          <pubDate>Sat, 14 Jun 2026 01:02:03 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    items = parse_feed(xml)
    assert len(items) == 1
    assert items[0]["title"] == "Semiconductor exports rise"
    assert items[0]["link"] == "https://example.com/chips"
    assert "exports" in items[0]["description"]


def test_legacy_markdown_parse_still_works():
    legacy = (
        "- Title: Old style RSS item\n"
        "- Source: Reuters\n"
        "- URL: https://example.com/legacy\n"
        "- Timestamp (UTC+9): 2026-06-14 10:00:00\n"
        "- Collection Status: legacy_rss\n"
        "- Summary: Legacy summary body text.\n"
    )
    meta, body = parse_rssarchive_markdown(legacy)
    assert meta is not None
    assert meta["title"] == "Old style RSS item"
    assert meta["url"] == "https://example.com/legacy"
    assert meta["date"] == "2026-06-14"
    assert "Legacy summary body text" in body


def test_public_mode_does_not_store_full_text():
    evidence = {
        "id": "rss_public",
        "collector": "rss",
        "source_type": "news",
        "source": "Reuters",
        "title": "AI capex",
        "url": "https://example.com/p",
        "normalized_url": "https://example.com/p",
        "published_at_utc": None,
        "collected_at_utc": None,
        "query": "feed",
        "query_source": "rss_feed",
        "summary": "Short summary.",
        "full_text": "SECRET FULL ARTICLE BODY that must not be saved by default.",
        "collection_status": "summary_only",
        "error": "",
        "relevance_score": 3,
        "search_score": None,
        "related_tickers": [],
        "related_themes": [],
        "event_id": None,
        "narrative_ids": [],
        "reliability_tier": 2,
    }
    md = evidence_markdown(evidence, store_full_text=False)
    assert "SECRET FULL ARTICLE BODY" not in md
    assert "Full text is not saved by default" in md
    # With explicit opt-in the full text is written.
    md_full = evidence_markdown(evidence, store_full_text=True)
    assert "SECRET FULL ARTICLE BODY" in md_full


def test_frontmatter_round_trips_intake_metadata():
    md = evidence_markdown(
        {
            "id": "rss_meta",
            "collector": "rss",
            "source_type": "news",
            "source": "Bloomberg",
            "title": "Grid power demand",
            "url": "https://example.com/grid",
            "normalized_url": "https://example.com/grid",
            "published_at_utc": None,
            "collected_at_utc": None,
            "query": "AI data center power demand",
            "query_source": "news_query",
            "language": "ja",
            "summary": "Power demand rises.",
            "collection_status": "summary_only",
            "error": "",
            "relevance_score": 4,
            "search_score": 0.8,
            "related_tickers": ["NVDA"],
            "related_themes": ["ai_power"],
            "event_id": "evt_1",
            "narrative_ids": ["nar_power"],
            "reliability_tier": 2,
        }
    )
    meta, _ = parse_rssarchive_markdown(md)
    assert meta["collector"] == "rss"
    assert meta["sourceType"] == "news"
    assert meta["query"] == "AI data center power demand"
    assert meta["querySource"] == "news_query"
    assert meta["language"] == "ja"
    # 파서는 옛 파일 호환으로 키를 계속 읽지만, 새로 쓰는 front matter에는 값이 없다.
    assert meta["country"] == ""
    assert str(meta["reliabilityTier"]) == "2"


def test_rss_api_preserves_original_local_language_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inbox = tmp_path / "rss"
    inbox.mkdir()
    db_path = tmp_path / "research-index.sqlite3"
    title = "日経平均、AI投資を背景に反発"
    summary = "日本株は半導体関連株を中心に上昇した。"
    md = evidence_markdown({
        "id": "rss_jp_exact",
        "collector": "rss",
        "source_type": "news",
        "source": "Google News JP",
        "title": title,
        "url": "https://example.com/jp-exact",
        "normalized_url": "https://example.com/jp-exact",
        "published_at_utc": None,
        "collected_at_utc": None,
        "query": "https://example.com/jp.xml",
        "query_source": "rss_feed",
        "language": "ja",
        "summary": summary,
        "collection_status": "summary_only",
        "relevance_score": 4,
        "related_tickers": [],
        "related_themes": [],
        "markets": ["JP"],
        "narrative_ids": [],
        "reliability_tier": 2,
    })
    (inbox / "2026-08-04 20-00-00 - Google News JP - jp.md").write_text(md, encoding="utf-8")
    monkeypatch.setattr(rss_service, "RSS_INBOX_DIR", inbox)
    monkeypatch.setattr(rss_service, "RESEARCH_DB_PATH", db_path)
    monkeypatch.setattr(rss_service, "_RSS_CACHE_LAST_REFRESH", 0.0)
    monkeypatch.setattr(rss_service, "_RSS_CACHE_MEDIA_REPAIRED", False)
    # 이 테스트의 관심사는 언어 보존이다. JP 항목이 보이려면 범위에 JP가 있어야 한다.
    from features.common import market_scope

    scope_path = tmp_path / "market-scope.json"
    market_scope.save_market_scope(["US", "KR", "JP"], scope_path)
    monkeypatch.setattr(market_scope, "SCOPE_PATH", scope_path)

    payload = rss_service.rss_feed_payload({"limit": ["20"], "offset": ["0"]})
    assert payload["items"][0]["title"] == title
    assert payload["items"][0]["description"] == summary
    assert payload["items"][0]["language"] == "ja"
    assert "country" not in payload["items"][0]
    assert payload["languages"] == ["ja"]
    assert "countries" not in payload
    _, merged = rss_service.rss_merge_payload({})
    assert title in merged and summary in merged
    assert 'language: "ja"' in merged
    assert 'country:' not in merged


def test_old_markdown_infers_exact_feed_identity_without_rewrite(tmp_path: Path):
    jp_feed = next(
        feed for feed in load_rss_feeds(ROOT / "config" / "rss_feeds.yaml")
        if feed["default_market"] == "JP" and feed["language"] == "ja"
    )
    md = evidence_markdown({
        "id": "rss_jp_pre_language",
        "collector": "rss",
        "source_type": "news",
        "source": "Google News JP",
        "title": "日経平均の市況",
        "url": "https://example.com/jp-old",
        "normalized_url": "https://example.com/jp-old",
        "query": jp_feed["url"],
        "query_source": "rss_feed",
        "summary": "日本株の動向。",
        "collection_status": "summary_only",
        "markets": ["JP"],
        "reliability_tier": 2,
    })
    path = tmp_path / "2026-08-04 20-00-00 - Google News JP - old.md"
    path.write_text(md, encoding="utf-8")
    before = path.read_bytes()

    item = archive_item(path)

    assert item["language"] == "ja"
    assert path.read_bytes() == before


def test_atom_sample_parse():
    xml = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>AI capex rises</title>
        <link href="https://example.com/ai-capex"/>
        <summary>Companies increase AI infrastructure spending.</summary>
        <updated>2026-06-14T01:02:03Z</updated>
      </entry>
    </feed>
    """
    items = parse_feed(xml)
    assert len(items) == 1
    assert items[0]["title"] == "AI capex rises"
    assert items[0]["link"] == "https://example.com/ai-capex"


def test_official_collector_stub_does_not_make_fake_data():
    items, usage = collect_official_items(load_simple_yaml(ROOT / "config" / "evidence_sources.yaml"))
    assert items == []
    assert usage["items"] == 0
    assert "stub" in usage["warning"]


def test_evidence_store_upserts_item():
    item = {
        "id": "rss_store_test",
        "collector": "rss",
        "source_type": "news",
        "source": "Reuters",
        "title": "AI infrastructure earnings",
        "url": "https://example.com/store",
        "normalized_url": "https://example.com/store",
        "published_at_utc": None,
        "collected_at_utc": None,
        "query": "feed",
        "query_source": "rss_feed",
        "language": "fr",
        "country": "FR",
        "summary": "AI infrastructure earnings improved.",
        "collection_status": "summary_only",
        "relevance_score": 3,
        "search_score": None,
        "related_tickers": [],
        "related_themes": [],
        "event_id": None,
        "narrative_ids": [],
        "reliability_tier": 2,
    }
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "evidence.sqlite3"
        save_evidence_item(db_path, item, "research-inbox/rss/x.md")
        assert db_path.exists()
        conn = sqlite3.connect(db_path)
        try:
            stored = conn.execute(
                "SELECT language, country FROM evidence_items WHERE id = ?", (item["id"],)
            ).fetchone()
        finally:
            conn.close()
        assert stored == ("fr", "FR")


def test_index_document_and_chunk_results_preserve_language_country(tmp_path: Path):
    db_path = tmp_path / "research-index.sqlite3"
    doc = {
        "id": "jp_doc",
        "path": "research-inbox/rss/jp.md",
        "title": "Nikkei AI investment",
        "source": "Example",
        "date": "2026-08-04",
        "type": "article",
        "url": "https://example.com/jp",
        "marketRelevance": 4,
        "summary": "Nikkei investment summary",
        "content": "Nikkei AI investment expands across Japanese semiconductor companies.",
        "contentHash": "hash-jp",
        "language": "ja",
        # 예전 front matter에 남아 있는 국가 값은 인덱스가 계속 보존한다. 새로 수집하는
        # 자료에는 붙지 않지만, 이미 저장된 문서에서 지우지는 않는다.
        "country": "JP",
        "markets": ["JP"],
    }
    sync_index(db_path, {"generatedAt": "2026-08-04T11:10:00Z", "documents": [doc]})
    stored = load_documents_from_db(db_path)[0]
    assert (stored["language"], stored["country"]) == ("ja", "JP")
    hits = hybrid_search(db_path, "Nikkei investment", limit=5)
    assert hits and hits[0]["metadata"]["language"] == "ja"
    assert hits[0]["metadata"]["country"] == "JP"


def test_file_manifest_adds_metadata_version_without_losing_legacy_rows(tmp_path: Path):
    db_path = tmp_path / "legacy-index.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE file_manifest (path TEXT PRIMARY KEY, file_signature TEXT NOT NULL, "
            "market_relevant INTEGER NOT NULL, doc_id TEXT NOT NULL, modified_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO file_manifest VALUES (?, ?, ?, ?, ?)",
            ("research-inbox/rss/old.md", "1:1", 1, "old", "2026-08-04T00:00:00Z"),
        )
        init_db(conn)
    finally:
        conn.close()

    legacy = read_manifest(db_path)
    assert legacy["research-inbox/rss/old.md"]["metadataVersion"] == 1
    legacy["research-inbox/rss/old.md"]["metadataVersion"] = MANIFEST_METADATA_VERSION
    write_manifest(db_path, legacy)
    assert read_manifest(db_path)["research-inbox/rss/old.md"]["metadataVersion"] == MANIFEST_METADATA_VERSION


if __name__ == "__main__":
    test_normalize_url_removes_tracking_query()
    test_retry_policy_defaults_to_no_repeated_fetch()
    test_relevance_score_accepts_market_items_and_penalizes_noise()
    test_paywall_detection()
    test_raw_item_strips_embedded_html_from_description()
    test_infer_doc_markets_word_boundaries_and_company_master()
    test_rss_item_to_evidence_feed_default_market_is_fallback_only()
    test_load_archive_index_reads_new_format_front_matter_urls()
    test_collect_article_body_skips_aggregator_redirect_urls()
    test_collect_article_body_trusts_long_public_body_over_footer_banner()
    test_frontmatter_markdown_parses_for_indexing()
    test_rss_feed_config_loads_default_feeds()
    test_rss_sample_parse()
    test_legacy_markdown_parse_still_works()
    test_public_mode_does_not_store_full_text()
    test_frontmatter_round_trips_intake_metadata()
    test_atom_sample_parse()
    test_official_collector_stub_does_not_make_fake_data()
    test_evidence_store_upserts_item()
    print("ok")


def test_parser_extracts_publisher_from_rss_source_tag():
    from features.common.research_library.rss.parser import parse_feed

    xml = (
        b"<rss><channel><item>"
        b"<title>Capital One closes accounts</title>"
        b"<link>https://finance.yahoo.com/news/capital-one</link>"
        b"<pubDate>Sun, 02 Aug 2026 12:00:00 GMT</pubDate>"
        b'<source url="http://www.reuters.com/">Reuters</source>'
        b"</item></channel></rss>"
    )
    rows = parse_feed(xml)
    assert len(rows) == 1
    assert rows[0]["publisher"] == "Reuters"


def test_publisher_filter_keeps_only_configured_outlets_and_retags():
    from features.common.research_library.rss.rss_archive import _matched_publisher, feed_item_allowed

    feed = {"media": "Yahoo Finance", "only_publishers": ["Reuters"]}
    reuters = {"publisher": "Reuters", "title": "t", "link": "https://finance.yahoo.com/a"}
    fool = {"publisher": "Motley Fool", "title": "t", "link": "https://finance.yahoo.com/b"}
    assert feed_item_allowed(feed, reuters) is True
    assert feed_item_allowed(feed, fool) is False
    # 저장 시에는 aggregator가 아니라 원 발행처로 태그한다.
    assert _matched_publisher(feed, reuters) == "Reuters"
    assert _matched_publisher(feed, fool) == ""


def test_unfiltered_feed_keeps_every_item():
    from features.common.research_library.rss.rss_archive import feed_item_allowed

    feed = {"media": "BBC", "only_publishers": []}
    assert feed_item_allowed(feed, {"publisher": "", "title": "t"}) is True
    assert feed_item_allowed(feed, {"publisher": "Anything", "title": "t"}) is True


def test_press_release_feeds_are_tagged_and_excluded_from_briefing_only():
    """와이어는 기업 자료로 분리한다: 브리핑 입력에서만 빠지고 검색·기업분석에는 남는다."""
    import datetime as dt

    from features.common.research_library.rss.normalizer import rss_item_to_evidence
    from features.daily_briefing.service import is_news_document

    item = {
        "title": "Acme Corp Reports Q2 Results",
        "link": "https://www.prnewswire.com/news-releases/acme-q2.html",
        "description": "Acme announced results",
        "published_at_utc": dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc),
    }
    wire_feed = {"media": "PR Newswire", "source_type": "press_release", "default_market": "US"}
    news_feed = {"media": "CNBC", "source_type": "news", "default_market": "US"}

    wire = rss_item_to_evidence(item=item, source="PR Newswire", feed=wire_feed)
    news = rss_item_to_evidence(item=item, source="CNBC", feed=news_feed)
    assert wire["source_type"] == "press_release"
    assert news["source_type"] == "news"

    base = "research-inbox/rss/2026-08-03 12-00-00 - x.md"
    # 브리핑 입력에서는 제외
    assert is_news_document({"path": base, "sourceType": "press_release"}) is False
    # 일반 뉴스는 그대로 통과
    assert is_news_document({"path": base, "sourceType": "news"}) is True
    # source_type이 없는 기존 문서도 회귀 없이 통과해야 한다
    assert is_news_document({"path": base}) is True


def test_rss_screen_never_shows_press_release_wires():
    """PR Newswire·GlobeNewswire는 RSS 피드 화면에 아예 노출하지 않는다.

    소스를 직접 고르면 보여주던 예외를 없앴다. 기업이 직접 낸 1차 자료라 매체 교차
    확인이 없고 발행량이 많아 목록에서 뉴스를 밀어낸다. 수집·인덱싱은 그대로여서
    워치리스트 종목 뉴스와 기업분석 보조자료로는 계속 쓰인다.
    """
    from features.common.research_library.rss.service import _cache_where

    default_where, _ = _cache_where()
    assert "press_release" in default_where

    # 소스를 직접 골라도 제외 조건이 남아야 한다.
    chosen_where, params = _cache_where(source="PR Newswire")
    assert "press_release" in chosen_where
    assert "PR Newswire" in params


def test_feeds_the_keyword_lists_cannot_read_skip_the_gate():
    """The gate is keyed on language, because the term lists are Korean/English.

    Measured against live feeds, those lists passed 4% of Japanese items and 95%
    of French ones — the French number came from ``ai`` colliding inside
    ``vrai``/``aider``, not from relevance. Keeping the gate would silently drop
    most real foreign market news.
    """
    from features.common.research_library.rss.relevance import should_archive_item

    target = {"media": "Handelsblatt", "default_market": "EUROPE", "language": "de"}
    assert should_archive_item("SAP hebt Prognose nach starkem Cloud-Wachstum an", "", "https://handelsblatt.com/a", target)
    assert should_archive_item("日経平均、半導体株高で反発", "", "https://nhk.or.jp/a", {"media": "NHK", "language": "ja"})

    # 구조 필터는 이 피드에서도 그대로 적용된다.
    assert not should_archive_item("About XYZ ETF", "", "https://handelsblatt.com/a", target)
    assert not should_archive_item("[포토] 행사 사진", "", "https://handelsblatt.com/a", target)


def test_korean_and_english_feeds_keep_the_keyword_gate():
    """Every feed declares a language now, so "has metadata" would open the gate.

    Reading the language as mere presence would hand the bypass to Korean and
    English feeds too — exactly the ones these lists can judge — and the Korean
    noise filter (`[포토]`, 맛집, 장바구니) would stop running.
    """
    from features.common.research_library.rss.relevance import should_archive_item

    us_feed = {"media": "CNBC", "default_market": "US", "language": "en"}
    kr_feed = {"media": "한국경제", "default_market": "KR", "language": "ko"}
    assert should_archive_item("삼성전자 영업이익 10조 돌파", "", "https://example.com/a", us_feed)
    assert not should_archive_item("맛집 랩스터 홈다이닝 할인 세일", "", "https://example.com/a", us_feed)
    assert not should_archive_item("맛집 랩스터 홈다이닝 할인 세일", "", "https://hankyung.com/a", kr_feed)
    # feed 인자 없이 호출하던 기존 경로도, 언어를 모르는 경우도 게이트를 지난다.
    assert should_archive_item("삼성전자 영업이익 10조 돌파", "", "https://example.com/a")
    assert not should_archive_item("맛집 랩스터 홈다이닝 할인 세일", "", "https://example.com/a", {"media": "?"})


def test_target_feed_score_floors_at_the_archive_threshold():
    """Foreign-language text scores near zero on Korean/English terms; the feed floors it."""
    from features.common.research_library.rss.policy import calculate_relevance_score

    item = {"title": "SAP hebt Prognose nach starkem Cloud-Wachstum an", "description": ""}
    target = {"language": "de"}
    assert calculate_relevance_score(item) < 1.0
    assert calculate_relevance_score(item, target, baseline=1.0) == 1.0

    # 용어가 실제로 맞는 항목은 바닥값보다 높게 남아 순위가 보존된다.
    rich = {"title": "Nvidia revenue guidance and earnings", "description": ""}
    assert calculate_relevance_score(rich, target, baseline=1.0) > 1.0
    # US/KR 경로는 feed 유무와 무관하게 동일하다.
    assert calculate_relevance_score(rich) == calculate_relevance_score(rich, {"media": "CNBC", "language": "en"})


def test_stored_relevance_score_matches_the_gate_score(monkeypatch: pytest.MonkeyPatch):
    """저장 점수는 게이트가 통과시킨 그 점수여야 한다.

    feed·baseline 없이 다시 매기면 키워드 표가 읽지 못하는 언어(de·ja)의 바닥 처리가
    빠진다. baseline으로 통과한 독일어 항목이 `evidence_items.relevance_score` 0점으로
    저장되어, 저장된 값이 그 항목을 들인 이유와 어긋났다.
    """
    monkeypatch.setattr(
        rss_archive, "collect_article_body",
        lambda link, description: {"status": "summary_only", "summary": description, "full_text": ""},
    )
    feed = {
        "media": "Handelsblatt", "default_market": "EUROPE", "language": "de",
        "url": "https://handelsblatt.test/rss.xml", "reliability_tier": 2,
    }
    item = {
        "title": "SAP hebt Prognose nach starkem Cloud-Wachstum an",
        "description": "Der Softwarekonzern rechnet mit hoeherem Wachstum.",
        "link": "https://handelsblatt.test/a",
        "published_at_utc": None,
    }
    gate = calculate_relevance_score(item, feed, baseline=1.0)
    assert gate == 1.0, "게이트는 바닥값으로 통과시킨다"

    built = rss_archive.build_manifest_item((feed, item, None, 1.0))
    assert built["relevance_score"] == gate
    assert built["evidence"]["relevance_score"] == gate

    # 한국어·영어 피드는 바닥 처리가 없으므로 기존 동작 그대로다.
    kr_feed = {"media": "한국경제", "default_market": "KR", "language": "ko", "url": "https://hankyung.test/rss.xml"}
    kr_item = {"title": "삼성전자 영업이익 10조 돌파", "description": "", "link": "https://hankyung.test/a", "published_at_utc": None}
    kr_built = rss_archive.build_manifest_item((kr_feed, kr_item, None, 1.0))
    assert kr_built["relevance_score"] == calculate_relevance_score(kr_item, kr_feed, baseline=1.0) > 1.0


def test_language_options_do_not_shrink_to_the_active_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """언어 선택지는 출처처럼 필터를 타지 않은 질의에서 만든다.

    필터 결과에서 뽑으면 de를 고른 순간 목록이 de 하나가 되어, 화면에서 다른 언어로
    돌아갈 방법이 사라진다.
    """
    inbox = tmp_path / "rss"
    inbox.mkdir()
    for idx, (language, source, title) in enumerate((
        ("de", "Handelsblatt", "SAP hebt Prognose an"),
        ("ja", "Nikkei", "日経平均、半導体株高で反発"),
    )):
        md = evidence_markdown({
            "id": f"rss_lang_{language}",
            "collector": "rss",
            "source_type": "news",
            "source": source,
            "title": title,
            "url": f"https://example.com/{language}",
            "normalized_url": f"https://example.com/{language}",
            "published_at_utc": None,
            "collected_at_utc": None,
            "query": f"https://example.com/{language}.xml",
            "query_source": "rss_feed",
            "language": language,
            "summary": title,
            "collection_status": "summary_only",
            "relevance_score": 3,
            "related_tickers": [],
            "related_themes": [],
            "markets": ["GLOBAL"],
            "narrative_ids": [],
            "reliability_tier": 2,
        })
        (inbox / f"2026-08-04 2{idx}-00-00 - {source} - x.md").write_text(md, encoding="utf-8")
    monkeypatch.setattr(rss_service, "RSS_INBOX_DIR", inbox)
    monkeypatch.setattr(rss_service, "RESEARCH_DB_PATH", tmp_path / "research-index.sqlite3")
    monkeypatch.setattr(rss_service, "_RSS_CACHE_LAST_REFRESH", 0.0)
    monkeypatch.setattr(rss_service, "_RSS_CACHE_MEDIA_REPAIRED", False)

    unfiltered = rss_service.rss_feed_payload({"limit": ["20"], "offset": ["0"]})
    assert unfiltered["languages"] == ["de", "ja"]

    filtered = rss_service.rss_feed_payload({"limit": ["20"], "offset": ["0"], "language": ["de"]})
    assert [item["language"] for item in filtered["items"]] == ["de"], "목록은 고른 언어만 보여준다"
    assert filtered["languages"] == ["de", "ja"], "선택지는 좁아지지 않는다"


def test_rss_feed_payload_filters_by_language():
    """국가 필터는 없앴다. 언어는 원문을 읽을 수 있는 항목만 추릴 때 쓴다."""
    from features.common.research_library.rss.service import _cache_where

    where, params = _cache_where(language="ja")
    assert "language = ?" in where
    assert "ja" in params

    # 대문자 입력을 저장 형식으로 맞춘다.
    _, params = _cache_where(language="JA")
    assert "ja" in params

    # 필터를 주지 않으면 조건이 늘어나지 않는다.
    where_plain, _ = _cache_where()
    assert "language = ?" not in where_plain
    assert "country" not in where_plain


def test_market_filter_accepts_the_new_markets_and_the_eu_alias():
    from features.common.research_library.rss.service import _normalize_market_filter

    assert _normalize_market_filter("EUROPE") == "EUROPE"
    assert _normalize_market_filter("JP") == "JP"
    # `EU`는 경계 alias일 뿐 저장/조회값은 EUROPE다.
    assert _normalize_market_filter("EU") == "EUROPE"
    assert _normalize_market_filter("US") == "US"
    assert _normalize_market_filter("KR") == "KR"
    assert _normalize_market_filter("ZZ") == ""
def test_rss_source_dropdown_excludes_press_release_wires():
    """목록에서 안 보이는 매체가 출처 목록에만 남으면 고를 수 있는 빈 항목이 된다."""
    from features.common.research_library.rss import service

    source = Path(service.__file__).read_text(encoding="utf-8")
    dropdown_count = source.count("SELECT DISTINCT media FROM")
    assert dropdown_count >= 1, "출처 목록 쿼리를 찾지 못했다"
    # 출처 목록 쿼리는 전부 목록과 같은 제외 조건을 공유해야 한다.
    guarded = source.count("_HIDE_PRESS_RELEASE_SQL} ORDER BY media")
    assert guarded == dropdown_count


def test_source_dropdown_only_offers_currently_collected_media(monkeypatch):
    """수집 경로가 사라진 매체는 필터에서 뺀다. 과거 항목은 목록에 그대로 남는다."""
    from features.common.research_library.rss import service

    monkeypatch.setattr(service, "_configured_source_names", lambda: {"CNBC", "Reuters"})
    rows = [{"media": "CNBC"}, {"media": "Barron's"}, {"media": "Reuters"}]
    assert service._selectable_sources(rows) == ["CNBC", "Reuters"]


def test_source_dropdown_keeps_republished_publisher_names(monkeypatch):
    """aggregating 피드는 원 발행처 이름으로 다시 태그되므로 그 이름이 살아야 한다."""
    from features.common.research_library.rss import service

    # Yahoo Finance 피드가 only_publishers=[Reuters]이면 새 항목은 Reuters로 저장된다.
    monkeypatch.setattr(service, "_configured_source_names", lambda: {"Reuters"})
    rows = [{"media": "Reuters"}, {"media": "Yahoo Finance"}]
    assert service._selectable_sources(rows) == ["Reuters"]


def test_source_dropdown_falls_back_to_all_media_when_config_is_unreadable(monkeypatch):
    """설정을 못 읽으면 필터를 비우지 말고 기존 동작대로 전부 노출한다."""
    from features.common.research_library.rss import service

    def boom():
        raise RuntimeError("config unreadable")

    monkeypatch.setattr(service, "_configured_source_names", boom)
    rows = [{"media": "CNBC"}, {"media": "Barron's"}]
    assert service._selectable_sources(rows) == ["CNBC", "Barron's"]


def test_configured_source_names_reads_the_live_feed_config():
    """헬퍼가 실제 config를 읽는지 확인한다(이름 하드코딩 방지)."""
    from features.common.research_library.rss.service import _configured_source_names

    names = _configured_source_names()
    assert names, "rss_feeds.yaml에서 매체를 읽지 못했다"
    assert "CNBC" in names



def test_the_country_migration_cannot_reparse_the_archive_forever():
    """`DROP COLUMN`이 실패해도 캐시를 되풀이해서 버리지 않는다.

    처음에는 컬럼 삭제 실패를 무효화 신호로 썼다. `DROP COLUMN`은 SQLite 3.35+이고
    인덱스나 뷰가 걸려 있으면 그 뒤로도 실패하는데, 그러면 `ensure_rss_cache`가 불릴
    때마다 — 즉 피드를 열 때마다 — 22,000행이 전부 다시 읽힌다. 다시 읽어야 하는지는
    `tagger_version`이 이미 행마다 들고 있으므로 여기서 따로 무효화하지 않는다.
    """
    from features.common.research_library.rss.service import RSS_CACHE_TABLE, ensure_rss_cache

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE rss_feed_items (filename TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL, title TEXT NOT NULL, timestamp TEXT NOT NULL, timestamp_sort TEXT NOT NULL,
        url TEXT NOT NULL, description TEXT NOT NULL, media TEXT NOT NULL, language TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT '', visible INTEGER NOT NULL, parsed_at TEXT NOT NULL)"""
    )
    # 뷰가 컬럼을 붙잡고 있어 DROP COLUMN이 실패한다.
    conn.execute("CREATE VIEW keeps_country AS SELECT country FROM rss_feed_items")
    for index in range(5):
        conn.execute(
            "INSERT INTO rss_feed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"f{index}.md", "p", 1, 100 + index, "t", "", "", "", "", "m", "", "US", 1, ""),
        )

    for _ in range(3):
        ensure_rss_cache(conn)
        invalidated = conn.execute(
            f"SELECT COUNT(*) FROM {RSS_CACHE_TABLE} WHERE mtime_ns = -1"
        ).fetchone()[0]
        assert invalidated == 0

    # 재파싱은 버전이 강제한다 — 업그레이드하면 컬럼이 0으로 새로 생긴다.
    assert conn.execute(
        f"SELECT COUNT(*) FROM {RSS_CACHE_TABLE} WHERE tagger_version = 0"
    ).fetchone()[0] == 5
    conn.close()
