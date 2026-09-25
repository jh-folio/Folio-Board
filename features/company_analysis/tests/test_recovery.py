from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from types import SimpleNamespace
from features.agent_mode import bridge

_invoke_cli = bridge._invoke_agent_cli

from features.company_analysis import service
from features.company_analysis.finalize import finalize_report
from features.company_analysis.recovery import candidate_path, preserve_candidate
from features.company_analysis.style import REQUIRED_SECTION_HEADINGS
from features.common.canonical_reports import prepare, ReportKind, WriteKind
from features.common.canonical_report_types import CanonicalValidationError
from features.common.canonical_report_types import CanonicalConflictError
from features.common.cli_completion import observe_completion
from features.common.job_json_producers import JobJsonProducers, ReportJobRequest
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import JobStatus
from features.common.shared_jobs_store import SharedJobStore
from features.common.shared_jobs_private import JobPrivateLifecycle


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ANALYSIS_REPORTS_DIR", tmp_path / "company-analysis")
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "MARKET_MEMORY_DB_PATH", tmp_path / "market-memory.sqlite3")
    return tmp_path


def report(*, partial=False):
    body = "# 분석\n\n" + "\n\n".join(f"## {h}\n\n확인된 내용입니다." for h in REQUIRED_SECTION_HEADINGS)
    return finalize_report({"company": {"ticker": "TEST", "name": "Test"},
                            "generatedAt": "2026-09-21T01:00:00Z", "headline": "Test 분석",
                            "markdown": body, "executionFacts": {
                                "completionStatus": "incomplete" if partial else "completed",
                                "stopReason": "limit" if partial else "end"}})


def test_partial_preserves_normal_bytes_overlay_and_reopens(root):
    normal = service.save_analysis_report(report())
    path = root / "company-analysis" / f"{normal['id']}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["personalOverlay"] = {"note": "preserve"}
    path.write_text(json.dumps(data), encoding="utf-8")
    original = path.read_bytes()
    partial = service.save_analysis_report(report(partial=True))
    assert partial["saved"] is False and partial["recoveryStored"] is True
    assert path.read_bytes() == original
    assert service.get_analysis_report(partial["id"])["markdown"] == report()["markdown"]
    assert partial["id"] in {row["id"] for row in service.list_analysis_reports()}
    assert "personalOverlay" not in partial
    assert service.delete_analysis_report(partial["id"])["deleted"]
    assert path.read_bytes() == original


def test_first_partial_never_becomes_canonical(root):
    candidate = service.save_analysis_report(report(partial=True))
    assert not list((root / "company-analysis").glob("*.json"))
    assert candidate_path(root / "company-analysis", candidate["id"]).exists()


def test_write_failure_keeps_recovery_without_overwriting(root, monkeypatch):
    normal = service.save_analysis_report(report())
    path = root / "company-analysis" / f"{normal['id']}.json"
    original = path.read_bytes()
    monkeypatch.setattr(service, "commit_sync", lambda *_: (_ for _ in ()).throw(PermissionError()))
    changed = report(); changed["markdown"] += "\n추가 본문"
    result = service.save_analysis_report(changed)
    assert result["saved"] is False and result["saveError"]["code"] == "save_failed"
    assert service.get_analysis_report(result["id"])["markdown"] == changed["markdown"]
    assert path.read_bytes() == original


def test_success_removes_only_its_own_recovery(root):
    earlier = preserve_candidate(root / "company-analysis", report(partial=True))
    changed = report(); changed["markdown"] += "\n새 실행"
    result = service.save_analysis_report(changed)
    assert result["saved"] is True
    assert [p.stem for p in (root / "company-analysis" / "recovery").glob("*.json")] == [earlier["id"]]


def test_guard_covers_bypassing_writers(root):
    item = report(partial=True); item["id"] = "safe-id"
    with pytest.raises(CanonicalValidationError, match="복구 후보"):
        prepare(report_kind=ReportKind.COMPANY_ANALYSIS, write_kind=WriteKind.CANONICAL,
                exact_path=root / "company-analysis" / "safe-id.json", candidate=item)


def test_bad_identity_cannot_write_outside_storage(root):
    item = report(); item["id"] = "../escaped"
    with pytest.raises(ValueError):
        service.save_analysis_report(item)
    assert not (root / "escaped.json").exists()
    assert not list((root / "company-analysis" / "recovery").glob("*.json"))


