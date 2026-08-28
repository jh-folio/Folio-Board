import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.change_intelligence.semantic import (
    apply_semantic_verdicts,
    evaluate_semantic_changes,
    semantic_eligible_items,
)


def _summary(status="developing_signal", tier1=1, items=None):
    return {
        "status": status,
        "corroboration": {"tier1": tier1, "independentTier2": 0, "countableSources": 3},
        "uncertainties": [],
        "changedItems": items if items is not None else [{
            "id": "u1", "kind": "market_driver", "subject": "반도체/AI", "change": "changed",
            "previousValue": {"rank": 3, "share": 0.18}, "currentValue": {"rank": 1, "share": 0.31},
            "magnitude": 0.31,
            "contextDocs": ["화웨이 어센드 AI 칩 투자 확대"], "previousContextDocs": ["엔비디아 실적 기대"],
        }],
    }


def _llm(verdict, note="확인된 변화", cited=None):
    def call(prompt, context):
        assert "units" in context
        return {"units": [{"id": "u1", "verdict": verdict, "note": note, "citedTitles": cited or ["화웨이 어센드 AI 칩 투자 확대"]}]}
    return call


def test_only_driver_and_issue_units_with_both_sides_are_eligible():
    """대조할 직전 제목이 없는 단위는 보내지 않는다.

    한쪽만 보내면 모델은 비교할 것이 없어 언제나 `new_information`을 답하고, 그
    verdict가 승격 게이트를 통과시킨다 — 매일 새로 뽑히는 이슈 목록이 그런 단위다.
    """
    summary = _summary(items=[
        {"id": "m", "kind": "market_metric", "subject": "^GSPC", "change": "changed",
         "contextDocs": ["t"], "previousContextDocs": ["p"]},
        {"id": "d", "kind": "market_driver", "subject": "금리", "change": "changed",
         "contextDocs": ["t"], "previousContextDocs": ["p"]},
        {"id": "added", "kind": "issue_coverage", "subject": "오늘 새 이슈", "change": "added", "contextDocs": ["t"]},
        {"id": "bare", "kind": "market_driver", "subject": "옛 형식", "change": "changed"},
    ])
    assert [row["id"] for row in semantic_eligible_items(summary)] == ["d"]


def test_new_information_with_evidence_gate_promotes_to_major():
    summary = _summary(status="developing_signal", tier1=1)
    evaluation = evaluate_semantic_changes(summary, llm_call=_llm("new_information"))
    result = apply_semantic_verdicts(summary, evaluation)
    assert result["status"] == "major_change"
    assert result["changedItems"][0]["semanticVerdict"] == "new_information"
    assert result["changedItems"][0]["semanticNote"] == "확인된 변화"


def test_promotion_requires_evidence_gate_not_just_the_llm():
    """LLM enum만으로 결론을 확정하지 않는다 — 증거 등급 관문은 규칙이다."""
    summary = _summary(status="developing_signal", tier1=0)
    evaluation = evaluate_semantic_changes(summary, llm_call=_llm("new_information"))
    result = apply_semantic_verdicts(summary, evaluation)
    assert result["status"] == "developing_signal"


def test_coverage_shift_only_demotes_volume_driven_major():
    summary = _summary(status="major_change")
    evaluation = evaluate_semantic_changes(summary, llm_call=_llm("coverage_shift_only"))
    result = apply_semantic_verdicts(summary, evaluation)
    assert result["status"] == "no_material_change"


def test_without_llm_major_is_not_confirmed():
    summary = _summary(status="major_change")
    result = apply_semantic_verdicts(summary, {"status": "not_evaluated", "verdicts": {}})
    assert result["status"] == "developing_signal"
    assert "semantic_not_evaluated" in result["uncertainties"]
    assert result["changedItems"][0]["semanticVerdict"] == "not_evaluated"


def test_metric_only_major_survives_without_semantics():
    summary = _summary(status="major_change", items=[
        {"id": "m", "kind": "market_metric", "subject": "^GSPC", "change": "changed", "magnitude": 0.9},
    ])
    result = apply_semantic_verdicts(summary, {"status": "no_eligible_items", "verdicts": {}})
    assert result["status"] == "major_change"


