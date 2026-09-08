from __future__ import annotations

import json

import pytest

from features.investment_review import review_v2
from features.investment_review import service
from features.investment_review.schema import normalize_review


def _inputs(*, revision: int = 1, linked: bool = True) -> dict:
    return {
        "portfolio": {"revision": revision, "updatedAt": "2026-09-01T00:00:00Z", "positions": [{"ticker": "NVDA", "name": "NVIDIA", "currency": "USD", "sector": "Technology"}]},
        "positions": [{"ticker": "NVDA", "name": "NVIDIA", "currency": "USD", "sector": "Technology"}],
        "theses": [{"ticker": "NVDA", "updated_at": "2026-08-31T00:00:00Z", "linked_regimes": ["ai_power"] if linked else [], "latestDelta": {"deltaId": "d1", "verdict": "maintained", "generatedAt": "2026-08-31T00:00:00Z"}}],
        "states": [{"stateId": "state-1", "stateKey": "ai_power", "stateLabel": "AI 전력", "updatedAt": "2026-08-31T00:00:00Z", "momentum": "stable", "linkedCompanies": ["UNRELATED"]}],
        "checkpoints": [{"id": "cp-1", "ticker": "NVDA", "checkpoint": "실적 확인", "dueAt": "2026-10-01T00:00:00Z", "status": "open"}],
        "analytics": {"methodVersion": "analytics-v1", "fingerprint": "a1"}, "reportRefs": [], "backtest": None,
        "backtestUncertainties": [{"code": "compatible_saved_backtest_missing"}], "manualLinks": {}, "capturedAt": "2026-09-01T00:00:00Z",
    }


def test_legacy_is_in_memory_v2_without_rewrite(tmp_path):
    path = tmp_path / "investment-review" / "2026-08-30.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"date": "2026-08-30", "summary": "old"}), encoding="utf-8")
    before = path.read_bytes()
    view = normalize_review(review_v2.load_raw(path.parent, "2026-08-30"), date="2026-08-30")
    assert view["sourceSchemaVersion"] == 1 and view["reviewRevision"] == 0
    assert view["reviewState"] == "stale" and view["inputBasis"]["status"] == "legacy_unknown"
    assert path.read_bytes() == before


def test_exact_and_missing_get_are_read_only_and_never_generate(tmp_path, monkeypatch):
    review_dir = tmp_path / "investment-review"
    review_dir.mkdir()
    legacy = review_dir / "2026-08-30.json"
    legacy.write_text(json.dumps({"date": "2026-08-30", "summary": "old"}), encoding="utf-8")
    before = legacy.read_bytes()
    monkeypatch.setattr(service, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("missing GET must not gather")))
    assert service.get_review("2026-08-29")["reviewRevision"] == 0
    opened = service.get_review("2026-08-30")
    assert opened["sourceSchemaVersion"] == 1 and legacy.read_bytes() == before


def test_explicit_thesis_link_never_uses_linked_companies_canary():
    inputs = _inputs(linked=False)
    basis = review_v2.build_input_basis(inputs)
    structured = review_v2.build_structured_review(inputs, basis)
    assert not [row for row in structured["sharedExposures"] if row["type"] == "narrative"]
    inputs = _inputs(linked=True)
    structured = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    assert structured["sharedExposures"][0]["key"] == "ai_power"


def test_open_tracked_checkpoint_item_survives_structured_normalized_due_and_portfolio_projection(monkeypatch):
    inputs = _inputs()
    # This is the authoritative row emitted by _tracked_checkpoint_rows for a
    # stored Thesis/State tracked checkpoint: it has ``item`` rather than the
    # older synthetic ``checkpoint`` display field.
    inputs["checkpoints"] = [{
        "id": "cp-tracked", "item": "실적 가이던스 확인", "status": "open",
        "dueBy": "2026-09-01T12:00:00Z", "dueAt": "2026-09-01T12:00:00Z",
        "ticker": "NVDA", "linkedTickers": ["NVDA"],
    }]
    basis = review_v2.build_input_basis(inputs)
    structured = review_v2.build_structured_review(inputs, basis)
    candidate = normalize_review({
        "schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01",
        "reviewState": "draft", "generatedAt": "2026-08-31T00:00:00Z",
        "inputBasis": basis, **structured,
    }, date="2026-09-01")
    due = candidate["positionReviews"][0]["dueCheckpoints"]
    assert due == [{"id": "cp-tracked", "label": "실적 가이던스 확인", "dueAt": "2026-09-01T12:00:00Z"}]
    assert candidate["positionReviews"][0]["reviewReasons"] == ["checkpoint_due"]
    monkeypatch.setattr(review_v2, "_now", lambda: "2026-09-02T00:00:00Z")
    state, freshness, _ = review_v2.effective_freshness(candidate, basis)
    assert state == "due" and freshness["dueCount"] == 1

    # Synthetic/legacy checkpoint text stays compatible, while terminal
    # tracked rows remain in authority but never become due actions.
    inputs["checkpoints"][0] = {**inputs["checkpoints"][0], "checkpoint": "기존 표시명"}
    assert review_v2.build_structured_review(inputs, basis)["positionReviews"][0]["dueCheckpoints"][0]["label"] == "기존 표시명"
    inputs["checkpoints"][0]["status"] = "confirmed"
    assert review_v2.build_structured_review(inputs, basis)["positionReviews"][0]["dueCheckpoints"] == []


