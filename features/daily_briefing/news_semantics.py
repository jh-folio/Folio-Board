"""Bounded, injected semantic evaluation for daily-news selection.

This module is deliberately a *consumer* of an evaluation adapter, not an
adapter itself.  The normal briefing paths do not call a provider from here.
An API/CLI owner may inject a callback for an explicitly enabled US/KR daily
run; the callback receives one bounded payload and must return a JSON-like
mapping.  The module owns the input identity, output validation, cache and
one-batch request ledger so a different adapter cannot silently change the
selection contract.

The input is made from external news candidates and a pinned prior briefing's
checkpoints.  A prior report is comparison context, not evidence, and private
note/overlay fields are excluded.  Cached values are validated result metadata
only; neither an article body nor a private path is retained.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
import threading
import time
from typing import Any, Callable, Iterable, Mapping

from features.common.change_intelligence.semantic import SEMANTIC_VERDICTS
from features.market_memory.evidence_roles import ROLE_CHOICES


SEMANTIC_TARGET = "daily_news_selection"
SEMANTIC_POLICY_VERSION = "q5-s2-news-semantics-v1"
SEMANTIC_PROMPT_VERSION = "q5-s2-news-payload-v1"
MAX_EVENTS = 24
MAX_EXCERPT_CHARS = 1200
MAX_INPUT_TOKENS = 12_000
MAX_OUTPUT_TOKENS = 3_000
MAX_TIMEOUT_SECONDS = 60.0
 # The transport owner may use a still smaller byte cap when it cannot expose
 # a tokenizer (the current CLI contract does so).  This is a preflight cap,
 # not a claim about provider token usage.
MAX_INPUT_BYTES = 12_000
MAX_OUTPUT_BYTES = 24_000
MAX_CACHE_ENTRIES = 128
MAX_CACHE_AGE_SECONDS = 24 * 60 * 60
MAX_NOTE_CHARS = 300
MAX_REASON_CHARS = 300
MAX_DIMENSIONS = 7

IMPORTANCE_CHOICES = frozenset({"high", "medium", "low", "unknown"})
EDITORIAL_ROLES = frozenset({"core_flow", "judgment_change", "new_signal", "checkpoint_result"})

_PRIVATE_KEYS = frozenset({
    "personalOverlay", "personal_overlay", "personalNotes", "personal_notes",
    "notes", "userNotes", "user_notes", "thesis", "hypothesisNotes",
    "hypothesis_notes", "absolutePath", "absolute_path", "path",
    "content", "fullText", "full_text", "rawText", "raw_text",
})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _canonical(value: Any) -> Any:
    """Build a stable, private-field-free JSON value for hashing."""

    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, set):
        return sorted((_canonical(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_canonical(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _estimate_tokens(value: Any) -> int:
    # This is intentionally a conservative preflight estimate.  A provider's
    # usage receipt is not available to this core and must not be fabricated.
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return max(1, (len(encoded) + 3) // 4)


def _bounded_text(value: Any, limit: int = MAX_EXCERPT_CHARS) -> str:
    return " ".join(_text(value).split())[: max(0, int(limit))]


def _safe_id(value: Any) -> str:
    return _text(value)[:160]


def _candidate_id(candidate: Mapping[str, Any], index: int = 0) -> str:
    value = _safe_id(candidate.get("candidateId") or candidate.get("id") or candidate.get("eventRef"))
    return value or f"candidate_{index}"


def _source_id(candidate: Mapping[str, Any], index: int = 0) -> str:
    for key in ("sourceId", "source_id", "sourceIdentity"):
        value = _safe_id(candidate.get(key))
        if value:
            return value
    # A missing source ID is intentionally not replaced by a URL/path here.
    # The caller may still inspect the row, but it cannot be semantically
    # validated as evidence without a stable source identity.
    return f"missing_source_{index}"


def _event_key(candidate: Mapping[str, Any], index: int = 0) -> str:
    explicit = _safe_id(candidate.get("eventKey") or candidate.get("eventRef") or candidate.get("eventId"))
    period = _bounded_text(candidate.get("observedPeriod") or candidate.get("period"), 80)
    correction = _bounded_text(candidate.get("correctionOf") or candidate.get("revisionOf"), 160)
    revision = _bounded_text(candidate.get("revisionAt") or candidate.get("revisionId"), 160)
    if explicit:
        # An explicit event id is stable, but a correction/revision of that id
        # is a distinct observation and must not be swallowed as a duplicate.
        return "|".join((explicit, period, correction, revision))
    source = _source_id(candidate, index)
    return "|".join((source, period, correction, revision))


def _is_correction(candidate: Mapping[str, Any]) -> bool:
    return bool(_text(candidate.get("correctionOf") or candidate.get("revisionOf") or candidate.get("revisionAt") or candidate.get("revisionId")))


def _claim_rows(
    candidate: Mapping[str, Any],
    source_id: str,
    candidate_id: str,
    excerpt: str,
    allowed_source_ids: set[str],
) -> list[dict[str, Any]]:
    raw = candidate.get("claims")
    if raw is None and candidate.get("claim") is not None:
        raw = [candidate.get("claim")]
    rows: list[dict[str, Any]] = []
    if isinstance(raw, Mapping):
        raw = [raw]
    if isinstance(raw, (list, tuple)):
        for index, item in enumerate(raw[:8]):
            if isinstance(item, Mapping):
                claim_id = _safe_id(item.get("claimId") or item.get("id")) or f"{candidate_id}:claim:{index + 1}"
                text = _bounded_text(item.get("text") or item.get("claim") or item.get("summary"), MAX_NOTE_CHARS)
                sources = item.get("sourceIds") or item.get("source_ids") or [source_id]
            else:
                claim_id = f"{candidate_id}:claim:{index + 1}"
                text = _bounded_text(item, MAX_NOTE_CHARS)
                sources = [source_id]
            source_ids = [_safe_id(value) for value in (sources if isinstance(sources, (list, tuple, set)) else [sources]) if _safe_id(value)]
            # Claim text must be present in the bounded event excerpt.  A
            # candidate-side claim is metadata, not independent evidence.
            normalized_excerpt = " ".join(excerpt.split())
            text_in_excerpt = text in excerpt or text in normalized_excerpt
            if text and text_in_excerpt and source_ids and set(source_ids).issubset(allowed_source_ids):
                rows.append({"claimId": claim_id, "text": text, "sourceIds": source_ids[:8]})
    if not rows:
        text = _bounded_text(excerpt, MAX_NOTE_CHARS)
        if text and source_id and not source_id.startswith("missing_source_") and (text in excerpt or " ".join(text.split()) in " ".join(excerpt.split())):
            rows.append({"claimId": f"{candidate_id}:claim:1", "text": text, "sourceIds": [source_id]})
    return rows


def _safe_hypothesis(item: Any, index: int) -> dict[str, Any] | None:
    if isinstance(item, Mapping):
        # Hypotheses are only copied from the pinned checkpoint shape.  A
        # caller cannot smuggle a personal note in an arbitrary nested field.
        if _lower(item.get("sourceLayer") or item.get("source_layer")) in {"hypothesis", "personal", "user_note"}:
            return None
        hypothesis_id = _safe_id(item.get("id") or item.get("checkpointId") or item.get("checkpoint_id") or item.get("hypothesisId"))
        text = _bounded_text(item.get("item") or item.get("question") or item.get("text") or item.get("condition"), MAX_NOTE_CHARS)
        direction = _lower(item.get("direction"))
        condition = _bounded_text(item.get("condition") or item.get("falsifier") or item.get("nextCheck"), MAX_NOTE_CHARS)
    else:
        hypothesis_id = ""
        text = _bounded_text(item, MAX_NOTE_CHARS)
        direction = ""
        condition = ""
    if not text:
        return None
    if not hypothesis_id:
        hypothesis_id = f"checkpoint:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"
    return {
        "hypothesisId": hypothesis_id,
        "text": text,
        "direction": direction if direction in ROLE_CHOICES else "",
        "condition": condition,
    }


def _extract_hypotheses(pinned_context: Mapping[str, Any] | None, market: str) -> list[dict[str, Any]]:
    if not isinstance(pinned_context, Mapping):
        return []
    baselines = pinned_context.get("baselines")
    baseline = baselines.get(market) if isinstance(baselines, Mapping) else None
    if not isinstance(baseline, Mapping) or _lower(baseline.get("status")) != "baseline_ready":
        return []
    report = baseline.get("report")
    if not isinstance(report, Mapping):
        return []
    raw_values: list[Any] = []
    for key in ("checkpoints", "checkpointQuestions", "previousCheckpoints"):
        value = report.get(key)
        if isinstance(value, (list, tuple)):
            raw_values.extend(value)
    for key in ("checkpoint", "checklist"):
        value = report.get(key)
        if isinstance(value, Mapping):
            raw_values.extend(value.values())
        elif _text(value):
            raw_values.append(value)
    hypotheses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_values):
        row = _safe_hypothesis(item, index)
        if row is None or row["hypothesisId"] in seen:
            continue
        seen.add(row["hypothesisId"])
        hypotheses.append(row)
        if len(hypotheses) >= 8:
            break
    return hypotheses


def _safe_baseline(pinned_context: Mapping[str, Any] | None, market: str) -> dict[str, Any]:
    if not isinstance(pinned_context, Mapping):
        return {}
    baselines = pinned_context.get("baselines")
    baseline = baselines.get(market) if isinstance(baselines, Mapping) else None
    if not isinstance(baseline, Mapping):
        return {}
    pin = baseline.get("pin") if isinstance(baseline.get("pin"), Mapping) else {}
    report = baseline.get("report") if isinstance(baseline.get("report"), Mapping) else {}
    # Identity-only pin.  Never send markdown, overlay or note content to the
    # callback, even when an older caller supplied it in the pinned report.
    return {
        "status": _lower(baseline.get("status")) or "unknown",
        "reportId": _safe_id(baseline.get("reportId") or pin.get("reportId") or report.get("id")),
        "sessionDate": _bounded_text(baseline.get("sessionDate") or pin.get("sessionDate") or report.get("sessionDate"), 32),
        "cutoff": _bounded_text(baseline.get("cutoff") or pin.get("cutoff") or report.get("cutoff"), 64),
        "version": _safe_id(baseline.get("version") or pin.get("version") or report.get("version") or report.get("selectionVersion")),
        "contentHash": _safe_id(baseline.get("contentHash") or pin.get("contentHash")),
    }


def _safe_event(candidate: Mapping[str, Any], index: int, *, duplicate_of: str = "") -> dict[str, Any] | None:
    candidate_id = _candidate_id(candidate, index)
    source_id = _source_id(candidate, index)
    if source_id.startswith("missing_source_"):
        return None
    event_key = _event_key(candidate, index)
    excerpt = _bounded_text(candidate.get("excerpt") or candidate.get("summary") or candidate.get("content"), MAX_EXCERPT_CHARS)
    if not excerpt:
        return None
    candidate_sources = candidate.get("sourceIds") or candidate.get("source_ids") or []
    candidate_source_ids = {
        _safe_id(value)
        for value in (candidate_sources if isinstance(candidate_sources, (list, tuple, set)) else [candidate_sources])
        if _safe_id(value)
    }
    allowed_source_ids = {source_id, *candidate_source_ids}
    claims = _claim_rows(candidate, source_id, candidate_id, excerpt, allowed_source_ids)
    if not claims:
        return None
    source_ids = sorted({source_id, *candidate_source_ids, *(source for claim in claims for source in claim["sourceIds"])})
    result = {
        "eventRef": event_key,
        "candidateId": candidate_id,
        "sourceIds": source_ids[:8],
        "claims": claims[:8],
        "excerpt": excerpt,
        "observedPeriod": _bounded_text(candidate.get("observedPeriod") or candidate.get("period"), 80),
        "correctionOf": _bounded_text(candidate.get("correctionOf") or candidate.get("revisionOf"), 160),
        "revisionAt": _bounded_text(candidate.get("revisionAt") or candidate.get("revisionId"), 80),
        "isCorrection": _is_correction(candidate),
    }
    if duplicate_of:
        result["duplicateOf"] = duplicate_of
    return result


def _dedupe_events(candidates: Iterable[Mapping[str, Any]] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_rows = list(candidates or [])
    events: list[dict[str, Any]] = []
    by_key: dict[str, str] = {}
    duplicate_rows: list[dict[str, str]] = []
    budget_rows: list[str] = []
    invalid_count = 0
    for index, candidate in enumerate(candidate_rows):
        if len(events) >= MAX_EVENTS:
            if isinstance(candidate, Mapping):
                budget_rows.append(_candidate_id(candidate, index))
            continue
        if not isinstance(candidate, Mapping):
            invalid_count += 1
            continue
        key = _event_key(candidate, index)
        duplicate_of = by_key.get(key, "")
        event = _safe_event(candidate, index, duplicate_of=duplicate_of)
        if event is None:
            invalid_count += 1
            continue
        if duplicate_of:
            duplicate_rows.append({"candidateId": event["candidateId"], "duplicateOf": duplicate_of})
            continue
        by_key[key] = event["candidateId"]
        events.append(event)
    input_count = len(candidate_rows)
    return events[:MAX_EVENTS], {
        "inputCount": input_count,
        "eventCount": len(events[:MAX_EVENTS]),
        "duplicateCount": len(duplicate_rows),
        "duplicateRows": duplicate_rows[:MAX_EVENTS],
        "invalidCount": invalid_count,
        "partial": input_count > MAX_EVENTS,
        "budgetUnassessedIds": budget_rows[:MAX_EVENTS],
        "budgetUnassessedCount": len(budget_rows),
    }


def build_semantic_payload(
    candidates: Iterable[Mapping[str, Any]] | None,
    pinned_context: Mapping[str, Any] | None,
    *,
    market: str,
    kind: str = "daily",
    analysis_as_of: str = "",
    policy_version: str = SEMANTIC_POLICY_VERSION,
    prompt_version: str = SEMANTIC_PROMPT_VERSION,
    input_byte_limit: int = MAX_INPUT_BYTES,
    adapter_identity: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Build one bounded model payload and its coverage metadata."""

    target_market = _lower(market)
    target_kind = _lower(kind) or "daily"
    baseline = _safe_baseline(pinned_context, target_market)
    hypotheses = _extract_hypotheses(pinned_context, target_market)
    events, coverage = _dedupe_events(candidates)
    if not baseline:
        return None, {**coverage, "status": "not_evaluated", "reason": "baseline_missing"}
    if baseline.get("status") != "baseline_ready":
        reason = baseline.get("status") or "baseline_missing"
        return None, {**coverage, "status": "not_evaluated", "reason": reason}
    if not events:
        return None, {**coverage, "status": "not_evaluated", "reason": "no_eligible_events"}
    payload_base = {
        "target": SEMANTIC_TARGET,
        "instructions": (
            "평가 대상은 일간 뉴스 사건이다. 제공된 사건·주장·출처 ID와 고정된 baseline checkpoint만 사용한다. "
            "각 사건을 가설별 supporting/challenging/neutral로 판정하고, 근거가 없으면 해당 효과를 생략한다. "
            "자료가 부족하면 변화 없음으로 추정하지 말고 assessmentStatus=not_evaluated로 남긴다. "
            "후보의 editorial/selection role 선언은 무시한다."
        ),
        "policyVersion": _safe_id(policy_version) or SEMANTIC_POLICY_VERSION,
        "promptVersion": _safe_id(prompt_version) or SEMANTIC_PROMPT_VERSION,
        "adapterIdentity": _safe_id(adapter_identity),
        "market": target_market,
        "kind": target_kind,
        "analysisAsOf": _bounded_text(analysis_as_of, 64),
        "baseline": baseline,
        "hypotheses": hypotheses,
        "events": [],
        "outputSchema": {
            "target": SEMANTIC_TARGET,
            "inputHash": "echo payload.inputHash exactly",
            "verdictChoices": list(SEMANTIC_VERDICTS),
            "relationChoices": sorted(ROLE_CHOICES),
            "importanceChoices": sorted(IMPORTANCE_CHOICES),
            "events": [{
                "eventRef": "one exact payload eventRef",
                "assessmentStatus": "assessed | insufficient_evidence | not_evaluated | failed",
                "verdict": " | ".join(SEMANTIC_VERDICTS) + " (only when assessed)",
                "currentEvidenceRefs": ["exact payload sourceIds"],
                "claimRefs": ["exact payload claimIds"],
                "explanationImportance": "high | medium | low | unknown",
                "judgmentUpdateImportance": "high | medium | low | unknown",
                "hypothesisEffects": [{
                    "hypothesisRef": "exact payload hypothesisId",
                    "relation": "supporting | challenging | neutral",
                    "changedDimensions": [],
                    "currentEvidenceRefs": ["exact payload sourceIds"],
                    "claimRefs": ["exact payload claimIds"],
                }],
            }],
        },
    }
    # The transport may only have a byte budget (for example, a CLI without a
    # tokenizer).  Fill the payload in input order until the serialized budget
    # is exhausted.  Overflow IDs remain metadata-only diagnostics.
    try:
        byte_limit = max(0, int(input_byte_limit))
    except (TypeError, ValueError):
        byte_limit = MAX_INPUT_BYTES
    # The transport sends the instruction string as a prompt *and* the JSON
    # payload as context.  Reserve the prompt bytes before fitting events so
    # the final request, including prompt overhead and inputHash, stays inside
    # the caller's UTF-8 budget.
    prompt_bytes = len(str(payload_base.get("instructions") or "").encode("utf-8"))
    payload_byte_limit = max(0, byte_limit - prompt_bytes)
    # Reserve the fixed-size SHA-256 field while fitting; otherwise adding the
    # final inputHash after selection would cross the transport boundary.
    payload_base_for_size = {**payload_base, "inputHash": "0" * 64}
    included: list[dict[str, Any]] = []
    overflow: list[str] = list(coverage.get("budgetUnassessedIds") or [])[:MAX_EVENTS]
    for event in events:
        candidate = {**payload_base_for_size, "events": [*included, event]}
        if len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= payload_byte_limit:
            included.append(event)
        else:
            overflow.append(str(event.get("candidateId") or event.get("eventRef") or ""))
    if not included:
        return None, {**coverage, "status": "not_evaluated", "reason": "input_limit", "budgetUnassessedIds": overflow[:MAX_EVENTS]}
    payload = {**payload_base_for_size, "events": included}
    hash_input = {key: value for key, value in payload.items() if key != "inputHash"}
    payload["inputHash"] = _hash_payload(hash_input)
    payload_only_bytes = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    payload_bytes = prompt_bytes + payload_only_bytes
    coverage.update({
        "status": "ready",
        "reason": "",
        "eventCount": len(included),
        "budgetUnassessedCount": len(overflow),
        "budgetUnassessedIds": overflow[:MAX_EVENTS],
        "partial": bool(coverage.get("partial") or overflow),
        "inputBytes": payload_bytes,
        "payloadBytes": payload_only_bytes,
        "promptBytes": prompt_bytes,
        "inputTokensEstimate": _estimate_tokens(payload),
        "inputHash": payload["inputHash"],
    })
    return payload, coverage


