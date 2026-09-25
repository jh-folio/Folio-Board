from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from features.common.canonical_identity import ReportKind
from features.common.canonical_report_state import canonical_content_hash
from features.common.canonical_report_types import WriteKind
from features.common.canonical_reports import commit_sync, prepare
from features.common.shared_jobs_completion import (
    ArtifactCompletionSource,
    _mint_artifact_completion_proof,
)
from features.common.shared_jobs_projection import (
    ARTIFACT_TASKS,
    new_shared_job,
    project_terminal_result,
)
from features.common.shared_jobs_schema import (
    CommitIntent,
    ErrorCode,
    ExpectedArtifact,
    JobStatus,
    SharedJob,
    StorageKind,
    TaskType,
)
from features.common.shared_jobs_store import SharedJobStore
from features.daily_briefing import builder


NOW = datetime(2026, 7, 22, 3, 4, 5, tzinfo=UTC)
SHA = "a" * 64
PRIVATE_CANARY = "PRIVATE_TODO14_CANARY_DO_NOT_PROJECT"


def _clock() -> datetime:
    return NOW


def _store(root: Path) -> SharedJobStore:
    return SharedJobStore(root / "jobs-v2.json", root / "jobs.json", clock=_clock)


def _running(root: Path, task_type: TaskType) -> tuple[SharedJobStore, SharedJob]:
    store = _store(root)
    proposal_id = "proposal-quality" if task_type is TaskType.QUALITY_REPAIR else None
    job = new_shared_job(
        kind="agent_bridge",
        task_type=task_type,
        generation_mode="llm_cli",
        adapter="codex",
        requested_mode="cli",
        mode="generate",
        attempted_engine="cli",
        clock=_clock,
        proposal_id=proposal_id,
    )
    store.add(job)
    store.transition(job.id, JobStatus.RUNNING)
    current = store.get(job.id)
    assert current is not None
    return store, current


NON_ARTIFACT_CASES = {
    TaskType.INDEX: (
        {"count": 7, "generatedAt": "2026-07-22T03:04:05Z", "incremental": True, "sqlite": "fixture.sqlite3"},
        {"status": "done", "count": 7, "generatedAt": "2026-07-22T03:04:05Z", "incremental": True, "sqlite": "fixture.sqlite3"},
    ),
    TaskType.RSS: (
        # `skipped`는 건너뛴 이유(코드)다. 정상 수집에서는 비어 있고, 워크스페이스를
        # 옮긴 직후처럼 건너뛴 실행에서만 채워진다 — 없으면 화면이 그 실행을
        # "수집 완료. 신규 0개"로 그린다.
        {"added": 2, "total": 5, "failed": 1},
        {"status": "done", "added": 2, "total": 5, "failed": 1, "skipped": None},
    ),
    TaskType.SETUP: (
        {"ok": False, "adapter": "antigravity"},
        {"status": "done", "ok": True, "adapter": "codex"},
    ),
    TaskType.COMPANION: (
        {"proposalId": "proposal-safe"},
        {
            "status": "done",
            "requestedMode": "cli",
            "attemptedEngine": "cli",
            "finalEngine": "cli",
            "fallbackReason": None,
            "adapter": "codex",
            "mode": "generate",
            "proposalId": "proposal-safe",
            "sessionId": None,
            "assistantMessageId": None,
        },
    ),
}


