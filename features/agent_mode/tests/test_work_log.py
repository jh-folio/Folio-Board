from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from starlette.requests import Request

from features.agent_mode import work_log_routes
from features.agent_mode.work_log import WorkLogService
from features.agent_mode.work_log_http_schema import WorkLogQuery
from features.agent_mode.work_log_schema import WORK_LOG_ENTRY_KEYS
from features.agent_mode.work_log_store import WorkLogStore, work_log_lock
from features.agent_mode.work_log_token import WorkLogConflictError
from features.common import jobs
from features.common.shared_jobs_projection import new_shared_job, project_terminal_result
from features.common.shared_jobs_schema import (
    ArtifactRef,
    CommitIntent,
    ErrorCode,
    ExpectedArtifact,
    JobStatus,
    SharedJob,
    TERMINAL_STATUSES,
)
from features.common.shared_jobs_store import SharedJobStore, store_lock


NOW = datetime(2026, 7, 22, 1, 2, 3, tzinfo=UTC)
NOW_Z = "2026-07-22T01:02:03Z"
HASH = "0" * 64

FORBIDDEN = {
    "operationId",
    "commitIntent",
    "resultProjection",
    "engine",
    "title",
    "reportId",
    "artifactId",
    "snapshotId",
    "artifactRefs",
    "path",
    "packPath",
    "message",
    "request",
    "context",
    "selectedText",
    "attachments",
    "reply",
    "markdown",
    "revisedMarkdown",
    "diff",
    "exception",
    "traceback",
}


def _clock() -> datetime:
    return NOW


def _job(
    sequence: int,
    task_type: str,
    *,
    kind: str = "agent_bridge",
    requested_mode: str | None = "cli",
    proposal_id: str | None = None,
    created_at: str = NOW_Z,
) -> SharedJob:
    job = new_shared_job(
        kind=kind,
        task_type=task_type,
        generation_mode="llm_cli" if requested_mode == "cli" else "llm_api",
        adapter="codex" if requested_mode == "cli" else "openai_api",
        requested_mode=requested_mode,
        mode="answer" if task_type == "companion" else "generate",
        attempted_engine="cli" if requested_mode == "cli" else "api",
        clock=_clock,
        proposal_id=proposal_id,
    )
    return job.model_copy(
        update={
            "id": f"job_{UUID(int=sequence, version=4)}",
            "createdAt": created_at,
            "updatedAt": created_at,
        }
    )


