"""Dynamic length and section-density policy for Topic Reports."""
from __future__ import annotations

from typing import Any

from features.common.report_prose import visible_character_count, visible_markdown
from features.topic_report.topic_schema import (
    EXPECTED_SECTIONS_V2,
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
    body_sections,
)

# 머리·꼬리의 분량 비중은 고정이고, 남은 몫을 본문 섹션이 나눠 갖는다.
# 머리 1개(Executive Summary, 옛 8+7)·꼬리 3개(반론과 리스크·체크포인트·Source & Data
# Notes)로 줄인 0.6 Phase 1(2026-09-13) 이후 값이다. 옛 머리 "핵심 데이터 대시보드"(9)와
# 옛 꼬리 "시나리오"(9)·"결론"(6)의 몫은 이제 이름을 강제하지 않는 본문으로 넘겼다 —
# 그 내용이 필요하면 본문 섹션 하나로 자연스럽게 들어가고, 필요 없으면 안 쓴다.
# (deep 15 + 65 + 9·7·4 = 100, ordinary 17 + 63 + 9·7·4 = 100).
_DEEP_HEAD_WEIGHTS = (15,)
_DEEP_TAIL_WEIGHTS = (9, 7, 4)
_DEEP_BODY_WEIGHT = 65
_ORDINARY_HEAD_WEIGHTS = (17,)
_ORDINARY_TAIL_WEIGHTS = (9, 7, 4)
_ORDINARY_BODY_WEIGHT = 63


# `visible_markdown`·`visible_character_count`는 `features/common/report_prose.py`가
# 소유한다. 기업분석도 같은 것을 쓰므로 기능 폴더에 두면 다른 기능이 이 모듈을
# import하게 된다(§13). 여기서는 이름만 그대로 내보낸다.


def _section_weights(sections: list[str], *, deep: bool) -> list[int]:
    head = list(_DEEP_HEAD_WEIGHTS if deep else _ORDINARY_HEAD_WEIGHTS)
    tail = list(_DEEP_TAIL_WEIGHTS if deep else _ORDINARY_TAIL_WEIGHTS)
    body_total = _DEEP_BODY_WEIGHT if deep else _ORDINARY_BODY_WEIGHT
    body_count = max(1, len(sections) - len(head) - len(tail))
    # 본문 섹션이 늘어나면 한 섹션의 몫은 줄지만, 본문 전체의 몫은 유지된다.
    # 분석축이 많을수록 축마다 얇아지는 대신 표·꼬리에 밀리지는 않는다.
    per_body = max(1, round(body_total / body_count))
    return [*head, *([per_body] * body_count), *tail]


def build_depth_policy(
    *,
    deep_research: bool,
    analysis_axis_count: int,
    subquestion_count: int,
    evidence_count: int,
    report_type: str,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    resolved = [str(item).strip() for item in (sections or EXPECTED_SECTIONS_V2) if str(item).strip()]
    if len(resolved) < len(REPORT_HEAD_SECTIONS) + len(REPORT_TAIL_SECTIONS) + 1:
        resolved = list(EXPECTED_SECTIONS_V2)
    if deep_research:
        target = 12_000
        target += min(max(analysis_axis_count - 3, 0), 3) * 500
        target += min(max(subquestion_count - 6, 0), 6) * 250
        target += min(max(evidence_count - 12, 0), 16) * 90
        target = min(16_000, target)
        recommended_min, recommended_max, safety_max = 12_000, 16_000, 18_000
    else:
        target = min(7_000, 3_000 + max(analysis_axis_count, 1) * 450 + min(evidence_count, 12) * 100)
        recommended_min, recommended_max, safety_max = 3_000, 7_000, 8_000
    weights = _section_weights(resolved, deep=deep_research)
    section_budgets = {
        heading: max(220, round(target * weight / sum(weights)))
        for heading, weight in zip(resolved, weights, strict=True)
    }
    return {
        "schemaVersion": 2,
        "mode": "deep" if deep_research else "ordinary",
        "reportType": str(report_type or "custom_research"),
        "sections": resolved,
        "bodySections": body_sections(resolved),
        "recommendedMinChars": recommended_min,
        "targetChars": target,
        "recommendedMaxChars": recommended_max,
        "safetyMaxChars": safety_max,
        "sectionBudgets": section_budgets,
    }


__all__ = ["build_depth_policy", "visible_character_count", "visible_markdown"]
