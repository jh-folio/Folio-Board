"""연도가 갈린 뺄셈, UTC 날짜로 묶인 보고서 id, 실제와 어긋난 웹 검색 기록."""
from __future__ import annotations

from features.company_analysis import financial_engine, generation_service, report_rules
from features.company_analysis.service import analysis_report_id


def _annual(metric: str, years: list[str]) -> dict:
    return {
        "metric": metric,
        "concept": metric,
        "annual": [{"end": f"{year}-12-31", "val": float(year)} for year in years],
    }


def test_fcf_series_never_subtracts_across_years():
    """CFO와 CapEx의 보고 연도가 갈리면 순서대로 빼서는 안 된다."""
    summary = {
        "ok": True,
        "rows": [
            _annual("Operating Cash Flow", ["2025", "2024"]),
            _annual("Capital Expenditure", ["2022", "2021"]),
        ],
    }
    assert financial_engine.fcf_series(summary) == []


def test_fcf_series_pairs_the_same_year():
    summary = {
        "ok": True,
        "rows": [
            {"metric": "Operating Cash Flow", "annual": [
                {"end": "2025-12-31", "val": 100.0}, {"end": "2024-12-31", "val": 80.0}]},
            {"metric": "Capital Expenditure", "annual": [
                {"end": "2025-12-31", "val": 30.0}, {"end": "2023-12-31", "val": 5.0}]},
        ],
    }
    # 2025만 겹친다. 2024 CFO에서 2023 CapEx를 빼지 않는다.
    assert financial_engine.fcf_series(summary) == [70.0]


def test_the_rule_report_fallback_only_subtracts_matching_years():
    disjoint = {
        "ok": True,
        "rows": [
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100.0}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2022-12-31", "val": 30.0}]},
            {"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1000.0}]},
        ],
    }
    text = report_rules.build_valuation_metrics({"ticker": "X", "name": "X"}, disjoint, {"ok": False})
    # 100 - 30 = 70을 만들어내면 안 된다. 어느 해의 FCF도 아니다.
    assert "FCF 확인 필요" in text

    aligned = {
        "ok": True,
        "rows": [
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100.0}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2025-12-31", "val": 30.0}]},
            {"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1000.0}]},
        ],
    }
    value, year = report_rules._latest_metric_entry(aligned, None, "Operating Cash Flow")
    assert (value, year) == (100.0, "2025")
    assert "FCF 확인 필요" not in report_rules.build_valuation_metrics(
        {"ticker": "X", "name": "X"}, aligned, {"ok": False}
    )


def test_the_quality_table_fallback_only_subtracts_matching_years():
    """밸류에이션 표가 '확인 필요'인 입력에서 품질 표만 FCF 판단을 내면 안 된다."""
    disjoint = {
        "ok": True,
        "rows": [
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100.0}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2022-12-31", "val": 30.0}]},
            {"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1000.0}]},
        ],
    }
    text = report_rules.build_financial_quality_analysis(disjoint, None)
    fcf_line = [line for line in text.splitlines() if line.startswith("| 자유현금흐름 ")]
    assert fcf_line, text
    # 100 - 30 = 70을 만들면 FCF 마진 7.0%가 나온다. 어느 해의 FCF도 아니다.
    assert "7.0%" not in text
    assert "| 확인 필요 |" in fcf_line[0]

    aligned = {
        "ok": True,
        "rows": [
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100.0}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2025-12-31", "val": 30.0}]},
            {"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1000.0}]},
        ],
    }
    assert "7.0%" in report_rules.build_financial_quality_analysis(aligned, None)


def test_derived_financials_leaves_fcf_missing_when_years_disjoint():
    disjoint = {
        "ok": True,
        "rows": [
            _annual("Operating Cash Flow", ["2025"]),
            _annual("Capital Expenditure", ["2022"]),
        ],
    }
    derived = financial_engine.derived_financials(disjoint)
    assert derived["fcf"] is None
    assert derived["fcfMargin"] is None

    aligned = {
        "ok": True,
        "rows": [
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100.0}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2025-12-31", "val": 30.0}]},
        ],
    }
    assert financial_engine.derived_financials(aligned)["fcf"] == 70.0


