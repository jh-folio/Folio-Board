from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from features.agent_mode.proposal_schema import ProposalIdError, ProposalRecord, parse_proposal_id
from features.agent_mode.work_log_schema import (
    ProposalStatus,
    ResultStatus,
    WorkLogCategory,
    WorkLogEntry,
    WorkLogFilter,
)
from features.agent_mode.work_log_store import WorkLogStore
from features.agent_mode.work_log_token import WorkLogValidationError
from features.common.jcs import JsonValue
from features.common.shared_jobs_projection import ARTIFACT_TASKS
from features.common.shared_jobs_schema import SharedJob, TaskType
from features.common.shared_jobs_store import SharedJobStore


PROPOSAL_STATUSES = frozenset(status.value for status in ProposalStatus if status != ProposalStatus.UNAVAILABLE)
type JsonObject = dict[str, JsonValue]


class WorkLogView:
    def __init__(
        self,
        job_store: SharedJobStore,
        control_store: WorkLogStore,
        proposals_dir: Path,
    ) -> None:
        self.job_store = job_store
        self.control_store = control_store
        self.proposals_dir = proposals_dir

    def _proposal_status(self, proposal_id: str | None) -> ProposalStatus | None:
        if proposal_id is None:
            return None
        try:
            safe_id = parse_proposal_id(proposal_id)
        except ProposalIdError:
            return ProposalStatus.UNAVAILABLE
        path = self.proposals_dir / f"{safe_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ProposalStatus.UNAVAILABLE
        if not isinstance(value, dict):
            return ProposalStatus.UNAVAILABLE
        try:
            proposal = ProposalRecord.model_validate(value)
        except ValidationError:
            return ProposalStatus.UNAVAILABLE
        if proposal.id != proposal_id or proposal.status.value not in PROPOSAL_STATUSES:
            return ProposalStatus.UNAVAILABLE
        return ProposalStatus(proposal.status.value)

    def _entry(self, job: SharedJob) -> WorkLogEntry:
        category = WorkLogCategory.COMPANION if job.taskType == TaskType.COMPANION else WorkLogCategory.TASK
        result_status = ResultStatus(job.resultProjection.status) if job.resultProjection is not None else None
        artifact_types = sorted({ref.type for ref in job.artifactRefs})
        return WorkLogEntry(
            id=f"wl_{hashlib.sha256(job.id.encode()).hexdigest()[:24]}",
            jobId=job.id,
            category=category,
            kind=job.kind,
            taskType=job.taskType,
            labelCode=job.labelCode,
            status=job.status,
            progress=job.progress,
            messageCode=job.messageCode,
            createdAt=job.createdAt,
            startedAt=job.startedAt,
            updatedAt=job.updatedAt,
            finishedAt=job.finishedAt,
            errorCode=job.errorCode,
            generationMode=job.generationMode,
            adapter=job.adapter,
            requestedMode=job.requestedMode,
            mode=job.mode,
            attemptedEngine=job.attemptedEngine,
            finalEngine=job.finalEngine,
            fallbackReason=job.fallbackReason,
            artifactTypes=artifact_types,
            artifactCount=len(job.artifactRefs),
            proposalId=job.proposalId,
            proposalStatus=self._proposal_status(job.proposalId),
            resultStatus=result_status,
            queueWaitMs=job.queueWaitMs,
            contextMs=job.contextMs,
            cliMs=job.cliMs,
            postprocessMs=job.postprocessMs,
            totalMs=job.totalMs,
        )

    def visible(self, kind: WorkLogFilter) -> tuple[WorkLogEntry, ...]:
        jobs = self.job_store.merged().jobs
        surviving = {job.id for job in jobs}
        state = self.control_store.load()
        hidden = {item.jobId for item in state.hidden_jobs if item.jobId in surviving}
        eligible = [
            job
            for job in jobs
            if job.id not in hidden and (job.taskType == TaskType.COMPANION or job.taskType in ARTIFACT_TASKS)
        ]
        entries = [self._entry(job) for job in eligible]
        if kind != WorkLogFilter.ALL:
            entries = [entry for entry in entries if entry.category.value == kind.value]
        entries.sort(key=lambda entry: entry.jobId)
        entries.sort(key=lambda entry: entry.createdAt, reverse=True)
        return tuple(entries)

    def list(self, *, limit: int, offset: int, kind: WorkLogFilter) -> JsonObject:
        if not 1 <= limit <= 200 or not 0 <= offset <= 10_000:
            raise WorkLogValidationError("pagination_invalid")
        entries = self.visible(kind)
        state = self.control_store.load()
        return {
            "schemaVersion": 1,
            "storeRevision": state.store_revision,
            "jobsStoreRevision": self.job_store.load().store_revision,
            "retention": {"maxEntries": 200, "maxDays": 30},
            "total": len(entries),
            "entries": [entry.model_dump(mode="json") for entry in entries[offset : offset + limit]],
        }
