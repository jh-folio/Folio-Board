from __future__ import annotations

from features.daily_briefing.concentration.signatures import overlap


def select_leader_pair(signatures: list[dict], *, mode: str = "shadow") -> dict:
    eligible = [row for row in signatures if int(row.get("directEvidenceCount") or 0) > 0]
    eligible.sort(key=lambda row: float(row.get("baseLeaderScore") or 0), reverse=True)
    original = [str(row.get("candidateId")) for row in eligible[:2]]
    if len(original) < 2:
        return _decision(mode, original, original, "uncertain", "rules", [], [], ["insufficient_eligible_candidates"])
    left, right = eligible[0], eligible[1]
    metrics = overlap(left, right)
    signals = []
    if left.get("sector") and left.get("sector") == right.get("sector"):
        signals.append("same_sector")
    if metrics["evidence"] >= 0.5:
        signals.append("shared_evidence")
    if metrics["causal"] >= 0.55:
        signals.append("shared_causal_path")
    shared = sorted(set(left.get("catalysts") or []) & set(right.get("catalysts") or []))
    conflict = bool(signals)
    if not conflict or metrics["independentDimensions"]:
        return _decision(mode, original, original, "allow_pair", "rules", signals, shared, ["independent_dimensions"] if conflict else [])
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
    return _decision(
        mode,
        original,
        final,
        "replace" if replacement else "uncertain",
        "fallback",
        signals,
        shared,
        ["redundant_pair_replaced"] if replacement else ["no_qualified_alternative"],
    )


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
