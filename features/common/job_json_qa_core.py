from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from features.common.canonical_json import JsonValue
from features.common.job_json_artifacts import (
    CommitInterruptedError,
    JobArtifactConflictError,
    JsonArtifactSpec,
    recover_json_job,
    recover_json_jobs_startup,
)
from features.common.job_json_producers import (
    BriefingJobRequest,
    InvestmentReviewJobRequest,
    JobJsonProducers,
)
from features.common.job_json_schema import JobArtifactValidationError
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import JobStatus, SharedJob, StorageKind
from features.common.shared_jobs_store import SharedJobStore
from features.agent_mode.briefing_contract import briefing_output_contract


NOW = datetime(2026, 7, 18, 2, 0, tzinfo=UTC)
type JsonObject = dict[str, JsonValue]


def clock() -> datetime:
    return NOW


@dataclass(frozen=True, slots=True)
class Harness:
    root: Path
    store: SharedJobStore
    lifecycle: JobPrivateLifecycle
    producers: JobJsonProducers


def harness(root: Path) -> Harness:
    store = SharedJobStore(root / "jobs-v2.json", root / "jobs.json", clock=clock)
    lifecycle = JobPrivateLifecycle(root / "job-context", clock=clock)
    producers = JobJsonProducers(
        root,
        clock=clock,
        review_builder=lambda body: {
            "date": body.get("date") if isinstance(body.get("date"), str) else "2026-07-18",
            "summary": "review",
            "markdown": "# Review",
        },
    )
    return Harness(root, store, lifecycle, producers)


def running(owner: Harness, task_type: str) -> SharedJob:
    job = new_shared_job(
        kind="agent_bridge",
        task_type=task_type,
        generation_mode="llm_cli",
        adapter="codex",
        requested_mode="cli",
        mode="generate",
        attempted_engine="cli",
        clock=clock,
    )
    owner.store.add(job)
    owner.store.transition(job.id, JobStatus.RUNNING)
    current = owner.store.get(job.id)
    if current is None:
        raise JobArtifactValidationError("running job was not persisted")
    return current


