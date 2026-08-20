from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from features.common.canonical_identity import DATE_PATTERN, ReportKind
from features.common.canonical_report_types import WriteKind
from features.common.job_json_producer_types import BriefingJobRequest
from features.common.job_json_schema import (
    ArtifactSpec,
    CanonicalArtifactSpec,
    JobArtifactValidationError,
    JsonArtifactSpec,
)
from features.common.shared_jobs_schema import StorageKind


def briefing_specs(data_root: Path, request: BriefingJobRequest) -> list[ArtifactSpec]:
    if DATE_PATTERN.fullmatch(request.date) is None:
        raise JobArtifactValidationError("briefing date is invalid")
    if not request.scopes or len(request.scopes) != len(set(request.scopes)):
        raise JobArtifactValidationError("briefing scopes must be unique and nonempty")
    if set(request.reports) != set(request.scopes):
        raise JobArtifactValidationError("briefing reports must exactly match requested scopes")
    if not set(request.visuals).issubset(request.scopes):
        raise JobArtifactValidationError("briefing visuals must belong to requested scopes")
    specs: list[ArtifactSpec] = []
    # 종류 접미사. 일간은 접미사가 없어 기존 경로가 그대로다. 접미사가 없으면 주간
    # 커밋이 같은 날 일간 파일을 덮어쓴다 — 일요일 실행이면 그 주 브리핑 하나가 사라진다.
    kind = str(request.kind or "daily").strip().lower()
    suffix = "" if kind == "daily" else f".{kind}"
    for scope in request.scopes:
        report = deepcopy(request.reports[scope])
        report["date"] = request.date
        report["marketScope"] = scope
        report["kind"] = kind
        specs.append(
            CanonicalArtifactSpec(
                artifact_type="briefing_report",
                artifact_id=f"{request.date}.{scope}{suffix}",
                report_kind=ReportKind.BRIEFING,
                exact_path=data_root / "briefings" / f"{request.date}.{scope}{suffix}.json",
                write_kind=WriteKind.CANONICAL,
                candidate=report,
            )
        )
        visual = deepcopy(request.visuals.get(scope, {}))
        snapshots = visual.get("snapshots")
        if isinstance(snapshots, dict) and snapshots:
            visual["date"] = request.date
            visual["marketScope"] = scope
            specs.append(
                JsonArtifactSpec(
                    storage=StorageKind.GZIP_JSON,
                    artifact_type="briefing_visual",
                    artifact_id=f"{request.date}.{scope}{suffix}",
                    exact_path=data_root / "briefings" / f"{request.date}.{scope}{suffix}.visuals.json.gz",
                    payload=visual,
                )
            )
    return specs
