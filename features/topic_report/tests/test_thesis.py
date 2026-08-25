"""핵심 논지 선정 계약 — 하나를 고르고, 지어낸 근거는 버리고, 실패해도 죽지 않는다."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import thesis as T
from features.topic_report.axis_analysis import build_axis_briefs, render_axis_briefs

_PLAN = {"topic": "기대 심리는 지표에 어떤 영향을 미치는가?"}
_BRIEFS = [
    {
        "axisKey": "inflation",
        "label": "2021~2022 인플레이션",
        "status": "ok",
        "evidenceCount": 4,
        "findings": ["기대가 재평가되며 금리가 올랐다"],
        "numbers": ["CPI = 7.0% (2021-12)"],
        "counterEvidence": ["공급 요인도 컸다"],
        "competingExplanations": ["수요 과열이 주도했다"],
        "whatWouldChangeThis": ["5년 기대인플레이션이 2% 아래로 내려가면"],
        "uncertainties": ["포지셔닝 자료 없음"],
        "sourceIds": ["ev_001", "macro_DGS10"],
    },
]


def _call(payload):
    return lambda _prompt, _context: json.dumps(payload, ensure_ascii=False)


# ----------------------------------------------------------------- 선정

def test_thesis_keeps_only_source_ids_the_axes_actually_saw():
    # 논지도 브리프와 같은 규칙을 쓴다. 지어낸 ID는 원장과 맞지 않아 태그가 깨진다.
    out = T.select_thesis(_PLAN, _BRIEFS, run_call=_call({
        "primaryThesis": {
            "claim": "지금의 핵심은 금리 수준이 아니라 기대의 재평가다",
            "because": ["기대 지표가 먼저 움직였다"],
            "sourceIds": ["ev_001", "ev_999", "macro_DGS10", "web_001"],
            "confidence": "medium",
        },
        "supportingTheses": [{"claim": "정책 신뢰가 변수다", "sourceIds": ["ev_001"]}],
        "rejectedExplanation": {"claim": "공급 충격 단독", "whyWeaker": "기간이 맞지 않는다"},
        "whatWouldChangeThis": ["T10YIE가 2.0% 아래로"],
    }))
    ids = out["primaryThesis"]["sourceIds"]
    assert "ev_001" in ids and "macro_DGS10" in ids
    assert "web_001" in ids  # 웹 근거는 원장에 등재되므로 인용할 수 있다
    assert "ev_999" not in ids  # 축이 본 적 없는 ID


def test_confidence_is_an_enum_not_free_text():
    # 결론의 세기를 자유 텍스트로 정하지 않는다(§5 원칙 4).
    out = T.select_thesis(_PLAN, _BRIEFS, run_call=_call({
        "primaryThesis": {"claim": "A가 아니라 B다", "confidence": "아주 높음"},
    }))
    assert out["primaryThesis"]["confidence"] == "medium"

    out = T.select_thesis(_PLAN, _BRIEFS, run_call=_call({
        "primaryThesis": {"claim": "A가 아니라 B다", "confidence": "HIGH"},
    }))
    assert out["primaryThesis"]["confidence"] == "high"


def test_supporting_theses_are_capped():
    out = T.select_thesis(_PLAN, _BRIEFS, run_call=_call({
        "primaryThesis": {"claim": "핵심 판단"},
        "supportingTheses": [{"claim": f"보조 {n}"} for n in range(9)],
    }))
    assert len(out["supportingTheses"]) == 3


def test_failure_returns_empty_instead_of_killing_the_report():
    # 논지 하나 때문에 수 분짜리 실행을 버리지 않는다.
    def boom(_prompt, _context):
        raise RuntimeError("engine down")

    assert T.select_thesis(_PLAN, _BRIEFS, run_call=boom) == {}
    assert T.select_thesis(_PLAN, _BRIEFS, run_call=lambda *_: "not json at all") == {}
    assert T.select_thesis(_PLAN, _BRIEFS, run_call=_call({"primaryThesis": {"claim": ""}})) == {}


def test_no_usable_brief_means_no_call():
    calls = []

    def spy(prompt, context):
        calls.append(prompt)
        return "{}"

    assert T.select_thesis(_PLAN, [{"label": "빈 축", "findings": [], "numbers": []}], run_call=spy) == {}
    assert calls == []


# ----------------------------------------------------------------- 렌더

def test_rendered_thesis_carries_the_rejected_explanation_and_falsifiers():
    # 논지를 세우는 일이 확증편향의 입구가 되지 않도록, 버린 해석과 반증 조건을
    # 본문 컨텍스트에 함께 싣는다(§5 원칙 3).
    block = T.render_thesis({
        "primaryThesis": {"claim": "기대의 재평가가 핵심이다", "because": ["기대 지표가 먼저"], "confidence": "high"},
        "supportingTheses": [{"claim": "정책 신뢰가 변수다"}],
        "rejectedExplanation": {"claim": "공급 충격 단독", "whyWeaker": "기간 불일치"},
        "whatWouldChangeThis": ["T10YIE가 2.0% 아래로"],
    })
    assert "기대의 재평가가 핵심이다" in block
    assert "공급 충격 단독" in block and "지우지 말고" in block
    assert "T10YIE가 2.0% 아래로" in block
    assert "단정형" in block  # high의 문장 강도 지침


def test_rendered_thesis_forbids_turning_the_claim_into_headings():
    # 형식을 강제한 지침이 오히려 품질을 해친 실패를 두 번 겪었다(고정 골격, 4단계 소제목).
    block = T.render_thesis({"primaryThesis": {"claim": "핵심 판단", "confidence": "low"}})
    assert "소제목으로 만들거나" in block
    assert T.render_thesis({}) == ""
    assert T.render_thesis({"primaryThesis": {"claim": ""}}) == ""


def test_summary_reports_unavailable_without_a_claim():
    assert T.thesis_summary({})["status"] == "unavailable"
    summary = T.thesis_summary({
        "primaryThesis": {"claim": "판단", "confidence": "low", "because": ["a", "b"], "sourceIds": ["ev_001"]},
        "rejectedExplanation": {"claim": "버린 해석"},
        "whatWouldChangeThis": ["x"],
    })
    assert summary == {
        "status": "ok",
        "claim": "판단",
        "confidence": "low",
        "reasonCount": 2,
        "supportingCount": 0,
        "hasRejectedExplanation": True,
        "falsifierCount": 1,
        "sourceIds": ["ev_001"],
    }


# ----------------------------------------------------------------- 축 브리프 확장

def test_axis_brief_carries_competing_explanations_and_falsifiers():
    # 반대 근거는 "어긋나는 자료", 경쟁 가설은 "같은 자료의 다른 이야기"라 다르다.
    plan = {"analysisAxes": [{"key": "a", "label": "축", "questions": ["왜?"]}], "deepResearch": {"subQuestions": []}}
    payload = {
        "findings": ["판단"],
        "counterEvidence": ["반대"],
        "competingExplanations": ["다른 해석 1", "다른 해석 2", "다른 해석 3"],
        "whatWouldChangeThis": ["지표 X가 내려가면"],
        "sourceIds": [],
    }
    briefs = build_axis_briefs(plan, [], run_call=_call(payload))
    assert briefs[0]["competingExplanations"] == ["다른 해석 1", "다른 해석 2"]  # 최대 2개
    assert briefs[0]["whatWouldChangeThis"] == ["지표 X가 내려가면"]

    block = render_axis_briefs(briefs)
    assert "다른 해석" in block and "이 판단이 틀렸다면" in block


def test_thesis_context_sees_the_new_brief_fields():
    context = T._context(_PLAN, _BRIEFS)
    assert "수요 과열이 주도했다" in context
    assert "5년 기대인플레이션이 2% 아래로 내려가면" in context


# ------------------------------------------- 축끼리 영역을 침범하지 않는다

def test_each_axis_is_told_what_the_other_sections_own():
    # 축 브리프는 축마다 독립 호출이라 서로의 몫을 모른다. 실측으로 전이 경로 축이
    # 2021~2022와 2024년 8월을 예시로 끌어와 전개했는데, 그 둘은 바로 뒤에 각자
    # 2,000자 넘는 섹션을 갖고 있었다.
    from features.topic_report.axis_analysis import _other_axes_notice

    axes = [
        {"key": "path", "label": "기대 심리가 지표로 옮겨가는 경로"},
        {"key": "y2021", "label": "2021~2022 인플레이션 국면"},
        {"key": "y2024", "label": "2024년 8월 엔캐리 청산"},
    ]
    notice = _other_axes_notice(axes[0], axes)
    assert "2021~2022 인플레이션 국면" in notice
    assert "2024년 8월 엔캐리 청산" in notice
    assert "기대 심리가 지표로 옮겨가는 경로" not in notice  # 자기 자신은 빼고
    assert "결론 한 줄만 빌려" in notice  # 금지가 아니라 대안을 준다


def test_a_single_axis_report_gets_no_notice():
    # 나눌 몫이 없으면 말하지 않는다. 빈 목록으로 겁주지 않는다.
    from features.topic_report.axis_analysis import _other_axes_notice

    axes = [{"key": "only", "label": "유일한 축"}]
    assert _other_axes_notice(axes[0], axes) == ""
    assert _other_axes_notice(axes[0], []) == ""


def test_the_axis_context_carries_the_notice():
    from features.topic_report.axis_analysis import _axis_context

    axes = [{"key": "a", "label": "축 A"}, {"key": "b", "label": "축 B"}]
    context = _axis_context(axes[0], ["질문?"], [], "", "원문 질문", "", axes)
    assert "축 B" in context and "다른 섹션이 맡은 주제" in context
    # 축 목록을 주지 않으면 예전처럼 조용히 동작한다.
    assert "다른 섹션이 맡은 주제" not in _axis_context(axes[0], ["질문?"], [], "", "원문 질문", "")
