from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from features.common.canonical_report_state import (
    canonical_content_hash,
    load_report,
    marker,
    revision,
    storage_hash,
)
from features.common.canonical_report_types import CanonicalConflictError, CanonicalValidationError, PreparedCanonicalWrite
from features.common.job_json_commit import JobArtifactCommitter
from features.common.job_json_cleanup import cleanup_json_recovery_residue, read_commit_journal
from features.common.job_json_schema import (
    CommitJournalStatus,
    JobArtifactConflictError,
    JobArtifactValidationError,
    JobCommitJournal,
    JobStageManifest,
    ManifestArtifact,
    StagedArtifact,
    StagedJobBundle,
)
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_schema import ErrorCode, JobMarker, JobStatus, TaskType
from features.common.shared_jobs_store import SharedJobStore


JSON_TASKS: Final = frozenset(
    {
        TaskType.BRIEFING,
        TaskType.COMPANY_ANALYSIS,
        TaskType.TOPIC_REPORT,
        TaskType.PERSONAL_OVERLAY,
        TaskType.QUALITY_REPAIR,
        TaskType.INVESTMENT_REVIEW,
    }
)


def _read_manifest(stage_root: Path) -> JobStageManifest | None:
    path = stage_root / "manifest.json"
    if not path.exists():
        return None
    try:
        return JobStageManifest.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise JobArtifactValidationError("job staging manifest is invalid") from exc


def _manifest_for_recovery(
    job_id: str,
    stage_root: Path,
    journal: JobCommitJournal | None,
) -> JobStageManifest:
    manifest = _read_manifest(stage_root)
    if manifest is not None:
        if journal is not None and journal.artifacts != manifest.artifacts:
            raise JobArtifactValidationError("job commit journal disagrees with staging manifest")
        return manifest
    if journal is None:
        raise JobArtifactValidationError("job recovery metadata is unavailable")
    return JobStageManifest(
        jobId=job_id,
        operationId=journal.operationId,
        taskType=journal.taskType,
        artifacts=journal.artifacts,
    )


def _canonical_recovery_bytes(
    item: ManifestArtifact,
    exact_path: Path,
    staged_path: Path,
    job_id: str,
    operation_id: str,
) -> bytes:
    if staged_path.exists():
        return staged_path.read_bytes()
    current = load_report(exact_path)
    current_revision = revision(current) if current is not None else None
    expected_marker = {"jobId": job_id, "operationId": operation_id}
    if (
        current is None
        or storage_hash(current) != item.expected.targetHash
        or marker(current) != expected_marker
        or current_revision is None
        or current_revision[0] != item.expected.targetRevision
        or canonical_content_hash(current) != item.canonicalContentHash
    ):
        raise JobArtifactConflictError("promoted canonical target does not match recovery intent")
    return exact_path.read_bytes()


def _load_recovery_bundle(data_root: Path, job_id: str, store: SharedJobStore) -> tuple[StagedJobBundle, JobCommitJournal | None]:
    current = store.get(job_id)
    if current is None or current.status != JobStatus.COMMITTING or current.commitIntent is None:
        raise JobArtifactValidationError("job is not recoverable JSON committing state")
    if current.taskType not in JSON_TASKS:
        raise JobArtifactValidationError("job task is not a JSON producer")
    stage_root = data_root / "job-staging" / job_id
    journal = read_commit_journal(data_root / "job-commits" / f"{job_id}.json")
    manifest = _manifest_for_recovery(job_id, stage_root, journal)
    if (
        manifest.jobId != job_id
        or manifest.operationId != current.commitIntent.operationId
        or manifest.taskType != current.taskType
        or [item.expected for item in manifest.artifacts] != current.commitIntent.expectedArtifacts
    ):
        raise JobArtifactValidationError("job recovery metadata disagrees with CommitIntent")
    if journal is not None and (
        journal.jobId != job_id
        or journal.operationId != manifest.operationId
        or journal.taskType != manifest.taskType
        or journal.expectedArtifacts != current.commitIntent.expectedArtifacts
    ):
        raise JobArtifactValidationError("job commit journal disagrees with CommitIntent")
    artifacts: list[StagedArtifact] = []
    root = data_root.resolve(strict=False)
    for item in manifest.artifacts:
        exact_path = (root / Path(item.targetRelativePath)).resolve(strict=False)
        try:
            exact_path.relative_to(root)
        except ValueError as exc:
            raise JobArtifactValidationError("recovery target escapes data root") from exc
        staged_path = stage_root / item.stageFile
        canonical: PreparedCanonicalWrite | None = None
        if item.reportKind is not None:
            expected = item.expected
            if item.canonicalContentHash is None or item.canonicalChanged is None or expected.targetRevision is None:
                raise JobArtifactValidationError("canonical manifest is incomplete")
            target_marker = JobMarker(jobId=staged_path.parent.name, operationId=manifest.operationId)
            canonical = PreparedCanonicalWrite(
                report_kind=item.reportKind,
                exact_path=exact_path,
                base_hash=expected.baseHash,
                base_marker=expected.baseMarker.model_dump(mode="json") if expected.baseMarker is not None else None,
                target_hash=expected.targetHash,
                target_revision=expected.targetRevision,
                canonical_content_hash=item.canonicalContentHash,
                canonical_changed=item.canonicalChanged,
                serialized_bytes=_canonical_recovery_bytes(
                    item,
                    exact_path,
                    staged_path,
                    job_id,
                    manifest.operationId,
                ),
                operation_id=manifest.operationId,
                target_marker=target_marker.model_dump(mode="json"),
            )
        artifacts.append(StagedArtifact(item, exact_path, staged_path, canonical))
    projection = current.commitIntent.terminalProjection.model_dump(mode="json")
    projection.pop("status", None)
    bundle = StagedJobBundle(current, manifest.operationId, manifest, current.commitIntent, projection, tuple(artifacts))
    return bundle, journal