def test_two_generation_times_in_one_kst_day_share_one_report_id():
    """UTC 23:00과 다음날 02:00은 같은 KST 날짜(다음날)다."""
    company = {"ticker": "HWM"}
    first = analysis_report_id(company, "2026-08-14T23:00:00+00:00")
    second = analysis_report_id(company, "2026-08-15T02:00:00+00:00")
    assert first == second


def test_different_kst_days_still_get_different_ids():
    company = {"ticker": "HWM"}
    assert analysis_report_id(company, "2026-08-14T10:00:00+00:00") != analysis_report_id(
        company, "2026-08-15T10:00:00+00:00"
    )


_RUNTIME = {
    "load_index": lambda: {},
    "search_documents": lambda *a, **k: [],
    "infer_requested_company": lambda *a, **k: {"name": "Howmet", "ticker": "HWM"},
    "build_company_analysis_materials": lambda *a, **k: {"selectedDocs": [], "secFacts": {}, "rankedFiling": {}},
    "build_company_analysis_charts": lambda *a, **k: [],
    "generate_llm_company_analysis": lambda *a, **k: (None, "disabled"),
    "build_rule_report": lambda *a, **k: "# 규칙 기반 보고서",
    "company_analysis_sources": lambda *a, **k: [],
    "selected_cli_config": lambda *a, **k: {"provider": "", "model": ""},
    "use_web_search_for_analysis": lambda: True,
}


def _install_fake_gaps(monkeypatch, recorded: dict):
    def fake_gaps(_materials, web_search_allowed=False):
        recorded["allowed"] = web_search_allowed
        return {"gaps": [], "attempts": ["official_web_search"] if web_search_allowed else []}

    monkeypatch.setattr(generation_service, "resolve_company_analysis_gaps", fake_gaps)
    monkeypatch.setattr(generation_service, "decorate_candidate", lambda _kind, report, **_kw: report)


def test_data_gaps_record_the_web_search_that_actually_ran(monkeypatch):
    """설정이 켜져 있어도 LLM이 웹 검색을 썼을 때만 시도로 남긴다."""
    recorded: dict = {}
    _install_fake_gaps(monkeypatch, recorded)

    used_web = {
        **_RUNTIME,
        "generate_llm_company_analysis": lambda *a, **k: (
            {"markdown": "# 보고서", "webSearch": True, "usedDocs": []}, "ok"),
    }
    report = generation_service.analyze_company("HWM", web_search_override=None, runtime=used_web)
    assert recorded["allowed"] is True
    assert "official_web_search" in report["dataGaps"]["attempts"]


def test_rule_fallback_does_not_claim_a_web_search_attempt(monkeypatch):
    """CLI 모드·LLM 실패·자료 없음은 규칙 fallback으로 끝난다. 웹 검색은 돌지 않았다."""
    recorded: dict = {}
    _install_fake_gaps(monkeypatch, recorded)

    # 설정은 켜져 있지만(_RUNTIME) LLM 결과가 없다.
    report = generation_service.analyze_company("HWM", web_search_override=None, runtime=_RUNTIME)
    assert recorded["allowed"] is False
    assert "official_web_search" not in report["dataGaps"]["attempts"]

    # LLM이 돌았어도 웹 검색을 쓰지 않았으면 마찬가지다.
    no_web = {
        **_RUNTIME,
        "generate_llm_company_analysis": lambda *a, **k: (
            {"markdown": "# 보고서", "webSearch": False, "usedDocs": []}, "ok"),
    }
    generation_service.analyze_company("HWM", web_search_override=None, runtime=no_web)
    assert recorded["allowed"] is False


# --------------------------------------------- 초안 가드 / 웹 조회 배선

