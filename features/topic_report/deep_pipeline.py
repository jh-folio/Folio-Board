"""Validated, checkpointed Deep Research candidate and bounded repair pipeline."""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from features.agent_mode import bridge as agent_bridge
from features.common.quality_generation.call_budget import deep_research_budget
from features.common.quality_generation.candidate_store import CandidateStore
from features.common.research_quality.contract_ceiling import apply_contract_ceiling
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.llm_settings.client import request_cli_text, selected_cli_config
from features.topic_report.approved_generation import ApprovedGenerationInput, ApprovedGenerationOutcome
from features.topic_report.candidate_pipeline import candidate_improves, repairable_sections
from features.topic_report.evaluation import evaluate_report
from features.topic_report.report_contract import (
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
    split_sections,
    validate_deep_report,
)
from features.topic_report.research_trace import build_research_trace_summary
from features.topic_report.section_repair import merge_section_patches, parse_patch_response
from features.common.jobs import current_diagnostic_recorder, diagnostic_stage_failure
from features.topic_report.execution import ensure_active, propagate_interruption, require_complete, report_incomplete


class DeepResearchGenerationError(RuntimeError):
    """딥 실행이 산출물을 되돌린 이유. `defects`에 결함 코드만 담는다."""

    def __init__(self, message: str, defects: list[str] | None = None) -> None:
        super().__init__(message)
        self.defects = list(defects or [])


RepairCall = Callable[[int, str], str]


def _task_reasoning_effort(command: ApprovedGenerationInput) -> str:
    effort = str((command.taskPolicy or {}).get("reasoningEffort") or "") if isinstance(command.taskPolicy, dict) else ""
    normalized = effort.strip().lower().replace("-", "_")
    return "" if normalized in {"", "default", "providerdefault", "provider_default"} else normalized


