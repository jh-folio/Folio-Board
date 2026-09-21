"""Strict section-patch merge guards for concentration repair."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

from features.daily_briefing.concentration.audit import audit_concentration


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_LEADER = re.compile(r"주도한 기업\s*[①②12].*?—\s*(.+?)\s*$")


def _leader_subjects(markdown: str) -> list[str]:
    subjects = []
    for heading in _HEADING.findall(markdown):
        match = _LEADER.search(heading.strip())
        if match:
            subjects.append(match.group(1).strip())
    return subjects


def apply_section_patches(markdown: str, patches: list[dict], *, allowed_headings: set[str]) -> str:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    bodies = {}
    order = []
    prefix = text[:matches[0].start()] if matches else text
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        order.append(heading)
        bodies[heading] = text[match.end():end].strip("\n")
    replacements = {}
    for patch in patches or []:
        heading = str(patch.get("heading") or "").removeprefix("## ").strip()
        body = str(patch.get("replacementBody") or "").strip()
        if heading not in allowed_headings or heading not in bodies or not body:
            raise ValueError("section_patch_outside_contract")
        if _HEADING.search(body):
            raise ValueError("nested_heading_in_patch")
        replacements[heading] = body
    before_leaders = _leader_subjects(text)
    result = prefix.rstrip()
    for heading in order:
        result += f"\n\n## {heading}\n\n{replacements.get(heading, bodies[heading]).strip()}"
    result = result.strip()
    after_leaders = _leader_subjects(result)
    if before_leaders != after_leaders:
        raise ValueError("leader_heading_changed")
    return result


def _improved(before: dict, after: dict) -> bool:
    before_metrics = before.get("metrics") or {}
    after_metrics = after.get("metrics") or {}
    before_key = (
        0 if before.get("status") == "pass" else 1 if before.get("status") == "review" else 2,
        int(before_metrics.get("claimOverlapPairs") or 0),
        int(before_metrics.get("causalOverlapPairs") or 0),
        len(before_metrics.get("displacedMajorSubjects") or []),
        int(before_metrics.get("maxEntitySectionSpan") or 0),
    )
    after_key = (
        0 if after.get("status") == "pass" else 1 if after.get("status") == "review" else 2,
        int(after_metrics.get("claimOverlapPairs") or 0),
        int(after_metrics.get("causalOverlapPairs") or 0),
        len(after_metrics.get("displacedMajorSubjects") or []),
        int(after_metrics.get("maxEntitySectionSpan") or 0),
    )
    return after_key < before_key


def repair_concentration(
    markdown: str,
    audit: dict,
    *,
    leader_subjects: list[str],
    other_major_subjects: list[str],
    invoke: Callable[[str], str],
) -> tuple[str, dict]:
    allowed = {str(row).removeprefix("## ").strip() for row in audit.get("affectedSections") or []}
    if audit.get("status") != "repair_candidate" or not allowed:
        return markdown, audit
    prompt = json.dumps({
        "task": "Remove repeated causal claims and restore displaced company coverage using section-body patches only.",
        "allowedHeadings": sorted(allowed),
        "leaderSubjectsInOrder": leader_subjects,
        "otherMajorSubjects": other_major_subjects,
        "audit": audit,
        "markdown": markdown,
        "output": {"patches": [{"heading": "exact allowed heading", "replacementBody": "body without any ## heading"}]},
        "constraints": ["JSON object only", "at most 3 patches", "do not change leader headings or order", "retain factual numbers and source grounding"],
    }, ensure_ascii=False, separators=(",", ":"))
    try:
        parsed = json.loads(str(invoke(prompt) or ""))
        patches = parsed.get("patches") if isinstance(parsed, dict) else None
        if not isinstance(patches, list) or not 1 <= len(patches) <= 3:
            raise ValueError("invalid_patch_count")
        candidate = apply_section_patches(markdown, patches, allowed_headings=allowed)
        from features.common.quality_generation.repair_grounding import preserves_briefing_input
        if not preserves_briefing_input(markdown, candidate):
            return markdown, {**audit, "repair": {"attempted": True, "applied": False, "reason": "outside_input", "changedSections": []}}
        if len(candidate) < int(len(markdown) * 0.75):
            raise ValueError("repair_removed_too_much")
        after = audit_concentration(candidate, leader_subjects=leader_subjects, other_major_subjects=other_major_subjects)
        if not _improved(audit, after):
            return markdown, {**audit, "repair": {"attempted": True, "applied": False, "reason": "no_improvement", "changedSections": []}}
        changed = [str(row.get("heading") or "").removeprefix("## ").strip() for row in patches]
        return candidate, {**after, "repair": {"attempted": True, "applied": True, "reason": "accepted", "changedSections": changed}}
    except TimeoutError:
        reason = "timeout"
    except (json.JSONDecodeError, TypeError, ValueError, OSError, RuntimeError):
        reason = "invalid_or_unavailable"
    return markdown, {**audit, "repair": {"attempted": True, "applied": False, "reason": reason, "changedSections": []}}


def configured_repair(
    markdown: str,
    audit: dict,
    *,
    leader_subjects: list[str],
    other_major_subjects: list[str],
    serialize: bool = True,
) -> tuple[str, dict]:
    from features.common.quality_generation.call_budget import current_briefing_budget
    shared = current_briefing_budget()
    def remaining():
        if shared:
            return min(180, shared.remaining_seconds() or 180)
        return 180
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return markdown, {**audit, "repair": {"attempted": True, "applied": False, "reason": "unavailable", "changedSections": []}}
    from features.llm_settings.client import ai_agent_enabled, ai_agent_mode, request_cli_text, selected_cli_config
    if not ai_agent_enabled():
        return markdown, {**audit, "repair": {"attempted": True, "applied": False, "reason": "unavailable", "changedSections": []}}
    from features.agent_mode.bridge import run_agent_prompt

    def invoke(prompt: str) -> str:
        result = run_agent_prompt(prompt, timeout=min(max(30, int(os.environ.get("KR_CONCENTRATION_REPAIR_TIMEOUT_SECONDS", "180"))), remaining()), serialize=serialize)
        return str(result.get("output") or "")
    return repair_concentration(
        markdown,
        audit,
        leader_subjects=leader_subjects,
        other_major_subjects=other_major_subjects,
        invoke=invoke,
    )


__all__ = ["apply_section_patches", "configured_repair", "repair_concentration"]