def _output_input_hash(raw: Mapping[str, Any]) -> str:
    return _safe_id(raw.get("inputHash") or raw.get("input_hash"))


def _output_events(raw: Mapping[str, Any]) -> list[Any]:
    value = raw.get("events")
    if value is None:
        value = raw.get("assessments")
    if value is None:
        value = raw.get("eventAssessments")
    return list(value) if isinstance(value, (list, tuple)) else []


def _find_effects(raw_event: Mapping[str, Any]) -> list[Any]:
    value = raw_event.get("hypothesisEffects")
    if value is None:
        value = raw_event.get("hypotheses")
    return list(value) if isinstance(value, (list, tuple)) else []


def _importance(raw: Mapping[str, Any], *keys: str) -> tuple[str, bool]:
    present = False
    value = ""
    for key in keys:
        if key in raw:
            present = True
            value = _lower(raw.get(key))
            break
    if not present:
        return "unknown", True
    return value, value in IMPORTANCE_CHOICES


def _valid_refs(values: Any, allowed: set[str], *, limit: int = 8) -> list[str] | None:
    if values is None:
        return []
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    result = [_safe_id(value) for value in raw if _safe_id(value)]
    if any(value not in allowed for value in result):
        return None
    return list(dict.fromkeys(result))[:limit]


