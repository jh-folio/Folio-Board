from __future__ import annotations

from copy import deepcopy

from features.daily_briefing import news_semantics as semantics


def _candidate(
    identifier: str,
    *,
    source: str | None = None,
    event_key: str | None = None,
    summary: str = "새로운 수요 사실",
    correction_of: str = "",
) -> dict:
    row = {
        "id": identifier,
        "eventKey": event_key or identifier,
        "sourceId": source or f"src-{identifier}",
        "title": summary,
        "summary": summary,
        "claims": [{"claimId": f"claim-{identifier}", "text": summary, "sourceIds": [source or f"src-{identifier}"]}],
    }
    if correction_of:
        row["correctionOf"] = correction_of
    return row


def _context(*, checkpoints=None, personal="private") -> dict:
    values = [{"id": "cp-a", "item": "수요가 이어지는가"}] if checkpoints is None else checkpoints
    return {
        "analysisAsOf": "2026-09-05T23:00:00Z",
        "baselines": {
            "us": {
                "status": "baseline_ready",
                "pin": {"reportId": "prior-us", "contentHash": "hash", "version": "v1"},
                "report": {
                    "id": "prior-us",
                    "checkpoints": values,
                    "personalOverlay": {"text": personal},
                    "personalNotes": personal,
                },
            }
        },
    }


def _adapter(payload: dict, *, timeout_seconds: float, max_output_tokens: int) -> dict:
    assert payload["target"] == semantics.SEMANTIC_TARGET
    assert timeout_seconds <= semantics.MAX_TIMEOUT_SECONDS
    assert max_output_tokens == semantics.MAX_OUTPUT_TOKENS
    events = []
    for event in payload["events"]:
        events.append({
            "eventRef": event["eventRef"],
            "assessmentStatus": "assessed",
            "verdict": "new_information",
            "currentEvidenceRefs": [event["sourceIds"][0]],
            "claimRefs": [event["claims"][0]["claimId"]],
            "explanationImportance": "high",
            "judgmentUpdateImportance": "low",
            "hypothesisEffects": [{
                "hypothesisRef": payload["hypotheses"][0]["hypothesisId"],
                "relation": "supporting",
                "changedDimensions": ["direction"],
                "currentEvidenceRefs": [event["sourceIds"][0]],
                "claimRefs": [event["claims"][0]["claimId"]],
            }],
        })
    return {"target": payload["target"], "inputHash": payload["inputHash"], "events": events}


def _run(candidates, *, callback=_adapter, **kwargs):
    return semantics.evaluate_news_semantics(
        candidates,
        _context(),
        market="us",
        kind="daily",
        mode="shadow",
        semantic_callback=callback,
        adapter_limits_verified=True,
        **kwargs,
    )


def test_same_fact_can_support_one_hypothesis_and_challenge_another():
    context = _context(checkpoints=[
        {"id": "cp-a", "item": "수요 증가가 지속되는가"},
        {"id": "cp-b", "item": "수요 증가가 꺾이는가"},
    ])
    event = _candidate("e1")

    def adapter(payload, *, timeout_seconds, max_output_tokens):
        return {
            "target": payload["target"], "inputHash": payload["inputHash"], "events": [{
                "eventRef": payload["events"][0]["eventRef"], "assessmentStatus": "assessed",
                "verdict": "new_information", "currentEvidenceRefs": ["src-e1"],
                "claimRefs": ["claim-e1"], "explanationImportance": "medium",
                "judgmentUpdateImportance": "high", "hypothesisEffects": [
                    {"hypothesisRef": "cp-a", "relation": "supporting", "currentEvidenceRefs": ["src-e1"], "claimRefs": ["claim-e1"]},
                    {"hypothesisRef": "cp-b", "relation": "challenging", "currentEvidenceRefs": ["src-e1"], "claimRefs": ["claim-e1"]},
                ],
            }],
        }

    result = semantics.evaluate_news_semantics(
        [event], context, market="us", mode="shadow", semantic_callback=adapter,
        adapter_limits_verified=True,
    )
    effects = result["rows"][0]["hypothesisEffects"]
    assert {(item["hypothesisRef"], item["relation"]) for item in effects} == {
        ("cp-a", "supporting"), ("cp-b", "challenging")
    }