def _service(tmp_path: Path) -> tuple[SharedJobStore, WorkLogService]:
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    service = WorkLogService(
        store,
        tmp_path / "agent-work-log.json",
        tmp_path / "agent-proposals",
        clock=_clock,
        token_bytes=lambda: b"w" * 32,
    )
    return store, service


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proposal(proposals: Path, proposal_id: str, status: str, *, canary: str = "BODY_CANARY") -> None:
    active = status in {"pending", "applying"}
    proposals.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 2,
        "id": proposal_id,
        "reportKind": "briefing",
        "reportId": "2026-07-22",
        "marketScope": "both",
        "status": status,
        "createdAt": NOW_Z,
        "updatedAt": NOW_Z,
        "finishedAt": None if active else NOW_Z,
        "baseRevision": {"number": 1, "hash": HASH},
        "targetRevision": {"number": 2, "hash": HASH} if status == "applying" else None,
        "operationId": "proposal-apply-operation" if status == "applying" else None,
        "errorCode": None,
        "requestHash": HASH,
        "revisedMarkdownHash": HASH,
        "diffHash": HASH,
        "legacyNormalizationHash": None,
        "userRequest": canary if active else None,
        "summary": canary if active else None,
        "revisedMarkdown": canary if active else None,
        "diff": canary if active else None,
        "adapter": "codex" if active else None,
        "model": "test" if active else None,
        "allowedSourceRefs": [] if active else None,
    }
    (proposals / f"{proposal_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_strict_entry_schema_has_exact_26_keys_and_no_forbidden_fields(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.add(_job(1, "companion"))

    entry = service.list(limit=200, offset=0, kind="all")["entries"][0]
    serialized = json.dumps(entry)

    assert len(WORK_LOG_ENTRY_KEYS) == 31
    assert set(entry) == WORK_LOG_ENTRY_KEYS
    assert not (set(entry) & FORBIDDEN)
    assert all(f'"{key}"' not in serialized for key in FORBIDDEN)


def test_ordering_filters_category_before_pagination_and_flattens_artifacts(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    companion = _job(4, "companion", created_at="2026-07-22T01:02:04Z")
    later_task = _job(3, "company_analysis", created_at="2026-07-22T01:02:05Z")
    tied_first = _job(1, "briefing")
    tied_second = _job(2, "topic_report").model_copy(
        update={
            "artifactRefs": [
                ArtifactRef(type="visual", id="v1"),
                ArtifactRef(type="report", id="r1"),
                ArtifactRef(type="visual", id="v2"),
            ]
        }
    )
    for job in (companion, tied_second, later_task, tied_first):
        store.add(job)

    first_page = service.list(limit=2, offset=0, kind="task")
    second_page = service.list(limit=2, offset=2, kind="task")

    assert first_page["total"] == second_page["total"] == 3
    assert [entry["jobId"] for entry in first_page["entries"]] == [later_task.id, tied_first.id]
    assert [entry["jobId"] for entry in second_page["entries"]] == [tied_second.id]
    flattened = second_page["entries"][0]
    assert flattened["artifactTypes"] == ["report", "visual"]
    assert flattened["artifactCount"] == 3


def test_direct_topic_is_included_while_index_rss_setup_and_install_are_excluded(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    topic = _job(1, "topic_report", kind="topic_report", requested_mode="direct")
    excluded = (
        _job(2, "index", kind="index", requested_mode=None),
        _job(3, "rss", kind="rss", requested_mode=None),
        _job(4, "setup", kind="setup", requested_mode=None),
        _job(5, "setup", kind="agent_cli_install", requested_mode=None),
    )
    store.add(topic)
    for job in excluded:
        store.add(job)

    entries = service.list(limit=200, offset=0, kind="all")["entries"]

    assert [(entry["taskType"], entry["requestedMode"]) for entry in entries] == [
        ("topic_report", "direct")
    ]


def test_cli_reports_include_briefing_and_company_and_visible_legacy_uses_same_projection(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    briefing = _job(1, "briefing")
    company = _job(2, "company_analysis")
    store.add(briefing)
    store.add(company)
    legacy = {
        "legacy-companion": {
            "id": "legacy-companion",
            "kind": "agent_bridge",
            "taskType": "companion",
            "status": "done",
            "createdAt": NOW_Z,
            "updatedAt": NOW_Z,
            "finishedAt": NOW_Z,
            "generationMode": "llm_cli",
            "adapter": "codex",
            "requestedMode": "cli",
            "attemptedEngine": "cli",
            "mode": "answer",
            "result": {"proposalId": None, "reply": "LEGACY_PRIVATE_CANARY"},
        }
    }
    store.legacy_path.write_text(json.dumps(legacy), encoding="utf-8")

    entries = service.list(limit=200, offset=0, kind="all")["entries"]
    by_task = {entry["taskType"] for entry in entries}
    legacy_entry = next(entry for entry in entries if entry["jobId"] == "legacy-companion")

    assert {"briefing", "company_analysis", "companion"} <= by_task
    assert set(legacy_entry) == WORK_LOG_ENTRY_KEYS
    assert "LEGACY_PRIVATE_CANARY" not in json.dumps(entries)


def test_synchronous_excluded_briefing_and_company_create_no_shared_job(monkeypatch, tmp_path: Path) -> None:
    import app

    store, service = _service(tmp_path)
    store.add(_job(1, "index", kind="index", requested_mode=None))
    before = store.path.read_bytes()
    monkeypatch.setattr(jobs, "JOBS_PATH", store.legacy_path)
    monkeypatch.setattr(app, "read_automation_settings", lambda: {})
    monkeypatch.setattr(app, "request_generation_mode", lambda _body: "rules")
    monkeypatch.setattr(app, "build_briefing", lambda *_args, **_kwargs: {"id": "briefing-sync"})
    monkeypatch.setattr(app, "analyze_company", lambda *_args, **_kwargs: {"id": "company-sync"})
    monkeypatch.setattr(app, "apply_quality_loop", lambda _kind, report, **_kwargs: report)
    monkeypatch.setattr(app, "save_analysis_report", lambda report: report)
    request = Request({"type": "http", "method": "GET", "path": "/api/analyze", "query_string": b"q=ACME", "headers": []})

    # 시장 하나로 부른다. 날짜를 주고 여러 시장을 고르면 발행일이 갈려 실행이 나뉘고
    # 응답이 `reports` 목록이 된다(`test_session_publication_date`). 이 테스트가 보는
    # 것은 동기 실행이 공유 job을 만들지 않는다는 것뿐이라 그 분기를 탈 이유가 없다.
    assert app.api_create_briefing({"date": "2026-07-22", "markets": ["us"]})["id"] == "briefing-sync"
    assert app.api_analyze(request)["id"] == "company-sync"

    assert store.path.read_bytes() == before
    assert service.list(limit=200, offset=0, kind="all")["entries"] == []


def test_restart_failed_and_every_job_and_proposal_state_survive_service_reload(tmp_path: Path) -> None:
    store, _service_before = _service(tmp_path)
    statuses = list(JobStatus)
    for sequence, status in enumerate(statuses, 1):
        base = _job(sequence, "topic_report" if status == JobStatus.COMMITTING else "companion")
        values = base.model_dump(mode="json")
        values.update({"status": status.value, "messageCode": status.value})
        if status in TERMINAL_STATUSES:
            values.update(
                {
                    "finishedAt": NOW_Z,
                    "errorCode": "restart_interrupted" if status == JobStatus.FAILED_RESTART else (
                        "internal_error" if status.value.startswith("failed") else None
                    ),
                    "resultProjection": project_terminal_result(
                        base,
                        status,
                        error_code="restart_interrupted" if status == JobStatus.FAILED_RESTART else "internal_error",
                    ).model_dump(mode="json"),
                }
            )
        elif status == JobStatus.COMMITTING:
            projection = project_terminal_result(
                base,
                JobStatus.DONE,
                {
                    "artifactId": "topic-artifact",
                    "reportId": "topic-report",
                    "date": "2026-07-22",
                    "title": "Safe code",
                },
            )
            expected = ExpectedArtifact(
                type="topic_report",
                id="topic-artifact",
                storage="json",
                baseHash=None,
                baseMarker=None,
                targetRevision=1,
                targetHash=HASH,
            )
            intent = CommitIntent(
                operationId="topic-commit-operation",
                expectedArtifacts=[expected],
                terminalProjection=projection,
            )
            values.update(
                {
                    "operationId": intent.operationId,
                    "artifactRefs": [ArtifactRef(type=expected.type, id=expected.id).model_dump(mode="json")],
                    "commitIntent": intent.model_dump(mode="json"),
                }
            )
        store.add(SharedJob.model_validate(values))

    proposal_statuses = ["pending", "applying", "applied", "rejected", "stale", "conflict", "failed_apply"]
    for index, status in enumerate(proposal_statuses, 100):
        proposal_id = f"{index:032x}"
        _proposal(tmp_path / "agent-proposals", proposal_id, status)
        store.add(_job(index, "companion", proposal_id=proposal_id))
    missing_id = "f" * 32
    store.add(_job(999, "companion", proposal_id=missing_id))

    reloaded = WorkLogService(
        SharedJobStore(store.path, store.legacy_path, clock=_clock),
        tmp_path / "agent-work-log.json",
        tmp_path / "agent-proposals",
        clock=_clock,
    )
    entries = reloaded.list(limit=200, offset=0, kind="all")["entries"]

    assert "failed_restart" in {entry["status"] for entry in entries}
    observed_proposals = {entry["proposalStatus"] for entry in entries if entry["proposalId"]}
    assert observed_proposals == {*proposal_statuses, "unavailable"}
    assert "BODY_CANARY" not in json.dumps(entries)


def test_dom_canary_projection_is_absent_at_asgi_boundary_and_invalid_proposal_id_cannot_escape(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store, _ = _service(tmp_path)
    legacy = {
        "legacy-malicious": {
            "kind": "agent_bridge",
            "taskType": "companion",
            "status": "queued",
            "createdAt": NOW_Z,
            "updatedAt": NOW_Z,
            "proposalId": "../outside",
            "request": "<img src=x onerror=PRIVATE_DOM_CANARY>",
            "context": "PRIVATE_CONTEXT_CANARY",
        }
    }
    store.legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text('"PRIVATE_OUTSIDE_CANARY"', encoding="utf-8")
    real_read_text = Path.read_text

    def reject_outside_read(path: Path, *args, **kwargs):
        if path.resolve() == outside.resolve():
            pytest.fail("invalid proposalId escaped proposals directory before validation")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_outside_read)
    monkeypatch.setattr(jobs, "JOBS_PATH", store.legacy_path)

    response = work_log_routes.list_work_log(WorkLogQuery())
    serialized = json.dumps(response)

    assert response["entries"][0]["proposalStatus"] == "unavailable"
    assert "CANARY" not in serialized
    assert set(response["entries"][0]) == WORK_LOG_ENTRY_KEYS


def test_clear_preserves_artifacts_shared_jobs_report_and_pending_proposal_hashes(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    proposal_id = "a" * 32
    _proposal(tmp_path / "agent-proposals", proposal_id, "pending", canary="PENDING_PROPOSAL_BODY")
    report = tmp_path / "briefings" / "2026-07-22.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"markdown": "# immutable report", "revision": 1}), encoding="utf-8")
    store.add(_job(1, "companion", proposal_id=proposal_id))
    paths = (store.path, report, tmp_path / "agent-proposals" / f"{proposal_id}.json")
    before = {path: _sha(path) for path in paths}

    preview = service.clear_preview("all")
    cleared = service.clear("all", preview["previewToken"])
    reloaded = WorkLogService(store, tmp_path / "agent-work-log.json", tmp_path / "agent-proposals", clock=_clock)

    assert cleared["hiddenCount"] == 1
    assert reloaded.list(limit=200, offset=0, kind="all")["entries"] == []
    assert {path: _sha(path) for path in paths} == before
    assert json.loads(paths[2].read_text(encoding="utf-8"))["userRequest"] == "PENDING_PROPOSAL_BODY"


def _concurrent_outcomes(operations) -> tuple[list[dict], list[str], list[str]]:
    start = Barrier(2)

    def invoke(operation):
        start.wait(timeout=5)
        try:
            return "success", operation()
        except WorkLogConflictError as error:
            return "conflict", error.code
        except Exception as error:  # The assertion reports unsafe store races by stable type only.
            return "error", type(error).__name__

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(invoke, operations))
    successes = [value for kind, value in outcomes if kind == "success"]
    conflicts = [value for kind, value in outcomes if kind == "conflict"]
    errors = [value for kind, value in outcomes if kind == "error"]
    return successes, conflicts, errors


@pytest.mark.parametrize("_repeat", range(3))
def test_concurrent_clear_same_token_has_exactly_one_success_and_one_replay_conflict(
    monkeypatch,
    tmp_path: Path,
    _repeat: int,
) -> None:
    store, issuer = _service(tmp_path)
    store.add(_job(1, "companion"))
    peer = WorkLogService(
        SharedJobStore(store.path, store.legacy_path, clock=_clock),
        tmp_path / "agent-work-log.json",
        tmp_path / "agent-proposals",
        clock=_clock,
    )
    token = issuer.clear_preview("all")["previewToken"]
    real_write = WorkLogStore.write

    def widen_pre_replace_window(self, hidden_jobs, tokens, revision):
        time.sleep(0.05)
        return real_write(self, hidden_jobs, tokens, revision)

    monkeypatch.setattr(WorkLogStore, "write", widen_pre_replace_window)

    successes, conflicts, errors = _concurrent_outcomes(
        (lambda: issuer.clear("all", token), lambda: peer.clear("all", token))
    )

    assert len(successes) == 1
    assert successes[0]["hiddenCount"] == 1
    assert conflicts == ["preview_token_replayed"]
    assert errors == []


@pytest.mark.parametrize("_repeat", range(3))
def test_concurrent_migration_same_token_has_exactly_one_commit_and_one_replay_conflict(
    monkeypatch,
    tmp_path: Path,
    _repeat: int,
) -> None:
    store, issuer = _service(tmp_path)
    store.legacy_path.write_text(
        json.dumps(
            {
                "legacy-visible": {
                    "kind": "agent_bridge",
                    "taskType": "companion",
                    "status": "queued",
                    "createdAt": NOW_Z,
                    "updatedAt": NOW_Z,
                }
            }
        ),
        encoding="utf-8",
    )
    peer = WorkLogService(
        SharedJobStore(store.path, store.legacy_path, clock=_clock),
        tmp_path / "agent-work-log.json",
        tmp_path / "agent-proposals",
        clock=_clock,
    )
    token = issuer.migration_preview()["previewToken"]
    real_write = WorkLogStore.write

    def widen_pre_replace_window(self, hidden_jobs, tokens, revision):
        time.sleep(0.05)
        return real_write(self, hidden_jobs, tokens, revision)

    monkeypatch.setattr(WorkLogStore, "write", widen_pre_replace_window)

    successes, conflicts, errors = _concurrent_outcomes(
        (
            lambda: issuer.migration_confirm(token, "migrate_keep_original"),
            lambda: peer.migration_confirm(token, "migrate_keep_original"),
        )
    )

    assert len(successes) == 1
    assert successes[0]["migratedJobs"] == 1
    assert conflicts == ["preview_token_replayed"]
    assert errors == []
    assert len(SharedJobStore(store.path, store.legacy_path, clock=_clock).load().jobs) == 1


def _churn_path_lock_registries(tmp_path: Path) -> None:
    for index in range(65):
        root = tmp_path / "lock-churn" / str(index)
        SharedJobStore(root / "jobs-v2.json", root / "jobs.json", clock=_clock)
        WorkLogStore(root / "agent-work-log.json", clock=_clock)


@pytest.mark.parametrize("_repeat", range(3))
def test_concurrent_clear_survives_lock_registry_eviction_churn(
    monkeypatch,
    tmp_path: Path,
    _repeat: int,
) -> None:
    store_lock.cache_clear()
    work_log_lock.cache_clear()
    store, issuer = _service(tmp_path)
    store.add(_job(1, "companion"))
    token = issuer.clear_preview("all")["previewToken"]
    _churn_path_lock_registries(tmp_path)
    peer = WorkLogService(
        SharedJobStore(store.path, store.legacy_path, clock=_clock),
        tmp_path / "agent-work-log.json",
        tmp_path / "agent-proposals",
        clock=_clock,
    )
    real_write = WorkLogStore.write

    def widen_pre_replace_window(self, hidden_jobs, tokens, revision):
        time.sleep(0.05)
        return real_write(self, hidden_jobs, tokens, revision)

    monkeypatch.setattr(WorkLogStore, "write", widen_pre_replace_window)
    successes, conflicts, errors = _concurrent_outcomes(
        (lambda: issuer.clear("all", token), lambda: peer.clear("all", token))
    )

    assert len(successes) == 1
    assert conflicts == ["preview_token_replayed"]
    assert errors == []


@pytest.mark.parametrize("_repeat", range(3))
def test_concurrent_migration_survives_lock_registry_eviction_churn(
    monkeypatch,
    tmp_path: Path,
    _repeat: int,
) -> None:
    store_lock.cache_clear()
    work_log_lock.cache_clear()
    store, issuer = _service(tmp_path)
    store.legacy_path.write_text(
        json.dumps(
            {
                "legacy-visible": {
                    "kind": "agent_bridge",
                    "taskType": "companion",
                    "status": "queued",
                    "createdAt": NOW_Z,
                    "updatedAt": NOW_Z,
                }
            }
        ),
        encoding="utf-8",
    )
    token = issuer.migration_preview()["previewToken"]
    _churn_path_lock_registries(tmp_path)
    peer = WorkLogService(
        SharedJobStore(store.path, store.legacy_path, clock=_clock),
        tmp_path / "agent-work-log.json",
        tmp_path / "agent-proposals",
        clock=_clock,
    )
    real_write = WorkLogStore.write

    def widen_pre_replace_window(self, hidden_jobs, tokens, revision):
        time.sleep(0.05)
        return real_write(self, hidden_jobs, tokens, revision)

    monkeypatch.setattr(WorkLogStore, "write", widen_pre_replace_window)
    successes, conflicts, errors = _concurrent_outcomes(
        (
            lambda: issuer.migration_confirm(token, "migrate_keep_original"),
            lambda: peer.migration_confirm(token, "migrate_keep_original"),
        )
    )

    assert len(successes) == 1
    assert conflicts == ["preview_token_replayed"]
    assert errors == []
