from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from features.agent_mode import job_runtime
from features.common import jobs
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import JobStatus, TaskType
from features.market_memory.attempt_store import AttemptStatus, AttemptStore
from features.market_memory.tests.sql_receipt_test_support import entry, snapshot_payload


def _running(monkeypatch: pytest.MonkeyPatch, root: Path, task_type: TaskType):
    monkeypatch.setattr(jobs, "JOBS_PATH", root / "jobs.json")
    jobs._LIFECYCLES.clear()
    job = new_shared_job(
        kind="agent_bridge",
        task_type=task_type,
        generation_mode="llm_cli",
        adapter="codex",
        requested_mode="cli",
        mode="generate",
        attempted_engine="cli",
        clock=jobs._clock,
    )
    jobs.shared_store().add(job)
    jobs.shared_store().transition(job.id, JobStatus.RUNNING)
    jobs.private_lifecycle().set_private(job.id, {"canary": f"PRIVATE_{task_type.value}"})
    jobs.write_job_pack(job.id, "pack", {"private": "PACK_CANARY"})
    return job


def _receipt_count(root: Path) -> int:
    with sqlite3.connect(root / "market-memory.sqlite3") as connection:
        return int(connection.execute("SELECT COUNT(*) FROM job_operation_receipts").fetchone()[0])


def test_live_sql_runtime_commits_each_registered_sql_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_root = tmp_path / "memory"
    memory = _running(monkeypatch, memory_root, TaskType.MARKET_MEMORY_LLM)
    memory_result = job_runtime.commit_market_memory_output(
        memory.id,
        {"artifactId": "2026-07-19", "internal": {"date": "2026-07-19", "usedDocs": []}},
        {"entries": [entry()]},
    )
    assert memory_result["savedCount"] == 1
    assert jobs.shared_store().get(memory.id).status is JobStatus.DONE
    assert _receipt_count(memory_root) == 1
    assert not (memory_root / "job-context" / memory.id).exists()

    snapshot_root = tmp_path / "snapshot"
    snapshot = _running(monkeypatch, snapshot_root, TaskType.MARKET_STATE_SNAPSHOT)
    snapshot_result = job_runtime.commit_market_state_output(
        snapshot.id,
        {
            "artifactId": "2026-07-19",
            "title": "Market State",
            "context": json.dumps({"inputWatermarks": {"GLOBAL": "2026-07-19T00:00:00Z"}}),
            "internal": {"sourceRefs": []},
        },
        snapshot_payload(),
    )
    assert snapshot_result["snapshotId"] == "snapshot-1"
    assert jobs.shared_store().get(snapshot.id).status is JobStatus.DONE
    assert _receipt_count(snapshot_root) == 1
    assert AttemptStore(snapshot_root / "market-state-update-attempts.json").load().attempts[0].status is AttemptStatus.SUCCESS

    thesis_root = tmp_path / "thesis"
    thesis = _running(monkeypatch, thesis_root, TaskType.THESIS_DELTA)
    thesis_result = job_runtime.commit_thesis_output(
        thesis.id,
        {
            "internal": {
                "thesis": {"ticker": "NVDA", "company": "NVIDIA", "coreThesis": "AI demand"},
                "meta": {"period": "90d", "periodDays": 90},
                "evidence": [],
            }
        },
        {
            "verdict": "maintained",
            "summary": "The bounded thesis remains unchanged.",
            "supportingEvidence": [],
            "counterEvidence": [],
            "contradictions": [],
            "uncertainties": [],
            "nextCheckpoints": [],
            "markdown": "# Thesis Delta",
        },
    )
    assert thesis_result["artifactId"]
    assert jobs.shared_store().get(thesis.id).status is JobStatus.DONE
    assert _receipt_count(thesis_root) == 1

    combined_root = tmp_path / "combined"
    combined = _running(monkeypatch, combined_root, TaskType.MARKET_MEMORY_UPDATE)

    def projected_snapshot(projected: sqlite3.Connection):
        candidate = snapshot_payload()
        count = int(projected.execute("SELECT COUNT(*) FROM market_memory").fetchone()[0])
        candidate["id"] = "combined-snapshot"
        candidate["headline"] = f"projected:{count}"
        return candidate

    combined_result = job_runtime.commit_combined_market_output(
        combined.id,
        (entry(),),
        projected_snapshot,
    )
    assert combined_result["savedCount"] == 1
    assert combined_result["snapshotId"] == "combined-snapshot"
    assert jobs.shared_store().get(combined.id).status is JobStatus.DONE
    assert _receipt_count(combined_root) == 2
    with sqlite3.connect(combined_root / "market-memory.sqlite3") as connection:
        payload = json.loads(connection.execute("SELECT payload_json FROM market_state_snapshots").fetchone()[0])
    assert payload["headline"] == "projected:1"
    assert AttemptStore(combined_root / "market-state-update-attempts.json").load().attempts[0].status is AttemptStatus.SUCCESS


