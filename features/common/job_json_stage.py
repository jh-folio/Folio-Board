from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, assert_never

from features.common.canonical_report_io import artifact_lock, atomic_write
from features.common.canonical_reports import prepare
from features.common.job_json_codec import copy_json, marker, read_logical, serialize_logical, storage_hash
from features.common.job_json_schema import (
    ArtifactSpec,
    CanonicalArtifactSpec,
    JobArtifactValidationError,
    JobStageManifest,
    JsonArtifactSpec,
    ManifestArtifact,
    StagedArtifact,
    StagedJobBundle,
)
from features.common.shared_jobs_projection import project_terminal_result
from features.common.shared_jobs_schema import (
    CommitIntent,
    ExpectedArtifact,
    JobMarker,
    JobStatus,
    SharedJob,
    StorageKind,
    TaskType,
)


PRIVATE_TARGET_ROOTS: Final = frozenset({"job-staging", "job-context", "job-commits"})
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


class JobArtifactStager:
    def __init__(self, data_root: Path, *, clock: Callable[[], datetime]) -> None:
        self.data_root = data_root.resolve(strict=False)
        self.clock = clock

    def _relative_target(self, exact_path: Path) -> str:
        resolved = exact_path.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.data_root)
        except ValueError as exc:
            raise JobArtifactValidationError("artifact target escapes data root") from exc
        if not relative.parts or relative.parts[0] in PRIVATE_TARGET_ROOTS:
            raise JobArtifactValidationError("artifact target uses a private job root")
        return relative.as_posix()

    def _stage_canonical(
        self,
        spec: CanonicalArtifactSpec,
        stage_path: Path,
        job: SharedJob,
        operation_id: str,
    ) -> StagedArtifact:
        relative_target = self._relative_target(spec.exact_path)
        prepared = prepare(
            report_kind=spec.report_kind,
            exact_path=spec.exact_path,
            write_kind=spec.write_kind,
            candidate=spec.candidate,
            operation_id=operation_id,
            job_marker={"jobId": job.id, "operationId": operation_id},
        )
        atomic_write(stage_path, prepared.serialized_bytes)
        if stage_path.read_bytes() != prepared.serialized_bytes:
            raise JobArtifactValidationError("staged canonical bytes changed after write")
        expected = ExpectedArtifact(
            storage=StorageKind.JSON,
            type=spec.artifact_type,
            id=spec.artifact_id,
            baseHash=prepared.base_hash,
            baseMarker=prepared.base_marker,
            targetRevision=prepared.target_revision,
            targetHash=prepared.target_hash,
        )
        manifest = ManifestArtifact(
            expected=expected,
            targetRelativePath=relative_target,
            stageFile=stage_path.name,
            reportKind=spec.report_kind,
            canonicalContentHash=prepared.canonical_content_hash,
            canonicalChanged=prepared.canonical_changed,
        )
        return StagedArtifact(manifest, spec.exact_path, stage_path, prepared)

    def _stage_json(
        self,
        spec: JsonArtifactSpec,
        stage_path: Path,
        job: SharedJob,
        operation_id: str,
    ) -> StagedArtifact:
        if spec.storage == StorageKind.SQLITE:
            raise JobArtifactValidationError("sqlite cannot enter JSON staging")
        relative_target = self._relative_target(spec.exact_path)
        with artifact_lock(spec.exact_path):
            current = read_logical(spec.exact_path, spec.storage)
            payload = copy_json(spec.payload)
            if spec.payload_validator is not None:
                payload = spec.payload_validator(payload, current)
            target = copy_json(payload)
            target["jobCommit"] = {"jobId": job.id, "operationId": operation_id}
            expected = ExpectedArtifact(
                storage=spec.storage,
                type=spec.artifact_type,
                id=spec.artifact_id,
                baseHash=storage_hash(current) if current is not None else None,
                baseMarker=marker(current),
                targetRevision=None,
                targetHash=storage_hash(target),
            )
            atomic_write(stage_path, serialize_logical(target, spec.storage))
        staged = read_logical(stage_path, spec.storage)
        if staged is None or storage_hash(staged) != expected.targetHash:
            raise JobArtifactValidationError("staged JSON hash changed after write")
        if marker(staged) != JobMarker(jobId=job.id, operationId=operation_id):
            raise JobArtifactValidationError("staged JSON marker changed after write")
        manifest = ManifestArtifact(
            expected=expected,
            targetRelativePath=relative_target,
            stageFile=stage_path.name,
            reportKind=None,
            canonicalContentHash=None,
            canonicalChanged=None,
        )
        return StagedArtifact(manifest, spec.exact_path, stage_path, None, spec.pre_promotion_validator)

    def stage(
        self,
        job: SharedJob,
        specs: Sequence[ArtifactSpec],
        terminal_result: dict[str, str | int | bool | None],
    ) -> StagedJobBundle:
        if job.status != JobStatus.RUNNING or job.taskType not in JSON_TASKS:
            raise JobArtifactValidationError("only a running registered artifact job may stage")
        if not specs:
            raise JobArtifactValidationError("artifact bundle cannot be empty")
        operation_id = job.operationId or f"{job.taskType.value}:{job.id}"
        stage_root = self.data_root / "job-staging" / job.id
        if stage_root.exists():
            raise JobArtifactValidationError("job staging root already exists")
        stage_root.mkdir(parents=True)
        complete = False
        try:
            ordered = sorted(
                specs,
                key=lambda item: (
                    StorageKind.JSON.value if isinstance(item, CanonicalArtifactSpec) else item.storage.value,
                    item.artifact_type,
                    item.artifact_id,
                ),
            )
            staged: list[StagedArtifact] = []
            for index, spec in enumerate(ordered):
                match spec:
                    case CanonicalArtifactSpec():
                        stage_path = stage_root / f"{index:03d}.json"
                        staged.append(self._stage_canonical(spec, stage_path, job, operation_id))
                    case JsonArtifactSpec(storage=StorageKind.GZIP_JSON):
                        stage_path = stage_root / f"{index:03d}.json.gz"
                        staged.append(self._stage_json(spec, stage_path, job, operation_id))
                    case JsonArtifactSpec(storage=StorageKind.JSON):
                        stage_path = stage_root / f"{index:03d}.json"
                        staged.append(self._stage_json(spec, stage_path, job, operation_id))
                    case JsonArtifactSpec(storage=StorageKind.SQLITE):
                        raise JobArtifactValidationError("sqlite cannot enter JSON staging")
                    case unreachable:
                        assert_never(unreachable)
            manifest = JobStageManifest(
                jobId=job.id,
                operationId=operation_id,
                taskType=job.taskType,
                artifacts=[item.manifest for item in staged],
            )
            atomic_write(stage_root / "manifest.json", manifest.model_dump_json(indent=2).encode("utf-8"))
            reread = JobStageManifest.model_validate_json((stage_root / "manifest.json").read_bytes())
            if reread != manifest:
                raise JobArtifactValidationError("staging manifest changed after write")
            terminal_projection = project_terminal_result(job, JobStatus.DONE, terminal_result)
            intent = CommitIntent(
                operationId=operation_id,
                expectedArtifacts=[item.manifest.expected for item in staged],
                terminalProjection=terminal_projection,
            )
            complete = True
            return StagedJobBundle(job, operation_id, manifest, intent, terminal_result, tuple(staged))
        finally:
            if not complete and stage_root.exists():
                shutil.rmtree(stage_root)
