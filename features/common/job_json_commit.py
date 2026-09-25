from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from features.common.canonical_report_io import artifact_lock, atomic_write
from features.common.canonical_reports import promote_job
from features.common.job_json_codec import marker, read_logical, storage_hash
from features.common.job_json_schema import (
    CommitJournalStatus,
    FaultHook,
    JobArtifactConflictError,
    JobArtifactValidationError,
    JobCommitJournal,
    StagedArtifact,
    StagedJobBundle,
)
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_projection import utc_z
from features.common.shared_jobs_completion import (
    ArtifactCompletionProof,
    ArtifactCompletionSource,
    _mint_artifact_completion_proof,
)
from features.common.shared_jobs_schema import CommitIntent, JobMarker, JobStatus, StorageKind
from features.common.shared_jobs_store import JobCommitClaimError, SharedJobStore
from features.common.atomic_replace import replace_with_retry


def _call(hook: FaultHook | None, phase: str) -> None:
    if hook is not None:
        hook(phase)


class JobArtifactCommitter:
    def __init__(self, data_root: Path, *, clock: Callable[[], datetime]) -> None:
        self.data_root = data_root.resolve(strict=False)
        self.clock = clock

    def _journal_path(self, job_id: str) -> Path:
        return self.data_root / "job-commits" / f"{job_id}.json"

    def _write_journal(
        self,
        bundle: StagedJobBundle,
        status: CommitJournalStatus,
        created_at: str | None = None,
    ) -> JobCommitJournal:
        now = utc_z(self.clock())
        journal = JobCommitJournal(
            jobId=bundle.job.id,
            operationId=bundle.operation_id,
            taskType=bundle.job.taskType,
            expectedArtifacts=bundle.intent.expectedArtifacts,
            artifacts=[item.manifest for item in bundle.artifacts],
            status=status,
            createdAt=created_at or now,
            updatedAt=now,
        )
        path = self._journal_path(bundle.job.id)
        atomic_write(path, journal.model_dump_json(indent=2).encode("utf-8"))
        try:
            reread = JobCommitJournal.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as exc:
            raise JobArtifactValidationError("job commit journal reread failed") from exc
        if reread != journal:
            raise JobArtifactValidationError("job commit journal changed after write")
        return reread

    def _promote_json(self, artifact: StagedArtifact, intent: CommitIntent) -> None:
        expected = artifact.manifest.expected
        if expected.storage == StorageKind.SQLITE:
            raise JobArtifactValidationError("sqlite cannot enter JSON promotion")
        target_marker = JobMarker(
            jobId=artifact.staged_path.parent.name,
            operationId=intent.operationId,
        )
        with artifact_lock(artifact.exact_path):
            current = read_logical(artifact.exact_path, expected.storage)
            if current is not None and storage_hash(current) == expected.targetHash and marker(current) == target_marker:
                return
            current_hash = storage_hash(current) if current is not None else None
            if current_hash != expected.baseHash or marker(current) != expected.baseMarker:
                raise JobArtifactConflictError("artifact target changed after prepare")
            staged = read_logical(artifact.staged_path, expected.storage)
            if staged is None:
                raise JobArtifactConflictError("staged artifact is missing")
            if storage_hash(staged) != expected.targetHash or marker(staged) != target_marker:
                raise JobArtifactConflictError("staged artifact hash or marker is invalid")
            artifact.exact_path.parent.mkdir(parents=True, exist_ok=True)
            replace_with_retry(artifact.staged_path, artifact.exact_path)
            committed = read_logical(artifact.exact_path, expected.storage)
            if committed is None or storage_hash(committed) != expected.targetHash or marker(committed) != target_marker:
                raise JobArtifactConflictError("promoted artifact verification failed")

    def _promote(self, artifact: StagedArtifact, intent: CommitIntent) -> None:
        if artifact.canonical is not None:
            promote_job(
                artifact.canonical,
                artifact.staged_path,
                intent.model_dump(mode="json"),
            )
            return
        self._promote_json(artifact, intent)

    def _verify_target(self, artifact: StagedArtifact, operation_id: str, job_id: str) -> None:
        expected = artifact.manifest.expected
        committed = read_logical(artifact.exact_path, expected.storage)
        expected_marker = JobMarker(jobId=job_id, operationId=operation_id)
        if (
            committed is None
            or storage_hash(committed) != expected.targetHash
            or marker(committed) != expected_marker
        ):
            raise JobArtifactConflictError("committed artifact does not match intent")
        revision = committed.get("canonicalRevision")
        if expected.targetRevision is not None and (
            not isinstance(revision, dict)
            or revision.get("number") != expected.targetRevision
        ):
            raise JobArtifactConflictError(
                "committed canonical revision does not match intent"
            )

    def _completion_proof(
        self,
        bundle: StagedJobBundle,
        store: SharedJobStore,
        journal: JobCommitJournal,
    ) -> ArtifactCompletionProof:
        path = self._journal_path(bundle.job.id)
        try:
            reread = JobCommitJournal.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as error:
            raise JobArtifactValidationError("completion journal reread failed") from error
        current = store.get(bundle.job.id)
        if (
            reread != journal
            or journal.status is not CommitJournalStatus.ARTIFACTS_WRITTEN
            or current is None
            or current.status is not JobStatus.COMMITTING
            or current.commitIntent != bundle.intent
            or journal.jobId != current.id
            or journal.operationId != bundle.intent.operationId
            or journal.taskType != current.taskType
            or journal.expectedArtifacts != bundle.intent.expectedArtifacts
            or journal.artifacts != bundle.manifest.artifacts
        ):
            raise JobArtifactValidationError("completion journal disagrees with intent")
        for artifact in bundle.artifacts:
            self._verify_target(artifact, bundle.operation_id, bundle.job.id)
        return _mint_artifact_completion_proof(
            current,
            ArtifactCompletionSource.JSON,
        )

    def _cleanup_stage(self, job_id: str) -> None:
        stage_root = self.data_root / "job-staging" / job_id
        if stage_root.exists():
            try:
                shutil.rmtree(stage_root)
            except OSError as exc:
                raise JobArtifactValidationError("job staging cleanup failed") from exc

    def _commit_proven(
        self,
        bundle: StagedJobBundle,
        store: SharedJobStore,
        *,
        fault_hook: FaultHook | None,
    ) -> ArtifactCompletionProof:
        try:
            store.claim_committing(bundle.job.id, bundle.intent)
        except JobCommitClaimError:
            self._cleanup_stage(bundle.job.id)
            raise
        _call(fault_hook, "intent_claimed")
        journal = self._write_journal(bundle, CommitJournalStatus.PREPARED)
        _call(fault_hook, "journal_prepared")
        for artifact in bundle.artifacts:
            self._promote(artifact, bundle.intent)
            expected = artifact.manifest.expected
            _call(fault_hook, f"promoted:{expected.type}:{expected.id}")
        completed_journal = self._write_journal(
            bundle,
            CommitJournalStatus.ARTIFACTS_WRITTEN,
            journal.createdAt,
        )
        _call(fault_hook, "artifacts_written")
        self._cleanup_stage(bundle.job.id)
        _call(fault_hook, "staging_cleaned")
        return self._completion_proof(bundle, store, completed_journal)

    def commit(
        self,
        bundle: StagedJobBundle,
        store: SharedJobStore,
        lifecycle: JobPrivateLifecycle,
        *,
        fault_hook: FaultHook | None = None,
    ) -> None:
        # Deliberately before claim/journal: a stale staged candidate must not
        # become recoverable intent, and must not mutate its authoritative
        # target.  JSON promotion still owns base-hash/CAS validation below.
        try:
            for artifact in bundle.artifacts:
                if artifact.pre_promotion_validator is not None:
                    artifact.pre_promotion_validator()
        except JobArtifactConflictError:
            self._cleanup_stage(bundle.job.id)
            raise
        # The common JSON lifecycle is the authoritative commit boundary for
        # every staged report.  It owns the diagnostic stage so it can close
        # it after proof verification but before `complete_artifact` invokes
        # the private terminal observer.
        from features.common.jobs import diagnostic_stage_end, diagnostic_stage_failure, diagnostic_stage_start

        diagnostic_recorder, diagnostic_stage = diagnostic_stage_start("commit")
        try:
            proof = self._commit_proven(bundle, store, fault_hook=fault_hook)
        except Exception as error:
            diagnostic_stage_failure(
                diagnostic_recorder,
                error,
                stage_id=diagnostic_stage,
                stage_code="commit" if diagnostic_stage is not None else None,
                boundary="save",
            )
            # The authoritative job remains COMMITTING for recovery.  Preserve
            # this real crash/interruption gap as an open stage; closing it
            # would falsely claim the durable boundary completed.
            raise
        diagnostic_stage_end(diagnostic_recorder, diagnostic_stage, "commit")
        lifecycle.complete_artifact(store, bundle.job.id, proof)
        _call(fault_hook, "job_terminal")
        self._journal_path(bundle.job.id).unlink(missing_ok=True)
