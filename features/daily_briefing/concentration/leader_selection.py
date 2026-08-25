from __future__ import annotations

from features.daily_briefing.concentration.signatures import overlap
from features.daily_briefing.concentration.history import history_metrics


def select_leader_pair(signatures: list[dict], *, mode: str = "shadow", history: list[dict] | None = None) -> dict:
    eligible = []
    for source in signatures:
        if int(source.get("directEvidenceCount") or 0) <= 0:
            continue
        row = dict(source)
        metrics = history_metrics(row, history or [])
        row["history"] = metrics
        repetition_penalty = min(
            0.22,
            0.03 * metrics["recentAppearanceCount"] + 0.07 * metrics["sameCausalPathCount"],
        )
        if metrics["novelCausalPath"]:
            repetition_penalty = 0.0
        row["historyPenalty"] = round(repetition_penalty, 3)
        base_score = float(row.get("baseLeaderScore") or 0)
        row["historyAdjustedScore"] = round(base_score * (1.0 - repetition_penalty), 4)
        eligible.append(row)
    score_key = "historyAdjustedScore" if mode == "active" else "baseLeaderScore"
    eligible.sort(key=lambda row: float(row.get(score_key) or 0), reverse=True)
    original = [str(row.get("candidateId")) for row in eligible[:2]]
    candidate_history = {
        str(row.get("candidateId")): {
            **dict(row.get("history") or {}),
            "penalty": row.get("historyPenalty", 0),
            "adjustedScore": row.get("historyAdjustedScore", 0),
        }
        for row in eligible
    }
    if len(original) < 2:
        return _with_history(
            _decision(mode, original, original, "uncertain", "rules", [], [], ["insufficient_eligible_candidates"]),
            candidate_history,
        )
    left, right = eligible[0], eligible[1]
    metrics = overlap(left, right)
    signals = []
    if any(int((row.get("history") or {}).get("sameCausalPathCount") or 0) > 0 for row in (left, right)):
        signals.append("recent_causal_repetition")
    if left.get("sector") and left.get("sector") == right.get("sector"):
        signals.append("same_sector")
    if metrics["evidence"] >= 0.5:
        signals.append("shared_evidence")
    if metrics["causal"] >= 0.55:
        signals.append("shared_causal_path")
    shared = sorted(set(left.get("catalysts") or []) & set(right.get("catalysts") or []))
    conflict = bool(signals)
    if not conflict or metrics["independentDimensions"]:
        return _with_history(
            _decision(mode, original, original, "allow_pair", "rules", signals, shared, ["independent_dimensions"] if conflict else []),
            candidate_history,
        )
    replacement = next(
        (
            row for row in eligible[2:5]
            if float(row.get("baseLeaderScore") or 0) >= float(right.get("baseLeaderScore") or 0) * 0.6
            and overlap(left, row)["causal"] < 0.55
            and overlap(left, row)["evidence"] < 0.5
        ),
        None,
    )
    final = [original[0], str(replacement.get("candidateId"))] if replacement else original
    return _with_history(_decision(
        mode,
        original,
        final,
        "replace" if replacement else "uncertain",
        "fallback",
        signals,
        shared,
        ["redundant_pair_replaced"] if replacement else ["no_qualified_alternative"],
    ), candidate_history)


def _with_history(decision: dict, candidate_history: dict) -> dict:
    return {**decision, "candidateHistory": candidate_history}


def _decision(mode, original, final, decision, source, signals, shared, reasons) -> dict:
    return {
        "policyVersion": 1,
        "mode": mode,
        "originalPair": original,
        "finalPair": final,
        "decision": decision,
        "decisionSource": source,
        "conflictSignals": signals,
        "sharedDrivers": shared,
        "independentDimensions": reasons if "independent_dimensions" in reasons else [],
        "replacementCandidateId": final[1] if len(final) > 1 and final != original else None,
        "reasonCodes": reasons,
        "agentStatus": "not_needed" if not signals else "unavailable",
    }


def apply_agent_decision(base: dict, response: dict, candidate_ids: set[str]) -> dict:
    decision = str(response.get("decision") or "")
    replacement = str(response.get("replacementCandidateId") or "")
    if decision not in {"allow_pair", "replace", "uncertain"}:
        raise ValueError("invalid_agent_decision")
    if decision == "replace" and replacement not in candidate_ids:
        raise ValueError("agent_candidate_outside_whitelist")
    out = dict(base)
    out["decision"] = decision
    out["decisionSource"] = "agent"
    out["agentStatus"] = "accepted"
    if decision == "replace":
        out["finalPair"] = [base["originalPair"][0], replacement]
        out["replacementCandidateId"] = replacement
    elif decision == "allow_pair":
        out["finalPair"] = list(base["originalPair"])
        out["replacementCandidateId"] = None
    return out


__all__ = ["apply_agent_decision", "select_leader_pair"]
