"""Semantic concentration audit for the full KR daily briefing body."""
from __future__ import annotations

import re
from collections import defaultdict

from features.common.text.tokenize import tokens


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_EXCLUDED = re.compile(r"source|data notes|참고자료|출처", re.IGNORECASE)
_TABLE = re.compile(r"(?m)^\s*\|.*?\|\s*$")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|원|달러|배|bp)?\b", re.IGNORECASE)
_CAUSAL = ("때문", "따라", "통해", "이어", "영향", "결과", "수요", "공급", "가격", "이익", "마진", "수급")


def _sections(markdown: str) -> list[tuple[str, str]]:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    rows = []
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        if _EXCLUDED.search(heading):
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = _TABLE.sub("", text[match.end():end])
        body = _NUMBER.sub("", body)
        rows.append((heading, body))
    return rows


def _fingerprints(body: str) -> list[set[str]]:
    rows = re.split(r"(?:다\.|[.!?。！？])\s+|[\r\n]+", body)
    output = []
    for row in rows:
        bag = {token.casefold() for token in tokens(row) if len(token) >= 2}
        if len(bag) >= 4:
            output.append(bag)
    return output


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def audit_concentration(
    markdown: str,
    *,
    leader_subjects: list[str] | None = None,
    other_major_subjects: list[str] | None = None,
) -> dict:
    sections = _sections(markdown)
    entity_sections: dict[str, set[str]] = defaultdict(set)
    for heading, body in sections:
        for subject in leader_subjects or []:
            if str(subject or "") and str(subject) in body:
                entity_sections[str(subject)].add(heading)
    claim_pairs = []
    causal_pairs = []
    for left_index, (left_heading, left_body) in enumerate(sections):
        for right_heading, right_body in sections[left_index + 1:]:
            best = 0.0
            for left in _fingerprints(left_body):
                for right in _fingerprints(right_body):
                    best = max(best, _jaccard(left, right))
            if best >= 0.58:
                claim_pairs.append((left_heading, right_heading, round(best, 3)))
                left_causal = {term for term in _CAUSAL if term in left_body}
                right_causal = {term for term in _CAUSAL if term in right_body}
                if len(left_causal & right_causal) >= 3:
                    causal_pairs.append((left_heading, right_heading))
    affected = sorted({heading for pair in claim_pairs for heading in pair[:2]})
    signals = []
    max_span = max((len(value) for value in entity_sections.values()), default=0)
    if max_span >= 4:
        signals.append("entity_section_span")
    if claim_pairs:
        signals.append("claim_overlap")
    if causal_pairs:
        signals.append("causal_path_overlap")
    missing_major = [
        subject for subject in other_major_subjects or []
        if subject and not any(subject in body for _, body in sections)
    ]
    if missing_major:
        signals.append("coverage_displacement")
    semantic_count = sum(signal in signals for signal in ("claim_overlap", "causal_path_overlap", "coverage_displacement"))
    repair_candidate = ("entity_section_span" in signals and semantic_count >= 1) or semantic_count >= 2
    status = "repair_candidate" if repair_candidate else "review" if signals else "pass"
    return {
        "status": status,
        "signals": signals,
        "affectedSections": [f"## {heading}" for heading in affected],
        "metrics": {
            "maxEntitySectionSpan": max_span,
            "claimOverlapPairs": len(claim_pairs),
            "causalOverlapPairs": len(causal_pairs),
            "displacedMajorSubjects": missing_major,
        },
        "repair": {"attempted": False, "applied": False, "reason": "", "changedSections": []},
    }


__all__ = ["audit_concentration"]
