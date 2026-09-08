"""일일 브리핑 자료 선별/시장 동인/LLM context 단위 테스트.

의존성: 프로젝트 모듈 + 표준 라이브러리만 사용한다. pytest가 있으면
`pytest`로, 없으면 스크립트로 바로 실행할 수 있다.

    py -3 -m features.daily_briefing.tests.test_briefing
    py -3 features/daily_briefing/tests/test_briefing.py
"""
import os
import sys
import json
from pathlib import Path
from tempfile import TemporaryDirectory

# 스크립트로 직접 실행할 때 프로젝트 루트를 import 경로에 추가
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.common.market_calendar import briefing_market_windows
from features.daily_briefing import selection as sel
from features.daily_briefing import service as svc
from features.market_memory.snapshot import save_market_state_snapshot


BRIEFING_DATE = "2026-06-10"
WINDOWS = briefing_market_windows(BRIEFING_DATE)
US_DATE = WINDOWS["usRegularSessionDate"]
KR_DATE = WINDOWS["krPreviousSessionDate"]


def _doc(**over):
    base = {
        "title": "", "summary": "", "content": "", "source": "User Archive",
        "sourceWeight": 5, "date": US_DATE, "path": "research-inbox/rss/x.md",
        "url": "", "companies": [], "sectors": [], "impactTags": [],
        "marketRelevance": 0, "wordCount": 0,
    }
    base.update(over)
    return base


def _us_rate_doc():
    return _doc(
        title="Fed signals rate cut as Treasury yields fall",
        summary="The 10-year Treasury yield dropped after dovish Fed remarks",
        content="x" * 900, source="Reuters", sourceWeight=9, date=US_DATE,
        path="research-inbox/rss/fed.md", url="http://r/fed",
        companies=[{"name": "Nvidia", "ticker": "NVDA", "market": "US"}],
        sectors=["Semiconductors"], impactTags=["금리", "AI"],
        marketRelevance=80, wordCount=900,
    )


def _kr_supply_doc():
    return _doc(
        title="코스피 외국인 순매수 전환, 원달러 환율 상승",
        summary="외국인 수급이 개선되며 코스피가 반등했다",
        content="y" * 300, source="연합인포맥스", sourceWeight=7, date=KR_DATE,
        path="research-inbox/rss/kr.md", url="http://r/kr",
        companies=[{"name": "삼성전자", "ticker": "005930.KS", "market": "KR"}],
        sectors=["Semiconductors"], impactTags=["수급", "환율"],
        marketRelevance=60, wordCount=300,
    )


def _weak_article():
    return _doc(
        title="개인 메모", summary="짧은 메모", content="z" * 40,
        source="User Archive", sourceWeight=5, date=US_DATE,
        path="research-inbox/articles/note.md", url="",
        companies=[], sectors=[], impactTags=[], marketRelevance=100, wordCount=40,
    )


# ---------------------------------------------------------------------------
# briefing_doc_score
# ---------------------------------------------------------------------------
def test_briefing_doc_score_orders_quality():
    strong = sel.briefing_doc_score(_us_rate_doc(), WINDOWS)
    weak = sel.briefing_doc_score(_weak_article(), WINDOWS)
    assert strong > weak, (strong, weak)
    assert weak >= 0.0


def test_briefing_doc_score_primary_bucket_bonus():
    # 같은 자료라도 시장 시간창에 맞으면(=US 전일 정규장) 점수가 더 높다
    in_window = _us_rate_doc()
    out_window = dict(in_window, date="2020-01-01")  # 어떤 버킷에도 안 맞음 → 보조 자료 감점
    assert sel.briefing_doc_score(in_window, WINDOWS) > sel.briefing_doc_score(out_window, WINDOWS)


def test_briefing_doc_score_rss_headline_penalty():
    # RSS이면서 본문이 매우 짧으면 감점된다
    headline = _doc(title="some market headline", source="Reuters", sourceWeight=9,
                    date=US_DATE, path="research-inbox/rss/h.md", wordCount=30,
                    impactTags=["금리"], sectors=["Semiconductors"], marketRelevance=40)
    longer = dict(headline, content="w" * 300, wordCount=300)
    assert sel.briefing_doc_score(longer, WINDOWS) > sel.briefing_doc_score(headline, WINDOWS)


