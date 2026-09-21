"""Telemetry helpers for report generation quality and token usage."""
from __future__ import annotations

from collections import Counter
from typing import Any
from features.common.research_schema.data_gaps import data_gap_rows


def estimate_tokens(text: str | None) -> int:
    return max(0, len(str(text or "")) // 4)


def normalize_token_usage(
    usage: dict | None,
    *,
    prompt: str = "",
    context: str = "",
    output: str = "",
    max_output_tokens: int | None = None,
) -> dict:
    usage = usage or {}
    estimated = {
        "estimated": True,
        "inputTokens": estimate_tokens(prompt) + estimate_tokens(context),
        "outputTokens": estimate_tokens(output),
    }
    estimated["totalTokens"] = estimated["inputTokens"] + estimated["outputTokens"]
    out = {
        "inputCharCount": len(str(prompt or "")) + len(str(context or "")),
        "outputCharCount": len(str(output or "")),
        "maxOutputTokens": max_output_tokens,
        **estimated,
    }
    actual = {
        "inputTokens": usage.get("inputTokens"),
        "outputTokens": usage.get("outputTokens"),
        "totalTokens": usage.get("totalTokens"),
    }
    if any(value is not None for value in actual.values()):
        out.update({k: v for k, v in actual.items() if v is not None})
        out["estimated"] = False
    if usage.get("providerRaw"):
        out["providerRaw"] = usage["providerRaw"]
    if usage.get("transport") == "cli":
        out["transport"] = "cli"
        out["outputTokenCapEnforced"] = False
        out["requestedOutputTokens"] = max_output_tokens
        out["maxOutputTokens"] = None
    return out


def evidence_coverage(artifact: dict | None) -> dict:
    artifact = artifact or {}
    items = list(artifact.get("evidenceItems") or [])
    ledger = list(artifact.get("sourceLedger") or artifact.get("sources") or [])
    gaps = data_gap_rows(artifact.get("dataGaps"))
    type_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for item in items:
        if not isinstance(item, dict):
            continue
        type_counts[str(item.get("type") or item.get("sourceType") or item.get("kind") or "unknown")] += 1
        role_counts[str(item.get("role") or item.get("evidenceRole") or "neutral")] += 1
        if item.get("source"):
            source_counts[str(item.get("source"))] += 1
    if not items:
        for item in ledger:
            if not isinstance(item, dict):
                continue
            type_counts[str(item.get("type") or item.get("sourceType") or "source")] += 1
            if item.get("source"):
                source_counts[str(item.get("source"))] += 1
    return {
        "evidenceItemCount": len(items),
        "sourceLedgerCount": len(ledger),
        "dataGapCount": len(gaps),
        "typeCounts": dict(type_counts),
        "roleCounts": dict(role_counts),
        "topSources": dict(source_counts.most_common(8)),
    }


def generation_telemetry(
    *,
    prompt: str = "",
    context: str = "",
    output: str = "",
    token_usage: dict | None = None,
    artifact: dict | None = None,
    max_output_tokens: int | None = None,
    quality_before: dict | None = None,
    quality_after: dict | None = None,
    weak_sections_before: list[dict] | None = None,
    weak_sections_after: list[dict] | None = None,
) -> dict:
    out: dict[str, Any] = {
        "tokenUsage": normalize_token_usage(
            token_usage,
            prompt=prompt,
            context=context,
            output=output,
            max_output_tokens=max_output_tokens,
        ),
        "evidenceCoverage": evidence_coverage(artifact),
    }
    if quality_before is not None:
        out["qualityBefore"] = {
            "score": quality_before.get("score"),
            "grade": quality_before.get("grade"),
            "status": quality_before.get("status"),
        }
    if quality_after is not None:
        out["qualityAfter"] = {
            "score": quality_after.get("score"),
            "grade": quality_after.get("grade"),
            "status": quality_after.get("status"),
        }
    if weak_sections_before is not None:
        out["weakSectionsBefore"] = weak_sections_before
    if weak_sections_after is not None:
        out["weakSectionsAfter"] = weak_sections_after
    return out