def test_invalid_verdicts_and_fabricated_citations_are_dropped():
    def bad_llm(prompt, context):
        return {"units": [
            {"id": "u1", "verdict": "totally_new_enum", "note": "x"},
            {"id": "ghost", "verdict": "reversal", "note": "x"},
        ]}
    evaluation = evaluate_semantic_changes(_summary(), llm_call=bad_llm)
    assert evaluation["status"] == "not_evaluated"

    def fabricating_llm(prompt, context):
        return {"units": [{"id": "u1", "verdict": "reversal", "note": "x", "citedTitles": ["지어낸 제목"]}]}
    evaluation = evaluate_semantic_changes(_summary(), llm_call=fabricating_llm)
    assert evaluation["verdicts"]["u1"]["citedTitles"] == []


def test_llm_failure_never_raises():
    def broken(prompt, context):
        raise RuntimeError("provider down")
    evaluation = evaluate_semantic_changes(_summary(), llm_call=broken)
    assert evaluation["status"] == "not_evaluated"


def test_conflicting_uncertain_is_left_alone():
    summary = _summary(status="conflicting_uncertain")
    evaluation = evaluate_semantic_changes(summary, llm_call=_llm("new_information"))
    result = apply_semantic_verdicts(summary, evaluation)
    assert result["status"] == "conflicting_uncertain"


def test_the_summary_records_why_it_could_not_judge():
    """판정하지 못한 **이유**를 남긴다.

    이유가 없으면 화면은 엔진이 없어서인지 호출이 실패해서인지 구분할 수 없어
    어댑터를 스스로 뒤지게 된다. 그 추측이 LLM API 키만 쓰는 설치에서
    "AI Agent를 연결하세요"를 되살렸다 — 판정 엔진은 이미 연결돼 있다.
    """
    from features.common.change_intelligence.semantic import apply_semantic_verdicts

    summary = {
        "status": "developing_signal",
        "generatedAt": "2026-08-21T09:00:00+09:00",
        "changedItems": [
            {"id": "u1", "kind": "market_driver", "contextDocs": ["제목"], "previousContextDocs": ["직전 제목"]},
        ],
    }

    unavailable = apply_semantic_verdicts(
        summary, {"status": "not_evaluated", "verdicts": {}, "reason": "llm_unavailable"},
    )
    assert unavailable["semanticEvaluation"]["reason"] == "llm_unavailable"
    assert unavailable["changedItems"][0]["semanticVerdict"] == "not_evaluated"

    failed = apply_semantic_verdicts(
        summary, {"status": "not_evaluated", "verdicts": {}, "reason": "llm_failed"},
    )
    assert failed["semanticEvaluation"]["reason"] == "llm_failed"


def test_items_that_cannot_be_compared_are_never_marked_unjudged():
    """대조할 수 없는 단위에는 아무 표시도 남기지 않는다.

    서버가 판정하지 않을 단위다. 표시가 남으면 화면이 그것을 "다음 생성에서 판정할
    기록"으로 세는데, 그 약속은 영원히 지켜지지 않는다.
    """
    from features.common.change_intelligence.semantic import apply_semantic_verdicts

    result = apply_semantic_verdicts(
        {
            "status": "developing_signal",
            "changedItems": [
                {"id": "u1", "kind": "market_driver"},
                {"id": "u2", "kind": "issue_coverage", "change": "added", "contextDocs": ["오늘 제목"]},
                {"id": "u3", "kind": "market_driver", "contextDocs": ["제목"], "previousContextDocs": ["직전 제목"]},
            ],
        },
        {"status": "not_evaluated", "verdicts": {}, "reason": "llm_unavailable"},
    )

    assert "semanticVerdict" not in result["changedItems"][0]
    assert "semanticVerdict" not in result["changedItems"][1]
    assert result["changedItems"][2]["semanticVerdict"] == "not_evaluated"