def _safe_result_row(
    raw_event: Mapping[str, Any],
    event_by_ref: Mapping[str, Mapping[str, Any]],
    hypothesis_ids: set[str],
) -> dict[str, Any] | None:
    event_ref = _safe_id(raw_event.get("eventRef") or raw_event.get("eventKey") or raw_event.get("id"))
    event = event_by_ref.get(event_ref)
    if event is None:
        return None
    source_ids = set(event.get("sourceIds") or [])
    claim_ids = {str(claim.get("claimId")) for claim in event.get("claims") or [] if isinstance(claim, Mapping)}
    event_sources = _valid_refs(
        raw_event.get("currentEvidenceRefs") or raw_event.get("sourceIds") or raw_event.get("evidenceRefs"),
        source_ids,
    )
    if event_sources is None:
        return None
    event_claims = _valid_refs(raw_event.get("claimRefs") or raw_event.get("claimIds"), claim_ids)
    if event_claims is None:
        return None
    # A minimal fixture may expose one claim only through the input.  It is
    # safe to infer that single claim, but never to guess among multiple
    # claims; an adapter with several claims must identify which it used.
    if not event_claims and len(claim_ids) == 1:
        event_claims = [next(iter(claim_ids))]
    # A validated event must identify the actual source/claim relation.  A
    # model cannot make a free-standing semantic assertion just by echoing an
    # event ID.
    if not event_sources or not event_claims:
        return None
    status = _lower(raw_event.get("assessmentStatus") or raw_event.get("status"))
    verdict = _lower(raw_event.get("verdict") or raw_event.get("semanticVerdict"))
    if status in {"", "assessed", "evaluated"}:
        status = "assessed"
    elif status not in {"not_evaluated", "insufficient_evidence", "failed"}:
        return None
    if status == "assessed" and verdict not in SEMANTIC_VERDICTS:
        return None
    if status != "assessed":
        # The row remains useful for coverage diagnostics, but no valid
        # semantic verdict or relationship is inferred.
        verdict = ""
    explanation, explanation_ok = _importance(raw_event, "explanationImportance", "descriptionImportance")
    judgment, judgment_ok = _importance(raw_event, "judgmentUpdateImportance", "judgmentImportance", "beliefUpdateImportance")
    novelty, novelty_ok = _importance(raw_event, "novelty", "newness")
    if not explanation_ok or not judgment_ok or not novelty_ok:
        return None
    effects: list[dict[str, Any]] = []
    effect_invalid = False
    for raw_effect in _find_effects(raw_event):
        if not isinstance(raw_effect, Mapping):
            effect_invalid = True
            continue
        hypothesis_ref = _safe_id(raw_effect.get("hypothesisRef") or raw_effect.get("hypothesisId") or raw_effect.get("checkpointId"))
        relation = _lower(raw_effect.get("relation") or raw_effect.get("role") or raw_effect.get("evidenceRole"))
        if hypothesis_ref not in hypothesis_ids or relation not in ROLE_CHOICES:
            effect_invalid = True
            continue
        effect_sources = _valid_refs(
            raw_effect.get("currentEvidenceRefs") or raw_effect.get("sourceIds") or event_sources,
            source_ids,
        )
        effect_claims = _valid_refs(raw_effect.get("claimRefs") or raw_effect.get("claimIds") or event_claims, claim_ids)
        if effect_sources is None or effect_claims is None or not effect_sources or not effect_claims:
            effect_invalid = True
            continue
        dimensions = raw_effect.get("changedDimensions") or raw_effect.get("dimensions") or []
        if not isinstance(dimensions, (list, tuple)):
            effect_invalid = True
            continue
        dimensions_safe = [_bounded_text(value, 48) for value in dimensions if _bounded_text(value, 48)][:MAX_DIMENSIONS]
        effects.append({
            "hypothesisRef": hypothesis_ref,
            "relation": relation,
            "changedDimensions": dimensions_safe,
            "reason": _bounded_text(raw_effect.get("reason"), MAX_REASON_CHARS),
            "currentEvidenceRefs": effect_sources,
            "claimRefs": effect_claims,
        })
    if status == "assessed" and effect_invalid:
        # A missing/invalid hypothesis relationship is not neutral.  It is an
        # unverified event and therefore cannot enter active selection.
        status = "not_evaluated"
        verdict = ""
        effects = []
    return {
        "eventRef": event_ref,
        "candidateId": event.get("candidateId", ""),
        "assessmentStatus": status,
        "verdict": verdict,
        "semanticVerdict": verdict,
        "newFact": _bounded_text(raw_event.get("newFact") or raw_event.get("summary"), MAX_REASON_CHARS),
        "hypothesisEffects": effects,
        "explanationImportance": explanation,
        "judgmentUpdateImportance": judgment,
        "novelty": novelty,
        # Keep the proposal vocabulary available without making the two axes a
        # single materiality score.
        "materiality": explanation,
        "editorialRoles": [],
        "currentEvidenceRefs": event_sources,
        "claimRefs": event_claims,
        "correction": bool(event.get("isCorrection")),
        "duplicateOf": event.get("duplicateOf", ""),
    }