def test_market_connection_rewards_price_reaction():
    connected = _kr_supply_doc()  # 코스피·순매수·외국인 등 지수/수급 신호
    assert sel.market_connection_score(connected) > 0
    # 지수/등락/수급 신호가 전혀 없는 단발 채권 기사는 연결성 0
    junk = _doc(title="Amazon issues record-setting Canadian dollar bond deal",
                summary="corporate bond issuance", content="bond " * 60, source="Reuters",
                sourceWeight=9, date=US_DATE, path="research-inbox/rss/bond.md", url="http://r/bond",
                companies=[{"name": "Amazon", "ticker": "AMZN", "market": "US"}],
                sectors=[], impactTags=[], marketRelevance=40, wordCount=300)
    assert sel.market_connection_score(junk) == 0.0


def test_broad_keyword_junk_scored_below_connected():
    # driver 키워드(dollar/bond)만 스친 단발 기사는 실제 시장 반응과 연결된 자료보다 낮아야 한다
    junk = _doc(title="BDC tied to Dell-backed bank sells $300 million high-grade bonds",
                summary="high-grade bond sale", content="bond " * 60, source="Bloomberg",
                sourceWeight=9, date=US_DATE, path="research-inbox/rss/bdc.md", url="http://r/bdc",
                companies=[{"name": "Dell"}], sectors=[], impactTags=[],
                marketRelevance=40, wordCount=300)
    connected = _kr_supply_doc()
    assert sel.briefing_doc_score(connected, WINDOWS) > sel.briefing_doc_score(junk, WINDOWS)


def test_effective_market_relevance_caps_weak_article():
    # 신호(회사/섹터/태그)가 없는 직접 저장 article은 100을 그대로 신뢰하지 않는다
    assert sel.effective_market_relevance(_weak_article()) <= 50.0
    # 신호가 충분한 article은 그대로 유지
    rich = _doc(path="research-inbox/articles/rich.md", marketRelevance=100,
                companies=[{"name": "Nvidia"}], sectors=["Semiconductors"], impactTags=["AI"])
    assert sel.effective_market_relevance(rich) == 100.0
    # RSS는 완화 대상이 아님
    assert sel.effective_market_relevance(_kr_supply_doc()) == 60.0


# ---------------------------------------------------------------------------
# infer_drivers
# ---------------------------------------------------------------------------
def test_infer_drivers_detects_terms():
    drivers = sel.infer_drivers(_us_rate_doc())
    assert "금리" in drivers
    assert "반도체/AI" in drivers


def test_infer_drivers_empty_for_irrelevant():
    assert sel.infer_drivers(_doc(title="local lunch menu", summary="", content="")) == []


# ---------------------------------------------------------------------------
# infer_market_session_date / doc_market_bucket 날짜 보정
# ---------------------------------------------------------------------------
def test_infer_session_date_shifts_korean_ny_close_article():
    # 한국 언론 뉴욕증시 브리핑: 발행일 2026-06-09 → 미국 직전 거래일 2026-06-08
    doc = _doc(title="반도체 반등에 나스닥 0.9% 올랐지만…다우 소폭 하락 [뉴욕증시 브리핑]",
               source="한국경제", date="2026-06-09", path="research-inbox/rss/ny.md")
    assert sel.is_us_market_close_article(doc) is True
    assert sel.infer_market_session_date(doc) == "2026-06-08"


def test_infer_session_date_keeps_date_for_non_us_close():
    # 한국 시장 기사는 발행일을 그대로 시장 거래일로 사용
    doc = _doc(title="코스피, 외국인 순매수에 반등", source="연합인포맥스", date="2026-06-09")
    assert sel.is_us_market_close_article(doc) is False
    assert sel.infer_market_session_date(doc) == "2026-06-09"


def test_infer_session_date_respects_explicit_field():
    doc = _doc(title="뉴욕증시 마감", source="한국경제", date="2026-06-09",
               marketSessionDate="2026-06-05")
    assert sel.infer_market_session_date(doc) == "2026-06-05"


def test_analysis_mode_detection():
    from features.common.market_calendar import briefing_market_windows as bmw
    assert bmw("2026-06-10")["analysisMode"] == "weekday_kr_open"
    assert bmw("2026-06-13")["analysisMode"] == "weekend"   # Saturday
    assert bmw("2026-06-14")["analysisMode"] == "weekend"   # Sunday


def test_weekday_priority_mapping():
    from features.common.market_calendar import doc_analysis_priority
    # 미국 전일 정규장 자료 → primary
    assert doc_analysis_priority(_us_rate_doc(), WINDOWS) == "primary"
    # 한국 전일 정규장 자료 → background (평일 모드에서 배경 맥락)
    kr_prev = _doc(title="코스피 정규장 마감 동향", source="연합인포맥스", date=KR_DATE,
                   companies=[{"name": "삼성전자", "market": "KR"}], sectors=["Semiconductors"])
    assert doc_analysis_priority(kr_prev, WINDOWS) == "background"