def _terminalize_recovery_failure(
    store: SharedJobStore,
    lifecycle: JobPrivateLifecycle,
    job_id: str,
) -> None:
    lifecycle.terminalize_recovery(
        store,
        job_id,
        JobStatus.FAILED_COMMIT_RECOVERY,
    )


def _validate_investment_review_recovery_authority(data_root: Path, bundle: StagedJobBundle, journal: JobCommitJournal | None) -> None:
    """Do not promote a staged review if its external personal inputs moved.

    Callbacks are intentionally process-local, so recovery reconstructs this
    narrow check from the staged candidate.  It is intentionally not a new
    manifest protocol: immutable journal redesign belongs to a later stage.
    """
    from features.common.job_json_codec import read_logical
    from features.investment_review.review_v2 import build_input_basis, gather_inputs

    # Once every artifact is durably promoted, recovery verifies and completes
    # that immutable intent; a later authority change cannot retroactively
    # invalidate an already-written target.
    if journal is not None and journal.status is CommitJournalStatus.ARTIFACTS_WRITTEN:
        return
    for artifact in bundle.artifacts:
        if artifact.manifest.expected.type != "investment_review":
            continue
        if not artifact.staged_path.exists():
            # Promotion already consumed this staged payload; target/hash
            # verification below owns recovery from this point onward.
            continue
        staged = read_logical(artifact.staged_path, artifact.manifest.expected.storage)
        basis = staged.get("inputBasis") if isinstance(staged, dict) else None
        expected = basis.get("fingerprint") if isinstance(basis, dict) else ""
        analytics_authority = basis.get("analytics") if isinstance(basis, dict) else None
        # Staged U.5 reviews pin their report-selection policy in the saved
        # basis. Versionless v2 stages must retain the original legacy
        # fingerprint shape during recovery rather than being reselected.
        selection_version = basis.get("reportSelectionVersion") if isinstance(basis, dict) else ""
        actual = build_input_basis(gather_inputs(
            data_root, analytics_authority=analytics_authority,
            report_selection_version=str(selection_version or ""),
        )).get("fingerprint")
        # Generic historic test/producer artifacts labelled investment_review
        # may predate v2 inputBasis.  Only a real v2 staged candidate gets the
        # external-authority guard; otherwise recovery retains its lifecycle.
        if not isinstance(expected, str) or not expected:
            continue
        if expected != actual:
            raise JobArtifactConflictError("investment_review_external_input_changed_reopen_generation")


def recover_json_job(
    data_root: Path,
    job_id: str,
    store: SharedJobStore,
    lifecycle: JobPrivateLifecycle,
    *,
    clock: Callable[[], datetime],
) -> bool:
    committer = JobArtifactCommitter(data_root, clock=clock)
    try:
        bundle, existing_journal = _load_recovery_bundle(data_root, job_id, store)
        _validate_investment_review_recovery_authority(data_root, bundle, existing_journal)
        journal = existing_journal or committer._write_journal(bundle, CommitJournalStatus.PREPARED)
        for artifact in bundle.artifacts:
            committer._promote(artifact, bundle.intent)
            committer._verify_target(artifact, bundle.operation_id, bundle.job.id)
        completed_journal = committer._write_journal(
            bundle,
            CommitJournalStatus.ARTIFACTS_WRITTEN,
            journal.createdAt,
        )
        committer._cleanup_stage(job_id)
        proof = committer._completion_proof(bundle, store, completed_journal)
        lifecycle.complete_artifact(store, job_id, proof)
        committer._journal_path(job_id).unlink(missing_ok=True)
        return True
    except (
        CanonicalConflictError,
        CanonicalValidationError,
        JobArtifactConflictError,
        JobArtifactValidationError,
        ValidationError,
        OSError,
    ):
        committer._cleanup_stage(job_id)
        _terminalize_recovery_failure(store, lifecycle, job_id)
        committer._journal_path(job_id).unlink(missing_ok=True)
        return False


def recover_json_jobs_startup(
    data_root: Path,
    store: SharedJobStore,
    lifecycle: JobPrivateLifecycle,
    *,
    clock: Callable[[], datetime],
) -> None:
    for job in store.load().jobs:
        if job.taskType in JSON_TASKS and job.status == JobStatus.COMMITTING:
            recover_json_job(data_root, job.id, store, lifecycle, clock=clock)
    state = store.load()
    committer = JobArtifactCommitter(data_root, clock=clock)
    repair_owners = cleanup_json_recovery_residue(
        data_root,
        state.jobs,
        committer,
        clock=clock,
    )
    lifecycle.set_repair_required(bool(repair_owners))