def _derive_editorial_roles(row: dict[str, Any], event: Mapping[str, Any], hypothesis_ids: set[str]) -> list[str]:
    effects = row.get("hypothesisEffects") or []
    roles: list[str] = []
    if effects:
        roles.append("checkpoint_result")
        if (
            any(effect.get("relation") == "challenging" for effect in effects)
            or row.get("judgmentUpdateImportance") in {"high", "medium"}
        ):
            roles.append("judgment_change")
    if not roles:
        # An event which did not establish a relationship to a prior
        # hypothesis is an open/new signal.  It is not neutral and should not
        # be promoted to core flow by the existence of unrelated hypotheses.
        roles.append("new_signal")
    return roles[:2]


def validate_semantic_output(
    raw: Mapping[str, Any] | None,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate callback output against this exact target/input payload."""

    if not isinstance(raw, Mapping):
        return {"status": "not_evaluated", "reason": "invalid_output", "rows": [], "invalidCount": 1}
    expected_hash = _safe_id(payload.get("inputHash"))
    if _output_input_hash(raw) != expected_hash:
        return {"status": "not_evaluated", "reason": "input_hash_mismatch", "rows": [], "invalidCount": 1}
    if _safe_id(raw.get("target")) != SEMANTIC_TARGET:
        # An existing Change Intelligence result can have valid IDs for a
        # different artifact.  It is never reused for this selection target.
        return {"status": "not_evaluated", "reason": "target_mismatch", "rows": [], "invalidCount": 1}
    event_by_ref = {str(item.get("eventRef")): item for item in payload.get("events") or [] if isinstance(item, Mapping)}
    hypothesis_ids = {str(item.get("hypothesisId")) for item in payload.get("hypotheses") or [] if isinstance(item, Mapping)}
    rows: list[dict[str, Any]] = []
    invalid = 0
    seen: set[str] = set()
    for raw_event in _output_events(raw):
        if not isinstance(raw_event, Mapping):
            invalid += 1
            continue
        event_ref = _safe_id(raw_event.get("eventRef") or raw_event.get("eventKey") or raw_event.get("id"))
        if event_ref in seen:
            invalid += 1
            continue
        row = _safe_result_row(raw_event, event_by_ref, hypothesis_ids)
        if row is None:
            invalid += 1
            continue
        seen.add(event_ref)
        row["editorialRoles"] = _derive_editorial_roles(row, event_by_ref[event_ref], hypothesis_ids)
        rows.append(row)
    if not rows:
        return {"status": "not_evaluated", "reason": "no_valid_results", "rows": [], "invalidCount": invalid}
    assessed = sum(1 for row in rows if row["assessmentStatus"] == "assessed")
    status = "evaluated" if assessed else "not_evaluated"
    reason = "" if assessed else "no_assessed_results"
    return {
        "status": status,
        "reason": reason,
        "rows": rows,
        "invalidCount": invalid,
        "coverageStatus": "partial" if invalid or len(rows) < len(event_by_ref) else "complete",
        "inputHash": expected_hash,
    }


def _cache_safe(result: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only bounded, source-ID-oriented evaluation metadata in cache."""

    safe = {
        "status": _lower(result.get("status")) or "not_evaluated",
        "reason": _lower(result.get("reason")),
        "rows": [],
        "invalidCount": int(result.get("invalidCount") or 0),
        "coverageStatus": _lower(result.get("coverageStatus")),
        "inputHash": _safe_id(result.get("inputHash")),
    }
    for row in list(result.get("rows") or [])[:MAX_EVENTS]:
        if not isinstance(row, Mapping):
            continue
        item = {
            key: deepcopy(row.get(key))
            for key in (
                "eventRef", "candidateId", "assessmentStatus", "verdict", "semanticVerdict",
                "hypothesisEffects", "explanationImportance", "judgmentUpdateImportance",
                "materiality", "novelty", "editorialRoles", "currentEvidenceRefs", "claimRefs",
                "correction", "duplicateOf",
            )
        }
        item["newFact"] = _bounded_text(row.get("newFact"), MAX_REASON_CHARS)
        safe["rows"].append(item)
    return safe


@dataclass
class _CacheEntry:
    created: float
    result: dict[str, Any]


class BoundedSemanticCache:
    """Small process cache keyed only by the complete input hash."""

    def __init__(self, *, max_entries: int = MAX_CACHE_ENTRIES, ttl_seconds: float = MAX_CACHE_AGE_SECONDS) -> None:
        self.max_entries = max(0, min(int(max_entries), MAX_CACHE_ENTRIES))
        self.ttl_seconds = max(0.0, min(float(ttl_seconds), MAX_CACHE_AGE_SECONDS))
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def _expired(self, entry: _CacheEntry, now: float) -> bool:
        return self.ttl_seconds <= 0 or now - entry.created >= self.ttl_seconds

    def get(self, input_hash: str) -> dict[str, Any] | None:
        key = _safe_id(input_hash)
        if not key or self.max_entries <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._expired(entry, now):
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry.result)

    def put(self, input_hash: str, result: Mapping[str, Any]) -> None:
        key = _safe_id(input_hash)
        if not key or self.max_entries <= 0:
            return
        with self._lock:
            self._entries[key] = _CacheEntry(time.monotonic(), _cache_safe(result))
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"entries": len(self._entries), "maxEntries": self.max_entries, "ttlSeconds": self.ttl_seconds}