def test_weekend_offsession_priority_and_score():
    from features.common.market_calendar import briefing_market_windows as bmw, doc_analysis_priority
    w = bmw("2026-06-14")  # Sunday → weekend
    assert w["weekendOrHolidayNewsMode"] is True
    assert "2026-06-13" in w["sourceDates"]  # 주말 뉴스 구간이 sourceDates에 포함
    # 주말 사이(토) 발행 뉴스 → off_session_news, 주말 모드에서 점수 가중
    weekend_doc = _doc(title="중앙은행 총재 매파적 발언", source="Reuters", date="2026-06-13",
                       content="x" * 300, wordCount=300, impactTags=["정책"])
    assert doc_analysis_priority(weekend_doc, w) == "off_session_news"
    assert sel.briefing_doc_score(weekend_doc, w) > 0
    # 최근 미국 정규장(금 6/12) 자료 → primary
    fri_us = _doc(title="nasdaq closes lower as chips slide", source="Reuters", date="2026-06-12",
                  companies=[{"name": "Nvidia", "market": "US"}], sectors=["Semiconductors"],
                  content="y" * 300, wordCount=300)
    assert doc_analysis_priority(fri_us, w) == "primary"


def test_weekend_rule_fallback_keeps_session_guardrails_out_of_reader_copy():
    from features.common.market_calendar import briefing_market_windows as bmw

    windows = bmw("2026-06-14")
    doc = _doc(
        title="해상 운송 위험과 유가 공급망 변화",
        source="Reuters",
        date="2026-06-13",
        content="해상 운송 위험이 원유 공급과 운임에 영향을 줄 수 있다는 분석입니다.",
        sectors=["Energy"],
        impactTags=["Oil"],
    )
    groups = [{"sector": "Energy", "docs": [doc], "score": 80}]
    drivers = sel.derive_market_drivers([doc], windows, limit=4)

    markdown = svc.build_prompt_markdown(
        "2026-06-14",
        "2026-06-13/2026-06-14",
        [doc],
        groups,
        [],
        market_drivers=drivers,
        market_windows=windows,
        market_scope="us",
    )

    assert "주말/휴장" not in markdown
    assert "정규장이 열리지" not in markdown
    assert "정규장 가격 반응" not in markdown
    assert "현재 반응을 단정" not in markdown
    assert "off_session_news" not in markdown


def test_reader_copy_removes_collection_failures_and_trivial_price_uncertainty():
    markdown = """# US Market Briefing — 2026.06.14

다만 해당 Financial Times 로컬 자료는 제목과 공개 요약만 확인되고 본문 수집에는 실패했다. 따라서 투자 구조, 자금 집행 시점, 회계 처리, 클라우드 사용 계약과의 연계는 입력 자료에서 확인되지 않는다. 다음 거래일 주가가 이 보도에 어떻게 반응할지도 아직 알 수 없다.

확인된 계약 규모는 공급사의 수주 가시성을 높일 수 있다. 다만 실제 매출 인식은 납품 일정과 고객 검수 조건에 달려 있다.
"""

    cleaned = svc.reader_facing_briefing_markdown(markdown)

    assert "Financial Times 로컬 자료" not in cleaned
    assert "본문 수집" not in cleaned
    assert "입력 자료" not in cleaned
    assert "주가가 이 보도에 어떻게 반응" not in cleaned
    assert "확인된 계약 규모는 공급사의 수주 가시성을 높일 수 있다." in cleaned
    assert "실제 매출 인식은 납품 일정과 고객 검수 조건에 달려 있다." in cleaned


def test_kr_current_intraday_seeded_in_context():
    from features.common.market_calendar import doc_market_bucket
    kr_doc = _doc(title="코스피 장중 외국인 순매수 전환…반도체 강세", source="연합인포맥스",
                  date=BRIEFING_DATE, path="research-inbox/rss/krc.md", url="http://r/krc",
                  companies=[{"name": "삼성전자", "market": "KR"}], sectors=["Semiconductors"],
                  content="장중" * 200, wordCount=400, impactTags=["수급"], marketRelevance=60)
    assert doc_market_bucket(kr_doc, WINDOWS) == "KR 당일 개장/장중"
    # driver/group이 비어도 한국 D 장중 자료는 컨텍스트에 시드되어야 한다
    ctx, refs = svc.build_llm_context(BRIEFING_DATE, "src", [_us_rate_doc(), kr_doc], [], market_windows=WINDOWS)
    assert "코스피 장중 외국인 순매수" in ctx
    assert "개장 후/장중 흐름을 별도 문단으로 작성" in ctx  # weekday 전용 지침
    tier = next((r.get("refTier") for r in refs if r.get("url") == "http://r/krc"), None)
    assert tier in {"kr_current_flow", "leading_company", "core_driver"}