ARTIFACT_CASES = {
    TaskType.BRIEFING: (
        {"artifactId": "2026-07-22", "reportId": "2026-07-22", "date": "2026-07-22", "title": "Briefing"},
        {"reportId": "2026-07-22", "date": "2026-07-22", "title": "Briefing"},
    ),
    TaskType.COMPANY_ANALYSIS: (
        {"artifactId": "TEST-2026-07-22", "reportId": "TEST-2026-07-22", "date": "2026-07-22", "title": "Test Co"},
        {"reportId": "TEST-2026-07-22", "date": "2026-07-22", "title": "Test Co"},
    ),
    TaskType.TOPIC_REPORT: (
        {"artifactId": "topic-22", "reportId": "topic-22", "date": "2026-07-22", "title": "Topic"},
        {"reportId": "topic-22", "date": "2026-07-22", "title": "Topic"},
    ),
    TaskType.PERSONAL_OVERLAY: (
        {"artifactId": "TEST-2026-07-22", "reportId": "TEST-2026-07-22"},
        {"reportId": "TEST-2026-07-22"},
    ),
    TaskType.THESIS_DELTA: ({"artifactId": "delta-22"}, {}),
    TaskType.MARKET_MEMORY_LLM: ({"artifactId": "memory-22"}, {}),
    TaskType.MARKET_STATE_SNAPSHOT: (
        {"artifactId": "snapshot-22", "snapshotId": "snapshot-22"},
        {"snapshotId": "snapshot-22"},
    ),
    TaskType.MARKET_MEMORY_UPDATE: (
        {"artifactId": "__JOB_ID__", "savedCount": 3, "snapshotId": "snapshot-combined"},
        {"savedCount": 3, "snapshotId": "snapshot-combined"},
    ),
    TaskType.QUALITY_REPAIR: (
        {"artifactId": "topic-22", "reportId": "topic-22"},
        {"reportId": "topic-22", "proposalId": "proposal-quality"},
    ),
    TaskType.INVESTMENT_REVIEW: (
        {"artifactId": "2026-07-22", "reportId": "2026-07-22"},
        {"reportId": "2026-07-22"},
    ),
}


def test_todo14_task_table_is_exhaustive() -> None:
    assert set(ARTIFACT_CASES) == set(ARTIFACT_TASKS)
    assert set(NON_ARTIFACT_CASES) | set(ARTIFACT_CASES) == set(TaskType)
    assert set(NON_ARTIFACT_CASES).isdisjoint(ARTIFACT_CASES)


