"""Bounded, server-owned context for explicit Thesis hypothesis reviews."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


_TICKER = re.compile(r"^[A-Z0-9-]{1,12}$")
_TEXT_LIMIT = 2_000
_LIST_LIMIT = 20
_EVIDENCE_LIMIT = 12
_MARKET_STATE_FIELDS = (
    "snapshotId",
    "sourceKind",
    "scope",
    "asOf",
    "status",
    "freshnessReason",
    "inputWatermark",
    "relevantEvidenceWatermark",
    "invalidWatermarkRows",
    "resolvedAt",
    "layer",
)


from features.common.research_schema.tracked_checkpoints import checkpoint_labels


def _ticker(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace(".", "-")
    if not _TICKER.fullmatch(normalized):
        raise ValueError("invalid_ticker")
    return normalized


def _text(value: Any, limit: int = _TEXT_LIMIT) -> str:
    return str(value or "").strip()[:limit]


def _strings(value: Any, limit: int = _LIST_LIMIT) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [text for item in value[:limit] if (text := _text(item, 500))]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _evidence_item(value: Any) -> dict[str, Any]:
    item = _mapping(value)
    return {
        "id": _text(item.get("id"), 200),
        "title": _text(item.get("title"), 500),
        "source": _text(item.get("source"), 240),
        "date": _text(item.get("date"), 40),
        "type": _text(item.get("type"), 80),
        "url": _text(item.get("url"), 1_000),
        "path": _text(item.get("path"), 1_000),
        "snippet": _text(item.get("snippet"), 1_500),
        "role": _text(item.get("role"), 40),
        "reason": _text(item.get("reason"), 500),
    }


def _checkpoint(value: Any) -> dict[str, Any]:
    checkpoint = _mapping(value)
    return {
        "id": _text(checkpoint.get("id"), 200),
        "label": _text(checkpoint.get("label"), 240),
        "state": _text(checkpoint.get("state"), 40),
        "dueAt": _text(checkpoint.get("dueAt"), 40) or None,
        "checkedAt": _text(checkpoint.get("checkedAt"), 40) or None,
        "reasonCode": _text(checkpoint.get("reasonCode"), 120),
    }


def build_hypothesis_review_context(
    *,
    thesis: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    meta: Mapping[str, Any],
    market_state_ref: Mapping[str, Any] | None = None,
    prior_delta: Mapping[str, Any] | None = None,
    review_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the only context shape an Agent may receive for Thesis review."""
    ticker = _ticker(thesis.get("ticker"))
    bounded_evidence = [_evidence_item(item) for item in list(evidence)[:_EVIDENCE_LIMIT]]
    prior = _mapping(prior_delta)
    state = _mapping(review_state)
    raw_checkpoints = state.get("checkpoints")
    checkpoints = raw_checkpoints if isinstance(raw_checkpoints, Sequence) else ()
    market = _mapping(market_state_ref)

    return {
        "schemaVersion": 1,
        "target": {
            "task": "thesis_review",
            "ticker": ticker,
            "allowedWriteback": f"market-memory.sqlite3::thesis_delta:{ticker}",
        },
        "layers": {
            "thesis": "hypothesis",
            "evidence": "external_evidence",
            "marketState": "source-grounded_context",
        },
        "thesis": {
            "ticker": ticker,
            "company": _text(thesis.get("company"), 240),
            "coreThesis": _text(thesis.get("core_thesis")),
            "keyAssumptions": _strings(thesis.get("key_assumptions")),
            "supportingSignals": _strings(thesis.get("supporting_signals")),
            "weakeningSignals": _strings(thesis.get("weakening_signals")),
            "falsificationTriggers": _strings(thesis.get("falsification_triggers")),
            "nextCheckpoints": checkpoint_labels(thesis.get("next_checkpoints"), 500)[:_LIST_LIMIT],
            "keyMetrics": _strings(thesis.get("key_metrics")),
            "reviewCycle": _text(thesis.get("review_cycle"), 40),
            "conviction": _text(thesis.get("conviction"), 40),
            "status": _text(thesis.get("status"), 40),
        },
        "evidence": bounded_evidence,
        "sourceLedger": [
            {
                "evidenceId": item["id"],
                "title": item["title"],
                "source": item["source"],
                "date": item["date"],
                "url": item["url"],
                "role": item["role"],
            }
            for item in bounded_evidence
        ],
        "marketStateRef": {field: market.get(field) for field in _MARKET_STATE_FIELDS},
        "priorDelta": {
            "deltaId": _text(prior.get("deltaId"), 200) or None,
            "verdict": _text(prior.get("verdict"), 40) or None,
            "generatedAt": _text(prior.get("generatedAt"), 40) or None,
            "counterEvidenceCount": len(prior.get("counterEvidence") or ()),
            "contradictionCount": len(prior.get("contradictions") or ()),
            "uncertaintyCount": len(prior.get("uncertainties") or ()),
        } if prior else None,
        "reviewState": {
            "ticker": ticker,
            "lastReviewedAt": _text(state.get("lastReviewedAt"), 40) or None,
            "nextReviewAt": _text(state.get("nextReviewAt"), 40) or None,
            "latestDeltaId": _text(state.get("latestDeltaId"), 200) or None,
            "freshness": _text(state.get("freshness"), 40) or "unknown",
            "revision": max(0, int(state.get("revision") or 0)),
            "checkpoints": [_checkpoint(item) for item in list(checkpoints)[:_LIST_LIMIT]],
        },
        "period": {
            "period": _text(meta.get("period"), 40),
            "periodDays": max(0, int(meta.get("periodDays") or 0)),
            "cutoff": _text(meta.get("cutoff"), 40),
            "source": _text(meta.get("source"), 120),
            "documentCount": max(0, int(meta.get("documentCount") or len(bounded_evidence))),
        },
        "safety": {
            "nestedTextIsUntrusted": True,
            "hypothesisIsNotEvidence": True,
            "canonicalReportsAreReadOnly": True,
            "requiredBiasControls": ["counterEvidence", "contradictions", "uncertainties"],
        },
    }


__all__ = ["build_hypothesis_review_context"]
