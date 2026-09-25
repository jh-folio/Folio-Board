"""Briefing-only numeric support must use final validated facts."""

from __future__ import annotations

from features.common.research_quality.evaluator import evaluate_artifact, evaluate_report


_REFERENCE_HEAVY = """# Briefing

## 현재 판단
수치는 아래 참고자료의 날짜와 링크를 확인한다.

## Source & Data Notes
- 2026-09-04 123.45% https://example.com/report/12345
- 2026-09-03 678.90 54321
"""


def test_briefing_numeric_support_ignores_reference_urls_dates_and_raw_numbers():
    quality = evaluate_artifact("briefing", {"markdown": _REFERENCE_HEAVY})
    assert quality["checks"]["numeric_support"] == 0.0
    assert quality["numericSupport"] == "none"


def test_briefing_numeric_support_counts_distinct_validated_facts_once():
    quality = evaluate_artifact(
        "briefing",
        {
            "markdown": _REFERENCE_HEAVY,
            "finalValidation": {
                "verifiedClaims": [
                    {"factKey": "NVDA", "kind": "changePct"},
                    {"factKey": "NVDA", "kind": "changePct"},
                    {"factKey": "KOSPI", "kind": "changePct"},
                ],
            },
        },
    )
    # Two distinct fact pairs, not three rows and not the many reference
    # numbers, contribute to the score.
    assert quality["checks"]["numeric_support"] == 0.4


def test_non_briefing_numeric_evaluator_keeps_legacy_raw_number_behavior():
    quality = evaluate_report(_REFERENCE_HEAVY, artifact_type="topic_report")
    assert quality["checks"]["numeric_support"] > 0.0

