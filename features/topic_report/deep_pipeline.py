"""Validated, checkpointed Deep Research candidate and bounded repair pipeline."""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from features.agent_mode import bridge as agent_bridge
from features.common.quality_generation.call_budget import deep_research_budget
from features.common.quality_generation.candidate_store import CandidateStore
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.llm_settings.client import request_llm_text, selected_llm_config
from features.topic_report.approved_generation import ApprovedGenerationInput, ApprovedGenerationOutcome
from features.topic_report.candidate_pipeline import candidate_improves, repairable_sections
from features.topic_report.evaluation import evaluate_report
from features.topic_report.report_contract import split_sections, validate_deep_report
from features.topic_report.research_trace import build_research_trace_summary
from features.topic_report.section_repair import merge_section_patches, parse_patch_response


class DeepResearchGenerationError(RuntimeError):
    pass


RepairCall = Callable[[int, str], str]


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
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise DeepResearchGenerationError("external_repair_disabled_in_tests")
        if command.requestedMode == "direct":
            config = selected_llm_config()
            if not config.get("apiKey"):
                raise DeepResearchGenerationError("repair_engine_unavailable")
            text, _response_id = request_llm_text(
                config,
                "Return one valid JSON object only. Repair only the allowlisted report sections.",
                context,
                web_search=False,
                max_output_tokens=7_000,
                json_mode=True,
                timeout_seconds=max(60, int(os.environ.get("TOPIC_REPORT_REPAIR_API_TIMEOUT_SECONDS", "300"))),
            )
            return str(text or "")
        result = agent_bridge.run_agent_prompt(
            "Return JSON only for this bounded Deep Research section repair.\n\n" + context,
            adapter=command.adapter,
            job_id=job_id,
            timeout=max(60, int(os.environ.get("TOPIC_REPORT_REPAIR_CLI_TIMEOUT_SECONDS", "900"))),
        )
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
    return validate_deep_report(
        str(report.get("markdown") or ""),
        source_ledger=list(report.get("sourceLedger") or []),
        depth_policy=dict(report.get("depthPolicy") or {}),
        material_resolution=dict(report.get("materialResolution") or {}),
        internal_score=int((report.get("quality") or {}).get("score") or 0),
    )


def run_deep_pipeline(
    outcome: ApprovedGenerationOutcome,
    command: ApprovedGenerationInput,
    *,
    job_id: str,
    report_id: str,
    candidate_store: CandidateStore,
    repair_call: RepairCall | None = None,
) -> ApprovedGenerationOutcome:
    if not command.approved.deepResearch:
        return outcome
    if outcome.finalEngine == "rules":
        raise DeepResearchGenerationError("deep_initial_engine_failed_without_candidate")
    report = dict(outcome.report)
    report["id"] = report_id
    validation = _validate(report)
    candidate_store.write(
        job_id, 0, report_id=report_id, accepted=bool(validation["valid"]), validation=validation,
        provenance={"pass": 0, "engine": outcome.finalEngine}, report=report,
    )
    if not validation["valid"]:
        raise DeepResearchGenerationError("deep_initial_candidate_invalid")
    budget = deep_research_budget()
    budget.claim("initial")
    best_report, best_validation, selected_index = report, validation, 0
    attempted_repairs = accepted_repairs = 0
    repair_call = repair_call or configured_repair_call(command, job_id=job_id)
    for pass_no, limit in ((1, 3), (2, 2)):
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
        except (DeepResearchGenerationError, OSError, RuntimeError, TimeoutError, ValueError):
            candidate_validation = {"valid": False, "defects": [], "metrics": {"blockingCount": 1}}
        candidate_store.write(
            job_id, pass_no, report_id=report_id, accepted=accepted, validation=candidate_validation,
            provenance={"pass": pass_no, "engine": outcome.finalEngine}, report=candidate_report,
        )
        if not accepted:
            break
        best_report, best_validation, selected_index = candidate_report, candidate_validation, pass_no
        accepted_repairs += 1
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
    return ApprovedGenerationOutcome(
        report=best_report,
        attemptedEngine=outcome.attemptedEngine,
        finalEngine=outcome.finalEngine,
        fallbackReason=outcome.fallbackReason,
        adapter=outcome.adapter,
        generationMode=outcome.generationMode,
        mode=outcome.mode,
    )


__all__ = ["DeepResearchGenerationError", "configured_repair_call", "run_deep_pipeline"]
