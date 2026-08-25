"""리서치 에디터 계약 — 전달 방식만 바꾸고, 사실은 못 바꾼다.

금지를 프롬프트로만 적어 두면 지켜지지 않는다는 것을 이 프로젝트에서 반복 확인했다.
여기서는 그 금지가 **코드로 집행되는지**를 검사한다.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import editor as E

_FILLER = "기대 심리가 지표에 반영되는 경로를 단계로 풀어 설명한 문장이다. " * 12


def _report(*, counter_body: str | None = None, extra: str = "") -> str:
    counter = counter_body if counter_body is not None else (
        "성장 기대가 주도했다는 반대 해석도 있다. " + _FILLER
        + "\n\n<!-- folio-source-ids: ev_003, macro_DGS10 -->"
    )
    return "\n\n".join([
        "# 기대 심리 리포트",
        "## Executive Summary",
        "핵심은 금리 수준이 아니라 기대의 재평가다. CPI는 2021년 12월까지 7.0% 올랐다. " + _FILLER,
        "<!-- folio-source-ids: ev_001, web_001 -->",
        "## 장기금리",
        "10년물은 4.35% 수준이다. " + _FILLER + extra,
        "<!-- folio-source-ids: ev_002 -->",
        "## 반론과 리스크",
        counter,
        "## 결론",
        "현재로서는 기대 재평가 쪽이 설득력 있다. " + _FILLER,
        "<!-- folio-source-ids: ev_001 -->",
    ])


def _call(text):
    return lambda _prompt, _context: text


# --------------------------------------------------------------- 금지의 집행

def test_new_numbers_are_rejected():
    # 에디터는 사실을 만들 수 없다. 초안에 없던 수치는 지어낸 것이다.
    edited = _report().replace("10년물은 4.35% 수준이다.", "10년물은 4.35%, 30년물은 4.92% 수준이다.")
    violations = E.check_edit(_report(), edited)
    assert any(v.startswith("editor_added_numbers") and "4.92" in v for v in violations)

    result = E.edit_report(_report(), run_call=_call(edited))
    assert result["status"] == "rejected"
    assert result["markdown"] == _report()  # 초안이 그대로 남는다


def test_reformatting_an_existing_number_is_allowed():
    # 7.0% → 7%처럼 표기만 바꾼 것까지 막으면 정당한 편집이 통째로 버려진다.
    edited = _report().replace("7.0% 올랐다", "7% 올랐다")
    assert E.check_edit(_report(), edited) == []


def test_dropping_or_inventing_source_tags_is_rejected():
    original = _report()
    without = original.replace("<!-- folio-source-ids: ev_002 -->", "")
    assert any(v.startswith("editor_dropped_source_ids") for v in E.check_edit(original, without))

    invented = original.replace("<!-- folio-source-ids: ev_002 -->", "<!-- folio-source-ids: ev_002, ev_777 -->")
    assert "editor_added_source_ids" in E.check_edit(original, invented)


def test_weakening_the_counterargument_is_rejected():
    # 반론은 확증편향 방지의 집행 장치다(§5 원칙 3). 다듬다 줄이면 장치가 약해진다.
    original = _report()
    trimmed = _report(counter_body="반대 해석도 있다.\n\n<!-- folio-source-ids: ev_003, macro_DGS10 -->")
    assert "editor_weakened_counterevidence" in E.check_edit(original, trimmed)

    fewer_tags = _report(counter_body="성장 기대가 주도했다는 반대 해석도 있다. " + _FILLER
                         + "\n\n<!-- folio-source-ids: ev_003 -->")
    assert "editor_weakened_counterevidence" in E.check_edit(original, fewer_tags)


def test_changing_the_section_shape_is_rejected():
    original = _report()
    renamed = original.replace("## 장기금리", "## 금리 이야기")
    assert "editor_changed_sections" in E.check_edit(original, renamed)

    merged = original.replace("## 결론\n", "")
    assert "editor_changed_sections" in E.check_edit(original, merged)


def test_shortening_the_report_is_rejected():
    # 압축은 caveat를 모으는 일이지 분량을 줄이는 일이 아니다.
    original = _report(extra=_FILLER * 3)
    assert "editor_shortened_report" in E.check_edit(original, _report())


def test_empty_output_is_rejected():
    assert E.check_edit(_report(), "") == ["editor_empty_output"]


# --------------------------------------------------------------- 정상 경로

def test_a_clean_edit_is_applied():
    original = _report()
    # 결론을 앞세우고 유보 표현을 걷어낸다 — 숫자·ID·섹션·분량은 그대로.
    edited = original.replace(
        "핵심은 금리 수준이 아니라 기대의 재평가다.",
        "현재로서는 기대의 재평가가 핵심이다. 금리 수준 자체가 아니다.",
    )
    result = E.edit_report(original, run_call=_call(edited))
    assert result["status"] == "applied"
    assert "현재로서는 기대의 재평가가 핵심이다" in result["markdown"]
    assert result["charsAfter"] >= result["charsBefore"] * E.MIN_LENGTH_RATIO


def test_code_fences_are_stripped():
    original = _report()
    result = E.edit_report(original, run_call=_call("```markdown\n" + original + "\n```"))
    assert result["status"] == "applied"
    assert not result["markdown"].startswith("```")


def test_engine_failure_keeps_the_draft():
    # 편집 실패가 수 분짜리 실행을 버리지 않는다.
    def boom(_prompt, _context):
        raise RuntimeError("engine down")

    result = E.edit_report(_report(), run_call=boom)
    assert result["status"] == "unavailable"
    assert result["markdown"] == _report()


def test_context_carries_the_thesis_but_not_permission_to_change_it():
    context = E._context(_report(), {"primaryThesis": {"claim": "기대 재평가가 핵심"}}, {"결론": 900})
    assert "기대 재평가가 핵심" in context
    assert "바꾸지 마라" in context


def test_prompt_forbids_the_five_things_the_checker_enforces():
    # 프롬프트와 검사기가 어긋나면 모델은 검사기가 막는 줄 모르고 계속 버려진다.
    for phrase in ("새 숫자", "새 근거 ID", "반대 근거", "섹션 제목", "분량"):
        assert phrase in E.PROMPT


def test_summary_shape():
    assert E.editor_summary({}) == {
        "status": "skipped", "violations": [], "charsBefore": 0, "charsAfter": 0,
        "hedgeBefore": 0.0, "hedgeAfter": 0.0,
    }
    assert E.editor_summary({"status": "rejected", "violations": ["editor_added_source_ids"]})["status"] == "rejected"


def test_expanding_the_report_is_rejected():
    # 실측: 초안 5,569자가 편집본 13,415자로 나왔다(+141%). 새 수치도 새 ID도 없어
    # 기존 검사를 전부 통과했지만, 근거 없는 산문이 채워져 unlinked_section 7건이 남았다.
    # 분석가가 사실을 정하고 에디터가 전달 방식을 정한다는 경계가 무너진 것이다.
    original = _report()
    padded = _report(extra=" 이 문장은 근거 없이 덧붙인 설명이다. " * 120)
    assert any(v.startswith("editor_expanded_report") for v in E.check_edit(original, padded))

    result = E.edit_report(original, run_call=_call(padded))
    assert result["status"] == "rejected"
    assert result["markdown"] == original


def test_modest_growth_is_still_allowed():
    # 얇은 섹션을 제대로 쓰는 것까지 막으면 에디터가 할 일이 없다(실측 정상 편집은 +1~6%).
    original = _report()
    grown = _report(extra=" 결론을 앞세워 다시 쓴 문장이다. " * 8)
    assert E.check_edit(original, grown) == []


def test_a_rejected_edit_still_records_what_it_measured():
    # 0/0으로 남으면 무엇이 거부됐는지 기록이 말하지 못한다(실측: 실제 실행에서 그랬다).
    original = _report()
    result = E.edit_report(original, run_call=_call(_report(extra=" 덧붙인 문장이다. " * 120)))
    assert result["status"] == "rejected"
    assert result["charsBefore"] > 0 and result["charsAfter"] > result["charsBefore"]
    assert E.editor_summary(result)["charsAfter"] > 0


def test_the_editor_is_not_told_to_fill_section_budgets():
    # 예산을 주면 하한까지 채우려 하고, 그러면 확장 상한에 걸려 통째로 버려진다.
    context = E._context(_report(), None, {"결론": 900})
    assert "900" not in context
    assert "당신의 일이 아닙니다" in context


# --------------------------------------------------------- 유보 압축은 과제로 준다

def test_the_hedge_task_is_a_number_not_a_principle():
    # 원칙만 준 세 번의 편집에서 유보가 한 번도 줄지 않았다(천자당 1.83 → 그대로,
    # 2.58, 3.42). 웹 검색에서 확인한 것과 같은 패턴이다 — 허가로는 안 움직이고
    # 과제를 주면 한다.
    hedged = _report(counter_body="반대 해석도 있을 수 있다. " * 40
                     + "\n\n<!-- folio-source-ids: ev_003, macro_DGS10 -->")
    task = E.hedge_target(hedged)
    assert "회 이하로 줄이세요" in task
    assert "수 있다" in task  # 어느 표현이 쏠렸는지 짚는다
    assert "없애는 것이 아니라 모으는 것" in task  # 불확실성을 지우라는 말이 아니다


def test_no_task_when_the_draft_is_already_decisive():
    # 이미 낮으면 과제를 주지 않는다. 줄일 것이 없는데 줄이라고 하면 근거를 지운다.
    assert E.hedge_target("## A\n\n" + "금리는 4.35% 수준에서 움직였다. " * 40) == ""
    assert E.hedge_target("") == ""


def test_the_task_rides_along_in_the_editor_context():
    hedged = _report(counter_body="그럴 수 있다. " * 60 + "\n\n<!-- folio-source-ids: ev_003, macro_DGS10 -->")
    assert "유보 표현 줄이기" in E._context(hedged, None, None)

def test_the_summary_records_whether_hedges_actually_fell():
    # 초안이 원래 낮았던 것과 에디터가 줄인 것을 구분하려면 둘 다 재야 한다.
    hedged = _report(counter_body="그럴 수 있다. " * 60 + "\n\n<!-- folio-source-ids: ev_003, macro_DGS10 -->")
    result = E.edit_report(hedged, run_call=_call(hedged))
    assert result["status"] == "applied"
    assert result["hedgeBefore"] > 0 and result["hedgeAfter"] == result["hedgeBefore"]
