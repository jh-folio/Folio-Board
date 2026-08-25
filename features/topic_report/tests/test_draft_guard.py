"""초안 재시도 계약 — 못 쓸 초안 하나가 앞의 모든 작업을 버리지 않게 한다."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import draft_guard as G
from features.topic_report.report_contract import REPORT_HEAD_SECTIONS, REPORT_TAIL_SECTIONS

_BODY = "기대 심리가 지표에 반영되는 경로를 단계로 풀어 설명한 문장이다. " * 8


def _report(*, body_sections=("장기금리",), drop_tail: int = 0, filler: int = 1) -> str:
    heads = [f"## {name}\n\n{_BODY * filler}" for name in REPORT_HEAD_SECTIONS]
    body = [f"## {name}\n\n{_BODY * filler}" for name in body_sections]
    tails = [f"## {name}\n\n{_BODY * filler}" for name in REPORT_TAIL_SECTIONS[: len(REPORT_TAIL_SECTIONS) - drop_tail]]
    return "\n\n".join(["# 제목", *heads, *body, *tails])


# ------------------------------------------------------------------ 판정

def test_a_healthy_draft_has_no_problems():
    assert G.draft_problems(_report(filler=6), min_chars=1000) == []


def test_a_truncated_draft_is_caught():
    # 2회차 실패의 모습 — 꼬리 섹션이 없어 잡이 통째로 죽었다.
    assert "draft_sections_missing" in G.draft_problems(_report(drop_tail=2), min_chars=0)


def test_a_stub_draft_is_caught():
    # 4회차의 모습 — 하한 12,000자에 5,569자(46%)였다.
    assert "draft_stub" in G.draft_problems(_report(), min_chars=12_000)
    assert G.draft_problems("", min_chars=0) == ["draft_empty"]


def test_a_merely_short_draft_is_left_to_the_repair_pass():
    # 하한의 60% 이상이면 짧은 보고서지 스텁이 아니다. 여기서 걸러 버리면
    # 보수가 할 일을 재생성이 대신하게 된다.
    text = _report(filler=7)
    assert len(text) > 12_000 * G.MIN_DRAFT_RATIO
    assert "draft_stub" not in G.draft_problems(text, min_chars=12_000)


def test_style_and_linkage_are_not_retry_reasons():
    # 문체·근거 연결은 보수 패스의 몫이다. 재시도 사유에 넣지 않는다.
    hedged = _report(filler=6).replace("문장이다.", "문장일 수 있다.")
    assert G.draft_problems(hedged, min_chars=1000) == []


# ------------------------------------------------------------------ 선택

def test_the_better_draft_wins():
    good, bad = _report(filler=6), _report(drop_tail=2, filler=6)
    assert G.better_draft(bad, good, min_chars=1000) == (good, "retry_better")
    assert G.better_draft(good, bad, min_chars=1000) == (good, "retry_worse")


def test_a_tie_goes_to_the_fuller_draft():
    short, long = _report(filler=2), _report(filler=6)
    chosen, reason = G.better_draft(short, long, min_chars=100)
    assert chosen == long and reason == "retry_longer"
    chosen, reason = G.better_draft(long, short, min_chars=100)
    assert chosen == long and reason == "retry_no_gain"


# ------------------------------------------------------------------ 지시문

def test_the_directive_names_the_missing_sections_without_showing_the_bad_draft():
    # 실패한 초안을 되돌려 주면 앵커가 되어 같은 실수를 되풀이한다.
    note = G.retry_directive(
        ["draft_sections_missing", "draft_stub"],
        min_chars=12_000,
        sections=["Executive Summary", "장기금리", "결론"],
    )
    assert "Executive Summary | 장기금리 | 결론" in note
    assert "Source & Data Notes" in note and "중간에 멈추지 마세요" in note
    assert "12,000" in note
    assert _BODY not in note


def test_the_directive_only_says_what_went_wrong():
    note = G.retry_directive(["draft_stub"], min_chars=12_000, sections=["A"])
    assert "고정 섹션이 빠졌습니다" not in note
