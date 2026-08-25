"""CLI 웹 검색 — 켜졌을 때만, 지원하는 어댑터에서만, 감사와 함께."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.agent_mode.bridge import (
    WEB_SEARCH_ARGS,
    _adapter_command,
    adapter_supports_web_search,
)
from features.common.web_search_scope import audit_urls, load_source_scope


def _codex():
    return {"id": "codex", "executable": "codex"}


def test_codex_gets_the_web_search_tool_without_loosening_the_sandbox():
    """`tools.web_search`는 모델 쪽 도구다 — 셸 네트워크·파일 쓰기를 열지 않는다."""
    command = _adapter_command(_codex(), "p", web_search=True)
    assert "tools.web_search=true" in command
    assert command[command.index("--sandbox") + 1] == "read-only"


def test_web_search_is_off_unless_requested():
    assert "tools.web_search=true" not in _adapter_command(_codex(), "p", web_search=False)


def test_unsupported_adapter_is_declared_not_silently_ignored():
    """지원하지 않는 어댑터에 조용히 넘기면 '설정은 켜져 있는데 아무 일도 안 하는' 상태가 된다."""
    assert adapter_supports_web_search("codex") is True
    assert adapter_supports_web_search("claude") is True
    assert adapter_supports_web_search("antigravity") is False
    assert set(WEB_SEARCH_ARGS) == {"codex", "claude"}


def test_out_of_scope_domains_are_recorded_not_dropped():
    """CLI에서는 모델이 어디든 검색할 수 있다 — 응답 감사가 유일한 실질 통제다."""
    scope = load_source_scope()
    result = audit_urls(
        "근거: https://www.boj.or.jp/en/mopo/index.htm 그리고 https://blog.example.com/post",
        scope,
    )
    assert result["checked"] == 2
    assert any(row["tier"] == "official" for row in result["allowed"])
    assert [row["url"] for row in result["rejected"]] == ["https://blog.example.com/post"]


def test_the_directive_grants_permission_not_just_restriction():
    """허용 목록만 주면 금지문으로 읽힌다.

    실측: 도구를 켰는데 모델이 한 번도 검색하지 않았고(본문 URL 0개), 본문에 "통계·원문
    근거가 충분하지 않아 … 전이 메커니즘 중심으로 한정한다"고 적었다. 프롬프트가
    "제공된 자료를 기준으로", "목록 밖에서 찾은 내용은 넣지 않습니다"만 말하고 있었다.
    """
    from features.common.web_search_scope import load_source_scope, render_web_search_directive

    text = render_web_search_directive(load_source_scope())
    assert "검색으로 보완" in text, "쓰라는 지시가 있어야 한다"
    assert "URL" in text, "URL이 없으면 감사가 대조할 것이 없다"
    assert "과거 사례" in text and "발언" in text, "로컬에 없는 것을 짚어 줘야 한다"


def test_axis_pass_receives_the_directive():
    """과거 사례를 실제로 파는 곳은 축별 분석이다."""
    from features.topic_report.axis_analysis import build_axis_briefs

    seen: list[str] = []

    def call(prompt, context):
        seen.append(context)
        return '{"findings": ["x"]}'

    build_axis_briefs(
        {"analysisAxes": [{"key": "a", "label": "2021~2022 인플레이션"}], "topic": "질문"},
        [],
        run_call=call,
        web_directive="## 웹 검색 사용\n보완하세요.",
    )
    assert seen and "## 웹 검색 사용" in seen[0]


def test_web_scope_is_resolved_before_the_axis_pass():
    """축 패스는 예외를 삼킨다 — 그 안에서 이름을 처음 쓰면 NameError가 보이지 않는다.

    실측: `source_scope`를 축 호출(122행)에서 쓰면서 정의를 170행에 뒀더니, NameError가
    `except Exception`에 삼켜져 축별 분석이 통째로 건너뛰어졌다.
    """
    import inspect

    from features.topic_report.approved_generation import build_approved_report

    source = inspect.getsource(build_approved_report)
    assert source.index("source_scope = load_source_scope(") < source.index("build_axis_briefs(")
    assert source.index("web_directive = (") < source.index("build_axis_briefs(")


def test_engine_failure_and_contract_failure_get_different_codes():
    from features.common.shared_jobs_schema import ErrorCode
    from features.topic_report.approved_jobs import _failure_code
    from features.topic_report.deep_pipeline import DeepResearchGenerationError

    assert _failure_code(DeepResearchGenerationError("deep_initial_engine_failed_without_candidate")) is ErrorCode.ADAPTER_FAILED
    assert _failure_code(DeepResearchGenerationError("deep_initial_candidate_invalid")) is ErrorCode.VALIDATION_FAILED
    assert _failure_code(ValueError("boom")) is ErrorCode.INTERNAL_ERROR


def test_the_pack_wrapper_does_not_contradict_the_web_directive():
    """겉 프롬프트가 "팩만 쓰라"고 하면 팩 안의 웹 허가는 무효가 된다.

    실측: 딥 리서치 본문에 URL이 하나도 없었는데(감사 checked=0), 같은 어댑터에 같은
    허가문을 겉 프롬프트로 주면 정확한 사실과 URL을 가져왔다.
    """
    import inspect

    from features.topic_report.approved_generation_support import attempt_cli

    source = inspect.getsource(attempt_cli)
    assert "웹 검색 사용" in source, "웹이 켜졌을 때의 겉 지시가 있어야 한다"
    assert "must cite the URL" in source
    # 웹이 꺼졌을 때의 기존 경계 문구는 그대로 남는다.
    assert "Use only its approved plan, evidence, and context boundaries." in source


def test_axis_brief_carries_web_source_urls():
    """URL이 없으면 감사도 인용도 없다."""
    from features.topic_report.axis_analysis import build_axis_briefs, render_axis_briefs

    briefs = build_axis_briefs(
        {"analysisAxes": [{"key": "a", "label": "축"}], "topic": "q"},
        [],
        run_call=lambda p, c: '{"findings": ["f"], "webSources": ["https://www.boj.or.jp/x", "notaurl"]}',
    )
    assert briefs[0]["webSources"] == ["https://www.boj.or.jp/x"], "URL이 아닌 것은 버린다"
    assert "웹 출처" in render_axis_briefs(briefs)


def test_thin_axes_are_told_to_search_not_merely_allowed():
    """허가만으로는 검색하지 않는다.

    실측: 도구·겉 프롬프트·팩 허가를 모두 갖춘 실행에서 감사 URL 9건이 **전부 로컬 근거**
    였고 웹에서 새로 온 것은 0건이었다. 팩에 근거가 많으면 모델은 스스로 충분하다고
    판단한다 — 몇 건뿐인지 숫자로 알려 주고 의무를 줘야 한다.
    """
    from features.topic_report.axis_analysis import build_axis_briefs

    seen: list[str] = []
    plan = {
        "analysisAxes": [{"key": "a", "label": "2021~2022 인플레이션"}, {"key": "b", "label": "최근 금리"}],
        "topic": "q",
    }
    evidence = [
        {"id": f"ev_{i:03d}", "axisKey": "b", "relevance": 0.5, "title": "t", "source": "s",
         "date": "2026-08-01", "summary": "x", "path": ""}
        for i in range(5)
    ]

    def call(prompt, context):
        seen.append(context)
        return '{"findings": ["f"]}'

    build_axis_briefs(plan, evidence, run_call=call, web_directive="## 웹 검색 사용")
    assert "반드시 보완" in seen[0], "근거가 얇은 축에는 의무를 준다"
    assert "반드시 보완" not in seen[1], "근거가 충분한 축까지 강제하지 않는다"


def test_no_obligation_when_web_search_is_off():
    from features.topic_report.axis_analysis import build_axis_briefs

    seen: list[str] = []
    build_axis_briefs(
        {"analysisAxes": [{"key": "a", "label": "축"}], "topic": "q"},
        [],
        run_call=lambda p, c: (seen.append(c), '{"findings": ["f"]}')[1],
        web_directive="",
    )
    assert "반드시 보완" not in seen[0]


def test_rejected_candidates_leave_their_defect_codes():
    """거부된 후보는 비공개 pack 정리로 사라진다 — 이유는 잡에 남아야 한다.

    실측으로 `validation_failed` 한 줄만 남아 두 번 연속 진단에 실패했다. 담는 것은
    결함 코드뿐이다(본문·프롬프트 조각은 담지 않는다).
    """
    from features.topic_report.approved_jobs import _failure_detail
    from features.topic_report.deep_pipeline import DeepResearchGenerationError

    detail = _failure_detail(
        DeepResearchGenerationError("deep_initial_candidate_invalid", ["required_sections_missing"])
    )
    assert "deep_initial_candidate_invalid" in detail
    assert "required_sections_missing" in detail
    assert len(detail) <= 200
    assert _failure_detail(ValueError("boom")) == "", "딥 오류가 아니면 아무것도 남기지 않는다"


def test_blocking_defects_travel_with_the_error():
    from features.topic_report.deep_pipeline import DeepResearchGenerationError

    error = DeepResearchGenerationError("x", ["a", "b"])
    assert error.defects == ["a", "b"]
    assert DeepResearchGenerationError("x").defects == []