class SemanticRequestLedger:
    """Thread-safe one-semantic-batch ledger for a generation run."""

    def __init__(
        self,
        *,
        max_batches_per_market: int = 1,
        deadline: float | None = None,
        cancelled: Callable[[], bool] | object | None = None,
    ) -> None:
        self.max_batches_per_market = max(0, min(int(max_batches_per_market), 1))
        self.deadline = deadline
        self.cancelled = cancelled
        self._used: dict[str, int] = {}
        self._records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def _is_cancelled(self) -> bool:
        if self.cancelled is None:
            return False
        try:
            return bool(self.cancelled() if callable(self.cancelled) else self.cancelled.is_set())
        except Exception:
            return True

    def unavailable_reason(self, market: str) -> str:
        if self._is_cancelled():
            return "cancelled"
        if self.deadline is not None:
            try:
                if time.monotonic() >= float(self.deadline):
                    return "deadline_expired"
            except (TypeError, ValueError):
                return "deadline_invalid"
        if self._used.get(market, 0) >= self.max_batches_per_market:
            return "semantic_batch_exhausted"
        return ""

    def claim(self, market: str, input_hash: str) -> tuple[bool, str]:
        market_key = _lower(market)
        with self._lock:
            reason = self.unavailable_reason(market_key)
            if reason:
                self._records.append({"market": market_key, "inputHash": _safe_id(input_hash), "status": "skipped", "reason": reason})
                return False, reason
            self._used[market_key] = self._used.get(market_key, 0) + 1
            self._records.append({"market": market_key, "inputHash": _safe_id(input_hash), "status": "claimed", "reason": ""})
            return True, ""

    def finish(self, market: str, *, status: str, reason: str = "") -> None:
        market_key = _lower(market)
        with self._lock:
            for row in reversed(self._records):
                if row.get("market") == market_key and row.get("status") == "claimed":
                    row["status"] = _lower(status) or "finished"
                    row["reason"] = _lower(reason)
                    break

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "maxBatchesPerMarket": self.max_batches_per_market,
                "used": dict(self._used),
                "records": deepcopy(self._records[-16:]),
            }