def test_bad_event_source_or_claim_ids_are_not_reused():
    def bad(payload, *, timeout_seconds, max_output_tokens):
        return {
            "target": payload["target"], "inputHash": payload["inputHash"], "events": [{
                "eventRef": "ghost", "assessmentStatus": "assessed", "verdict": "reversal",
                "currentEvidenceRefs": ["not-in-input"], "claimRefs": ["not-in-input"],
                "hypothesisEffects": [],
            }],
        }

    result = _run([_candidate("e1")], callback=bad)
    assert result["status"] == "not_evaluated"
    assert result["reason"] == "no_valid_results"


def test_missing_source_is_not_an_eligible_semantic_event():
    event = _candidate("e1", source="")
    event.pop("sourceId")
    result = _run([event])
    assert result["status"] == "not_evaluated"
    assert result["reason"] == "no_eligible_events"
    assert result["requestCount"] == 0


def test_open_event_without_checkpoint_relation_can_be_assessed_as_new_signal():
    context = _context(checkpoints=[])

    def adapter(payload, *, timeout_seconds, max_output_tokens):
        event = payload["events"][0]
        return {
            "target": payload["target"], "inputHash": payload["inputHash"], "events": [{
                "eventRef": event["eventRef"], "assessmentStatus": "assessed", "verdict": "new_information",
                "currentEvidenceRefs": event["sourceIds"], "claimRefs": [event["claims"][0]["claimId"]],
                "explanationImportance": "medium", "judgmentUpdateImportance": "unknown",
                "hypothesisEffects": [],
            }],
        }

    result = semantics.evaluate_news_semantics(
        [_candidate("e1")], context, market="us", mode="shadow", semantic_callback=adapter,
        adapter_limits_verified=True, cache=semantics.BoundedSemanticCache(),
    )
    assert result["status"] == "evaluated"
    assert result["rows"][0]["editorialRoles"] == ["new_signal"]
    assert result["rows"][0]["hypothesisEffects"] == []


def test_candidate_claim_outside_excerpt_is_not_a_claim_assertion():
    event = _candidate("e1")
    event["claims"][0]["text"] = "fabricated fact not present"
    payload, coverage = semantics.build_semantic_payload([event], _context(), market="us")
    assert payload is not None
    # The adapter input retains the bounded, truthful fallback excerpt claim;
    # the fabricated candidate-side claim text is not sent as evidence.
    assert payload["events"][0]["claims"][0]["text"] == "새로운 수요 사실"


def test_duplicate_observation_is_collapsed_but_correction_is_retained():
    original = _candidate("e1", event_key="same-event")
    duplicate = _candidate("e2", event_key="same-event")
    correction = _candidate("e3", event_key="same-event", correction_of="e1")
    payload, coverage = semantics.build_semantic_payload(
        [original, duplicate, correction], _context(), market="us"
    )
    assert payload is not None
    assert coverage["duplicateCount"] == 1
    assert coverage["eventCount"] == 2
    refs = [event["candidateId"] for event in payload["events"]]
    assert refs == ["e1", "e3"]
    assert payload["events"][1]["isCorrection"] is True


def test_personal_note_change_does_not_change_input_hash_or_cached_result():
    cache = semantics.BoundedSemanticCache()
    context = _context(personal="first")
    calls = []

    def adapter(payload, *, timeout_seconds, max_output_tokens):
        calls.append(payload["inputHash"])
        return _adapter(payload, timeout_seconds=timeout_seconds, max_output_tokens=max_output_tokens)

    first = semantics.evaluate_news_semantics(
        [_candidate("e1")], context, market="us", mode="shadow",
        semantic_callback=adapter, adapter_limits_verified=True, cache=cache,
    )
    context["baselines"]["us"]["report"]["personalNotes"] = "changed"
    context["baselines"]["us"]["report"]["personalOverlay"]["text"] = "changed"
    second = semantics.evaluate_news_semantics(
        [_candidate("e1")], context, market="us", mode="shadow",
        semantic_callback=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("cache miss")),
        adapter_limits_verified=True, cache=cache,
    )
    assert first["inputHash"] == second["inputHash"]
    assert second["cacheHit"] is True
    assert len(calls) == 1


