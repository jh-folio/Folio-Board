"""Dynamic length and section-density policy for Topic Reports."""
from __future__ import annotations

import re
from typing import Any

from features.topic_report.topic_schema import EXPECTED_SECTIONS_V2


_SOURCE_TAG = re.compile(r"<!--\s*folio-source-ids:\s*.*?-->", re.IGNORECASE)
_DEEP_WEIGHTS = (8, 7, 9, 15, 16, 10, 9, 9, 7, 6, 4)
_ORDINARY_WEIGHTS = (10, 7, 9, 15, 15, 10, 9, 8, 7, 6, 4)


def visible_markdown(markdown: str) -> str:
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    return _SOURCE_TAG.sub("", text).strip()


def visible_character_count(markdown: str) -> int:
    return len(visible_markdown(markdown))


def build_depth_policy(
    *,
    deep_research: bool,
    analysis_axis_count: int,
    subquestion_count: int,
    evidence_count: int,
    report_type: str,
) -> dict[str, Any]:
    if deep_research:
        target = 12_000
        target += min(max(analysis_axis_count - 3, 0), 3) * 500
        target += min(max(subquestion_count - 6, 0), 6) * 250
        target += min(max(evidence_count - 12, 0), 16) * 90
        target = min(16_000, target)
        recommended_min, recommended_max, safety_max = 12_000, 16_000, 18_000
        weights = _DEEP_WEIGHTS
    else:
        target = min(7_000, 3_000 + max(analysis_axis_count, 1) * 450 + min(evidence_count, 12) * 100)
        recommended_min, recommended_max, safety_max = 3_000, 7_000, 8_000
        weights = _ORDINARY_WEIGHTS
    section_budgets = {
        heading: max(220, round(target * weight / sum(weights)))
        for heading, weight in zip(EXPECTED_SECTIONS_V2, weights, strict=True)
    }
    return {
        "schemaVersion": 1,
        "mode": "deep" if deep_research else "ordinary",
        "reportType": str(report_type or "custom_research"),
        "recommendedMinChars": recommended_min,
        "targetChars": target,
        "recommendedMaxChars": recommended_max,
        "safetyMaxChars": safety_max,
        "sectionBudgets": section_budgets,
    }


__all__ = ["build_depth_policy", "visible_character_count", "visible_markdown"]