def test_manual_link_rotates_to_current_state_lineage_only(tmp_path):
    db = tmp_path / "market-memory.sqlite3"
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE market_regime_thesis_links (state_id TEXT, thesis_ticker TEXT, relationship TEXT, method TEXT)")
        conn.execute("CREATE TABLE market_narrative_states (state_id TEXT, state_key TEXT)")
        conn.execute("INSERT INTO market_regime_thesis_links VALUES ('retired-1', 'NVDA', 'linked_regimes', 'manual')")
        conn.execute("INSERT INTO market_narrative_states VALUES ('retired-1', 'ai_power')")
    current = [{"stateId": "current-9", "stateKey": "ai_power", "stateLabel": "AI 전력", "linkedCompanies": ["NVDA"]}]
    links = review_v2._manual_links(tmp_path, current)
    assert links == {"NVDA": {"current-9"}}
    inputs = _inputs(linked=False)
    inputs["states"] = current
    inputs["manualLinks"] = links
    narratives = [row for row in review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))["sharedExposures"] if row["type"] == "narrative"]
    assert narratives == [{"type": "narrative", "key": "ai_power", "stateKey": "ai_power", "label": "AI 전력", "stateId": "current-9", "tickers": ["NVDA"], "momentum": "stable"}]


def test_saved_backtest_requires_weight_currency_window_and_method(tmp_path):
    folder = tmp_path / "portfolio-backtests"
    folder.mkdir()
    analytics = {
        "available": True, "baseCurrency": "USD", "methodVersion": "portfolio-backtest-v1",
        "backtestMethodVersion": "portfolio-backtest-v1", "backtestWindow": "monthly", "backtestStart": "2025-01-01", "backtestEnd": "2026-01-01",
        "positions": [{"ticker": "NVDA", "weight": 0.6, "quoteCurrency": "USD"}, {"ticker": "005930.KS", "weight": 0.4, "quoteCurrency": "KRW"}],
    }
    # Exact saved shape from run_portfolio_backtest: no methodVersion field,
    # rebalance/start/end and riskContributions carry its immutable identity.
    saved = {"id": "saved", "baseCurrency": "USD", "rebalance": "monthly", "start": "2025-01-01", "end": "2026-01-01",
             "riskContributions": [{"ticker": "NVDA", "weight": 0.6, "volatilityContribution": 0.2}],
             "positions": [{"ticker": "NVDA", "weight": 0.6, "currency": "USD"}, {"ticker": "005930.KS", "weight": 0.4, "currency": "KRW"}]}
    (folder / "saved.json").write_text(json.dumps(saved), encoding="utf-8")
    assert review_v2._backtest_ref(tmp_path, [], analytics)[0]["id"] == "saved"
    for key, value in (("weight", 0.5), ("currency", "JPY"), ("rebalance", ""), ("methodVersion", "other-v2")):
        changed = json.loads(json.dumps(saved))
        if key in {"weight", "currency"}:
            changed["positions"][0][key] = value
        else:
            changed[key] = value
        (folder / "saved.json").write_text(json.dumps(changed), encoding="utf-8")
        assert review_v2._backtest_ref(tmp_path, [], analytics)[0] is None


def test_malformed_v2_nested_values_are_bounded_and_market_basis_stays_partial():
    normalized = normalize_review({
        "schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01",
        "reviewState": "not-a-state", "inputBasis": {"status": "complete", "marketData": {"status": "complete", "priceAsOf": "fake", "fxAsOf": "fake"}},
        "changesSincePrevious": [{"kind": "risk", "change": "changed"}, {"kind": "oops", "change": "added"}],
        "positionReviews": [{"ticker": "nvda", "reviewReasons": ["x"] * 50, "uncertainties": [{"code": "nope"}]}],
        "sharedExposures": [{"type": "narrative", "key": "ai", "tickers": ["NVDA"]}, {"type": "unsupported", "key": "drop"}],
        "portfolioRisks": [{"riskKey": "portfolio_concentration", "methodVersion": "analytics-v1", "status": "available"}, {"riskKey": "bad", "methodVersion": "x", "status": "available"}],
        "freshness": {"reasons": [{"code": "nope"}]}, "uncertainties": [{"code": "nope"}],
    }, date="2026-09-01")
    assert normalized["reviewState"] == "draft"
    assert normalized["inputBasis"]["status"] == "partial"
    assert normalized["inputBasis"]["marketData"] == {"status": "partial", "priceAsOf": "", "fxAsOf": ""}
    assert normalized["changesSincePrevious"] == []
    assert normalized["positionReviews"][0]["reviewReasons"] == []
    assert normalized["positionReviews"][0]["uncertainties"] == [{"code": "additional_confirmation_needed"}]
    assert len(normalized["sharedExposures"]) == len(normalized["portfolioRisks"]) == 1


def test_commit_cas_stale_and_reviewed_isolated(tmp_path, monkeypatch):
    review_dir = tmp_path / "investment-review"
    inputs = _inputs()
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: inputs)
    candidate = review_v2.build_candidate(tmp_path, review_dir, "2026-09-01")
    saved = review_v2.finalize_and_commit(tmp_path, review_dir, candidate)
    assert saved["reviewRevision"] == 1 and saved["reviewState"] == "draft"
    state, _freshness, _reasons = review_v2.effective_freshness(saved, review_v2.build_input_basis(inputs))
    assert state == "draft"  # candidate analytics snapshot is not a GET authority mismatch
    reviewed = review_v2.mark_reviewed(tmp_path, review_dir, "2026-09-01", 1)
    assert reviewed["reviewRevision"] == 2 and reviewed["reviewState"] == "reviewed"
    with pytest.raises(review_v2.ReviewRevisionConflict):
        review_v2.mark_reviewed(tmp_path, review_dir, "2026-09-01", 1)
    stale_candidate = dict(candidate)
    stale_candidate["baseReviewRevision"] = 2
    changed = _inputs(revision=2)
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: changed)
    stale = review_v2.finalize_and_commit(tmp_path, review_dir, stale_candidate)
    assert stale["reviewState"] == "stale" and stale["staleReasons"][0]["code"] == "input_changed_during_generation"


