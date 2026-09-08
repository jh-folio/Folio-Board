from __future__ import annotations

import json
import sqlite3

import features.market_memory.checkpoint_verdicts as checkpoint_verdicts
import features.market_memory.evidence_roles as roles
import features.market_memory.regime_v2 as regime_v2
from features.market_memory.memory import connect, init_db
from features.market_memory.regime_v2 import classify_evidence, refresh_regime_state


AS_OF = "2026-09-01T00:00:00+00:00"
STATE_ID = "state-1"
STATE_KEY = "ai_power"


def _seed(db_path: str, *, memory_count: int = 1, checkpoint: list | None = None) -> None:
    conn = connect(db_path)
    init_db(conn)
    try:
        conn.execute(
            """
            INSERT INTO market_narrative_states (
                state_id, state_key, state_label, story, story_family, status, bias,
                summary, rationale, effective_from, updated_at, next_checkpoints_json
            ) VALUES (?, ?, ?, ?, ?, 'active', 'bullish', ?, ?, '2026-08-01', ?, ?)
            """,
            (
                STATE_ID, STATE_KEY, "AI 전력 수요", STATE_KEY, "AI 전력",
                "AI 전력 수요가 늘고 있다", "전력 병목이 이어진다", AS_OF,
                json.dumps(checkpoint or [], ensure_ascii=False),
            ),
        )
        for index in range(memory_count):
            memory_id = f"mem-{index:02d}"
            conn.execute(
                """
                INSERT INTO market_memory (
                    memory_id, as_of, date, title, summary, story, story_family,
                    story_thesis, state_key, state_label, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id, AS_OF, "2026-08-31", f"전력 수요 가이던스 상향 {index}",
                    "AI 데이터센터 전력 수요가 strong growth를 보인다", STATE_KEY, "AI 전력",
                    "AI 전력 수요 확대", STATE_KEY, "AI 전력 수요", AS_OF,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _role_rows(db_path: str) -> list[sqlite3.Row]:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT * FROM market_evidence_roles ORDER BY memory_id"
        ).fetchall()
    finally:
        conn.close()


def test_basis_hash_is_nfkc_canonical_and_excludes_net_effect(tmp_path):
    state = {
        "state_key": "ＡＩ   power",
        "state_label": "전력  수요",
        "story": "story",
        "story_family": "family",
        "summary": "요약",
        "rationale": "근거",
        "bias": "bullish",
        "net_effect": "risk_pressure",
    }
    memory = {
        "memory_id": "mem-1",
        "date": "2026-08-31",
        "title": "ＡＩ  전력",
        "summary": "요약",
        "story_thesis": "확대",
        "net_effect": "benefit",
    }
    first = roles.basis_hash(state, memory)
    state["net_effect"] = "tailwind"
    memory["net_effect"] = "downside_pressure"
    assert roles.basis_hash(state, memory) == first
    state["state_label"] = "전력 수요 변화"
    assert roles.basis_hash(state, memory) != first


def test_role_context_is_the_exact_canonical_basis_without_internal_hashes():
    state = {
        "state_key": "ＡＩ   power", "state_label": "전력  수요", "story": "story",
        "story_family": "family", "summary": "상태  요약", "rationale": "근거\u3000문장", "bias": "bullish",
    }
    memory = {
        "memory_id": "mem-1", "date": "2026-08-31", "title": "ＡＩ  전력",
        "summary": "메모리  요약", "story_thesis": "확대\u3000전제",
    }
    candidate = roles._role_candidate(state, memory, ["ＡＩ  전력"])
    context = roles.role_candidates_for_context([candidate])[0]

    assert context["state"] == roles.basis_payload(state, memory)["state"]
    assert context["memory"] == roles.basis_payload(state, memory)["memory"]
    assert context["stateKey"] == context["state"]["stateKey"]
    assert context["memoryId"] == context["memory"]["memoryId"]
    assert set(context) == {"stateKey", "memoryId", "state", "memory"}
    assert not {"basisHash", "classifierVersion", "matchedTerms"} & set(context)


def test_conservative_rule_fallback_ignores_net_effect_and_ambiguous_bias():
    assert classify_evidence("guidance raise and strong growth", {"bias": "bullish"}) == "supporting"
    assert classify_evidence("guidance cut and weak demand", {"bias": "bullish"}) == "challenging"
    assert classify_evidence("risk and downside pressure", {"bias": "bearish"}) == "supporting"
    assert classify_evidence("surge and recovery", {"bias": "bearish"}) == "challenging"
    assert classify_evidence("risk and pressure", {"bias": "mixed", "net_effect": "benefit"}) == "neutral"
    assert classify_evidence("risk and pressure", {"bias": "", "net_effect": "risk_pressure"}) == "neutral"


def test_primary_candidates_are_bounded_and_deterministic(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=52)

    selection = roles.build_role_candidates(db_path, as_of=AS_OF)

    assert selection["candidateCount"] == 52
    assert len(selection["selected"]) == 50
    assert [item["memoryId"] for item in selection["selected"][:3]] == ["mem-00", "mem-01", "mem-02"]


def test_invalid_items_fall_back_without_discarding_valid_llm_roles(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=2)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    first, second = selection["selected"]

    summary = roles.classify_role_payload(
        db_path,
        selection,
        {
            "evidenceRoles": [
                {"stateKey": first["stateKey"], "memoryId": first["memoryId"], "role": "supporting"},
                {"stateKey": "unknown", "memoryId": "bad", "role": "challenging"},
                {"stateKey": second["stateKey"], "memoryId": second["memoryId"], "role": "not-an-enum"},
            ]
        },
    )

    rows = _role_rows(db_path)
    assert summary["classifiedCount"] == 1
    assert summary["ruleFallbackCount"] == 1
    assert summary["invalidCount"] >= 2
    assert [(row["memory_id"], row["role_source"]) for row in rows] == [
        ("mem-00", "llm"), ("mem-01", "rule")
    ]
    assert rows[1]["llm_failure_count"] == 1
    assert rows[1]["next_llm_retry_at"]
    assert rows[1]["last_error_code"] == "invalid_output"


def test_untrusted_basis_or_version_extra_fields_do_not_change_validation(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    candidate = selection["selected"][0]

    summary = roles.classify_role_payload(db_path, selection, {
        "evidenceRoles": [{
            "stateKey": candidate["stateKey"], "memoryId": candidate["memoryId"], "role": "challenging",
            "basisHash": "model-invented", "classifierVersion": "model-invented", "anything": {"else": True},
        }],
    })

    assert summary["classifiedCount"] == 1
    assert _role_rows(db_path)[0]["role"] == "challenging"


def test_rule_upgrade_waits_until_primary_backlog_is_empty(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=2)
    first = roles.build_role_candidates(db_path, as_of=AS_OF)
    roles.classify_role_payload(db_path, {**first, "selected": [first["selected"][0]]}, None, failure_code="llm_request_failed")

    waiting = roles.build_role_candidates(db_path, as_of=AS_OF)
    assert waiting["selection"] == "primary"
    assert waiting["selected"][0]["memoryId"] == "mem-01"


def test_rule_retry_schedule_and_budget_exhaustion_do_not_increment_failure(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    first = roles.build_role_candidates(db_path, as_of=AS_OF)
    budget = roles.classify_role_payload(
        db_path, first, None, failure_code="role_budget_exhausted", budget_exhausted=True
    )
    row = _role_rows(db_path)[0]
    assert budget["ruleFallbackCount"] == 1
    assert row["llm_failure_count"] == 0
    assert row["next_llm_retry_at"][:10] == "2026-09-02"

    conn = connect(db_path)
    try:
        conn.execute("UPDATE market_evidence_roles SET next_llm_retry_at='2026-08-31T00:00:00+00:00'")
        conn.commit()
    finally:
        conn.close()
    upgrade = roles.build_role_candidates(db_path, as_of=AS_OF)
    assert upgrade["selection"] == "upgrade"
    roles.classify_role_payload(db_path, upgrade, None, failure_code="llm_request_failed")
    row = _role_rows(db_path)[0]
    assert row["llm_failure_count"] == 1
    assert row["next_llm_retry_at"][:10] == "2026-09-02"


def test_provider_budget_signal_uses_the_non_incrementing_role_fallback():
    import features.market_memory.service as memory_service
    from features.llm_settings.client import LlmRequestError

    assert memory_service._llm_budget_exhausted(
        LlmRequestError(429, "Too Many Requests", '{"code":"insufficient_quota"}')
    ) is True
    assert memory_service._llm_budget_exhausted(LlmRequestError(429, "Too Many Requests", "rate limited")) is False


def test_budget_exhaustion_keeps_failure_index_but_always_retries_in_24_hours(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    first = roles.build_role_candidates(db_path, as_of=AS_OF)
    roles.classify_role_payload(db_path, first, None, failure_code="llm_request_failed")
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE market_evidence_roles SET llm_failure_count=2, next_llm_retry_at='2026-08-31T00:00:00+00:00'"
        )
        conn.commit()
    finally:
        conn.close()
    upgrade = roles.build_role_candidates(db_path, as_of=AS_OF)
    assert upgrade["selection"] == "upgrade"

    roles.classify_role_payload(
        db_path, upgrade, None, failure_code="role_budget_exhausted", budget_exhausted=True
    )
    row = _role_rows(db_path)[0]
    assert row["llm_failure_count"] == 2
    assert row["next_llm_retry_at"][:10] == "2026-09-02"


def test_changed_basis_resets_rule_retry_to_first_24_hour_delay(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    first = roles.build_role_candidates(db_path, as_of=AS_OF)
    roles.classify_role_payload(db_path, first, None, failure_code="llm_request_failed")
    conn = connect(db_path)
    try:
        conn.execute("UPDATE market_evidence_roles SET llm_failure_count=3, next_llm_retry_at='2026-08-31T00:00:00+00:00'")
        conn.execute("UPDATE market_narrative_states SET summary='changed semantic basis'")
        conn.commit()
    finally:
        conn.close()

    changed = roles.build_role_candidates(db_path, as_of=AS_OF)
    roles.classify_role_payload(db_path, changed, None, failure_code="llm_request_failed")
    row = _role_rows(db_path)[0]
    assert row["llm_failure_count"] == 1
    assert row["next_llm_retry_at"][:10] == "2026-09-02"


def test_future_evidence_is_not_a_role_candidate(tmp_path):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=2)
    conn = connect(db_path)
    try:
        conn.execute("UPDATE market_memory SET date='2026-09-02' WHERE memory_id='mem-01'")
        conn.commit()
    finally:
        conn.close()
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    assert selection["candidateCount"] == 1
    assert [item["memoryId"] for item in selection["selected"]] == ["mem-00"]


def test_pending_match_suppresses_due_and_age_expiry(tmp_path, monkeypatch):
    checkpoint = [{
        "id": "cp-1",
        "item": "전력 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": [], "keywords": ["가이던스 상향"]},
        "dueBy": "2026-08-15",
        "status": "open",
        "createdAt": "2026-05-01T00:00:00+00:00",
        "history": [],
    }]
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, checkpoint=checkpoint)
    monkeypatch.setattr(checkpoint_verdicts, "is_llm_mode", lambda: True)

    refreshed = refresh_regime_state(db_path, STATE_ID, days=90, role_mode="llm")
    assert refreshed["evidence"] == []
    result = checkpoint_verdicts.run_checkpoint_verdicts(db_path, as_of=AS_OF)

    assert result["changeCount"] == 0
    conn = connect(db_path)
    try:
        stored = json.loads(conn.execute("SELECT next_checkpoints_json FROM market_narrative_states").fetchone()[0])
    finally:
        conn.close()
    assert stored[0]["status"] == "open"


def test_auto_mode_uses_actual_resolver_for_pending_and_rules_projection(tmp_path, monkeypatch):
    import features.llm_settings.client as llm_client

    checkpoint = [{
        "id": "cp-auto", "item": "전력 가이던스 상향", "direction": "supporting",
        "matchers": {"tickers": [], "keywords": ["가이던스 상향"]}, "dueBy": "2026-08-15",
        "status": "open", "createdAt": "2026-05-01T00:00:00+00:00", "history": [],
    }]
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, checkpoint=checkpoint)
    monkeypatch.setattr(regime_v2, "_now", lambda: AS_OF)

    for mode in ("llm", "llm_cli"):
        monkeypatch.setattr(llm_client, "default_generation_mode", lambda mode=mode: mode)
        assert roles.is_llm_mode("auto") is True
        assert refresh_regime_state(db_path, STATE_ID, role_mode="auto")["evidence"] == []
        assert checkpoint_verdicts.run_checkpoint_verdicts(db_path, as_of=AS_OF)["changeCount"] == 0

    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    candidate = selection["selected"][0]
    roles.classify_role_payload(db_path, selection, {"evidenceRoles": [{
        "stateKey": candidate["stateKey"], "memoryId": candidate["memoryId"], "role": "challenging",
    }]})
    monkeypatch.setattr(llm_client, "default_generation_mode", lambda: "rules")
    assert roles.is_llm_mode("auto") is False
    evidence = refresh_regime_state(db_path, STATE_ID, role_mode="auto")["evidence"]
    assert evidence and evidence[0]["roleSource"] == "rule" and evidence[0]["role"] == "supporting"


def test_rules_mode_overrides_conflicting_durable_llm_role(tmp_path, monkeypatch):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    candidate = selection["selected"][0]
    roles.classify_role_payload(db_path, selection, {"evidenceRoles": [{
        "stateKey": candidate["stateKey"], "memoryId": candidate["memoryId"], "role": "challenging",
    }]})
    monkeypatch.setattr(regime_v2, "_now", lambda: AS_OF)

    refreshed = refresh_regime_state(db_path, STATE_ID, role_mode="rules")
    assert refreshed["evidence"][0]["role"] == "supporting"
    assert refreshed["evidence"][0]["roleSource"] == "rule"


def test_pending_only_preserves_prior_aggregate_without_change_rows(tmp_path, monkeypatch):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    old_checkpoints = [{"id": "cp", "item": "keep", "direction": "supporting", "matchers": {"keywords": ["keep"], "tickers": []}}]
    old_triggers = ["keep prior falsifier"]
    conn = connect(db_path)
    try:
        conn.execute(
            """UPDATE market_narrative_states SET momentum='fading', confidence=.81,
                evidence_count_7d=2, evidence_count_30d=4, evidence_count_90d=7,
                last_confirmed_at='2026-08-30', last_challenged_at='2026-08-29',
                next_checkpoints_json=?, falsification_triggers_json=? WHERE state_id=?""",
            (json.dumps(old_checkpoints), json.dumps(old_triggers), STATE_ID),
        )
        conn.execute(
            """INSERT INTO market_regime_evidence
                (evidence_id, state_id, memory_id, evidence_date, role, score, created_at)
                VALUES ('old-evidence', ?, 'old-memory', '2026-08-30', 'supporting', .8, ?)""",
            (STATE_ID, AS_OF),
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(regime_v2, "_now", lambda: AS_OF)

    refreshed = refresh_regime_state(db_path, STATE_ID, role_mode="llm")
    assert refreshed["evidence"] == []
    assert refreshed["pendingEvidenceCount"] == 1
    conn = connect(db_path)
    try:
        state = conn.execute("SELECT * FROM market_narrative_states WHERE state_id=?", (STATE_ID,)).fetchone()
        projection = conn.execute("SELECT COUNT(*) FROM market_regime_evidence WHERE state_id=?", (STATE_ID,)).fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM market_regime_changes WHERE state_id=?", (STATE_ID,)).fetchone()[0]
    finally:
        conn.close()
    assert projection == 0 and changes == 0
    assert (state["momentum"], state["confidence"], state["evidence_count_90d"]) == ("fading", .81, 7)
    assert json.loads(state["next_checkpoints_json"]) == old_checkpoints
    assert json.loads(state["falsification_triggers_json"]) == old_triggers


def test_classified_subset_calculates_normally_when_other_pair_is_pending(tmp_path, monkeypatch):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=2)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    first = selection["selected"][0]
    roles.classify_role_payload(db_path, {**selection, "selected": [first]}, {"evidenceRoles": [{
        "stateKey": first["stateKey"], "memoryId": first["memoryId"], "role": "supporting",
    }]})
    monkeypatch.setattr(regime_v2, "_now", lambda: AS_OF)

    refreshed = refresh_regime_state(db_path, STATE_ID, role_mode="llm")
    assert len(refreshed["evidence"]) == 1
    assert refreshed["evidence"][0]["memoryId"] == first["memoryId"]


def test_rules_projection_excludes_future_memory(tmp_path, monkeypatch):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=2)
    conn = connect(db_path)
    try:
        conn.execute("UPDATE market_memory SET date='2026-09-02' WHERE memory_id='mem-01'")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(regime_v2, "_now", lambda: AS_OF)

    assert len(refresh_regime_state(db_path, STATE_ID, role_mode="rules")["evidence"]) == 1


def test_role_batch_rolls_back_as_a_unit(tmp_path, monkeypatch):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path, memory_count=2)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    original = roles._fresh_candidate
    calls = 0

    def fail_second(conn, state_key, memory_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("forced")
        return original(conn, state_key, memory_id)

    monkeypatch.setattr(roles, "_fresh_candidate", fail_second)
    outcomes = [{**item, "role": "supporting", "source": "llm"} for item in selection["selected"]]
    try:
        roles._persist_outcomes(db_path, outcomes, now=AS_OF)
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("expected forced persistence failure")
    assert _role_rows(db_path) == []


def test_locked_role_persistence_and_backlog_read_are_bounded(tmp_path, monkeypatch):
    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(roles, "_persist_outcomes", locked)
    monkeypatch.setattr(roles, "_remaining_primary", locked)
    summary = roles.classify_role_payload(db_path, selection, None, failure_code="llm_request_failed")

    assert summary["failureCode"] == "role_persistence_failed"
    assert summary["remainingBacklogCount"] == selection["primaryCount"]


def test_finalizer_isolates_non_sqlite_role_subsystem_errors(tmp_path, monkeypatch):
    import features.market_memory.service as memory_service

    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    monkeypatch.setattr(memory_service, "_reconcile_role_inputs", lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bug")))

    summary = memory_service.finalize_role_classification(selection, {}, db_path=db_path)

    assert summary["failureCode"] == "role_persistence_failed"
    assert summary["remainingBacklogCount"] == selection["primaryCount"]


def test_api_role_candidate_builder_failure_does_not_abort_memory_generation(monkeypatch):
    import features.market_memory.service as memory_service

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(roles, "build_role_candidates", locked)
    monkeypatch.setattr(memory_service, "selected_llm_config", lambda: {"apiKey": "x", "provider": "openai", "model": "test"})
    monkeypatch.setattr(memory_service, "read_market_memory_prompt", lambda: "prompt")
    monkeypatch.setattr(memory_service, "build_memory_llm_context", lambda _date: ("{}", [], "2026-09-01"))
    monkeypatch.setattr(memory_service, "request_llm_text", lambda *_a, **_kw: ('{"entries": []}', "", {}))
    monkeypatch.setattr(memory_service, "save_memory_entries", lambda _entries: {"saved": [], "checkpointsMerged": 0, "checkpointsDropped": 0})

    result = memory_service.run_llm_market_memory("2026-09-01")

    assert result["ok"] is True
    assert result["roleClassification"]["failureCode"] == "role_persistence_failed"


def test_cli_role_candidate_builder_failure_keeps_pack_preparation_alive(tmp_path, monkeypatch):
    import features.agent_mode.service as agent_service

    def matcher_bug(*_args, **_kwargs):
        raise ValueError("matcher bug")

    monkeypatch.setattr(roles, "build_role_candidates", matcher_bug)
    monkeypatch.setattr(agent_service, "build_memory_llm_context", lambda _date: ("{}", [], "2026-09-01"))
    monkeypatch.setattr(agent_service, "read_market_memory_prompt", lambda: "prompt")
    monkeypatch.setattr(agent_service, "_write_pack", lambda _pack, _owner: tmp_path / "pack.json")

    pack, _path = agent_service.prepare_market_memory_pack("2026-09-01")

    assert pack["internal"]["roleSelection"]["roleFailureCode"] == "role_persistence_failed"
    assert json.loads(pack["context"])["roleCandidates"] == []


def test_same_run_basis_mutation_falls_back_to_current_durable_rule_row(tmp_path):
    import features.market_memory.service as memory_service

    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    before = roles.build_role_candidates(db_path, as_of=AS_OF)
    candidate = before["selected"][0]
    conn = connect(db_path)
    try:
        conn.execute("UPDATE market_narrative_states SET rationale='same-run changed rationale' WHERE state_id=?", (STATE_ID,))
        conn.commit()
    finally:
        conn.close()

    summary = memory_service.finalize_role_classification(before, {"evidenceRoles": [{
        "stateKey": candidate["stateKey"], "memoryId": candidate["memoryId"], "role": "challenging",
    }]}, db_path=db_path)
    row = _role_rows(db_path)[0]
    current = roles.build_role_candidates(db_path, as_of=AS_OF)

    assert summary["classifiedCount"] == 0
    assert summary["ruleFallbackCount"] == 1
    assert summary["invalidCount"] >= 1
    assert summary["remainingBacklogCount"] == 0
    assert row["role_source"] == "rule"
    assert row["basis_hash"] != candidate["basisHash"]
    assert current["selection"] == "upgrade" or current["primaryCount"] == 0


def test_same_run_new_pair_stays_backlog_outside_issued_batch(tmp_path):
    import features.market_memory.service as memory_service

    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    before = roles.build_role_candidates(db_path, as_of=AS_OF)
    old = before["selected"][0]
    conn = connect(db_path)
    try:
        conn.execute(
            """INSERT INTO market_memory
                (memory_id, as_of, date, title, summary, story, story_family, story_thesis, state_key, state_label, created_at)
                VALUES ('mem-new', ?, '2026-08-31', '전력 수요 신규 근거', 'AI 데이터센터 전력 수요 strong growth', ?, 'AI 전력', 'AI 전력 수요 확대', ?, 'AI 전력 수요', ?)""",
            (AS_OF, STATE_KEY, STATE_KEY, AS_OF),
        )
        conn.commit()
    finally:
        conn.close()

    summary = memory_service.finalize_role_classification(before, {"evidenceRoles": [{
        "stateKey": old["stateKey"], "memoryId": old["memoryId"], "role": "supporting",
    }]}, db_path=db_path)
    rows = _role_rows(db_path)

    assert summary["candidateCount"] == 1
    assert summary["classifiedCount"] == 1
    assert summary["remainingBacklogCount"] >= 1
    assert [row["memory_id"] for row in rows] == ["mem-00"]


def test_finalizer_keeps_unknown_output_in_invalid_count(tmp_path):
    import features.market_memory.service as memory_service

    db_path = str(tmp_path / "market-memory.sqlite3")
    _seed(db_path)
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    candidate = selection["selected"][0]

    summary = memory_service.finalize_role_classification(selection, {"evidenceRoles": [
        {"stateKey": candidate["stateKey"], "memoryId": candidate["memoryId"], "role": "supporting"},
        {"stateKey": "unknown", "memoryId": "out-of-batch", "role": "challenging"},
    ]}, db_path=db_path)

    assert summary["classifiedCount"] == 1
    assert summary["invalidCount"] == 1


def test_finalizer_refreshes_selected_state_beyond_background_limit(tmp_path):
    import features.market_memory.service as memory_service

    db_path = str(tmp_path / "market-memory.sqlite3")
    conn = connect(db_path)
    init_db(conn)
    try:
        for index in range(31):
            key = f"state_{index:02d}"
            state_id = f"state-{index:02d}"
            updated_at = "2020-01-01T00:00:00+00:00" if index == 30 else AS_OF
            conn.execute(
                """INSERT INTO market_narrative_states
                    (state_id, state_key, state_label, story, story_family, status, bias, summary, rationale, effective_from, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'active', 'bullish', ?, 'rationale', '2026-08-01', ?)""",
                (state_id, key, key, key, key, key, updated_at),
            )
            conn.execute(
                """INSERT INTO market_memory
                    (memory_id, as_of, date, title, summary, story, story_family, story_thesis, state_key, state_label, created_at)
                    VALUES (?, ?, '2026-08-31', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"memory-{index:02d}", AS_OF, key, f"{key} strong growth", key, key, key, key, key, AS_OF),
            )
        conn.commit()
    finally:
        conn.close()
    selection = roles.build_role_candidates(db_path, as_of=AS_OF)
    target = next(item for item in selection["selected"] if item["stateId"] == "state-30")

    memory_service.finalize_role_classification(selection, {"evidenceRoles": [{
        "stateKey": target["stateKey"], "memoryId": target["memoryId"], "role": "supporting",
    }]}, db_path=db_path)
    conn = connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM market_regime_evidence WHERE state_id='state-30'").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_api_and_agent_writeback_share_role_result(tmp_path, monkeypatch):
    import features.agent_mode.service as agent_service
    import features.market_memory.service as memory_service

    api_db = str(tmp_path / "api.sqlite3")
    cli_db = str(tmp_path / "cli.sqlite3")
    _seed(api_db)
    _seed(cli_db)
    api_selection = roles.build_role_candidates(api_db, as_of=AS_OF)
    cli_selection = roles.build_role_candidates(cli_db, as_of=AS_OF)
    payload = {
        "entries": [],
        "evidenceRoles": [{
            "stateKey": STATE_KEY,
            "memoryId": "mem-00",
            "role": "challenging",
        }],
    }

    api = memory_service.finalize_role_classification(api_selection, payload, db_path=api_db)
    monkeypatch.setattr(agent_service, "MARKET_MEMORY_DB_PATH", cli_db)
    agent = agent_service.write_market_memory_from_json(
        {"internal": {"date": "2026-09-01", "usedDocs": [], "roleSelection": cli_selection}}, payload
    )

    assert api == agent["roleClassification"]
    assert [(row["role"], row["role_source"]) for row in _role_rows(api_db)] == [
        ("challenging", "llm")
    ]
    assert [(row["role"], row["role_source"]) for row in _role_rows(cli_db)] == [
        ("challenging", "llm")
    ]