def test_briefing_identity_covers_every_market_and_legacy_files():
    """접미사를 `.us`/`.kr`로만 알던 자리.

    이 함수는 CLI 실행이 **다 끝난 뒤** 커밋 단계에서 불린다. 여기서 던지면 수십 초~몇
    분의 Agent 실행이 통째로 버려진다. `canonical_identity`는 네 시장과 접미사 없는 옛
    브리핑을 모두 해결할 수 있는데 그 앞의 판정만 막고 있었다.
    """
    from features.common.canonical_identity import BRIEFING_MARKETS, ReportKind

    for market in BRIEFING_MARKETS:
        report_id = f"2026-08-14.{market}"
        path = str(Path("D:/data/briefings") / f"{report_id}.json")
        assert job_runtime._identity(ReportKind.BRIEFING, report_id, path) == ("2026-08-14", market, "")

    # 접미사 없는 옛 브리핑도 저장 대상이다. 하류 `_briefing_identity`가 scope=None을 받는다.
    assert job_runtime._identity(
        ReportKind.BRIEFING, "2026-06-18", "/data/briefings/2026-06-18.json",
    ) == ("2026-06-18", None, "")


def test_quality_repair_save_target_prefix_is_stripped():
    """`saveTarget`은 `briefing:{id}` 형태다.

    접두가 남으면 `briefing:2026-08-14`가 report id가 되어 경로 해석이 거부한다.
    """
    from features.common.canonical_identity import ReportKind

    assert job_runtime._identity(
        ReportKind.BRIEFING, "2026-08-14.jp", "briefing:2026-08-14.jp",
    ) == ("2026-08-14", "jp", "")
    assert job_runtime._identity(
        ReportKind.BRIEFING, "briefing:2026-08-14", "briefing:2026-08-14",
    ) == ("2026-08-14", None, "")


def test_non_briefing_identities_are_untouched():
    from features.common.canonical_identity import ReportKind

    assert job_runtime._identity(
        ReportKind.COMPANY_ANALYSIS, "NVDA_2026-08-14", "/data/company-analysis/NVDA_2026-08-14.json",
    ) == ("NVDA_2026-08-14", None, "")


def test_the_weekly_kind_survives_the_identity_split():
    """종류를 벗기되 **버리지 않는다.**

    시장을 찾으려면 접미사를 먼저 떼야 하는데, 떼고 잊으면 주간 대상이 일간 id가 되어
    하류 `resolve_exact_report_path`가 그날 **일간 파일**을 연다 — 주간 품질 개선이
    CLI를 다 돌린 뒤 커밋에서 정체성 검증에 걸리거나 일간 보고서를 덮어쓴다.
    """
    from features.common.canonical_identity import ReportKind

    assert job_runtime._identity(
        ReportKind.BRIEFING, "2026-08-23.us.weekly", "/data/briefings/2026-08-23.us.weekly.json",
    ) == ("2026-08-23", "us", "weekly")

    # report id에는 종류를, artifact id에는 저장 파일과 같은 순서를 싣는다.
    assert job_runtime._briefing_target("2026-08-23", "us", "weekly") == ("2026-08-23.weekly", "2026-08-23.us.weekly")
    assert job_runtime._briefing_target("2026-08-23", "us", "") == ("2026-08-23", "2026-08-23.us")


def test_the_weekly_report_id_resolves_to_the_weekly_file(tmp_path):
    """정체성 분해 결과가 실제로 주간 파일을 연다."""
    from features.common.canonical_identity import ReportKind, resolve_exact_report_path

    briefings = tmp_path / "briefings"
    briefings.mkdir()
    (briefings / "2026-08-23.us.json").write_text("{}", encoding="utf-8")
    (briefings / "2026-08-23.us.weekly.json").write_text("{}", encoding="utf-8")

    report_id, _ = job_runtime._briefing_target("2026-08-23", "us", "weekly")

    assert resolve_exact_report_path(tmp_path, ReportKind.BRIEFING, report_id, "us").name == "2026-08-23.us.weekly.json"