def test_previous_comparison_uses_contract_keys_and_skips_risk_method_mismatch():
    previous = normalize_review({"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-08-31", "inputBasis": {"status": "partial", "fingerprint": "old", "marketData": {"status": "partial"}, "analytics": {"backtest": {"id": "run", "methodVersion": "v1", "baseCurrency": "USD", "window": "monthly", "start": "2025", "end": "2026"}}},
        "positionReviews": [{"ticker": "NVDA", "thesisVerdict": "maintained"}], "checkpointReviews": [{"id": "cp-1", "status": "open", "lastVerdict": "maintained", "direction": "up", "dueBy": "2026-10-01"}],
        "sharedExposures": [{"type": "narrative", "stateKey": "energy", "key": "ignored", "tickers": ["NVDA"]}, {"type": "sector", "key": "energy", "tickers": ["NVDA"]}],
        "portfolioRisks": [{"riskKey": "saved_backtest", "methodVersion": "v1", "status": "available"}]}, date="2026-08-31")
    current = {"positionReviews": [{"ticker": "NVDA", "thesisVerdict": "maintained"}], "checkpointReviews": [{"id": "cp-1", "status": "challenged", "lastVerdict": "weakened", "direction": "down", "dueBy": "2026-10-02"}],
               "sharedExposures": [{"type": "narrative", "stateKey": "energy", "key": "ignored", "tickers": ["NVDA", "MSFT"]}, {"type": "sector", "key": "energy", "tickers": ["NVDA"]}],
               "portfolioRisks": [{"riskKey": "saved_backtest", "methodVersion": "v2", "status": "available"}]}
    basis = {"analytics": {"backtest": {"id": "run", "methodVersion": "v2", "baseCurrency": "USD", "window": "monthly", "start": "2025", "end": "2026"}}}
    changes, uncertainties = review_v2.compare_previous(current, previous, current_basis=basis)
    assert any(row["kind"] == "checkpoint" and row["key"] == "cp-1" and row["change"] == "changed" for row in changes)
    assert any(row["kind"] == "narrative" and row["key"] == "energy" for row in changes)
    assert not any(row["key"] == "sector:energy" for row in changes)
    assert not any(row["kind"] == "risk" for row in changes)
    assert {row["code"] for row in uncertainties} == {"previous_risk_not_comparable"}


def test_job_stage_failure_never_writes_review_and_newer_revision_blocks_commit(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from features.common.job_json_producer_types import InvestmentReviewJobRequest
    from features.common.job_json_producers import JobJsonProducers
    from features.common.shared_jobs_private import JobPrivateLifecycle
    from features.common.shared_jobs_projection import new_shared_job
    from features.common.shared_jobs_schema import JobStatus
    from features.common.shared_jobs_store import SharedJobStore

    inputs = _inputs()
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: inputs)
    review_dir = tmp_path / "investment-review"
    candidate = review_v2.build_candidate(tmp_path, review_dir, "2026-09-01")
    clock = lambda: datetime(2026, 9, 1, tzinfo=UTC)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=clock)
    lifecycle = JobPrivateLifecycle(tmp_path / "job-context", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="investment_review", generation_mode="llm_cli", adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    running = store.get(job.id)
    assert running is not None
    producer = JobJsonProducers(tmp_path, clock=clock, review_builder=lambda _body: candidate)
    bundle = producer.stage_investment_review(running, InvestmentReviewJobRequest({}, {"artifactId": "2026-09-01", "reportId": "2026-09-01", "date": "2026-09-01"}))
    assert not (review_dir / "2026-09-01.json").exists()
    with pytest.raises(RuntimeError):
        producer.workspace.commit(bundle, store, lifecycle, fault_hook=lambda phase: (_ for _ in ()).throw(RuntimeError("stop")) if phase == "intent_claimed" else None)
    assert not (review_dir / "2026-09-01.json").exists()

    # A newer direct write after staging changes the stager's base hash, so
    # the older job cannot overwrite it during promotion.
    review_v2.finalize_and_commit(tmp_path, review_dir, candidate)
    with pytest.raises(Exception):
        producer.workspace.commit(bundle, store, lifecycle)
    assert review_v2.load_raw(review_dir, "2026-09-01")["reviewRevision"] == 1


@pytest.mark.parametrize("existing_target", [False, True])
def test_cli_prepromotion_input_change_conflicts_without_touching_review(tmp_path, monkeypatch, existing_target):
    from datetime import UTC, datetime
    from features.common.job_json_producer_types import InvestmentReviewJobRequest
    from features.common.job_json_producers import JobJsonProducers
    from features.common.job_json_schema import JobArtifactConflictError
    from features.common.shared_jobs_private import JobPrivateLifecycle
    from features.common.shared_jobs_projection import new_shared_job
    from features.common.shared_jobs_schema import JobStatus
    from features.common.shared_jobs_store import SharedJobStore

    current = _inputs(revision=1)
    authorities = []
    def gather(*_args, **kwargs):
        authorities.append(kwargs.get("analytics_authority"))
        return current
    monkeypatch.setattr(review_v2, "gather_inputs", gather)
    review_dir = tmp_path / "investment-review"
    candidate = review_v2.build_candidate(tmp_path, review_dir, "2026-09-01")
    clock = lambda: datetime(2026, 9, 1, tzinfo=UTC)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=clock)
    lifecycle = JobPrivateLifecycle(tmp_path / "job-context", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="investment_review", generation_mode="llm_cli", adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    running = store.get(job.id)
    assert running is not None
    producer = JobJsonProducers(tmp_path, clock=clock, review_builder=lambda _body: candidate)
    bundle = producer.stage_investment_review(running, InvestmentReviewJobRequest({}, {"artifactId": "2026-09-01", "reportId": "2026-09-01", "date": "2026-09-01"}))
    # Cover both a missing review and an existing review: the guard may not
    # create/replace either target when external authority moved post-stage.
    existing = {"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01", "reviewRevision": 7, "reviewState": "draft", "inputBasis": {"status": "partial", "fingerprint": "existing", "marketData": {"status": "partial"}}}
    target = review_dir / "2026-09-01.json"
    if existing_target:
        review_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing), encoding="utf-8")
        before = target.read_bytes()
    else:
        before = None
    current = _inputs(revision=2)  # changed after stage, before promotion
    with pytest.raises(JobArtifactConflictError, match="investment_review_external_input_changed_reopen_generation"):
        producer.workspace.commit(bundle, store, lifecycle)
    assert (target.read_bytes() if target.exists() else None) == before
    assert not (tmp_path / "job-commits" / f"{job.id}.json").exists()
    assert authorities[-1] == candidate["inputBasis"]["analytics"]