@pytest.mark.parametrize("task_type", tuple(NON_ARTIFACT_CASES), ids=lambda item: item.value)
def test_todo14_nonartifact_terminal_projection_is_exact_after_reread(
    tmp_path: Path,
    task_type: TaskType,
) -> None:
    result, expected = NON_ARTIFACT_CASES[task_type]
    store, job = _running(tmp_path, task_type)
    misleading = {**result, "artifactId": PRIVATE_CANARY, "title": PRIVATE_CANARY}

    store.transition(job.id, JobStatus.DONE, result=misleading)
    durable = _store(tmp_path).get(job.id)

    assert durable is not None
    assert durable.status is JobStatus.DONE
    assert durable.artifactRefs == []
    assert durable.resultProjection is not None
    assert durable.resultProjection.model_dump(mode="json") == expected
    assert PRIVATE_CANARY not in (tmp_path / "jobs-v2.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("task_type", tuple(ARTIFACT_CASES), ids=lambda item: item.value)
def test_todo14_artifact_terminal_projection_and_refs_are_exact_after_reread(
    tmp_path: Path,
    task_type: TaskType,
) -> None:
    store, running = _running(tmp_path, task_type)
    result_template, task_fields = ARTIFACT_CASES[task_type]
    result = {
        key: (running.id if value == "__JOB_ID__" else value)
        for key, value in result_template.items()
    }
    artifact_id = str(result["artifactId"])
    ref_type = f"{task_type.value}_artifact"
    terminal = project_terminal_result(
        running,
        JobStatus.DONE,
        {**result, "reply": PRIVATE_CANARY, "path": PRIVATE_CANARY, "savedCount": result.get("savedCount", 999)},
    )
    intent = CommitIntent(
        operationId=f"todo14-{task_type.value}",
        expectedArtifacts=[
            ExpectedArtifact(
                type=ref_type,
                id=artifact_id,
                storage=StorageKind.JSON,
                baseHash=None,
                baseMarker=None,
                targetRevision=1,
                targetHash=SHA,
            )
        ],
        terminalProjection=terminal,
    )

    store.claim_committing(running.id, intent)
    committing = _store(tmp_path).get(running.id)
    assert committing is not None
    assert [ref.model_dump() for ref in committing.artifactRefs] == [{"type": ref_type, "id": artifact_id}]
    proof = _mint_artifact_completion_proof(committing, ArtifactCompletionSource.JSON)
    store.complete_artifact(running.id, proof)
    durable = _store(tmp_path).get(running.id)

    assert durable is not None
    assert durable.status is JobStatus.DONE
    assert [ref.model_dump() for ref in durable.artifactRefs] == [{"type": ref_type, "id": artifact_id}]
    expected_projection = {
        "status": "done",
        "artifactType": task_type.value,
        "artifactId": artifact_id,
        "reportId": None,
        "date": None,
        "title": None,
        "savedCount": None,
        "snapshotId": None,
        "proposalId": None,
        "requestedMode": "cli",
        "attemptedEngine": "cli",
        "finalEngine": "cli",
        "fallbackReason": None,
        "adapter": "codex",
        "mode": "generate",
        **task_fields,
    }
    assert durable.resultProjection is not None
    assert durable.resultProjection.model_dump(mode="json") == expected_projection
    raw = (tmp_path / "jobs-v2.json").read_text(encoding="utf-8")
    assert PRIVATE_CANARY not in raw


def test_todo14_cancel_restart_and_malformed_id_are_safe_and_durable(tmp_path: Path) -> None:
    cancel_store, queued = _running(tmp_path / "cancel", TaskType.COMPANION)
    cancel_store.transition(queued.id, JobStatus.CANCEL_REQUESTED)
    cancel_store.transition(queued.id, JobStatus.CANCELLED, result={"reply": PRIVATE_CANARY})
    cancelled = _store(tmp_path / "cancel").get(queued.id)
    assert cancelled is not None
    assert cancelled.resultProjection is not None
    assert cancelled.resultProjection.model_dump(mode="json") == {"status": "cancelled", "errorCode": None}

    restart_store, running = _running(tmp_path / "restart", TaskType.COMPANION)
    restart_store.transition_recovery(running.id, JobStatus.FAILED_RESTART)
    restarted = _store(tmp_path / "restart").get(running.id)
    assert restarted is not None
    assert restarted.resultProjection is not None
    assert restarted.resultProjection.model_dump(mode="json") == {
        "status": "failed",
        "errorCode": ErrorCode.RESTART_INTERRUPTED.value,
    }
    assert restarted.artifactRefs == []

    values = running.model_dump(mode="json")
    values["id"] = "job_../../escape"
    with pytest.raises(ValidationError, match="invalid job id"):
        SharedJob.model_validate(values)


def _canonical_seed(path: Path, scope: str, markdown: str, *, overlay: bool = False) -> dict:
    candidate = {
        "date": "2026-07-22",
        "generatedAt": "2026-07-22T03:04:05Z",
        "marketScope": scope,
        "generationScope": scope,
        "markdown": markdown,
        "briefings": {},
        "sources": [],
    }
    if overlay:
        candidate["personalOverlay"] = {"stale": False, "markdown": PRIVATE_CANARY}
    prepared = prepare(
        report_kind=ReportKind.BRIEFING,
        exact_path=path,
        write_kind=WriteKind.CANONICAL,
        candidate=candidate,
    )
    commit_sync(prepared)
    return json.loads(path.read_text(encoding="utf-8"))


def _scope_result(scope: str) -> dict:
    # Exercise canonical persistence with a candidate that satisfies the
    # shared production structure gate, rather than a now-invalid one-liner.
    label = "미국장" if scope == "us" else "한국장"
    title = "US Market Briefing" if scope == "us" else "Korea Market Briefing"
    companies = ("NVIDIA", "Alphabet") if scope == "us" else ("삼성전자", "SK하이닉스")
    markdown = "\n\n".join([
        f"# {title} — 2026.07.21 마감",
        f"## 0. 오늘의 {label} 성격",
        f"## 1. {label} 시장 흐름",
        f"## 2. {label}을 움직인 핵심 변수",
        f"## 3. {label}을 주도한 기업 ① — {companies[0]}",
        f"## 4. {label}을 주도한 기업 ② — {companies[1]}",
        "## 5. 일반 투자자 관점",
        f"## 6. 다음 {label} 체크포인트",
        "## 오늘의 결론",
        "## Source & Data Notes",
        "**한 줄 결론:** 합성 자료의 검토 결과\n" * 7,
        "· 합성 확인 항목\n" * 18,
        f"{scope} changed body\n" + "합성 자료 기반 분석 문장 " * 600,
    ])
    return {
        "markdown": markdown,
        "sessionMode": f"{scope}_close",
        "marketSessionDate": "2026-07-21",
        "sources": [],
        "generation": {"mode": "rules", "status": "ok", "provider": "fixture"},
        "status": "ok",
        "headlines": [],
        "groups": [],
        "issueCoverageRaw": [],
        "issueCoverage": [],
        "marketDrivers": [],
        "documents": [],
    }


def _patch_direct_briefing(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(builder, "BRIEFINGS_DIR", root)
    monkeypatch.setattr(builder, "build_index", lambda **_kwargs: {})
    monkeypatch.setattr(builder, "load_index", lambda: {"documents": []})
    monkeypatch.setattr(
        builder,
        "select_briefing_docs",
        lambda *_args, **_kwargs: ([], "2026-07-21", {"sourceDates": ["2026-07-21"]}),
    )
    monkeypatch.setattr(builder, "cached_market_snapshot", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(builder, "cached_korea_market_data", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(builder, "build_market_tape", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(builder, "preflight_from_context", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(builder, "list_briefing_memories", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(builder, "load_prev_briefing", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(builder, "_scope_result", lambda scope, *_args, **_kwargs: _scope_result(scope))
    monkeypatch.setattr(builder, "leading_company_subjects_from_markdown", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        builder,
        "collect_briefing_visuals",
        lambda *_args, **_kwargs: {"visualRecommendations": [], "visualSnapshots": [], "sidecar": {}, "warnings": []},
    )
    monkeypatch.setattr(builder, "session_doc_counts", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(builder, "checkpoints_from_markdown", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(builder, "data_gaps_from_messages", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(builder, "read_briefing_prompt", lambda *_args, **_kwargs: "fixture prompt")
    monkeypatch.setattr(builder, "apply_quality_loop", lambda _kind, payload, **_kwargs: payload)
    monkeypatch.setattr(builder, "build_memory_from_briefing", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(builder, "now_iso", lambda: "2026-07-22T03:04:05Z")


def test_todo14_direct_sync_briefing_uses_canonical_revision_noop_and_scoped_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "briefings"
    us_path = root / "2026-07-22.us.json"
    kr_path = root / "2026-07-22.kr.json"
    _canonical_seed(us_path, "us", "# US Market Briefing\n\nold", overlay=True)
    seeded_kr = _canonical_seed(kr_path, "kr", "# Korea Market Briefing\n\nsibling")
    sibling_bytes = kr_path.read_bytes()
    _patch_direct_briefing(monkeypatch, root)

    builder.build_briefing(
        "2026-07-22",
        strict_date=True,
        llm_override=False,
        persist=True,
        market_scope="us",
    )
    changed = json.loads(us_path.read_text(encoding="utf-8"))
    after_first_bytes = us_path.read_bytes()
    builder.build_briefing(
        "2026-07-22",
        strict_date=True,
        llm_override=False,
        persist=True,
        market_scope="us",
    )
    no_op = json.loads(us_path.read_text(encoding="utf-8"))

    assert changed["canonicalRevision"]["number"] == 2
    assert changed["canonicalRevision"]["hash"] == canonical_content_hash(changed)
    assert changed["personalOverlay"] == {
        "stale": True,
        "staleReason": "canonical_revision_changed",
        "markdown": PRIVATE_CANARY,
    }
    assert no_op["canonicalRevision"] == changed["canonicalRevision"]
    assert us_path.read_bytes() == after_first_bytes
    assert kr_path.read_bytes() == sibling_bytes
    assert json.loads(kr_path.read_text(encoding="utf-8")) == seeded_kr