def test_session_doc_counts():
    counts = sel.session_doc_counts([_us_rate_doc(), _kr_supply_doc()], WINDOWS)
    assert set(counts) == {"krCurrentIntradayDocCount", "usPrevRegularDocCount", "krPrevRegularDocCount"}
    assert counts["usPrevRegularDocCount"] >= 1


def test_doc_market_bucket_prefers_market_session_date():
    from features.common.market_calendar import doc_market_bucket
    # 발행일은 미국 정규장 기준일(2026-06-09)과 같지만, 실제 시장 거래일은 2026-06-08.
    # marketSessionDate를 우선하므로 'US 전일 정규장'으로 잡히면 안 된다.
    doc = _doc(title="나스닥 마감 [뉴욕증시 브리핑]", source="Reuters",
               date=WINDOWS["usRegularSessionDate"], marketSessionDate="2026-06-08")
    assert doc_market_bucket(doc, WINDOWS) != "US 전일 정규장"


# ---------------------------------------------------------------------------
# derive_market_drivers
# ---------------------------------------------------------------------------
def test_derive_market_drivers_groups_and_limits():
    docs = [_us_rate_doc(), _kr_supply_doc(), _weak_article()]
    drivers = sel.derive_market_drivers(docs, WINDOWS, limit=4)
    names = [d["driver"] for d in drivers]
    assert "금리" in names
    assert len(drivers) <= 4
    # 점수 내림차순 정렬
    scores = [d["score"] for d in drivers]
    assert scores == sorted(scores, reverse=True)
    # 각 그룹은 enriched doc(briefingDocScore/marketBucket)을 가진다
    for g in drivers:
        for d in g["docs"]:
            assert "briefingDocScore" in d and "marketBucket" in d
        assert len(g["docs"]) <= 5
        assert isinstance(g["sources"], list) and isinstance(g["markets"], list)


def test_derive_market_drivers_no_driver_doc_falls_back():
    drivers = sel.derive_market_drivers([_doc(title="unclassifiable note")], WINDOWS)
    assert any(d["driver"] == "시장 전반" for d in drivers)


def test_derive_market_drivers_limit_respected():
    docs = [_us_rate_doc(), _kr_supply_doc()]
    assert len(sel.derive_market_drivers(docs, WINDOWS, limit=1)) == 1


# ---------------------------------------------------------------------------
# build_llm_context
# ---------------------------------------------------------------------------
def test_news_documents_exclude_rss_state_file():
    docs = [
        _doc(path="research-inbox/rss/.state.json", title="RSS run state"),
        _doc(path="research-inbox/rss/reuters-2026-06-30.md", title="Market article"),
        _doc(path="research-inbox/articles/manual-note.md", title="Manual article"),
    ]

    paths = [d["path"] for d in svc.news_documents({"documents": docs})]

    assert "research-inbox/rss/.state.json" not in paths
    assert "research-inbox/rss/reuters-2026-06-30.md" in paths
    assert "research-inbox/articles/manual-note.md" in paths


def test_build_llm_context_without_drivers():
    docs = [_us_rate_doc(), _kr_supply_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": [docs[0]], "score": 80}]
    # market_drivers=None (기본값) 으로도 정상 동작해야 한다
    ctx, refs = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups, market_windows=WINDOWS)
    assert "## 후보 이슈 묶음" in ctx
    assert "## 핵심 변수 후보" not in ctx
    assert len(refs) >= 1


def test_build_llm_context_with_drivers_inserts_section():
    docs = [_us_rate_doc(), _kr_supply_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": [docs[0]], "score": 80}]
    drivers = sel.derive_market_drivers(docs, WINDOWS, limit=4)
    ctx, refs = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups,
                                      market_drivers=drivers, market_windows=WINDOWS)
    assert "## 핵심 변수 후보" in ctx
    assert "자료등급" in ctx
    # 동인 섹션이 후보 이슈 묶음보다 앞에 온다
    assert ctx.index("## 핵심 변수 후보") < ctx.index("## 후보 이슈 묶음")


def test_build_llm_context_has_numeric_guidance():
    # '시장 수치 사용 지침'이 context에 포함되어 시장 흐름 섹션 수치 앵커를 유도한다
    docs = [_us_rate_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": [docs[0]], "score": 80}]
    ctx, _ = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups, market_windows=WINDOWS)
    assert "## 시장 수치 사용 지침" in ctx


