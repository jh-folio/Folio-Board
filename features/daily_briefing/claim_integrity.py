"""Deterministic guardrails for high-risk briefing claims.

This is deliberately narrower than a general fact checker.  It catches claim
shapes that routinely overstate what market-news evidence can establish:
capital moving from one asset to another and broad sector participation inferred
from a handful of companies.  Unsupported wording is downgraded without another
LLM call; the audit stays in report metadata, never in reader Markdown.
"""
from __future__ import annotations

import os
import re
from copy import deepcopy


_CAPITAL_FLOW_PATTERNS = (
    re.compile(r"(?P<origin>[^\n.!?]{1,45}?)에서\s*(?:빠져나오거나\s*)?이탈한\s*자금이\s*(?P<target>[^\n.!?]{1,45}?)(?:로|으로)\s*(?:이동|유입|몰렸)(?:했(?:다|으며|고)?|한\s*것으로\s*(?:해석됐|보였)다)?", re.I),
    re.compile(r"(?P<target>[^\n.!?]{1,45}?)(?:은|는)\s*(?:이탈한\s*)?자금의\s*(?:대체\s*)?목적지", re.I),
)
_SECTOR_BREADTH_PATTERNS = (
    re.compile(r"반도체\s*소부장(?:\s*전반)?(?:의|이|은|도)?\s*(?:동반\s*)?강세", re.I),
    re.compile(r"소부장(?:\s*전반)?(?:의|이|은|도)?\s*(?:동반\s*)?강세", re.I),
    re.compile(r"업종\s*전반(?:의|이|은|도)?\s*(?:동반\s*)?강세", re.I),
)

_DIRECT_FLOW_TERMS = (
    "자금 이동", "자금이 이동", "자금 유입", "자금이 유입", "자금 이탈",
    "순환매", "갈아타", "로테이션", "rotation", "rotated into",
    "flows into", "funds moved", "capital moved",
)
_DIRECT_BREADTH_TERMS = (
    "업종 전반 강세", "업종 전반이 강세", "업종 전반의 강세", "동반 강세",
    "소부장 전반", "반도체 소부장 강세", "sector-wide", "broad-based",
    "across the sector",
)


def claim_integrity_mode() -> str:
    value = str(os.environ.get("BRIEFING_CLAIM_INTEGRITY_MODE", "active") or "active").strip().lower()
    return value if value in {"off", "diagnose", "active"} else "active"


def _source_text(source: dict) -> str:
    values = [
        source.get("title"), source.get("summary"), source.get("description"),
        str(source.get("content") or "")[:6000], source.get("excerpt"),
    ]
    return re.sub(r"\s+", " ", " ".join(str(value or "") for value in values)).casefold()


def _direct_support(sources, claim_type: str) -> tuple[bool, list[str]]:
    terms = _DIRECT_FLOW_TERMS if claim_type == "capital_flow" else _DIRECT_BREADTH_TERMS
    supporting = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        text = _source_text(source)
        if text and any(term.casefold() in text for term in terms):
            source_id = str(source.get("sourceId") or "").strip()
            if source_id:
                supporting.append(source_id)
    return bool(supporting), supporting


def _downgrade_flow(match: re.Match) -> str:
    target = re.sub(r"\s+", " ", str(match.groupdict().get("target") or "해당 자산")).strip()
    if "origin" in match.groupdict() and match.groupdict().get("origin"):
        origin = re.sub(r"\s+", " ", str(match.group("origin"))).strip()
        return f"{origin}의 약세와 {target}의 상대 강세가 동시에 나타났지만 동일 자금의 직접 이동으로 단정할 근거는 부족하다"
    return f"{target}은 상대 강세가 나타난 후보"


def _downgrade_breadth(match: re.Match) -> str:
    value = match.group(0)
    if "반도체" in value:
        return "일부 반도체 소부장 종목의 강세"
    if "소부장" in value:
        return "일부 소부장 종목의 강세"
    return "업종 일부 종목의 강세"


def enforce_claim_integrity(
    markdown: str,
    sources,
    claim_ledger: dict | None = None,
    *,
    mode: str | None = None,
) -> tuple[str, dict]:
    """Return guarded Markdown and an augmented internal claim ledger."""
    effective_mode = str(mode or claim_integrity_mode()).strip().lower()
    if effective_mode not in {"off", "diagnose", "active"}:
        effective_mode = "active"
    text = str(markdown or "")
    ledger = deepcopy(claim_ledger or {"version": 1, "claims": []})
    findings: list[dict] = []

    def inspect(patterns, claim_type, downgrade):
        nonlocal text
        supported, source_ids = _direct_support(sources, claim_type)
        for pattern in patterns:
            def replace(match: re.Match) -> str:
                original = match.group(0)
                replacement = original if supported or effective_mode != "active" else downgrade(match)
                findings.append({
                    "claimType": claim_type,
                    "status": "supported" if supported else ("downgraded" if replacement != original else "review"),
                    "reasonCodes": [] if supported else ["direct_source_relationship_missing"],
                    "supportingSourceIds": source_ids,
                    "original": original[:240],
                    "replacement": replacement[:240] if replacement != original else "",
                })
                return replacement
            text = pattern.sub(replace, text)

    if effective_mode != "off":
        inspect(_CAPITAL_FLOW_PATTERNS, "capital_flow", _downgrade_flow)
        inspect(_SECTOR_BREADTH_PATTERNS, "sector_breadth", _downgrade_breadth)

    reason_codes = sorted({code for row in findings for code in row.get("reasonCodes") or []})
    ledger["integrity"] = {
        "version": 1,
        "mode": effective_mode,
        "status": "review" if reason_codes else "pass",
        "findingCount": len(findings),
        "reasonCodes": reason_codes,
        "findings": findings,
    }
    validation = dict(ledger.get("validation") or {})
    prior_codes = list(validation.get("reasonCodes") or [])
    validation["reasonCodes"] = sorted(set([*prior_codes, *reason_codes]))
    if reason_codes and validation.get("status") == "pass":
        validation["status"] = "review"
    ledger["validation"] = validation
    return text, ledger


__all__ = ["claim_integrity_mode", "enforce_claim_integrity"]