def test_cli_recovery_refuses_stale_staged_review_without_writing_target(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from features.common.job_json_producer_types import InvestmentReviewJobRequest
    from features.common.job_json_producers import JobJsonProducers
    from features.common.job_json_recovery import recover_json_job
    from features.common.shared_jobs_private import JobPrivateLifecycle
    from features.common.shared_jobs_projection import new_shared_job
    from features.common.shared_jobs_schema import JobStatus
    from features.common.shared_jobs_store import SharedJobStore

    current = _inputs(revision=1)
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: current)
    clock = lambda: datetime(2026, 9, 1, tzinfo=UTC)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=clock)
    lifecycle = JobPrivateLifecycle(tmp_path / "job-context", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="investment_review", generation_mode="llm_cli", adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    running = store.get(job.id)
    assert running is not None
    candidate = review_v2.build_candidate(tmp_path, tmp_path / "investment-review", "2026-09-01")
    producer = JobJsonProducers(tmp_path, clock=clock, review_builder=lambda _body: candidate)
    bundle = producer.stage_investment_review(running, InvestmentReviewJobRequest({}, {"artifactId": "2026-09-01", "reportId": "2026-09-01", "date": "2026-09-01"}))
    store.claim_committing(job.id, bundle.intent)  # simulate interruption after intent claim
    current = _inputs(revision=2)
    assert not recover_json_job(tmp_path, job.id, store, lifecycle, clock=clock)
    assert not (tmp_path / "investment-review" / "2026-09-01.json").exists()
    assert store.get(job.id).status == JobStatus.FAILED_COMMIT_RECOVERY


def test_cli_recovery_reuses_only_saved_analytics_authority_when_unchanged(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from features.common.job_json_producer_types import InvestmentReviewJobRequest
    from features.common.job_json_producers import JobJsonProducers
    from features.common.job_json_recovery import recover_json_job
    from features.common.shared_jobs_private import JobPrivateLifecycle
    from features.common.shared_jobs_projection import new_shared_job
    from features.common.shared_jobs_schema import JobStatus
    from features.common.shared_jobs_store import SharedJobStore

    current = _inputs(revision=1)
    current["analytics"] = {"methodVersion": "portfolio-analytics-v1", "baseCurrency": "USD", "available": True,
                            "positions": [{"ticker": "NVDA", "weight": 1.0, "currency": "USD"}],
                            "compatibilitySignature": {"positions": [{"ticker": "NVDA", "weight": 1.0, "currency": "USD"}], "baseCurrency": "USD"}}
    current["backtest"] = {"id": "run", "methodVersion": "portfolio-backtest-v1", "baseCurrency": "USD", "window": "monthly", "start": "2025-01-01", "end": "2026-01-01", "fingerprint": "run"}
    seen = []
    def gather(*_args, **kwargs):
        seen.append(kwargs.get("analytics_authority")); return current
    monkeypatch.setattr(review_v2, "gather_inputs", gather)
    clock = lambda: datetime(2026, 9, 1, tzinfo=UTC)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=clock)
    lifecycle = JobPrivateLifecycle(tmp_path / "job-context", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="investment_review", generation_mode="llm_cli", adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    candidate = review_v2.build_candidate(tmp_path, tmp_path / "investment-review", "2026-09-01")
    producer = JobJsonProducers(tmp_path, clock=clock, review_builder=lambda _body: candidate)
    bundle = producer.stage_investment_review(store.get(job.id), InvestmentReviewJobRequest({}, {"artifactId": "2026-09-01", "reportId": "2026-09-01", "date": "2026-09-01"}))
    store.claim_committing(job.id, bundle.intent)
    assert recover_json_job(tmp_path, job.id, store, lifecycle, clock=clock)
    assert (tmp_path / "investment-review" / "2026-09-01.json").is_file()
    assert seen[-1] == candidate["inputBasis"]["analytics"]


def test_cli_recovery_completes_already_promoted_review_after_authority_changes(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from features.common.job_json_producer_types import InvestmentReviewJobRequest
    from features.common.job_json_producers import JobJsonProducers
    from features.common.job_json_recovery import recover_json_job
    from features.common.job_json_schema import CommitInterruptedError
    from features.common.shared_jobs_private import JobPrivateLifecycle
    from features.common.shared_jobs_projection import new_shared_job
    from features.common.shared_jobs_schema import JobStatus
    from features.common.shared_jobs_store import SharedJobStore

    current = _inputs(revision=1)
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: current)
    clock = lambda: datetime(2026, 9, 1, tzinfo=UTC)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=clock)
    lifecycle = JobPrivateLifecycle(tmp_path / "job-context", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="investment_review", generation_mode="llm_cli", adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    candidate = review_v2.build_candidate(tmp_path, tmp_path / "investment-review", "2026-09-01")
    producer = JobJsonProducers(tmp_path, clock=clock, review_builder=lambda _body: candidate)
    bundle = producer.stage_investment_review(store.get(job.id), InvestmentReviewJobRequest({}, {"artifactId": "2026-09-01", "reportId": "2026-09-01", "date": "2026-09-01"}))
    with pytest.raises(CommitInterruptedError):
        producer.workspace.commit(bundle, store, lifecycle, fault_hook=lambda phase: (_ for _ in ()).throw(CommitInterruptedError(phase)) if phase == "artifacts_written" else None)
    target = tmp_path / "investment-review" / "2026-09-01.json"
    assert target.exists()
    current = _inputs(revision=2)
    assert recover_json_job(tmp_path, job.id, store, lifecycle, clock=clock)
    assert store.get(job.id).status == JobStatus.DONE


def test_challenge_context_requires_exact_current_revision(tmp_path):
    review_dir = tmp_path / "investment-review"
    review_dir.mkdir()
    row = normalize_review({"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01", "reviewRevision": 3, "reviewState": "draft", "inputBasis": {"status": "partial", "fingerprint": "x", "marketData": {"status": "partial"}}}, date="2026-09-01")
    (review_dir / "2026-09-01.json").write_text(json.dumps(row), encoding="utf-8")
    assert review_v2.challenge_context(tmp_path, review_dir, "2026-09-01", 3)["investmentReview"]["reviewRevision"] == 3
    assert review_v2.challenge_context(tmp_path, review_dir, "2026-09-01", 2)["dataGaps"][0]["code"] == "review_changed_reopen_challenge"


def test_existing_v2_get_is_strictly_read_only_without_market_memory(tmp_path, monkeypatch):
    import os
    review_dir = tmp_path / "investment-review"
    review_dir.mkdir()
    row = normalize_review({"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01", "reviewRevision": 1, "reviewState": "draft", "inputBasis": {"status": "partial", "fingerprint": "old", "marketData": {"status": "partial"}}}, date="2026-09-01")
    target = review_dir / "2026-09-01.json"; target.write_text(json.dumps(row), encoding="utf-8")
    monkeypatch.setattr(service, "DATA_DIR", tmp_path); monkeypatch.setattr(service, "REVIEW_DIR", review_dir)
    before = {path.relative_to(tmp_path).as_posix(): (path.read_bytes(), os.stat(path).st_mtime_ns) for path in tmp_path.rglob("*") if path.is_file()}
    opened = service.get_review("2026-09-01")
    after = {path.relative_to(tmp_path).as_posix(): (path.read_bytes(), os.stat(path).st_mtime_ns) for path in tmp_path.rglob("*") if path.is_file()}
    assert opened["reviewRevision"] == 1
    assert before == after
    assert not (tmp_path / "market-memory.sqlite3").exists()


def test_tracked_checkpoint_authority_keeps_owner_status_and_current_lineage(tmp_path, monkeypatch):
    import sqlite3
    from features.portfolio import service as portfolio_service

    db = tmp_path / "market-memory.sqlite3"
    thesis_cp = {"item": "실적 가이던스", "direction": "supporting", "matchers": {"tickers": ["NVDA"], "keywords": ["가이던스 상향"]}, "dueBy": "2026-09-10", "status": "confirmed", "createdAt": "2026-01-01", "lastVerdict": {"verdict": "confirmed", "at": "2026-09-01", "evidence": []}, "history": [{"at": "2026-09-01", "from": "open", "to": "confirmed", "verdict": "confirmed"}]}
    state_cp = {"item": "전력 병목 확인", "direction": "challenging", "matchers": {"tickers": [], "keywords": ["전력 병목"]}, "dueBy": "2026-09-11", "status": "challenged", "createdAt": "2026-01-01", "lastVerdict": {"verdict": "challenged", "at": "2026-09-01", "evidence": []}, "history": [{"at": "2026-09-01", "from": "open", "to": "challenged", "verdict": "challenged"}]}
    unrelated = {**state_cp, "item": "무관 상태", "matchers": {"tickers": [], "keywords": ["무관"]}}
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE thesis (ticker TEXT, company TEXT, updated_at TEXT, linked_regimes_json TEXT, next_checkpoints_json TEXT)")
        conn.execute("CREATE TABLE thesis_delta (delta_id TEXT, ticker TEXT, generated_at TEXT, verdict TEXT, analysis_json TEXT)")
        conn.execute("CREATE TABLE market_narrative_states (state_id TEXT, state_key TEXT, state_label TEXT, status TEXT, momentum TEXT, updated_at TEXT, next_checkpoints_json TEXT)")
        conn.execute("CREATE TABLE market_regime_thesis_links (state_id TEXT, thesis_ticker TEXT, relationship TEXT, method TEXT)")
        conn.execute("INSERT INTO thesis VALUES (?,?,?,?,?)", ("NVDA", "NVIDIA", "2026-09-01", json.dumps(["power"]), json.dumps([thesis_cp])))
        conn.execute("INSERT INTO thesis_delta VALUES (?,?,?,?,?)", ("d1", "NVDA", "2026-09-01", "maintained", "{}"))
        conn.execute("INSERT INTO market_narrative_states VALUES (?,?,?,?,?,?,?)", ("state-current", "power", "전력", "active", "turning", "2026-09-01", json.dumps([state_cp])))
        conn.execute("INSERT INTO market_narrative_states VALUES (?,?,?,?,?,?,?)", ("state-other", "other", "무관", "active", "stable", "2026-09-01", json.dumps([unrelated])))
    monkeypatch.setattr(portfolio_service, "get_portfolio", lambda *_args: {"revision": 1, "updatedAt": "2026-09-01", "positions": [{"ticker": "NVDA", "name": "NVIDIA", "currency": "USD"}]})
    inputs = review_v2.gather_inputs(tmp_path)
    assert {row["owner"] for row in inputs["checkpoints"]} == {"thesis", "state"}
    assert {row["status"] for row in inputs["checkpoints"]} == {"confirmed", "challenged"}
    assert all("state-other" not in row.get("stateId", "") for row in inputs["checkpoints"])
    structured = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    # Confirmed/challenged terminal checkpoints remain authority/history but
    # never become future due actions for the position.
    assert structured["positionReviews"][0]["dueCheckpoints"] == []
    watermark = review_v2.build_input_basis(inputs)["checkpointWatermark"]
    inputs["checkpoints"][0]["status"] = "expired"
    assert review_v2.build_input_basis(inputs)["checkpointWatermark"] != watermark
    previous = {"sourceSchemaVersion": 2, "checkpointReviews": structured["checkpointReviews"]}
    changed = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    changes, _ = review_v2.compare_previous(changed, previous)
    assert any(row["kind"] == "checkpoint" and row["change"] == "changed" for row in changes)


def test_used_canonical_reports_are_consumed_and_empty_portfolio_uses_none(tmp_path):
    report_dir = tmp_path / "company-analysis"; report_dir.mkdir()
    (report_dir / "nvda.json").write_text(json.dumps({"id": "nvda", "ticker": "NVDA", "revision": 1}), encoding="utf-8")
    (report_dir / "other.json").write_text(json.dumps({"id": "other", "ticker": "MSFT", "revision": 1}), encoding="utf-8")
    assert review_v2._used_reports(tmp_path, set()) == []
    refs = review_v2._used_reports(tmp_path, {"NVDA"})
    assert [row["id"] for row in refs] == ["nvda"] and refs[0]["tickers"] == ["NVDA"]
    inputs = _inputs(); inputs["reportRefs"] = refs
    structured = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    assert structured["positionReviews"][0]["canonicalReferences"][0]["id"] == "nvda"
    first = review_v2.build_input_basis(inputs)["fingerprint"]
    inputs["reportRefs"] = [{**refs[0], "revision": 2}]
    assert review_v2.build_input_basis(inputs)["fingerprint"] != first


def test_analytics_method_and_saved_backtest_identity_are_authority_watermarks(tmp_path):
    analytics = {"methodVersion": "portfolio-analytics-v1", "available": True, "baseCurrency": "USD", "positions": [{"ticker": "NVDA", "weight": 1.0, "quoteCurrency": "USD"}], "compatibilitySignature": {"positions": [{"ticker": "NVDA", "weight": 1.0, "currency": "USD"}], "baseCurrency": "USD"}}
    folder = tmp_path / "portfolio-backtests"; folder.mkdir()
    saved = {"id": "run-1", "baseCurrency": "USD", "rebalance": "monthly", "start": "2025-01-01", "end": "2026-01-01", "positions": [{"ticker": "NVDA", "weight": 1.0, "currency": "USD"}], "riskContributions": []}
    (folder / "run.json").write_text(json.dumps(saved), encoding="utf-8")
    ref, _ = review_v2._backtest_ref(tmp_path, [], analytics)
    inputs = _inputs(); inputs["analytics"] = analytics; inputs["backtest"] = ref
    baseline = review_v2.build_input_basis(inputs)
    same = review_v2.build_input_basis(inputs)
    assert baseline["fingerprint"] == same["fingerprint"]
    inputs["analytics"] = {**analytics, "methodVersion": "portfolio-analytics-v2"}
    assert review_v2.build_input_basis(inputs)["fingerprint"] != baseline["fingerprint"]
    inputs["analytics"] = analytics
    changed = {**saved, "end": "2026-02-01"}; (folder / "run.json").write_text(json.dumps(changed), encoding="utf-8")
    inputs["backtest"], _ = review_v2._backtest_ref(tmp_path, [], analytics)
    assert review_v2.build_input_basis(inputs)["fingerprint"] != baseline["fingerprint"]
    (folder / "run.json").unlink()
    inputs["backtest"] = None
    assert review_v2.build_input_basis(inputs)["fingerprint"] != baseline["fingerprint"]


def test_nested_allowlist_and_challenge_rejects_secret_and_path_traversal(tmp_path):
    from features.agent_mode.consultation_schema import normalize_scope
    row = normalize_review({"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01", "reviewRevision": 2, "inputBasis": {"status": "partial", "fingerprint": "x", "marketData": {"status": "partial"}}, "positionReviews": [{"ticker": "NVDA", "thesisVerdict": "BUY_NOW", "secret": "leak", "quantitativeRiskSignals": [{"kind": "current_weight", "weight": 2, "secret": "leak"}]}], "counterEvidence": [{"title": "반증", "secret": "leak"}]}, date="2026-09-01")
    assert row["positionReviews"][0]["thesisVerdict"] == "insufficient_evidence"
    assert "secret" not in row["positionReviews"][0] and row["positionReviews"][0]["quantitativeRiskSignals"] == []
    review_dir = tmp_path / "investment-review"; review_dir.mkdir(); (review_dir / "2026-09-01.json").write_text(json.dumps(row), encoding="utf-8")
    context = review_v2.challenge_context(tmp_path, review_dir, "2026-09-01", 2)
    assert "secret" not in json.dumps(context, ensure_ascii=False)
    assert review_v2.challenge_context(tmp_path, review_dir, "../portfolio", 2)["dataGaps"][0]["code"] == "review_changed_reopen_challenge"
    assert normalize_scope({"kind": "investment_review", "id": "../portfolio", "revision": 2, "intent": "challenge"})["id"] == ""


def test_v2_allowlists_drop_top_level_and_every_basis_secret():
    row = normalize_review({
        "schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01", "topSecret": "no",
        "inputBasis": {"status": "partial", "secret": "no", "portfolio": {"revision": 1, "secret": "no"},
                       "marketData": {"status": "partial", "secret": "no"},
                       "analytics": {"methodVersion": "v1", "secret": "no", "compatibilitySignature": {"secret": "no", "positions": [{"ticker": "NVDA", "weight": .5, "currency": "USD", "secret": "no"}]}},
                       "canonicalReports": [{"kind": "briefing", "id": "us", "secret": "no"}]},
    }, date="2026-09-01")
    encoded = json.dumps(row, ensure_ascii=False)
    assert "secret" not in encoded.casefold() and "topSecret" not in row
    assert row["inputBasis"]["analytics"]["compatibilitySignature"]["positions"] == [{"ticker": "NVDA", "weight": .5, "currency": "USD"}]


def test_v2_projection_allowlists_every_remaining_nested_shape_and_keeps_valid_fields():
    row = normalize_review({
        "schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-01", "reviewRevision": 3,
        "freshness": {"status": "partial", "dueCount": 2, "reasons": [{"code": "checkpoint_due", "secret": "no"}], "secret": "no"},
        "checkpointReviews": [{"id": "cp-1", "ticker": "NVDA", "item": "실적", "direction": "supporting", "status": "open", "dueBy": "2026-09-10", "lastVerdict": {"verdict": "maintained", "at": "2026-09-01", "evidence": [{"memoryId": "m1", "role": "supporting", "secret": "no"}], "secret": "no"}, "secret": "no"}],
        "qualitySummary": {"status": "partial", "score": 82, "grade": "B", "warnings": ["보완 필요", {"secret": "no"}], "suggestedFixes": ["확인", {"secret": "no"}], "secret": "no"},
        "marketTape": {"asOf": "2026-09-01", "items": [{"label": "S&P 500", "value": 5000, "changePct": 1.2, "status": "fresh", "size": "lg", "secret": "no"}], "secret": "no"},
        "warnings": ["저장된 경고", {"message": "drop", "secret": "no"}],
        "marketState": [{"label": "AI", "momentum": "strengthening", "secret": "no"}],
        "thesisChanges": [{"ticker": "NVDA", "verdict": "maintained", "secret": "no"}],
        "portfolioImpacts": [{"ticker": "NVDA", "impact": "watch", "linkedNarratives": ["AI", {"secret": "no"}], "secret": "no"}],
        "keyCheckpoints": [{"checkpoint": "실적", "ticker": "NVDA", "secret": "no"}],
        "linkedNotes": [{"title": "내 노트", "ticker": "NVDA", "secret": "no"}],
        "exposure": [{"narrative": "AI", "count": 2, "secret": "no"}],
        "recentReports": [{"type": "briefing", "id": "2026-09-01.us", "title": "미국", "secret": "no"}],
        "stats": {"marketTotal": 1, "thesisDistribution": {"maintained": 1, "secret": 9}, "secret": "no"},
    }, date="2026-09-01")
    encoded = json.dumps(row, ensure_ascii=False)
    assert "secret" not in encoded.casefold()
    assert row["freshness"] == {"status": "partial", "dueCount": 2, "reasons": [{"code": "checkpoint_due"}]}
    assert row["checkpointReviews"] == [{"id": "cp-1", "ticker": "NVDA", "item": "실적", "direction": "supporting", "status": "open", "lastVerdict": {"verdict": "maintained", "at": "2026-09-01", "evidence": [{"memoryId": "m1", "role": "supporting"}]}, "dueBy": "2026-09-10"}]
    assert row["qualitySummary"]["score"] == 82 and row["qualitySummary"]["warnings"] == ["보완 필요"]
    assert row["marketTape"]["items"] == [{"label": "S&P 500", "status": "fresh", "size": "lg", "value": 5000, "changePct": 1.2}]
    assert row["warnings"] == ["저장된 경고"]
    assert row["marketState"][0]["label"] == "AI" and row["thesisChanges"][0]["ticker"] == "NVDA"
    assert row["portfolioImpacts"][0]["linkedNarratives"] == ["AI"] and row["keyCheckpoints"][0]["checkpoint"] == "실적"
    assert row["linkedNotes"][0]["title"] == "내 노트" and row["recentReports"][0]["id"] == "2026-09-01.us"


def test_legacy_projection_drops_raw_nested_mappings_before_read_only_open():
    row = normalize_review({
        "schemaVersion": 1, "date": "2026-09-01", "summary": "이전 리뷰", "secret": "no",
        "marketTape": {"items": [{"label": "KOSPI", "value": 2600, "secret": "no"}], "secret": "no"},
        "warnings": ["경고", {"secret": "no"}],
        "marketState": [{"label": "AI", "momentum": "stable", "secret": "no"}],
        "qualitySummary": {"score": 90, "secret": "no"},
        "checkpointReviews": [{"id": "old-cp", "secret": "no"}],
    }, date="2026-09-01")
    assert row["sourceSchemaVersion"] == 1 and row["reviewState"] == "stale"
    assert "secret" not in json.dumps(row, ensure_ascii=False).casefold()
    assert row["marketTape"]["items"][0]["label"] == "KOSPI"
    assert row["warnings"] == ["경고"] and row["checkpointReviews"][0]["id"] == "old-cp"


def test_checkpoint_watermark_uses_full_last_verdict_and_terminal_rows_are_not_due():
    base = _inputs()
    checkpoint = {"id": "cp-1", "item": "확인", "direction": "supporting", "status": "open", "dueBy": "2099-01-01", "createdAt": "2026-09-01",
                  "matchers": {"tickers": ["NVDA"], "keywords": ["확인"]}, "lastVerdict": {"verdict": "confirmed", "at": "2026-09-01T01:00:00Z", "evidence": [{"memoryId": "m1", "role": "supporting"}]}, "history": []}
    base["checkpoints"] = [checkpoint]
    first = review_v2.build_input_basis(base)["checkpointWatermark"]
    changed = json.loads(json.dumps(checkpoint)); changed["lastVerdict"]["at"] = "2026-09-02T01:00:00Z"; changed["lastVerdict"]["evidence"][0]["memoryId"] = "m2"
    base["checkpoints"] = [changed]
    assert review_v2.build_input_basis(base)["checkpointWatermark"] != first
    base["checkpoints"] = [{**changed, "status": "expired", "dueAt": "2020-01-01"}]
    structured = review_v2.build_structured_review(base, review_v2.build_input_basis(base))
    assert structured["positionReviews"][0]["dueCheckpoints"] == []


def test_production_wal_get_reads_current_rows_without_touching_data_tree(tmp_path, monkeypatch):
    import os
    import sqlite3
    from features.portfolio import service as portfolio_service

    db = tmp_path / "market-memory.sqlite3"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE thesis (ticker TEXT, company TEXT, updated_at TEXT, linked_regimes_json TEXT, next_checkpoints_json TEXT)")
    writer.execute("INSERT INTO thesis VALUES (?,?,?,?,?)", ("NVDA", "NVIDIA", "2026-09-01", "[]", "[]"))
    writer.commit()  # Keep the writer open: current content remains in WAL.
    monkeypatch.setattr(portfolio_service, "get_portfolio", lambda *_args: {"revision": 1, "positions": [{"ticker": "NVDA"}]})
    before = {path.relative_to(tmp_path).as_posix(): (path.read_bytes(), os.stat(path).st_mtime_ns) for path in tmp_path.rglob("*") if path.is_file()}
    try:
        gathered = review_v2.gather_inputs(tmp_path)
        after = {path.relative_to(tmp_path).as_posix(): (path.read_bytes(), os.stat(path).st_mtime_ns) for path in tmp_path.rglob("*") if path.is_file()}
        assert [row["ticker"] for row in gathered["theses"]] == ["NVDA"]
        assert before == after
    finally:
        writer.close()


def test_used_briefings_match_final_position_reference_union(tmp_path):
    folder = tmp_path / "briefings"; folder.mkdir()
    for index in range(12):
        (folder / f"2026-08-{index + 1:02d}.us.json").write_text(json.dumps({"id": f"us-{index}", "marketScope": "us", "tickers": ["NVDA"]}), encoding="utf-8")
        (folder / f"2026-08-{index + 1:02d}.kr.json").write_text(json.dumps({"id": f"kr-{index}", "marketScope": "kr", "tickers": ["005930"]}), encoding="utf-8")
    positions = [{"ticker": "NVDA", "marketScope": "us"}]
    refs = review_v2._used_reports(tmp_path, {"NVDA"}, positions=positions)
    assert len(refs) == 8 and {row["marketScope"] for row in refs} == {"us"}
    inputs = _inputs(); inputs["positions"] = positions; inputs["reportRefs"] = refs
    structured = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    consumed = {(row["kind"], row["id"]) for row in structured["positionReviews"][0]["canonicalReferences"]}
    basis_refs = {(row["kind"], row["id"]) for row in review_v2.build_input_basis(inputs)["canonicalReports"]}
    assert basis_refs == consumed and review_v2._used_reports(tmp_path, set(), positions=[]) == []