def test_build_llm_context_includes_market_memory_context():
    with TemporaryDirectory() as tmp:
        original_db = svc.MARKET_MEMORY_DB_PATH
        svc.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            save_market_state_snapshot(svc.MARKET_MEMORY_DB_PATH, {
                "headline": "AI 공급망이 시장의 중심축",
                "oneLineSummary": "AI 반도체와 전력 병목이 위험선호를 설명한다.",
                "marketRegime": "selective_growth",
                "actionPosture": "추격보다 확인된 수혜와 반대 근거를 함께 점검",
                "keyDrivers": [{"title": "AI 반도체 공급망", "summary": "HBM 수요가 유지된다.", "sourceRefs": ["rss:1"]}],
                "watchItems": ["HBM 출하 가이던스"],
                "counterEvidence": ["금리 상승은 밸류에이션 상단을 제한한다."],
                "sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}],
                "confidence": 0.82,
            })
            ctx, _ = svc.build_llm_context(BRIEFING_DATE, "src", [_us_rate_doc()], [], market_windows=WINDOWS)
            assert "## Market Memory Context" in ctx
            assert "AI 공급망이 시장의 중심축" in ctx
        finally:
            svc.MARKET_MEMORY_DB_PATH = original_db
    assert "## 한국장 시장 수치" in ctx
    assert "시장 흐름" in ctx


def _weekly_memory_snapshot(as_of, headline):
    return {
        "asOf": as_of,
        "headline": headline,
        "oneLineSummary": "주간 회고용 시장 배경",
        "marketRegime": "mixed",
        "actionPosture": "반대 근거를 함께 점검",
        "keyDrivers": [{"title": "주간 동인", "summary": "자료에 근거한 동인"}],
        "watchItems": ["다음 확인"],
        "counterEvidence": ["반대 근거"],
        "sourceRefs": [{"id": "rss:weekly", "title": "weekly source", "source": "Reuters"}],
    }


def test_weekly_context_does_not_promote_a_future_market_memory_snapshot():
    """과거 주간에는 현재(사후) Market Memory를 당시 배경으로 쓰지 않는다."""
    window = {
        "weekStart": "2026-08-24",
        "weekEnd": "2026-08-30",
        "publicationDate": "2026-09-04",
        "previewStart": "2026-08-31",
        "previewEnd": "2026-09-06",
    }
    with TemporaryDirectory() as tmp:
        original_db = svc.MARKET_MEMORY_DB_PATH
        svc.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            save_market_state_snapshot(
                svc.MARKET_MEMORY_DB_PATH,
                _weekly_memory_snapshot("2026-09-04T00:00:00Z", "사후 최신 메모리"),
            )
            ctx, _ = svc.build_llm_context(
                "2026-09-04",
                "2026-08-24~2026-08-30",
                [_us_rate_doc()],
                [],
                market_windows=WINDOWS,
                market_scope="us",
                markets=["us"],
                kind="weekly",
                weekly_window=window,
            )
        finally:
            svc.MARKET_MEMORY_DB_PATH = original_db

    assert "status: unavailable" in ctx
    assert "사후 최신 메모리" not in ctx


def test_weekly_context_accepts_a_snapshot_at_the_kst_week_end():
    """UTC 스냅샷은 KST로 변환한 뒤 주간 cutoff와 비교한다."""
    window = {
        "weekStart": "2026-08-24",
        "weekEnd": "2026-08-30",
        "publicationDate": "2026-09-04",
        "previewStart": "2026-08-31",
        "previewEnd": "2026-09-06",
    }
    with TemporaryDirectory() as tmp:
        original_db = svc.MARKET_MEMORY_DB_PATH
        svc.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            save_market_state_snapshot(
                svc.MARKET_MEMORY_DB_PATH,
                _weekly_memory_snapshot("2026-08-30T14:59:59Z", "당시 메모리"),
            )
            ctx, _ = svc.build_llm_context(
                "2026-09-04",
                "2026-08-24~2026-08-30",
                [_us_rate_doc()],
                [],
                market_windows=WINDOWS,
                market_scope="us",
                markets=["us"],
                kind="weekly",
                weekly_window=window,
            )
        finally:
            svc.MARKET_MEMORY_DB_PATH = original_db

    assert "당시 메모리" in ctx
    assert "status: unavailable" not in ctx