def test_partial_byte_budget_marks_overflow_without_calling_it():
    events = [_candidate(f"e{i}", summary=("fact " + str(i) + " ") * 150) for i in range(24)]
    captured = []

    def adapter(payload, *, timeout_seconds, max_output_tokens):
        captured.append(payload)
        return _adapter(payload, timeout_seconds=timeout_seconds, max_output_tokens=max_output_tokens)

    result = _run(events, callback=adapter, input_byte_limit=6_000)
    assert result["status"] == "evaluated"
    assert result["coverageStatus"] == "partial"
    assert result["budgetUnassessedCount"] > 0
    assert len(captured[0]["events"]) < 24


def test_event_cap_marks_candidates_beyond_24_as_budget_unassessed():
    events = [_candidate(f"e{i}") for i in range(30)]
    payload, coverage = semantics.build_semantic_payload(events, _context(), market="us")
    assert payload is not None
    assert len(payload["events"]) == 24
    assert coverage["budgetUnassessedCount"] == 6
    assert coverage["partial"] is True


def test_cache_key_changes_when_external_event_changes():
    cache = semantics.BoundedSemanticCache()
    first = _run([_candidate("e1")], cache=cache)
    changed = _candidate("e1", summary="수요 감소라는 다른 사실")
    second = _run([changed], cache=cache)
    assert first["cacheHit"] is False
    assert second["cacheHit"] is False
    assert first["inputHash"] != second["inputHash"]


def test_modes_and_unverified_adapter_do_zero_callback_calls():
    calls = []

    def adapter(payload, *, timeout_seconds, max_output_tokens):
        calls.append(1)
        return _adapter(payload, timeout_seconds=timeout_seconds, max_output_tokens=max_output_tokens)

    candidates = [_candidate("e1")]
    for kwargs, reason in (
        ({"mode": "off"}, "mode_off"),
        ({"mode": "shadow", "kind": "weekly"}, "unsupported_scope"),
        ({"mode": "shadow", "selected_markets": ["kr"]}, "market_not_selected"),
        ({"mode": "shadow", "adapter_limits_verified": False}, "adapter_limits_unverified"),
    ):
        result = semantics.evaluate_news_semantics(
            candidates, _context(), market="us", semantic_callback=adapter, **kwargs
        )
        assert result["reason"] == reason
        assert result["requestCount"] == 0
    assert calls == []


def test_request_ledger_allows_one_batch_then_rejects_changed_input():
    ledger = semantics.SemanticRequestLedger()
    first = _run([_candidate("e1")], request_ledger=ledger)
    second = _run([_candidate("e2")], request_ledger=ledger)
    assert first["status"] == "evaluated"
    assert second["status"] == "not_evaluated"
    assert second["reason"] == "semantic_batch_exhausted"
    assert ledger.snapshot()["used"] == {"us": 1}


def test_not_evaluated_is_not_no_new_information():
    result = _run(
        [_candidate("e1")],
        callback=lambda *_a, **_k: {"bad": True},
        cache=semantics.BoundedSemanticCache(),
    )
    assert result["status"] == "not_evaluated"
    assert result["reason"] in {"input_hash_mismatch", "no_valid_results"}
    assert all(row.get("verdict") != "no_new_information" for row in result.get("rows", []))


def test_the_callback_timeout_never_exceeds_the_contract_maximum(monkeypatch):
    """`(now + MAX) - now`가 반올림으로 MAX를 넘는 monotonic 값에서도 계약을 지킨다 (Ubuntu CI 간헐 실패)."""
    maximum = float(semantics.MAX_TIMEOUT_SECONDS)
    now = next(n for n in (i * 0.013 + 0.0071 for i in range(1, 200_000)) if (n + maximum) - n > maximum)
    monkeypatch.setattr(semantics.time, "monotonic", lambda: now)
    seen = []

    def adapter(payload, *, timeout_seconds, max_output_tokens):
        seen.append(timeout_seconds)
        return _adapter(payload, timeout_seconds=timeout_seconds, max_output_tokens=max_output_tokens)

    result = _run([_candidate("e-rounding")], callback=adapter, cache=semantics.BoundedSemanticCache())
    assert seen == [maximum]
    assert result["status"] == "evaluated"