_PROCESS_CACHE = BoundedSemanticCache()


def clear_semantic_cache() -> None:
    _PROCESS_CACHE.clear()


def _callback_can_receive_contract(callback: Callable[..., Any]) -> bool:
    """Require the new payload callback contract; do not guess old adapters."""

    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters
    if not parameters:
        return False
    # A callable accepting **kwargs is fine; otherwise the two keyword names
    # are required so the timeout/output contract cannot silently disappear.
    has_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    return has_kwargs or {"timeout_seconds", "max_output_tokens"}.issubset(parameters)


def _invoke_callback(
    callback: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    timeout_seconds: float,
    cancelled: Callable[[], bool] | object | None,
) -> tuple[dict[str, Any] | None, str]:
    """Invoke one injected callback with a cooperative deadline contract.

    The transport owns cancellation of a provider request.  Keeping this call
    synchronous preserves the caller's ContextVar/job budget and avoids a
    timed-out daemon thread continuing into the next generation stage.  The
    callback receives the remaining timeout and this core checks the same
    deadline again before accepting its result.
    """

    if cancelled is not None:
        try:
            if bool(cancelled() if callable(cancelled) else cancelled.is_set()):
                return None, "cancelled"
        except Exception:
            return None, "cancelled"
    try:
        value = callback(payload, timeout_seconds=timeout_seconds, max_output_tokens=MAX_OUTPUT_TOKENS)
    except Exception:
        return None, "callback_failed"
    if cancelled is not None:
        try:
            if bool(cancelled() if callable(cancelled) else cancelled.is_set()):
                return None, "cancelled"
        except Exception:
            return None, "cancelled"
    if timeout_seconds <= 0:
        return None, "deadline_expired"
    if not isinstance(value, Mapping):
        return None, "invalid_output"
    return dict(value), ""


