"""Dynamic length and section-density policy for Topic Reports."""
from __future__ import annotations

import re
from typing import Any

from features.topic_report.topic_schema import (
    EXPECTED_SECTIONS_V2,
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
    body_sections,
)


# 태그 이름을 특정하지 않는다. 모델이 새 이름을 만들어 쓰면 분량 계산에 주석이 섞인다.
_SOURCE_TAG = re.compile(r"<!--.*?-->", re.DOTALL)

# 머리·꼬리의 분량 비중은 고정이고, 남은 몫을 본문 섹션이 나눠 갖는다.
# 본문이 기본 3개일 때 예전 고정 가중치와 같은 값이 나오도록 총합을 맞춰 뒀다
# (deep 8·7·9 + 41 + 9·9·7·6·4 = 100, ordinary 10·7·9 + 40 + 9·8·7·6·4 = 100).
_DEEP_HEAD_WEIGHTS = (8, 7, 9)
_DEEP_TAIL_WEIGHTS = (9, 9, 7, 6, 4)
_DEEP_BODY_WEIGHT = 41
_ORDINARY_HEAD_WEIGHTS = (10, 7, 9)
_ORDINARY_TAIL_WEIGHTS = (9, 8, 7, 6, 4)
_ORDINARY_BODY_WEIGHT = 40


def visible_markdown(markdown: str) -> str:
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    return _SOURCE_TAG.sub("", text).strip()


def visible_character_count(markdown: str) -> int:
    return len(visible_markdown(markdown))


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