def _draft(*, drop=()):
    from features.company_analysis.style import REQUIRED_SECTION_HEADINGS

    names = [n for n in REQUIRED_SECTION_HEADINGS if n not in drop]
    return "\n\n".join(f"## {n}\n\n본문입니다." for n in names)


def test_a_draft_missing_sections_is_rewritten_once(monkeypatch):
    # 실측 4건 중 3건이 계약과 다른 제목을 썼고 두 섹션이 통째로 빠졌다. 보수 패스는
    # 섹션 3개를 손볼 뿐이라 골격이 어긋난 초안을 되살리지 못한다.
    seen: list[str] = []

    def llm(*_args, **kwargs):
        seen.append(str(kwargs.get("context") or ""))
        broken = len(seen) == 1
        return ({"markdown": _draft(drop=("어떻게 접근할까",)) if broken else _draft(),
                 "usedDocs": [], "webSearch": False}, "ok")

    runtime = {**_RUNTIME, "generate_llm_company_analysis": llm, "use_web_search_for_analysis": lambda: False}
    report = generation_service.analyze_company("HWM", runtime=runtime)

    guard = report["draftGuard"]
    assert guard["missing"] == ["어떻게 접근할까"]
    assert guard["retried"] is True and guard["outcome"] == "retry_better"
    assert len(seen) == 2
    assert "다시 작성 요청" not in seen[0] and "다시 작성 요청" in seen[1]
    assert "어떻게 접근할까" in report["markdown"]


def test_a_healthy_draft_is_not_rewritten():
    calls = {"n": 0}

    def llm(*_args, **_kwargs):
        calls["n"] += 1
        return ({"markdown": _draft(), "usedDocs": [], "webSearch": False}, "ok")

    runtime = {**_RUNTIME, "generate_llm_company_analysis": llm, "use_web_search_for_analysis": lambda: False}
    report = generation_service.analyze_company("HWM", runtime=runtime)
    assert calls["n"] == 1
    assert report["draftGuard"] == {"missing": [], "retried": False, "outcome": ""}


def test_a_worse_retry_keeps_the_first_draft():
    # 나쁜 초안이라도 없는 것보다 낫다.
    drafts = [_draft(drop=("어떻게 접근할까",)), _draft(drop=("어떻게 접근할까", "밸류에이션"))]

    def llm(*_args, **_kwargs):
        return ({"markdown": drafts.pop(0), "usedDocs": [], "webSearch": False}, "ok")

    runtime = {**_RUNTIME, "generate_llm_company_analysis": llm, "use_web_search_for_analysis": lambda: False}
    report = generation_service.analyze_company("HWM", runtime=runtime)
    assert report["draftGuard"]["outcome"] == "retry_no_gain"
    assert "밸류에이션" in report["markdown"]


def test_web_lookup_feeds_the_ledger_and_the_context():
    import json

    payload = {"facts": [{"statement": "2026 2분기 매출 $8.7B", "url": "https://investor.x/q2"}],
               "quotes": [{"who": "Tim Archer, CEO", "when": "2026-08", "what": "수요 견조", "url": "https://investor.x/call"}]}
    seen: list[str] = []

    def llm(*_args, **kwargs):
        seen.append(str(kwargs.get("context") or ""))
        return ({"markdown": _draft(), "usedDocs": [], "webSearch": True}, "ok")

    runtime = {
        **_RUNTIME,
        "generate_llm_company_analysis": llm,
        "use_web_search_for_analysis": lambda: True,
        "configured_lookup_call": lambda **_k: (lambda _p, _c: json.dumps(payload, ensure_ascii=False)),
    }
    report = generation_service.analyze_company("HWM", runtime=runtime)

    # 찾아온 사실이 원장에 등재돼야 본문이 인용할 자격을 갖는다.
    web_ids = [row["sourceId"] for row in report["sourceLedger"] if str(row["sourceId"]).startswith("web_")]
    assert web_ids == ["web_001", "web_002"]
    assert "[web_001]" in seen[0]
    assert report["webLookup"]["speakerSources"] == [{"sourceId": "web_002", "role": "CEO", "name": "Archer"}]
