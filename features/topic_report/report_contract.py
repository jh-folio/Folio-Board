"""Strict structural and evidence-boundary validation for Deep Research."""
from __future__ import annotations

import re
from collections import Counter

from features.topic_report.depth_policy import visible_character_count
from features.topic_report.section_sources import apply_section_usage
from features.topic_report.topic_schema import EXPECTED_SECTIONS_V2


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SENTENCE = re.compile(r"(?:다\.|[.!?。！？])\s+|[\r\n]+")
_SOURCE_REQUIRED = set(EXPECTED_SECTIONS_V2) - {"질문 정의와 분석 범위", "Source & Data Notes"}


def canonical_heading(value: str) -> str:
    return re.sub(r"^\d+\.\s*", "", str(value or "").strip())


def split_sections(markdown: str) -> list[dict]:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    rows = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        rows.append({
            "heading": canonical_heading(match.group(1)),
            "rawHeading": match.group(1).strip(),
            "body": text[match.end():end].strip(),
        })
    return rows


def _defect(category: str, code: str, severity: int, *, section: str = "", fixable: bool = True) -> dict:
    return {"category": category, "code": code, "severity": severity, "section": section, "fixable": fixable}


def validate_deep_report(
    markdown: str,
    *,
    source_ledger: list[dict],
    depth_policy: dict,
    material_resolution: dict | None = None,
    internal_score: int = 0,
) -> dict:
    text = str(markdown or "").strip()
    defects = []
    sections = split_sections(text)
    headings = [row["heading"] for row in sections]
    if not text:
        defects.append(_defect("blocking", "empty_body", 100, fixable=False))
    if headings != EXPECTED_SECTIONS_V2:
        defects.append(_defect("blocking", "required_heading_order", 100))
    projected_ledger, source_result = apply_section_usage(text, source_ledger)
    for code, values in (
        ("malformed_source_tag", source_result["malformedSourceIds"]),
        ("unknown_source_tag", source_result["unknownSourceIds"]),
        ("forbidden_source_tag", source_result["forbiddenSourceIds"]),
    ):
        if values:
            defects.append(_defect("blocking", code, 100))
    usage = source_result["sectionUsage"]
    linked_required = sum(bool(usage.get(heading)) for heading in _SOURCE_REQUIRED)
    linkage_ratio = linked_required / max(1, len(_SOURCE_REQUIRED))
    for heading in _SOURCE_REQUIRED:
        if not usage.get(heading):
            defects.append(_defect("evidence", "unlinked_section", 35, section=heading))
    if linkage_ratio < 0.7:
        defects.append(_defect("evidence", "low_source_linkage", 70))
    material_missing = [
        row for category in ("market", "macro")
        for row in (material_resolution or {}).get(category, [])
        if row.get("status") != "available"
    ]
    if material_missing:
        defects.append(_defect("non_fixable", "required_material_unavailable", 60, fixable=False))
    count = visible_character_count(text)
    recommended_min = int(depth_policy.get("recommendedMinChars") or 0)
    safety_max = int(depth_policy.get("safetyMaxChars") or 18_000)
    if count < recommended_min:
        defects.append(_defect("depth", "below_recommended_length", 45))
    if count > safety_max:
        defects.append(_defect("depth", "above_safety_length", 80))
    budgets = depth_policy.get("sectionBudgets") or {}
    for section in sections:
        target = int(budgets.get(section["heading"]) or 0)
        if target and len(section["body"]) < max(180, int(target * 0.35)):
            defects.append(_defect("depth", "thin_section", 35, section=section["heading"]))
    sentences = [re.sub(r"\s+", " ", row).strip() for row in _SENTENCE.split(text)]
    repeats = Counter(row for row in sentences if len(row) >= 40)
    if any(count >= 3 for count in repeats.values()):
        defects.append(_defect("depth", "repeated_sentence", 55))
    if "시나리오" in headings:
        scenario = next((row["body"] for row in sections if row["heading"] == "시나리오"), "")
        if not any(term in scenario for term in ("조건", "이상", "이하", "상회", "하회", "경우")):
            defects.append(_defect("reasoning", "unconditional_scenarios", 45, section="시나리오"))
    blocking = [row for row in defects if row["category"] == "blocking"]
    fixable = [row for row in defects if row["fixable"]]
    return {
        "valid": not blocking,
        "defects": defects,
        "metrics": {
            "characterCount": count,
            "sourceLinkageRatio": round(linkage_ratio, 4),
            "requiredSectionCount": len(headings),
            "blockingCount": len(blocking),
            "fixableSeverity": sum(int(row["severity"]) for row in fixable),
            "fixableCount": len(fixable),
            "internalScore": int(internal_score),
        },
        "sourceLedger": projected_ledger,
        "sourceResult": source_result,
    }


__all__ = ["canonical_heading", "split_sections", "validate_deep_report"]