def evaluate_news_semantics(
    candidates: Iterable[Mapping[str, Any]] | None,
    pinned_context: Mapping[str, Any] | None,
    *,
    market: str,
    kind: str = "daily",
    mode: str = "off",
    selected_markets: Iterable[str] | None = None,
    analysis_as_of: str = "",
    semantic_callback: Callable[..., Any] | None = None,
    adapter_limits_verified: bool | None = None,
    request_ledger: SemanticRequestLedger | None = None,
    cache: BoundedSemanticCache | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | object | None = None,
    input_byte_limit: int = MAX_INPUT_BYTES,
    output_byte_limit: int = MAX_OUTPUT_BYTES,
    adapter_identity: str = "",
) -> dict[str, Any]:
    """Evaluate one bounded daily-news batch without calling a provider by default."""

    target_market = _lower(market)
    target_kind = _lower(kind) or "daily"
    requested_mode = _lower(mode) if _lower(mode) in {"off", "shadow", "active"} else "off"
    base = {
        "target": SEMANTIC_TARGET,
        "market": target_market,
        "kind": target_kind,
        "mode": requested_mode,
        "status": "not_evaluated",
        "reason": "",
        "rows": [],
        "coverageStatus": "not_run",
        "cacheHit": False,
        "requestCount": 0,
        "inputTokensEstimate": 0,
        "inputBytes": 0,
        "outputTokensEstimate": 0,
    }
    if requested_mode == "off":
        base["reason"] = "mode_off"
        return base
    if target_kind != "daily" or target_market not in {"us", "kr"}:
        base["reason"] = "unsupported_scope"
        return base
    if selected_markets is not None and target_market not in {_lower(item) for item in selected_markets}:
        base["reason"] = "market_not_selected"
        return base
    payload, coverage = build_semantic_payload(
        candidates,
        pinned_context,
        market=target_market,
        kind=target_kind,
        analysis_as_of=(
            analysis_as_of
            or ((pinned_context or {}).get("analysisAsOf", "") if isinstance(pinned_context, Mapping) else "")
        ),
        input_byte_limit=input_byte_limit,
        adapter_identity=_hash_payload({"adapter": adapter_identity or getattr(semantic_callback, "cache_identity", "")}),
    )
    base.update({
        "candidateCount": int(coverage.get("inputCount") or 0),
        "eventCount": int(coverage.get("eventCount") or 0),
        "budgetUnassessedCount": int(coverage.get("budgetUnassessedCount") or 0),
        "budgetUnassessedIds": list(coverage.get("budgetUnassessedIds") or [])[:MAX_EVENTS],
        "duplicateCount": int(coverage.get("duplicateCount") or 0),
        "invalidCount": int(coverage.get("invalidCount") or 0),
        "coverageStatus": "partial" if coverage.get("partial") else coverage.get("status", "not_run"),
        "inputHash": _safe_id(coverage.get("inputHash")),
        "inputTokensEstimate": int(coverage.get("inputTokensEstimate") or 0),
        "inputBytes": int(coverage.get("inputBytes") or 0),
    })
    if payload is None:
        base["reason"] = _lower(coverage.get("reason")) or "not_evaluated"
        return base
    if base["inputTokensEstimate"] > MAX_INPUT_TOKENS:
        base["reason"] = "input_limit"
        base["coverageStatus"] = "partial"
        return base
    if semantic_callback is None:
        base["reason"] = "callback_missing"
        return base
    if not _callback_can_receive_contract(semantic_callback):
        base["reason"] = "callback_contract_unverified"
        return base
    if adapter_limits_verified is None:
        adapter_limits_verified = bool(getattr(semantic_callback, "limits_verified", False))
    if not adapter_limits_verified:
        base["reason"] = "adapter_limits_unverified"
        return base
    cache_obj = cache or _PROCESS_CACHE
    cached = cache_obj.get(str(payload["inputHash"]))
    if cached is not None:
        cached = deepcopy(cached)
        cached.update({
            "target": SEMANTIC_TARGET,
            "market": target_market,
            "kind": target_kind,
            "mode": requested_mode,
            "cacheHit": True,
            "candidateCount": base.get("candidateCount", 0),
            "eventCount": base.get("eventCount", 0),
            "budgetUnassessedCount": base.get("budgetUnassessedCount", 0),
            "budgetUnassessedIds": list(base.get("budgetUnassessedIds") or [])[:MAX_EVENTS],
            "duplicateCount": base.get("duplicateCount", 0),
            "inputTokensEstimate": base.get("inputTokensEstimate", 0),
            "inputBytes": base.get("inputBytes", 0),
            "requestCount": 0,
        })
        return cached
    ledger = request_ledger or SemanticRequestLedger(deadline=deadline, cancelled=cancelled)
    allowed, reason = ledger.claim(target_market, str(payload["inputHash"]))
    if not allowed:
        base["reason"] = reason
        return base
    now = time.monotonic()
    local_deadline = now + MAX_TIMEOUT_SECONDS
    if deadline is not None:
        try:
            local_deadline = min(local_deadline, float(deadline))
        except (TypeError, ValueError):
            ledger.finish(target_market, status="not_evaluated", reason="deadline_invalid")
            base["reason"] = "deadline_invalid"
            return base
    # `(now + MAX) - now`는 부동소수점 반올림으로 MAX보다 1ulp 클 수 있다. monotonic 값이 작은
    # 갓 부팅한 Linux CI에서 약 6% 확률로 계약(≤ MAX)을 어겨 콜백이 거절됐다. 상한을 다시 건다.
    timeout_seconds = min(float(MAX_TIMEOUT_SECONDS), max(0.0, local_deadline - now))
    if timeout_seconds <= 0:
        ledger.finish(target_market, status="not_evaluated", reason="deadline_expired")
        base["reason"] = "deadline_expired"
        return base
    result, invoke_reason = _invoke_callback(
        semantic_callback,
        payload,
        timeout_seconds=timeout_seconds,
        cancelled=cancelled,
    )
    base["requestCount"] = 1
    if invoke_reason:
        ledger.finish(target_market, status="not_evaluated", reason=invoke_reason)
        base["reason"] = invoke_reason
        return base
    output_estimate = _estimate_tokens(result or {})
    base["outputTokensEstimate"] = output_estimate
    try:
        output_bytes = len(json.dumps(result or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        output_limit = max(0, int(output_byte_limit))
    except (TypeError, ValueError):
        output_bytes, output_limit = 0, MAX_OUTPUT_BYTES
    base["outputBytes"] = output_bytes
    if output_estimate > MAX_OUTPUT_TOKENS or output_bytes > output_limit:
        ledger.finish(target_market, status="not_evaluated", reason="output_limit")
        base["reason"] = "output_limit"
        return base
    validated = validate_semantic_output(result, payload)
    validated.update({
        "target": SEMANTIC_TARGET,
        "market": target_market,
        "kind": target_kind,
        "mode": requested_mode,
        "cacheHit": False,
        "requestCount": 1,
        "candidateCount": base.get("candidateCount", 0),
        "eventCount": base.get("eventCount", 0),
        "budgetUnassessedCount": base.get("budgetUnassessedCount", 0),
        "budgetUnassessedIds": list(base.get("budgetUnassessedIds") or [])[:MAX_EVENTS],
        "duplicateCount": base.get("duplicateCount", 0),
        "inputTokensEstimate": base.get("inputTokensEstimate", 0),
        "inputBytes": base.get("inputBytes", 0),
        "outputTokensEstimate": output_estimate,
    })
    ledger.finish(target_market, status=validated.get("status", "not_evaluated"), reason=validated.get("reason", ""))
    if validated.get("status") == "evaluated":
        validated["coverageStatus"] = "partial" if coverage.get("partial") or validated.get("invalidCount") else "complete"
        validated["inputHash"] = payload["inputHash"]
        cache_obj.put(str(payload["inputHash"]), validated)
    return validated


__all__ = [
    "EDITORIAL_ROLES",
    "IMPORTANCE_CHOICES",
    "MAX_CACHE_AGE_SECONDS",
    "MAX_CACHE_ENTRIES",
    "MAX_EVENTS",
    "MAX_EXCERPT_CHARS",
    "MAX_INPUT_TOKENS",
    "MAX_INPUT_BYTES",
    "MAX_OUTPUT_TOKENS",
    "MAX_OUTPUT_BYTES",
    "MAX_TIMEOUT_SECONDS",
    "ROLE_CHOICES",
    "SEMANTIC_POLICY_VERSION",
    "SEMANTIC_PROMPT_VERSION",
    "SEMANTIC_TARGET",
    "BoundedSemanticCache",
    "SemanticRequestLedger",
    "build_semantic_payload",
    "clear_semantic_cache",
    "evaluate_news_semantics",
    "validate_semantic_output",
]