def read_json(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise JobArtifactValidationError("QA target is not a JSON object")
    return value


def _valid_briefing_markdown(scope: str) -> str:
    contract = briefing_output_contract(scope, markets=[scope])
    names = ("NVIDIA", "Alphabet") if scope == "us" else ("Samsung Electronics", "SK hynix")
    headings = []
    for section in contract["requiredSections"]:
        if section == "US Market Briefing":
            headings.append("# US Market Briefing — 2026.07.18")
        elif section == "Korea Market Briefing":
            headings.append("# Korea Market Briefing — 2026.07.18")
        elif "주도한 기업 ①" in section:
            headings.append(f"## {section} — {names[0]}")
        elif "주도한 기업 ②" in section:
            headings.append(f"## {section} — {names[1]}")
        else:
            headings.append(f"## {section}")
    return "\n\n".join(headings + [
        "**한 줄 결론:** 확인\n" * 7,
        "· 확인 항목\n" * 18,
        "근거 있는 분석 문장 " * 1000,
    ])


def restart_boundaries(runtime: Path) -> bool:
    phases = (
        "intent_claimed",
        "journal_prepared",
        "promoted:investment_review:2026-07-18",
        "artifacts_written",
        "staging_cleaned",
        "job_terminal",
    )
    for index, phase in enumerate(phases):
        owner = harness(runtime / f"restart-{index}")
        job = running(owner, "investment_review")
        target = owner.root / "investment-review" / "2026-07-18.json"
        bundle = owner.producers.stage_investment_review(
            job,
            InvestmentReviewJobRequest(
                body={"date": "2026-07-18"},
                terminal_result={"artifactId": "2026-07-18", "reportId": "2026-07-18", "date": "2026-07-18"},
            ),
        )

        def interrupt(observed: str) -> None:
            if observed == phase:
                raise CommitInterruptedError(phase)

        interrupted = False
        try:
            owner.producers.workspace.commit(bundle, owner.store, owner.lifecycle, fault_hook=interrupt)
        except CommitInterruptedError:
            interrupted = True
        if not interrupted:
            return False
        recover_json_jobs_startup(
            owner.root,
            owner.store,
            JobPrivateLifecycle(owner.root / "job-context", clock=clock),
            clock=clock,
        )
        saved = read_json(target)
        current = owner.store.get(job.id)
        commit = saved.get("jobCommit")
        if (
            not isinstance(commit, dict)
            or commit.get("operationId") != bundle.operation_id
            or current is None
            or current.status != JobStatus.DONE
        ):
            return False
    return True


def briefing_matrix(runtime: Path) -> tuple[bool, bool, bool]:
    owner = harness(runtime / "briefing")
    job = running(owner, "briefing")
    bundle = owner.producers.stage_briefing(
        job,
        BriefingJobRequest(
            date="2026-07-18",
            scopes=("kr", "us"),
            reports={"us": {"markdown": _valid_briefing_markdown("us")}, "kr": {"markdown": _valid_briefing_markdown("kr")}},
            visuals={"us": {"snapshots": {"SPY": {"rows": [1, 2]}}}},
            terminal_result={
                "artifactId": "2026-07-18",
                "reportId": "2026-07-18",
                "date": "2026-07-18",
                "title": "Daily Briefing",
            },
        ),
    )
    ordered = [(item.storage.value, item.type, item.id) for item in bundle.intent.expectedArtifacts]
    promotions = 0

    def interrupt(observed: str) -> None:
        nonlocal promotions
        if observed.startswith("promoted:"):
            promotions += 1
        if promotions == 1:
            raise CommitInterruptedError(observed)

    interrupted = False
    try:
        owner.producers.workspace.commit(bundle, owner.store, owner.lifecycle, fault_hook=interrupt)
    except CommitInterruptedError:
        interrupted = True
    recovered = interrupted and recover_json_job(owner.root, job.id, owner.store, owner.lifecycle, clock=clock)
    reports = [read_json(owner.root / "briefings" / f"2026-07-18.{scope}.json") for scope in ("us", "kr")]
    with gzip.open(owner.root / "briefings" / "2026-07-18.us.visuals.json.gz", "rt", encoding="utf-8") as stream:
        visual = json.load(stream)
    matrix = recovered and all((report.get("jobCommit") or {}).get("jobId") == job.id for report in reports)
    # 브리핑이 만드는 저장물은 시장별 보고서와 gzip visuals 사이드카뿐이다
    # (`job_briefing_producer.briefing_specs()`). `.link.json`은 존재하지 않는다.
    reread = (visual.get("jobCommit") or {}).get("jobId") == job.id
    return matrix, ordered == sorted(ordered), reread


def invalid_and_stale(runtime: Path) -> tuple[bool, bool]:
    owner = harness(runtime / "boundaries")
    invalid_job = running(owner, "investment_review")
    invalid_target = owner.root / "investment-review" / "invalid.json"
    invalid = False
    try:
        owner.producers.workspace.stage(
            invalid_job,
            [JsonArtifactSpec(StorageKind.GZIP_JSON, "investment_review", "invalid", invalid_target, {"date": "invalid"})],
            terminal_result={"artifactId": "invalid"},
        )
    except (JobArtifactValidationError, ValueError):
        invalid = not (owner.root / "job-staging" / invalid_job.id).exists() and not invalid_target.exists()
    stale_job = running(owner, "investment_review")
    target = owner.root / "investment-review" / "2026-07-18.json"
    bundle = owner.producers.stage_investment_review(
        stale_job,
        InvestmentReviewJobRequest(
            body={"date": "2026-07-18"},
            terminal_result={"artifactId": "2026-07-18", "reportId": "2026-07-18"},
        ),
    )
    conflicting = {"date": "2026-07-18", "summary": "other", "jobCommit": {"jobId": "other", "operationId": "other"}}

    def replace_target(observed: str) -> None:
        if observed == "journal_prepared":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(conflicting), encoding="utf-8")

    conflicted = False
    try:
        owner.producers.workspace.commit(bundle, owner.store, owner.lifecycle, fault_hook=replace_target)
    except JobArtifactConflictError:
        conflicted = True
    before = target.read_bytes()
    recovered = recover_json_job(owner.root, stale_job.id, owner.store, owner.lifecycle, clock=clock)
    return invalid, conflicted and not recovered and target.read_bytes() == before


def has_runtime_residue(runtime: Path) -> bool:
    for root_name in ("job-staging", "job-commits", "job-context"):
        for path in runtime.rglob(root_name):
            if path.is_dir() and any(path.iterdir()):
                return True
    return False