def test_weekly_context_does_not_treat_an_unknown_snapshot_date_as_historical(monkeypatch):
    monkeypatch.setattr(
        svc,
        "current_market_state_snapshot",
        lambda _db: {"asOf": "", "headline": "날짜불명 메모리"},
    )
    monkeypatch.setattr(svc, "render_market_memory_context", lambda _db: "SHOULD NOT USE")

    context = svc._weekly_market_memory_context({"weekEnd": "2026-08-30"})

    assert "status: unavailable" in context
    assert "날짜불명 메모리" not in context
    assert "SHOULD NOT USE" not in context


def test_weekly_context_does_not_query_db_again_after_cutoff_check(monkeypatch):
    checked = _weekly_memory_snapshot("2026-08-30T14:59:59Z", "검사한 메모리")
    calls = []

    def read_current(_db):
        calls.append(True)
        return checked

    monkeypatch.setattr(svc, "current_market_state_snapshot", read_current)
    monkeypatch.setattr(svc, "render_market_memory_context", lambda _db: "SHOULD NOT QUERY")

    context = svc._weekly_market_memory_context({"weekEnd": "2026-08-30"})

    assert calls == [True]
    assert "검사한 메모리" in context
    assert "layer: source-grounded market context" in context
    assert "SHOULD NOT QUERY" not in context


def test_build_llm_context_includes_requested_briefing_type_guidance():
    docs = [_us_rate_doc()]
    ctx, _ = svc.build_llm_context(
        BRIEFING_DATE,
        "src",
        docs,
        [],
        market_windows=WINDOWS,
        briefing_type="market_focused",
    )

    assert "브리핑 유형(briefingType): market_focused" in ctx
    assert "기존 섹션을 삭제하지" in ctx
    assert "시장 흐름" in ctx and "수급" in ctx


def test_rule_fallback_body_is_briefing_type_agnostic():
    # Briefing-type differentiation lives in the LLM context (build_llm_context,
    # covered by test_build_llm_context_includes_requested_briefing_type_guidance),
    # not in the rule-based report body. The rule fallback produces the same
    # baseline markdown regardless of type and never leaks prompt-style type
    # guidance into the report.
    docs = [_us_rate_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": docs, "score": 80}]
    default = svc.build_prompt_markdown(
        BRIEFING_DATE, "src", docs, groups, [], market_windows=WINDOWS, market_scope="us"
    )
    focused = svc.build_prompt_markdown(
        BRIEFING_DATE,
        "src",
        docs,
        groups,
        [],
        market_windows=WINDOWS,
        market_scope="us",
        briefing_type="market_focused",
    )

    assert default == focused
    assert "브리핑 유형:" not in focused
    assert "기존 섹션을 삭제하지" not in focused


def test_korea_market_data_block_formats_indices_and_flows():
    data = {
        "ok": True,
        "provider": "test",
        "date": BRIEFING_DATE,
        "indices": {
            "KOSPI": {"close": 2920.03, "changePct": 1.23, "tradingValue": 12_345_000_000_000, "asOfDate": BRIEFING_DATE},
            "KOSDAQ": {"close": 845.12, "changePct": -0.45, "tradingValue": None, "asOfDate": BRIEFING_DATE},
        },
        "investorFlows": {
            "KOSPI": {"foreign": 123_400_000_000, "institution": -50_000_000_000, "individual": -73_400_000_000}
        },
        "sectors": [{"label": "코스피 전기전자", "changePct": 2.1}],
        "fx": {"USDKRW": {"close": 1372.5, "changePct": 0.1, "asOfDate": BRIEFING_DATE, "source": "test"}},
    }
    md = svc.korea_market_data_to_markdown(data)
    assert "KOSPI: 2,920.03 / +1.23%" in md
    assert "KOSDAQ: 845.12 / -0.45%" in md
    assert "투자자별 수급(KOSPI)" in md
    ctx, _ = svc.build_llm_context(BRIEFING_DATE, "src", [_us_rate_doc()], [], market_windows=WINDOWS, korea_market_data=data)
    assert "한국장은 KOSPI가 전일 대비 X%" in ctx


def test_korea_market_data_failure_states_limit():
    md = svc.korea_market_data_to_markdown({"ok": False, "provider": "test", "warnings": ["boom"]})
    assert "한국장 시장 수치를 불러오지 못했습니다" in md
    assert "입력 자료에서 한국장 종가 등락률은 확인되지 않는다" in md


def test_refs_carry_tier_labels():
    # usedDocs/참고자료에 우선순위 라벨(refTier)이 부여되고 core_driver가 최상단에 온다
    docs = [_us_rate_doc(), _kr_supply_doc()]
    groups = [{"company": "삼성전자", "sector": "Semiconductors", "docs": [docs[1]], "score": 60}]
    drivers = sel.derive_market_drivers([docs[0]], WINDOWS, limit=4)
    _, refs = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups,
                                    market_drivers=drivers, market_windows=WINDOWS)
    tiers = [r.get("refTier") for r in refs]
    assert all(t in {"us_close", "kr_current_flow", "korea_market_data", "semiconductor", "macro_market", "core_driver", "leading_company", "market_flow", "support"} for t in tiers)
    assert refs[0]["refTier"] in {"korea_market_data", "core_driver", "macro_market", "semiconductor"}


