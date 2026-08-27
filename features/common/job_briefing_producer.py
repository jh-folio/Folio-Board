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
        # **저장 키는 그 시장의 세션일이다** — 보고서가 이미 알고 있다.
        # `write_briefing_from_markdown`이 시장별 세션 키(pre-open 새벽 실행이면 직전
        # 마감일)를 계산해 `date`에 실어 보내는데, 예전에는 여기서 요청 발행일로
        # 도로 덮어썼다. 그래서 02:04에 만든 08-27 세션 브리핑이 `2026-08-28.kr.json`
        # 으로 저장됐고(실측), 다음 날 저녁의 진짜 08-28 세션 실행이 그 파일을
        # 덮어써 08-27 세션 브리핑이 통째로 사라질 상태였다. 주간은 세션 키가 곧
        # 발행일이라 이 변경으로 달라지지 않는다.
        report_date = str(report.get("date") or request.date)
        if DATE_PATTERN.fullmatch(report_date) is None:
            report_date = request.date
        report["date"] = report_date
        report["marketScope"] = scope
        report["kind"] = kind
        specs.append(
            CanonicalArtifactSpec(
                artifact_type="briefing_report",
                artifact_id=f"{report_date}.{scope}{suffix}",
                report_kind=ReportKind.BRIEFING,
                exact_path=data_root / "briefings" / f"{report_date}.{scope}{suffix}.json",
                write_kind=WriteKind.CANONICAL,
                candidate=report,
            )
        )
        visual = deepcopy(request.visuals.get(scope, {}))
        snapshots = visual.get("snapshots")
        if isinstance(snapshots, dict) and snapshots:
            # 사이드카는 자기 보고서와 같은 키를 가져야 리더가 찾는다.
            visual["date"] = report_date
            visual["marketScope"] = scope
            specs.append(
                JsonArtifactSpec(
                    storage=StorageKind.GZIP_JSON,
                    artifact_type="briefing_visual",
                    artifact_id=f"{report_date}.{scope}{suffix}",
                    exact_path=data_root / "briefings" / f"{report_date}.{scope}{suffix}.visuals.json.gz",
                    payload=visual,
                )
            )
    return specs
