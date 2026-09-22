"""Private recovery copies, distinct from canonical company reports.

No automatic promotion: interrupted/partial candidates remain inspectable through
the existing report list/detail API. A canonical commit is the only success proof.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

from features.common.canonical_report_io import atomic_write, safe_child_path
from features.common.canonical_report_types import CanonicalValidationError

_ID = re.compile(r"recovery-[a-f0-9]{32}\Z")
_NOTICE = "복구 후보입니다. 정상 보고서로 저장되지 않았으며 기존 보고서는 유지됩니다."


def is_recovery_id(value: str) -> bool:
    return bool(_ID.fullmatch(str(value)))


def candidate_path(root: Path, identity: str) -> Path:
    if not is_recovery_id(identity):
        raise ValueError("invalid recovery identity")
    return safe_child_path(safe_child_path(root, "recovery"), f"{identity}.json")


def load_candidate(root: Path, identity: str) -> dict | None:
    try:
        value = json.loads(candidate_path(root, identity).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("id") != identity or value.get("recoveryStored") is not True:
        return None
    return value


def preserve_candidate(root: Path, report: dict) -> dict:
    candidate = deepcopy(report)
    # Content identity avoids cross-run overwrites and makes repeated preservation
    # idempotent. Exclude our envelope and canonical revision bookkeeping.
    basis = {k: candidate.get(k) for k in ("company", "generatedAt", "markdown")}
    digest = hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
    identity = f"recovery-{digest}"
    target = candidate.get("id")
    candidate.update(id=identity, saved=False, recoveryStored=True,
                     recoveryTargetId=target if not is_recovery_id(str(target)) else candidate.get("recoveryTargetId"))
    candidate.pop("jobCommit", None)
    for key in ("changeBasis", "changeSummary", "changeIntelligence", "personalOverlay"):
        candidate.pop(key, None)
    candidate["headline"] = "[복구 후보] " + str(candidate.get("headline") or "기업 분석").removeprefix("[복구 후보] ")
    generation = dict(candidate.get("generation") or {})
    completion = candidate.get("completion") or {}
    reason = ("출력 한도에 도달했습니다. " if completion.get("stopReason") == "limit" else
              "필수 섹션이 누락되었습니다. " if completion.get("structureIncomplete") else
              "실행이 정상 완료되지 않았습니다. " if completion.get("status") == "failed" else "")
    generation["message"] = reason + _NOTICE
    candidate["generation"] = generation
    atomic_write(candidate_path(root, identity), json.dumps(candidate, ensure_ascii=False, indent=2).encode("utf-8"))
    return candidate


def discard_promoted(root: Path, report: dict) -> None:
    """Only remove our redundant copy after the exact canonical commit succeeds."""
    basis = {k: report.get(k) for k in ("company", "generatedAt", "markdown")}
    digest = hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
    try:
        candidate_path(root, f"recovery-{digest}").unlink(missing_ok=True)
    except OSError:
        # Cleanup failure must not change the proven canonical outcome.
        pass


def completion_summary(report: dict) -> dict:
    facts = report.get("executionFacts") or {}
    status = facts.get("completionStatus", "unknown")
    if status not in {"completed", "incomplete", "failed", "unknown"}:
        status = "unknown"
    reason = facts.get("stopReason", "unknown")
    if reason not in {"end", "limit", "tool_error", "cancelled", "other", "unknown"}:
        reason = "unknown"
    defects = (report.get("contractValidation") or {}).get("defects") or []
    missing = any(d.get("code") in {"empty_body", "section_missing"} for d in defects if isinstance(d, dict))
    if missing and status not in {"incomplete", "failed"}:
        status = "incomplete"
    return {"status": status, "stopReason": reason, "structureIncomplete": missing}


def guard_canonical(root: Path, report: dict) -> None:
    """Called inside the canonical prepare lock by every company writer."""
    completion = report.get("completion") or {}
    if is_recovery_id(str(report.get("id"))) or completion.get("status") in {"incomplete", "failed"}:
        preserve_candidate(root, report)
        raise CanonicalValidationError("company_report_incomplete", _NOTICE)