def _repair_payload(report: dict, validation: dict, sections: list[str], pass_no: int) -> str:
    by_heading = {row["heading"]: row["body"] for row in split_sections(str(report.get("markdown") or ""))}
    ledger = [
        {
            "sourceId": row.get("sourceId"),
            "title": row.get("title"),
            "date": row.get("date"),
            "evidenceRole": row.get("evidenceRole"),
        }
        for row in report.get("sourceLedger") or []
    ]
    payload = {
        "task": f"Deep Research section repair pass {pass_no}",
        "allowedSections": sections,
        "sections": {heading: by_heading.get(heading, "") for heading in sections},
        "defects": [row for row in validation.get("defects") or [] if row.get("section") in sections],
        "allowedSources": ledger,
        "dataGaps": report.get("dataGaps") or [],
        "sectionBudgets": {
            heading: (report.get("depthPolicy") or {}).get("sectionBudgets", {}).get(heading)
            for heading in sections
        },
        "outputContract": {
            "format": "json",
            "shape": {"patches": [{"heading": "allowed H2", "replacementBody": "body only", "sourceIds": ["allowed id"]}]},
            "maximumPatches": len(sections),
            "noNewFactsNumbersOrSources": True,
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configured_repair_call(command: ApprovedGenerationInput, *, job_id: str) -> RepairCall:
    def invoke(_pass_no: int, context: str) -> str:
        ensure_active(job_id)
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise DeepResearchGenerationError("external_repair_disabled_in_tests")
        result_sink = {}
        result = agent_bridge.run_agent_prompt(
            "Return JSON only for this bounded Deep Research section repair.\n\n" + context,
            adapter=command.adapter,
            model=str((command.taskPolicy or {}).get("model") or "") if isinstance(command.taskPolicy, dict) else "",
            reasoning_effort=_task_reasoning_effort(command),
            job_id=job_id,
            timeout=max(60, int(os.environ.get("TOPIC_REPORT_REPAIR_CLI_TIMEOUT_SECONDS", "900"))),
            result_sink=result_sink,
        )
        ensure_active(job_id)
        require_complete(result_sink)
        return str(result.get("output") or "")
    return invoke


def _quality(report: dict, markdown: str) -> dict:
    return evaluate_report(
        markdown,
        evidence_summary=report.get("evidencePackSummary") or {},
        topic_plan=report.get("topicPlan") or {},
        user_context_present=bool(report.get("userContext")),
        checkpoints=report.get("checkpoints") or [],
        source_ledger=report.get("sourceLedger") or [],
        evidence_items=report.get("evidenceItems") or [],
        data_gaps=report.get("dataGaps") or [],
        market_tape=report.get("marketTape") or {},
        artifact_type="topic_report",
    )


def _validate(report: dict) -> dict:
    plan = report.get("topicPlan") or {}
    validation = validate_deep_report(
        str(report.get("markdown") or ""),
        source_ledger=list(report.get("sourceLedger") or []),
        depth_policy=dict(report.get("depthPolicy") or {}),
        material_resolution=dict(report.get("materialResolution") or {}),
        internal_score=int((report.get("quality") or {}).get("score") or 0),
        expected_sections=list(plan.get("expectedSections") or []) or None,
        research_questions=list(plan.get("researchQuestions") or []) or None,
        quote_sources=list((report.get("webLookup") or {}).get("speakerSources") or []),
    )
    if report_incomplete(report):
        validation["valid"] = False
        validation.setdefault("defects", []).append({"code": "provider_incomplete", "category": "blocking", "section": ""})
        validation.setdefault("metrics", {})["blockingCount"] = int(validation.get("metrics", {}).get("blockingCount") or 0) + 1
    return validation


def _missing_fixed_sections(markdown: str) -> list[str]:
    """빠진 고정 섹션 이름. 진단 문자열이 200자를 넘지 않게 두 개까지만."""
    written = {str(row.get("heading") or "") for row in split_sections(markdown)}
    missing = [name for name in (*REPORT_HEAD_SECTIONS, *REPORT_TAIL_SECTIONS) if name not in written]
    return [f"missing={'/'.join(missing[:2])}"] if missing else []


def run_deep_pipeline(
    outcome: ApprovedGenerationOutcome,
    command: ApprovedGenerationInput,
    *,
    job_id: str,
    report_id: str,
    candidate_store: CandidateStore,
    repair_call: RepairCall | None = None,
) -> ApprovedGenerationOutcome:
    ensure_active(job_id)
    if not command.approved.deepResearch:
        return outcome
    if outcome.finalEngine == "rules":
        # 왜 규칙으로 떨어졌는지를 함께 싣는다. `engine_rate_limited`면 사용자가 할 일은
        # 한도가 풀린 뒤 다시 누르는 것이고, 그때 재개 체크포인트가 남은 단계부터 잇는다.
        raise DeepResearchGenerationError(
            "deep_initial_engine_failed_without_candidate",
            [outcome.fallbackReason or ""],
        )
    report = dict(outcome.report)
    from features.common.report_citations import render_citation_links, strip_citation_links
    report["markdown"] = strip_citation_links(str(report.get("markdown") or ""))

    def cited_copy(candidate):
        return {**candidate, "markdown": render_citation_links(
            str(candidate.get("markdown") or ""), candidate.get("sourceLedger"), execution=outcome.execution,
        )}
    report["id"] = report_id
    validation = _validate(report)
    candidate_store.write(
        job_id, 0, report_id=report_id, accepted=bool(validation["valid"]), validation=validation,
        provenance={"pass": 0, "engine": outcome.finalEngine}, report=cited_copy(report),
    )
    if not validation["valid"]:
        # 초안 재시도 결과를 함께 싣는다. 실패한 잡은 보고서를 저장하지 않으므로
        # `draftGuard`가 정확히 필요한 순간에 사라진다 — 다시 쓰게 했는데도 같은 계약을
        # 어긴 것인지, 아예 재시도가 돌지 않은 것인지 구분되지 않는다.
        guard = report.get("draftGuard") or {}
        raise DeepResearchGenerationError(
            "deep_initial_candidate_invalid",
            [
                *[str(row.get("code") or "") for row in validation.get("defects") or [] if row.get("category") == "blocking"],
                *([f"draft_retry={guard.get('outcome') or 'none'}"] if guard.get("retried") else ["draft_retry=skipped"]),
                # 어느 고정 섹션이 없었는지. 모델이 제목을 바꿔 쓴 것인지 중간에 멈춘
                # 것인지는 이것으로만 갈린다.
                *_missing_fixed_sections(str(report.get("markdown") or "")),
            ],
        )
    budget = deep_research_budget()
    budget.claim("initial")
    best_report, best_validation, selected_index = report, validation, 0
    attempted_repairs = accepted_repairs = 0
    repair_call = repair_call or configured_repair_call(command, job_id=job_id)
    for pass_no, limit in ((1, 3), (2, 2)):
        ensure_active(job_id)
        sections = repairable_sections(best_validation, limit=limit)
        if not sections:
            break
        budget.claim("repair")
        attempted_repairs += 1
        accepted = False
        candidate_report = dict(best_report)
        try:
            response = repair_call(pass_no, _repair_payload(best_report, best_validation, sections, pass_no))
            patches = parse_patch_response(response)
            candidate_report["markdown"] = merge_section_patches(
                str(best_report.get("markdown") or ""), patches, allowed_sections=set(sections),
            )
            candidate_report["quality"] = _quality(candidate_report, str(candidate_report["markdown"]))
            candidate_validation = _validate(candidate_report)
            accepted = candidate_validation["valid"] and candidate_improves(best_validation, candidate_validation)
        except (DeepResearchGenerationError, OSError, RuntimeError, TimeoutError, ValueError) as error:
            propagate_interruption(error)
            diagnostic_stage_failure(
                current_diagnostic_recorder(), error, stage_id=None,
                stage_code="validate", boundary="validation",
            )
            candidate_validation = {"valid": False, "defects": [], "metrics": {"blockingCount": 1}}
        ensure_active(job_id)
        candidate_store.write(
            job_id, pass_no, report_id=report_id, accepted=accepted, validation=candidate_validation,
            provenance={"pass": pass_no, "engine": outcome.finalEngine}, report=cited_copy(candidate_report),
        )
        if not accepted:
            break
        best_report, best_validation, selected_index = candidate_report, candidate_validation, pass_no
        accepted_repairs += 1
    best_report["quality"] = apply_contract_ceiling(best_report.get("quality") or {}, best_validation)
    best_report["sourceLedger"] = best_validation.get("sourceLedger") or best_report.get("sourceLedger") or []
    best_report["researchTraceSummary"] = build_research_trace_summary(
        best_report["sourceLedger"], best_report.get("dataGaps") or [],
    )
    best_report["checkpoints"] = checkpoints_from_markdown(
        str(best_report.get("markdown") or ""), artifact_type="topic_report", scope="market",
        topic=str(best_report.get("topicLabel") or ""), headings=["앞으로 확인할 체크포인트"],
    )
    provenance = dict(best_report.get("executionProvenance") or {})
    provenance.update({
        "schemaVersion": 2,
        "generationPolicyVersion": 2,
        "attemptedRepairCount": attempted_repairs,
        "acceptedRepairCount": accepted_repairs,
        "selectedCandidateIndex": selected_index,
        "completedFromCheckpoint": False,
        "callBudget": budget.snapshot(),
    })
    best_report["executionProvenance"] = provenance
    # Step 11 필드(qualityBefore/After 등)를 덮어쓰지 않는다 — 딥 정보는 같은 필드의
    # 하위 키로 둔다. executionProvenance에도 같은 값이 있으므로 소비자는 어느 쪽을
    # 읽어도 된다.
    best_report["qualityGeneration"] = {
        **(best_report.get("qualityGeneration") or {}),
        "deep": {
            "policyVersion": 2,
            "selectedCandidateIndex": selected_index,
            "attemptedRepairCount": attempted_repairs,
            "acceptedRepairCount": accepted_repairs,
            "validation": best_validation,
        },
    }
    ensure_active(job_id)
    return ApprovedGenerationOutcome(
        report=cited_copy(best_report),
        attemptedEngine=outcome.attemptedEngine,
        finalEngine=outcome.finalEngine,
        fallbackReason=outcome.fallbackReason,
        adapter=outcome.adapter,
        generationMode=outcome.generationMode,
        mode=outcome.mode,
        execution=outcome.execution.with_text(str(best_report.get("markdown") or "")) if outcome.execution is not None else None,
    )


__all__ = ["DeepResearchGenerationError", "configured_repair_call", "run_deep_pipeline"]