def test_job_partial_is_not_done_and_survives_new_reader(root):
    clock = lambda: datetime(2026, 9, 21, tzinfo=UTC)
    store = SharedJobStore(root / "jobs-v2.json", root / "jobs.json", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="company_analysis", generation_mode="llm_cli",
                         adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    producer = JobJsonProducers(root, clock=clock)
    with pytest.raises(CanonicalValidationError):
        producer.stage_company(store.get(job.id), ReportJobRequest(report(partial=True), {}))
    assert store.get(job.id).status is JobStatus.RUNNING
    assert service.list_analysis_reports()[0]["title"].startswith("[복구 후보]")


def test_job_success_uses_existing_commit_proof_and_cleans_recovery(root):
    clock = lambda: datetime(2026, 9, 21, tzinfo=UTC)
    store = SharedJobStore(root / "jobs-v2.json", root / "jobs.json", clock=clock)
    job = new_shared_job(kind="agent_bridge", task_type="company_analysis", generation_mode="llm_cli",
                         adapter="codex", requested_mode="cli", mode="generate", attempted_engine="cli", clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    producer = JobJsonProducers(root, clock=clock)
    bundle = producer.stage_company(store.get(job.id), ReportJobRequest(report(), {"artifactId": "test", "reportId": "test", "date": "2026-09-21", "title": "Test"}))
    assert list((root / "company-analysis" / "recovery").glob("*.json"))
    producer.workspace.commit(bundle, store, JobPrivateLifecycle(root / "job-context", clock=clock))
    assert not list((root / "company-analysis" / "recovery").glob("*.json"))
    assert store.get(job.id).status is JobStatus.DONE


@pytest.mark.parametrize("adapter,events,status,reason", [
    ("claude", [{"type": "result", "subtype": "success", "result": "본문"}], "completed", "end"),
    ("claude", [{"type": "result", "stop_reason": "max_tokens", "result": "일부"}], "incomplete", "limit"),
    ("claude", [{"type": "result", "stop_reason": "pause_turn", "result": "일부"}], "incomplete", "other"),
    ("claude", [{"type": "result", "is_error": True, "result": "일부"}], "failed", "other"),
    ("codex", [{"type": "item.completed", "item": {"type": "agent_message", "text": "본문"}}, {"type": "turn.completed"}], "completed", "end"),
    ("codex", [{"type": "turn.failed"}], "failed", "other"),
    ("antigravity", [], "unknown", "unknown"),
])
def test_completion_only_claims_observed_facts(adapter, events, status, reason):
    _, facts = observe_completion(adapter, "\n".join(json.dumps(e) for e in events))
    assert facts == {"completionStatus": status, "stopReason": reason}


def test_structural_gap_is_not_provider_limit():
    item = report(); item["markdown"] = "# 시작만 있음"
    item = finalize_report(item)
    assert item["completion"] == {"status": "incomplete", "stopReason": "end", "structureIncomplete": True}


@pytest.mark.parametrize("exit_code,stop,status", [(0, "end_turn", "completed"), (1, "max_tokens", "incomplete")])
def test_transport_returns_body_and_completion_without_raw_events(monkeypatch, exit_code, stop, status):
    stdout = json.dumps({"type": "result", "subtype": "success", "result": "보고서 본문", "stop_reason": stop, "private": "CANARY"})
    commands = []
    monkeypatch.setattr(bridge, "_adapter_command", lambda *a, **k: ["claude", "--output-format", "text"])
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda command, **k: (commands.append(command) or SimpleNamespace(returncode=exit_code, communicate=lambda *a, **kw: (stdout, ""))))
    facts = {}
    assert _invoke_cli({"id": "claude"}, "prompt", 30, facts_sink=facts, observe_result=True) == "보고서 본문"
    assert facts["executionFacts"]["completionStatus"] == status
    assert "stream-json" in commands[0] and "--verbose" in commands[0]
    assert "CANARY" not in repr(facts)


def test_transport_rejects_unparseable_event_stream(monkeypatch):
    monkeypatch.setattr(bridge, "_adapter_command", lambda *a, **k: ["codex", "exec", "-"])
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: SimpleNamespace(returncode=0, communicate=lambda *a, **kw: ('{"unexpected":"CANARY"}', "")))
    with pytest.raises(bridge.AgentProcessError, match="본문"):
        _invoke_cli({"id": "codex"}, "prompt", 30, facts_sink={}, observe_result=True)


def test_concurrent_newer_commit_wins_and_loser_remains_recoverable(root, monkeypatch):
    normal = service.save_analysis_report(report())
    actual_commit = service.commit_sync
    def concurrent_commit(prepared):
        competing = report(); competing["id"] = normal["id"]; competing["markdown"] += "\n다른 실행"
        newer = prepare(report_kind=ReportKind.COMPANY_ANALYSIS, write_kind=WriteKind.CANONICAL,
                        exact_path=prepared.exact_path, candidate=competing)
        actual_commit(newer)
        return actual_commit(prepared)
    monkeypatch.setattr(service, "commit_sync", concurrent_commit)
    loser = report(); loser["markdown"] += "\n경합한 실행"
    with pytest.raises(CanonicalConflictError):
        service.save_analysis_report(loser)
    assert service.get_analysis_report(normal["id"])["markdown"].endswith("다른 실행")
    recovery = next(r for r in service.list_analysis_reports() if r["id"].startswith("recovery-"))
    assert service.get_analysis_report(recovery["id"])["markdown"] == loser["markdown"]


def test_corrupted_candidate_does_not_break_list_or_detail(root):
    candidate = preserve_candidate(root / "company-analysis", report(partial=True))
    candidate_path(root / "company-analysis", candidate["id"]).write_text("broken", encoding="utf-8")
    assert service.get_analysis_report(candidate["id"]) is None
    assert service.list_analysis_reports() == []


def test_recovery_write_failure_never_replaces_normal(root, monkeypatch):
    normal = service.save_analysis_report(report())
    original = service.get_analysis_report(normal["id"])
    monkeypatch.setattr("features.company_analysis.recovery.atomic_write", lambda *a: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        service.save_analysis_report(report(partial=True))
    assert service.get_analysis_report(normal["id"]) == original


def test_quality_repair_does_not_inherit_previous_completion(root, monkeypatch):
    from features.agent_mode import service as agent_service
    monkeypatch.setattr(agent_service, "evaluate_artifact", lambda *a: {})
    result = agent_service.write_quality_repair_from_markdown({
        "draftArtifact": report(),
        "internal": {"targetArtifactType": "company_analysis", "targetArtifactId": "test"},
        "executionFacts": {"completionStatus": "incomplete", "stopReason": "limit"},
    }, report()["markdown"], persist=False)
    assert result["completion"]["status"] == "incomplete"
