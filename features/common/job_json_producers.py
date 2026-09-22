from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from features.common.canonical_json import JsonValue
from features.common.job_briefing_producer import briefing_specs
from features.common.job_json_artifacts import JobArtifactWorkspace, JsonArtifactSpec
from features.common.job_json_producer_types import (
    BriefingJobRequest,
    InvestmentReviewJobRequest,
    OverlayJobRequest,
    QualityRepairJobRequest,
    ReportJobRequest,
)
from features.common.job_json_schema import JobArtifactConflictError, JobArtifactValidationError, StagedJobBundle
from features.common.job_report_producers import company_spec, overlay_spec, quality_repair_spec, topic_spec
from features.common.change_intelligence.service import decorate_candidate, strip_change_metadata
from features.common.shared_jobs_schema import SharedJob, StorageKind, TaskType


type ReviewBuilder = Callable[[dict[str, JsonValue]], dict[str, JsonValue]]


def _dump_rejected_candidate(scope: str, report: dict, validation: dict) -> None:
    """Write one rejected briefing candidate to a local file when asked.

    거절은 저장 보고서에 `rejectedReasonCodes`의 코드 하나만 남긴다.  어느 문장의
    어느 숫자가 걸렸는지 뒤에서 알 수 없어, 같은 거절이 반복돼도 원인을 좁힐 수
    없었다.  보고서에는 원문·수치·출처를 복제하지 않는 계약이므로(§daily_briefing
    README) 이 덤프는 보고서 밖의 로컬 파일이고, `BRIEFING_REJECTION_DUMP_DIR`을
    설정한 실행에서만 쓴다.  진단이 생성을 막아서는 안 되므로 실패는 삼킨다.
    """
    target = str(os.environ.get("BRIEFING_REJECTION_DUMP_DIR") or "").strip()
    if not target:
        return
    try:
        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        payload = {
            "scope": scope,
            "date": report.get("date"),
            "kind": report.get("kind"),
            "markdown": report.get("markdown"),
            "validation": validation,
        }
        (directory / f"rejected-{scope}-{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        return


def _review_builder(body: dict[str, JsonValue]) -> dict[str, JsonValue]:
    from features.investment_review.service import build_review

    date_value = body.get("date")
    date = date_value if isinstance(date_value, str) else None
    return build_review(
        date=date,
        include_portfolio=body.get("includePortfolio") is not False,
        include_watchlist=body.get("includeWatchlist") is not False,
        include_obsidian=body.get("includeObsidian") is not False,
        use_llm=body.get("useLlm") is True,
        force_refresh=True,
        persist=False,
    )


class JobJsonProducers:
    def __init__(
        self,
        data_root: Path,
        *,
        clock: Callable[[], datetime],
        review_builder: ReviewBuilder = _review_builder,
    ) -> None:
        self.data_root = data_root.resolve(strict=False)
        self.workspace = JobArtifactWorkspace(self.data_root, clock=clock)
        self.review_builder = review_builder

    @staticmethod
    def _require(job: SharedJob, task_type: TaskType) -> None:
        if job.taskType != task_type:
            raise JobArtifactValidationError(f"producer requires taskType={task_type.value}")

    def stage_briefing(self, job: SharedJob, request: BriefingJobRequest) -> StagedJobBundle:
        self._require(job, TaskType.BRIEFING)
        # Validate requested identity/visual ownership before filtering rejected markets.
        briefing_specs(self.data_root, request)
        from features.daily_briefing.finalize import BriefingFinalizationError, finalize_briefing_candidate
        from features.common.quality_generation.call_budget import SharedRepairBudget, current_briefing_budget
        budget = current_briefing_budget() or SharedRepairBudget()
        reports = {
            scope: strip_change_metadata(
                # 세션일을 발행일로 덮어쓰지 않는다(§job_briefing_producer와 같은 계약).
                # 여기서 덮어쓰면 새벽 실행의 08-27 세션이 08-28 파일에 등록된다.
                {**request.reports[scope],
                 "date": str(request.reports[scope].get("date") or request.date),
                 "marketScope": scope, "kind": request.kind},
            )
            for scope in request.scopes
        }
        accepted = {}
        rejected_codes = set()
        for scope, report in reports.items():
            try:
                accepted[scope] = finalize_briefing_candidate(
                    report,
                    repair_budget=budget,
                    visual_context=request.visuals.get(scope),
                    require_structure=True,
                )
            except BriefingFinalizationError as error:
                _dump_rejected_candidate(scope, report, error.validation)
                codes = set(error.validation.get("reasonCodes") or [])
                codes.update(row.get("kind") for row in error.validation.get("contradictions", []) if isinstance(row, dict) and row.get("kind"))
                if error.validation.get("requiredOmissions"):
                    codes.add("required_omission")
                codes.update((error.validation.get("sourceChecks") or {}).get("errors") or [])
                if codes.intersection({"cancelled", "deadline_expired"}):
                    raise
                rejected_codes.update(codes)
                continue
        if not accepted:
            raise BriefingFinalizationError("briefing_final_validation_failed", validation={"reasonCodes": sorted(rejected_codes)})
        scopes = tuple(scope for scope in request.scopes if scope in accepted)
        terminal = dict(request.terminal_result)
        if len(scopes) != len(request.scopes):
            terminal.update(partial=True, includedMarkets=",".join(scopes), omittedMarketCount=len(request.scopes) - len(scopes))
            terminal["title"] = str(terminal.get("title") or "브리핑") + " (일부 시장)"
            for report in accepted.values():
                report["expectedMarkets"] = [scope.upper() for scope in request.scopes]
                report["includedMarkets"] = [scope.upper() for scope in scopes]
                report["coverageWarnings"] = ["briefing_final_validation_partial"]
        decorated = BriefingJobRequest(
            date=request.date, scopes=scopes, reports=accepted,
            visuals={scope: value for scope, value in request.visuals.items() if scope in accepted},
            terminal_result=terminal, kind=request.kind,
        )
        budget.check_active()
        return self.workspace.stage(job, briefing_specs(self.data_root, decorated), terminal_result=terminal)

    def stage_company(self, job: SharedJob, request: ReportJobRequest) -> StagedJobBundle:
        self._require(job, TaskType.COMPANY_ANALYSIS)
        from features.company_analysis.service import analysis_report_id
        report = dict(request.report)
        if not report.get("id") and isinstance(report.get("company"), dict) and report.get("generatedAt"):
            report["id"] = analysis_report_id(report["company"], report["generatedAt"])
        from features.company_analysis.recovery import preserve_candidate
        preserve_candidate(self.data_root / "company-analysis", report)
        report = decorate_candidate("company_analysis", report, data_dir=self.data_root, generation_provenance=True)
        return self.workspace.stage(job, [company_spec(self.data_root, ReportJobRequest(report, request.terminal_result))], terminal_result=request.terminal_result)

    def stage_topic(self, job: SharedJob, request: ReportJobRequest) -> StagedJobBundle:
        self._require(job, TaskType.TOPIC_REPORT)
        from features.topic_report.service import _stable_topic_id
        report = dict(request.report)
        if not report.get("id") and report.get("date") and report.get("topicKey") and report.get("topicLabel"):
            report["id"] = _stable_topic_id(str(report["date"]), str(report["topicKey"]), str(report["topicLabel"]))
        report = decorate_candidate("topic_report", report, data_dir=self.data_root, generation_provenance=True)
        return self.workspace.stage(job, [topic_spec(self.data_root, ReportJobRequest(report, request.terminal_result))], terminal_result=request.terminal_result)

    def stage_overlay(self, job: SharedJob, request: OverlayJobRequest) -> StagedJobBundle:
        self._require(job, TaskType.PERSONAL_OVERLAY)
        return self.workspace.stage(job, [overlay_spec(self.data_root, request)], terminal_result=request.terminal_result)

    def stage_quality_repair(self, job: SharedJob, request: QualityRepairJobRequest) -> StagedJobBundle:
        self._require(job, TaskType.QUALITY_REPAIR)
        spec = quality_repair_spec(self.data_root, request)
        return self.workspace.stage(job, [spec], terminal_result=request.terminal_result)

    def stage_investment_review(
        self,
        job: SharedJob,
        request: InvestmentReviewJobRequest,
    ) -> StagedJobBundle:
        self._require(job, TaskType.INVESTMENT_REVIEW)
        # The CLI target becomes an exact JSON path below.  Validate before
        # calling the builder/stager so a hostile date can never create a
        # manifest, staged payload, or sibling file outside review storage.
        from features.investment_review.service import normalize_review_date

        requested_date = request.body.get("date")
        if requested_date is not None:
            try:
                normalize_review_date(requested_date)
            except ValueError as exc:
                raise JobArtifactValidationError("investment review date is invalid") from exc
        review = self.review_builder(request.body)
        date_value = review.get("date")
        try:
            date_value = normalize_review_date(date_value)
        except ValueError as exc:
            raise JobArtifactValidationError("investment review date is invalid") from exc
        prepared: dict[str, JsonValue] = {}

        def validate_review_candidate(payload: dict[str, JsonValue], current: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
            # This is deliberately a no-write finalization pass.  The common
            # stager owns the only durable write and calls us under the same
            # exact artifact lock used by direct API review writes.
            from features.investment_review.review_v2 import prepare_commit_candidate

            finalized = prepare_commit_candidate(
                self.data_root,
                self.data_root / "investment-review",
                payload,
                current_raw=current,
            )
            prepared["review"] = finalized
            return finalized

        def validate_authority_before_promotion() -> None:
            # The CLI job must not turn a long-lived stage into a stale write.
            # Direct rules/API generation instead finalizes inside its shared
            # lock and persists a visibly stale candidate by contract.
            from features.investment_review.review_v2 import build_input_basis, gather_inputs

            candidate = prepared.get("review")
            basis = candidate.get("inputBasis") if isinstance(candidate, dict) else None
            expected = basis.get("fingerprint") if isinstance(basis, dict) else ""
            # Older injected/compat producer seams do not carry a v2 basis;
            # they are not Investment Review v2 candidates and retain the
            # common JSON lifecycle's normal recovery behavior.
            if not isinstance(expected, str) or not expected:
                return
            # Only the stored analytics authority carries the compatibility
            # signature/backtest identity. Passing the whole inputBasis makes
            # the read path lose that shape and turns unchanged jobs stale.
            analytics_authority = basis.get("analytics") if isinstance(basis, dict) else None
            selection_version = basis.get("reportSelectionVersion") if isinstance(basis, dict) else ""
            actual = build_input_basis(gather_inputs(
                self.data_root, analytics_authority=analytics_authority,
                report_selection_version=str(selection_version or ""),
            )).get("fingerprint")
            if expected != actual:
                raise JobArtifactConflictError("investment_review_external_input_changed_reopen_generation")

        spec = JsonArtifactSpec(
            storage=StorageKind.JSON,
            artifact_type="investment_review",
            artifact_id=date_value,
            exact_path=self.data_root / "investment-review" / f"{date_value}.json",
            payload=review,
            payload_validator=validate_review_candidate,
            pre_promotion_validator=validate_authority_before_promotion,
        )
        return self.workspace.stage(job, [spec], terminal_result=request.terminal_result)


__all__ = [
    "BriefingJobRequest",
    "InvestmentReviewJobRequest",
    "JobJsonProducers",
    "OverlayJobRequest",
    "QualityRepairJobRequest",
    "ReportJobRequest",
]
