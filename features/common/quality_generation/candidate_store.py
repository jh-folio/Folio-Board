"""Owner-scoped validated report checkpoints for long-running quality pipelines."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from features.common.atomic_replace import write_bytes_atomic
from features.common.shared_jobs_schema import JOB_ID_PATTERN


class CandidateCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schemaVersion: int = 1
    ownerJobId: str
    candidateIndex: int = Field(ge=0, le=2)
    reportId: str = Field(min_length=1, max_length=240)
    normalizedHash: str = Field(pattern=r"[0-9a-f]{64}")
    accepted: bool
    validation: dict[str, Any]
    provenance: dict[str, Any]
    report: dict[str, Any]


def report_hash(report: dict) -> str:
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CandidateStore:
    def __init__(self, context_root: Path) -> None:
        self.context_root = context_root.resolve()

    def _owner(self, job_id: str) -> Path:
        if JOB_ID_PATTERN.fullmatch(job_id) is None:
            raise ValueError("invalid_candidate_owner")
        owner = (self.context_root / job_id).resolve()
        owner.relative_to(self.context_root)
        return owner

    def path(self, job_id: str, index: int) -> Path:
        if index not in {0, 1, 2}:
            raise ValueError("invalid_candidate_index")
        return self._owner(job_id) / f"quality-candidate-{index}.json"

    def write(
        self,
        job_id: str,
        index: int,
        *,
        report_id: str,
        accepted: bool,
        validation: dict,
        provenance: dict,
        report: dict,
    ) -> CandidateCheckpoint:
        checkpoint = CandidateCheckpoint(
            ownerJobId=job_id,
            candidateIndex=index,
            reportId=report_id,
            normalizedHash=report_hash(report),
            accepted=accepted,
            validation=validation,
            provenance=provenance,
            report=report,
        )
        path = self.path(job_id, index)
        payload = json.dumps(checkpoint.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8")
        write_bytes_atomic(path, payload)
        return checkpoint

    def read(self, job_id: str, index: int) -> CandidateCheckpoint | None:
        path = self.path(job_id, index)
        if not path.exists():
            return None
        try:
            checkpoint = CandidateCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        if checkpoint.ownerJobId != job_id or checkpoint.candidateIndex != index:
            return None
        if checkpoint.normalizedHash != report_hash(checkpoint.report):
            return None
        return checkpoint

    def latest_accepted(self, job_id: str) -> CandidateCheckpoint | None:
        rows = [checkpoint for index in range(3) if (checkpoint := self.read(job_id, index)) is not None and checkpoint.accepted]
        return max(rows, key=lambda row: row.candidateIndex) if rows else None


__all__ = ["CandidateCheckpoint", "CandidateStore", "report_hash"]