def test_build_llm_context_old_positional_signature():
    # 기존 호출부 호환: (date, source_date, docs, groups) 위치 인자만으로 호출
    docs = [_us_rate_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": [docs[0]], "score": 80}]
    ctx, refs = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups)
    assert isinstance(ctx, str) and isinstance(refs, list)


def test_menu_only_company_is_not_promoted_into_writer_context():
    valid = _doc(
        title="현대차 주가 급락과 외국인 매도",
        summary="현대차 주가는 5.62% 하락했고 외국인은 순매도했다.",
        content="현대차 주가는 5.62% 하락했고 외국인은 순매도했다.",
        companies=[{"name": "현대차", "ticker": "005380", "market": "KR"}],
        path="research-inbox/rss/valid.md",
        url="http://r/valid",
    )
    menu = _doc(
        title="관련기사 삼성전자 추천 종목",
        summary="추천기사 삼성전자 많이 본 기사",
        content="추천기사 삼성전자 많이 본 기사",
        companies=[{"name": "삼성전자", "ticker": "005930", "market": "KR"}],
        path="research-inbox/rss/menu.md",
        url="http://r/menu",
    )
    groups = [
        {"company": "현대차", "docs": [valid], "score": 80},
        {"company": "삼성전자", "docs": [menu], "score": 79},
    ]

    ctx, refs = svc.build_llm_context(BRIEFING_DATE, "src", [valid, menu], groups, market_windows=WINDOWS)

    assert "삼성전자 추천 종목" not in ctx
    assert "http://r/menu" not in {row.get("url") for row in refs}
    assert all(row.get("writerExcerpt") for row in refs)


# ---------------------------------------------------------------------------
# 참고자료(usedDocs/sources) 우선순위
# ---------------------------------------------------------------------------
def test_refs_prioritise_market_flow_docs():
    driver_doc = _us_rate_doc()                 # 금리/매크로 핵심 변수 자료
    group_only = _kr_supply_doc()               # 한국장 수급/지수 직접 자료
    support_only = _doc(title="misc note", source="User Archive",
                        path="research-inbox/articles/misc.md", date=US_DATE,
                        content="m" * 200, wordCount=200, url="http://r/misc")
    docs = [driver_doc, group_only, support_only]
    # group_only만 그룹에 넣고, driver_doc은 market_drivers로 driver tier가 되게 한다
    groups = [{"company": "삼성전자", "sector": "Semiconductors", "docs": [group_only], "score": 60}]
    drivers = sel.derive_market_drivers([driver_doc], WINDOWS, limit=4)
    _, refs = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups,
                                    market_drivers=drivers, market_windows=WINDOWS)
    paths = [r.get("path") for r in refs]
    # 한국장 수치/수급 직접 자료와 매크로 핵심 자료가 보조 자료보다 앞에 온다
    assert paths.index(group_only["path"]) < paths.index(support_only["path"])
    assert paths.index(driver_doc["path"]) < paths.index(support_only["path"])


def test_source_lines_strip_title_brackets_for_clickable_markdown_links():
    line = svc.source_lines([{
        "title": "[뉴욕증시-1보] 스페이스X도 'AI 빚잔치' 합류",
        "source": "연합인포맥스",
        "date": "2026-06-23",
        "url": "https://example.com/news?id=1&ref=folio",
    }], limit=1)

    assert line.startswith("- [뉴욕증시-1보 스페이스X도 'AI 빚잔치' 합류](")
    assert "](https://example.com/news?id=1&ref=folio)" in line
    assert line.count("[") == 1
    assert line.count("](") == 1


