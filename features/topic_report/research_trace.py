"""User-facing factual projection of internal research provenance."""
from __future__ import annotations

from features.common.research_schema.data_gaps import data_gap_rows


def build_research_trace_summary(source_ledger: list[dict], data_gaps, *, caution_limit: int = 2) -> dict:
    used = [row for row in source_ledger if isinstance(row, dict) and row.get("usedInSections")]
    dates = sorted(str(row.get("date") or "")[:10] for row in used if str(row.get("date") or "")[:10])
    gaps = data_gap_rows(data_gaps)
    cautions: list[str] = []
    for gap in gaps:
        message = str(gap.get("message") or "").strip()
        if message and message not in cautions:
            cautions.append(message)
        if len(cautions) >= caution_limit:
            break
    return {
        "schemaVersion": 1,
        "usedSourceCount": len(used),
        "latestSourceDate": dates[-1] if dates else None,
        "challengingSourceCount": sum(str(row.get("evidenceRole") or "") == "challenging" for row in used),
        "unresolvedDataGapCount": len(gaps),
        "cautionReasons": cautions,
    }


__all__ = ["build_research_trace_summary"]
