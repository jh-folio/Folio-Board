from __future__ import annotations


def candidate_rank(validation: dict) -> tuple:
    metrics = validation.get("metrics") or {}
    return (
        -int(metrics.get("blockingCount") or 0),
        -int(metrics.get("fixableSeverity") or 0),
        -int(metrics.get("fixableCount") or 0),
        float(metrics.get("sourceLinkageRatio") or 0.0),
        min(int(metrics.get("characterCount") or 0), 16_000),
        int(metrics.get("internalScore") or 0),
    )


def candidate_improves(before: dict, after: dict) -> bool:
    before_metrics, after_metrics = before.get("metrics") or {}, after.get("metrics") or {}
    if int(after_metrics.get("blockingCount") or 0) > int(before_metrics.get("blockingCount") or 0):
        return False
    if float(after_metrics.get("sourceLinkageRatio") or 0) < float(before_metrics.get("sourceLinkageRatio") or 0):
        return False
    return candidate_rank(after) > candidate_rank(before)


def repairable_sections(validation: dict, *, limit: int) -> list[str]:
    sections = []
    for defect in sorted(validation.get("defects") or [], key=lambda row: int(row.get("severity") or 0), reverse=True):
        section = str(defect.get("section") or "")
        if defect.get("fixable") and section and section not in sections:
            sections.append(section)
        if len(sections) >= limit:
            break
    return sections


__all__ = ["candidate_improves", "candidate_rank", "repairable_sections"]