# ---------------------------------------------------------------------------
# generate_llm_briefing 호환성 / fallback 안전성
# ---------------------------------------------------------------------------
def test_generate_llm_briefing_disabled_is_graceful():
    docs = [_us_rate_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": [docs[0]], "score": 80}]
    # LLM off → 예외 없이 (None, 'disabled')
    res, status = svc.generate_llm_briefing(BRIEFING_DATE, "src", docs, groups,
                                            llm_override=False, market_windows=WINDOWS)
    assert res is None and status == "disabled"
    # market_drivers 전달해도 동일하게 안전
    res2, status2 = svc.generate_llm_briefing(BRIEFING_DATE, "src", docs, groups,
                                              market_drivers=sel.derive_market_drivers(docs, WINDOWS),
                                              llm_override=False, market_windows=WINDOWS)
    assert res2 is None and status2 == "disabled"


# ---------------------------------------------------------------------------
# 시장 스냅샷 날짜 어긋남 경고
# ---------------------------------------------------------------------------
def test_snapshot_staleness_note_when_stale():
    # 스냅샷 미국 데이터가 6/8까지인데 미국 정규장 기준일은 6/9 → 경고 발생
    snap = {"ok": True, "latestUsEquityDate": "2026-06-08"}
    win = {"usRegularSessionDate": "2026-06-09"}
    note = svc.snapshot_staleness_note(snap, win)
    assert note and "2026-06-08" in note and "2026-06-09" in note


def test_snapshot_staleness_note_silent_when_fresh():
    # 스냅샷이 기준일까지 반영돼 있으면 경고 없음
    assert svc.snapshot_staleness_note(
        {"ok": True, "latestUsEquityDate": "2026-06-09"},
        {"usRegularSessionDate": "2026-06-09"},
    ) == ""
    # 데이터 없거나 실패한 스냅샷이면 경고 없음
    assert svc.snapshot_staleness_note({"ok": False}, {"usRegularSessionDate": "2026-06-09"}) == ""
    assert svc.snapshot_staleness_note({"ok": True}, {"usRegularSessionDate": "2026-06-09"}) == ""


def test_build_llm_context_includes_stale_warning():
    docs = [_us_rate_doc()]
    groups = [{"company": "Nvidia", "sector": "Semiconductors", "docs": [docs[0]], "score": 80}]
    stale_snap = {"ok": True, "latestUsEquityDate": "2026-06-08", "tickers": {}, "signals": []}
    ctx, _ = svc.build_llm_context(BRIEFING_DATE, "src", docs, groups,
                                   market_snapshot=stale_snap, market_windows=WINDOWS)
    # WINDOWS(usRegularSessionDate)가 2026-06-09 이므로 경고가 들어가야 한다
    assert "## 시장 스냅샷 날짜 주의" in ctx


def test_briefing_listing_and_previous_report_ignore_visual_sidecars():
    original_dir = svc.BRIEFINGS_DIR
    try:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc.BRIEFINGS_DIR = root
            (root / "2026-06-18.json").write_text(
                json.dumps({"date": "2026-06-18", "markdown": "# report"}),
                encoding="utf-8",
            )
            (root / "2026-06-19.visuals.json").write_text(
                json.dumps({"date": "2026-06-19", "snapshots": {}}),
                encoding="utf-8",
            )
            (root / "2026-06-19.visuals.json.gz").write_bytes(b"not-a-report")

            assert [row["date"] for row in svc.list_briefings()] == ["2026-06-18"]
            assert svc.load_prev_briefing("2026-06-20")["date"] == "2026-06-18"
    finally:
        svc.BRIEFINGS_DIR = original_dir


def test_briefing_listing_finds_every_market_not_only_us_and_kr():
    """접미사를 손으로 `us|kr`이라 적어 둔 동안 유럽·일본 브리핑은 저장은 되면서
    `GET /api/briefings`와 전일 체크포인트 조회에서만 빠졌다.
    """
    from features.daily_briefing.schema import SINGLE_MARKET_SCOPES

    original_dir = svc.BRIEFINGS_DIR
    try:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc.BRIEFINGS_DIR = root
            for scope in SINGLE_MARKET_SCOPES:
                (root / f"2026-06-18.{scope}.json").write_text(
                    json.dumps({"date": "2026-06-18", "marketScope": scope, "markdown": f"# {scope}"}),
                    encoding="utf-8",
                )
            (root / "2026-06-18.europe.visuals.json.gz").write_bytes(b"not-a-report")

            listed = svc.list_briefings()

            assert {row["marketScope"] for row in listed} == set(SINGLE_MARKET_SCOPES)
            assert svc.load_prev_briefing("2026-06-19") is not None
    finally:
        svc.BRIEFINGS_DIR = original_dir


def test_briefing_report_file_pattern_rejects_sidecars_and_unknown_markets():
    assert svc.BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-13.jp.json")
    assert svc.BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-13.europe.json")
    assert svc.BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-13.json")
    assert not svc.BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-13.visuals.json")
    assert not svc.BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-13.link.json")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
