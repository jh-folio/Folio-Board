"""Evidence Pack / Source Ledger 단위 테스트.

    py -3 features/topic_report/tests/test_evidence_pack.py
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import evidence as E
from features.topic_report import planner as P
from features.topic_report.source_ledger import build_source_ledger

_DOCS = [
    {"title": "BOJ raise rate, yen surge and strong recovery", "summary": "엔화 강세 회복 확대", "source": "Reuters", "date": "2026-06-10", "url": "http://a/1"},
    {"title": "Korean banks risk and weak pressure", "summary": "약세 우려 부담 둔화 하락", "source": "WSJ", "date": "2026-06-09", "url": "http://a/2"},
    {"title": "Yield table", "summary": "10Y 4.5% 2Y 4.1% spread 0.4% CPI 2.9% rate 5.25%", "source": "FRED", "date": "2026-06-08", "url": "http://a/3"},
    {"title": "Old context piece", "summary": "과거 배경", "source": "FT", "date": "2025-12-01", "url": "http://a/4"},
]


def _search_docs(queries, limit=12):
    return list(_DOCS)


def _search_memories(keywords, limit=20):
    return [{"title": "금리·달러 유동성", "date": "2026-06-01"}]


def _plan():
    return P.build_rule_plan("일본 금리 인상이 원화와 한국 금융주에 미치는 영향")


def test_evidence_role_enum_and_rules():
    assert E.classify_evidence_role("surge gain strong growth 개선 회복", 3) == "supporting"
    assert E.classify_evidence_role("risk weak 우려 부담 하락", 3) == "challenging"
    assert E.classify_evidence_role("4.5% 4.1% 0.4% 2.9% 5.25% spread", 3) == "data_point"
    assert E.classify_evidence_role("배경 설명", 120) == "background"
    assert E.classify_evidence_role("중립적 내용", 3) == "neutral"


def test_pack_axis_coverage_and_dedupe():
    pack = E.build_evidence_pack(_plan(), search_docs=_search_docs, search_memories=_search_memories, date="2026-06-11")
    assert pack["totalDocs"] == len(_DOCS), "동일 URL 중복은 한 번만 들어가야 함"
    assert pack["axisCoverage"], "축별 커버리지 계산"
    first_axis = next(iter(pack["axisCoverage"].values()))
    assert {"label", "count", "level"} <= set(first_axis)
    assert all(item["evidenceRole"] in {"supporting", "challenging", "neutral", "background", "data_point"} for item in pack["items"])
    assert all(item["freshness"] in {"recent", "current", "dated", "stale"} for item in pack["items"])
    assert pack["marketMemory"], "메모리 검색 결과 포함"


def test_pack_handles_search_failure():
    def broken(queries, limit=12):
        raise RuntimeError("index down")
    pack = E.build_evidence_pack(_plan(), search_docs=broken, search_memories=_search_memories, date="2026-06-11")
    assert pack["totalDocs"] == 0
    assert pack["dataGaps"], "검색 실패 시 데이터 갭으로 기록"


def test_admission_normalizes_url_and_preserves_exact_document_id():
    docs = [
        {
            "id": "doc-first",
            "title": "First",
            "source": "Reuters",
            "date": "2026-06-10",
            "url": "https://EXAMPLE.com/story/?utm_source=rss",
            "path": "research-inbox/rss/first.md",
        },
        {
            "id": "doc-duplicate",
            "title": "Duplicate URL",
            "source": "Reuters",
            "date": "2026-06-10",
            "url": "https://example.com/story",
            "path": "research-inbox/rss/duplicate.md",
        },
        {
            "id": "doc-path",
            "title": "Path fallback",
            "source": "Local",
            "date": "2026-06-10",
            "url": "",
            "path": r"D:\\workspace\\research-inbox\\articles\\path.md",
        },
    ]

    pack = E.build_evidence_pack(
        _plan(),
        search_docs=lambda _queries, limit=12: docs[:limit],
        search_memories=lambda _keywords, limit=20: [],
        date="2026-06-11",
    )

    assert [item["documentId"] for item in pack["items"]] == ["doc-first", "doc-path"]
    assert pack["totalDocs"] == 2
    assert sum(pack["roleCounts"].values()) == 2


def test_source_ledger_dedupes_and_ids():
    pack = E.build_evidence_pack(_plan(), search_docs=_search_docs, search_memories=_search_memories, date="2026-06-11")
    ledger = build_source_ledger(pack["items"] + pack["items"])  # 중복 입력
    assert len(ledger) == len(_DOCS)
    assert ledger[0]["sourceId"] == "src_001"
    assert all(row["evidenceRole"] for row in ledger)
    assert all("usedInSections" in row for row in ledger)


def test_deep_research_pack_records_question_coverage_and_rounds():
    plan = P.apply_deep_research_plan(_plan())
    pack = E.build_evidence_pack(
        plan,
        search_docs=_search_docs,
        search_memories=_search_memories,
        date="2026-06-11",
        deep_research=True,
    )

    assert pack["deepResearch"]["enabled"] is True
    assert pack["deepResearch"]["maxRounds"] == 2
    assert pack["questionCoverage"], "하위 질문별 커버리지가 있어야 함"
    assert all({"question", "count", "level", "round"} <= set(row) for row in pack["questionCoverage"].values())
    assert any(item.get("researchQuestionId") for item in pack["items"])
    assert {item.get("researchRound") for item in pack["items"] if item.get("researchRound")} <= {1, 2}
    assert pack["deepResearch"]["rounds"]
    assert pack["deepResearch"]["round2Reason"] in {
        "executed_for_coverage_gaps", "skipped_sufficient_round_1", "skipped_no_approved_round_2_questions"
    }


def test_round_two_is_skipped_when_round_one_has_coverage_and_challenging_evidence():
    base = _plan()
    base["analysisAxes"] = base["analysisAxes"][:1]
    plan = P.apply_deep_research_plan(base)
    unique = 0

    def search(_queries, limit=12):
        nonlocal unique
        unique += 1
        return [
            {
                "id": f"doc-{unique}-{index}",
                "title": f"risk weak pressure evidence {unique} {index}",
                "summary": "리스크 약세 우려 부담 하락 압력",
                "source": "Reuters",
                "date": "2026-06-10",
                "url": f"https://example.com/{unique}/{index}",
            }
            for index in range(4)
        ]

    pack = E.build_evidence_pack(
        plan,
        search_docs=search,
        search_memories=lambda *_args, **_kwargs: [],
        date="2026-06-11",
        deep_research=True,
    )
    assert pack["deepResearch"]["round2Reason"] == "skipped_sufficient_round_1"
    assert all(item.get("researchRound") != 2 for item in pack["items"])


def test_source_ledger_keeps_deep_research_metadata():
    plan = P.apply_deep_research_plan(_plan())
    pack = E.build_evidence_pack(
        plan,
        search_docs=_search_docs,
        search_memories=_search_memories,
        date="2026-06-11",
        deep_research=True,
    )
    ledger = build_source_ledger(pack["items"])

    assert any(row.get("researchQuestionId") for row in ledger)
    assert any(row.get("researchRound") for row in ledger)


def test_summary_compact():
    pack = E.build_evidence_pack(_plan(), search_docs=_search_docs, search_memories=_search_memories, date="2026-06-11")
    summary = E.evidence_pack_summary(pack)
    assert summary["totalDocs"] == pack["totalDocs"]
    assert "items" not in summary, "요약에는 원본 아이템 전체를 넣지 않는다"


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
