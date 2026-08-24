from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from features.agent_mode.market_state_context import MarketStateProjection, render_market_state_projection
from features.common.jcs import JsonValue
from features.common.market_data.tape import build_market_tape
from features.common.quality_generation.preflight import preflight_from_context
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.common.research_schema.data_gaps import data_gaps_from_messages
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.topic_report.approval_store import utc_z
from features.topic_report.approved_generation_support import (
    EngineFailedError,
    EngineOutput,
    EngineUnavailableError,
    _materials,
    _normalized_evidence,
    _topic,
    attempt_cli,
    attempt_direct,
)
from features.topic_report.approved_research import PreparedResearch
from features.topic_report.approved_schema import ApprovedRequest
from features.topic_report.evaluation import evaluate_report
from features.topic_report.evidence import evidence_pack_summary
from features.topic_report.depth_policy import build_depth_policy
from features.topic_report.material_requirements import (
    material_gap_messages,
    material_source_items,
    resolve_material_requirements,
)
from features.topic_report.research_trace import build_research_trace_summary
from features.topic_report.section_sources import apply_section_usage
from features.topic_report.report_rules import build_rule_report
from features.topic_report.resolution_schema import ResearchPreview
from features.topic_report.service import _build_llm_context, _read_prompt
from features.topic_report.templates import compose_prompt


@dataclass(frozen=True, slots=True)
class ApprovedGenerationInput:
    approved: ApprovedRequest
    approvalId: str
    requestedMode: str
    adapter: str
    preview: ResearchPreview
    research: PreparedResearch
    marketState: MarketStateProjection


@dataclass(frozen=True, slots=True)
class ApprovedGenerationOutcome:
    report: dict[str, JsonValue]
    attemptedEngine: str
    finalEngine: str
    fallbackReason: str | None
    adapter: str
    generationMode: str
    mode: str




def build_approved_report(
    command: ApprovedGenerationInput,
    *,
    job_id: str,
    clock: Callable[[], datetime],
) -> ApprovedGenerationOutcome:
    approved = command.approved
    rows = command.research.evidence_items
    evidence_items = _normalized_evidence(rows)
    selected = [str(item.get("documentId") or "") for item in evidence_items]
    if selected != command.preview.resolution.selectedEvidenceIds:
        raise ValueError("persisted_evidence_resolution_mismatch")
    if command.preview.zeroEvidence.required:
        topic = _topic(approved)
        market_data = {"tickers": {}, "asOf": approved.asOfDate}
        macro_data = {"ok": False}
    else:
        topic, market_data, macro_data = _materials(approved, rows)
    material_resolution = resolve_material_requirements(
        approved.topicPlan.model_dump(mode="json"),
        market_data,
        macro_data,
        resolved_at=utc_z(clock()),
    )
    pack = dict(command.research.evidencePack)
    memories = pack.get("marketMemory") if isinstance(pack.get("marketMemory"), list) else []
    gaps = pack.get("dataGaps") if isinstance(pack.get("dataGaps"), list) else []
    gap_messages = [
        *list(gaps),
        *(material_gap_messages(material_resolution) if approved.deepResearch else []),
    ]
    depth_policy = build_depth_policy(
        deep_research=approved.deepResearch,
        analysis_axis_count=len(approved.topicPlan.analysisAxes),
        subquestion_count=len(approved.topicPlan.deepResearch.subQuestions),
        evidence_count=len(evidence_items),
        report_type=approved.topicPlan.reportType,
    )
    prompt = _read_prompt()
    if prompt:
        prompt = compose_prompt(prompt, approved.topicPlan.reportType)
    context = _build_llm_context(
        topic,
        market_data,
        macro_data,
        rows,
        list(memories),
        approved.userContext,
        approved.asOfDate,
        data_gaps=gap_messages,
        topic_plan=approved.topicPlan.model_dump(mode="json"),
    )
    if approved.deepResearch:
        context = "\n\n".join([
            context,
            "## Deep Research generation contract",
            f"Visible Markdown target: {depth_policy['recommendedMinChars']}~{depth_policy['recommendedMaxChars']} characters; safety max {depth_policy['safetyMaxChars']}.",
            f"Section character budgets: {depth_policy['sectionBudgets']}",
            "Write all 11 required H2 sections exactly once and in the approved order.",
            "At the end of every evidence-bearing H2 section add one hidden tag like <!-- folio-source-ids: ev_001, market_SPY, macro_DGS10 -->.",
            "Use only source IDs present in the supplied evidence/material context. Never use userContext as a source.",
            f"Material resolution: {material_resolution}",
        ])
    context = "\n\n".join([context, render_market_state_projection(command.marketState)])
    attempted = "none" if command.preview.zeroEvidence.required else "api" if command.requestedMode == "direct" else "cli"
    fallback_reason = "confirmed_zero_evidence" if attempted == "none" else None
    output: EngineOutput | None = None
    if attempted == "api":
        try:
            supports_deep_options = "timeout_seconds" in inspect.signature(attempt_direct).parameters
            output = (
                attempt_direct(prompt, context, max_output_tokens=14_000, timeout_seconds=600)
                if approved.deepResearch and supports_deep_options
                else attempt_direct(prompt, context)
            )
        except EngineUnavailableError:
            fallback_reason = "engine_unavailable"
        except EngineFailedError:
            fallback_reason = "engine_failed"
    elif attempted == "cli":
        try:
            cli_args = {
                "adapter": command.adapter,
                "job_id": job_id,
                "approved": approved,
                "evidence_items": evidence_items,
            }
            if approved.deepResearch:
                cli_args["timeout_seconds"] = 1800
            output = attempt_cli(prompt, context, **cli_args)
        except EngineUnavailableError:
            fallback_reason = "engine_unavailable"
        except EngineFailedError:
            fallback_reason = "engine_failed"
    markdown = output.markdown if output is not None else build_rule_report(
        topic,
        market_data,
        macro_data,
        rows,
        list(memories),
        approved.userContext,
        topic_plan=approved.topicPlan.model_dump(mode="json"),
        data_gaps=gap_messages,
        as_of=approved.asOfDate,
    )
    final_engine = attempted if output is not None else "rules"
    final_adapter = (
        output.adapter
        if output is not None
        else "rules"
        if attempted == "none"
        else command.adapter
    )
    generation_mode = "llm_api" if output is not None and attempted == "api" else "llm_cli" if output is not None else "rules"
    mode = "generate" if output is not None else "fallback"
    material_items = material_source_items(material_resolution, market_data, macro_data)
    source_ledger = source_ledger_from_items(
        [*evidence_items, *material_items], artifact_type="topic_report", limit=140,
    )
    source_ledger, source_usage = apply_section_usage(markdown, source_ledger)
    data_gaps = data_gaps_from_messages(
        gap_messages,
        artifact_type="topic_report",
        category="evidence",
        source_section="Evidence Pack",
    )
    checkpoints = checkpoints_from_markdown(
        markdown,
        artifact_type="topic_report",
        scope="market",
        topic=approved.topicPlan.topicLabel,
        headings=["앞으로 확인할 체크포인트", "체크포인트", "다음 체크포인트"],
    )
    market_tape = build_market_tape(date=approved.asOfDate, topic_market_data=market_data)
    summary = evidence_pack_summary(pack)
    quality_preflight = preflight_from_context(
        "topic_report",
        {},
        {
            "artifactId": f"{approved.asOfDate}:custom",
            "sourceCount": len(evidence_items),
            "sourceLedger": source_ledger,
            "evidenceItems": evidence_items,
            "dataGaps": data_gaps,
        },
    )
    quality = evaluate_report(
        markdown,
        evidence_summary=summary,
        topic_plan=approved.topicPlan.model_dump(mode="json"),
        user_context_present=bool(approved.userContext),
        checkpoints=checkpoints,
        source_ledger=source_ledger,
        evidence_items=evidence_items,
        data_gaps=data_gaps,
        market_tape=market_tape,
        artifact_type="topic_report",
    )
    executed_at = utc_z(clock())
    # 숨은 출처 태그 계약은 딥 모드에만 있다 — 일반 보고서에 요약을 쓰면 근거 30건을
    # 쓴 보고서가 "사용 근거 0건"으로 표시된다(태그가 없을 뿐인데).
    research_trace = (
        build_research_trace_summary(source_ledger, data_gaps)
        if approved.deepResearch else None
    )
    report: dict[str, JsonValue] = {
        "saved": False,
        "generatedAt": executed_at,
        "date": approved.asOfDate,
        "topicKey": "custom",
        "topicLabel": approved.topicPlan.topicLabel,
        "title": f"{approved.topicPlan.topicLabel} 분석 리포트 — {approved.asOfDate}",
        "markdown": markdown,
        "topicPlan": approved.topicPlan.model_dump(mode="json"),
        "evidencePackSummary": summary,
        "materialResolution": material_resolution,
        "depthPolicy": depth_policy,
        "researchTraceSummary": research_trace,
        "sourceUsage": source_usage,
        "evidenceItems": evidence_items,
        "sourceLedger": source_ledger,
        "checkpoints": checkpoints,
        "dataGaps": data_gaps,
        "marketTape": market_tape,
        "quality": quality,
        "qualityPreflight": quality_preflight,
        "researchResolution": command.preview.model_dump(mode="json"),
        "marketStateResolution": command.marketState.resolution,
        "generation": {
            "mode": generation_mode,
            "provider": output.provider if output is not None else "rules",
            "model": output.model if output is not None else "",
            "responseId": output.responseId if output is not None else "",
            "message": fallback_reason or "approved_engine_completed",
        },
        "executionProvenance": {
            "schemaVersion": 2 if approved.deepResearch else 1,
            "generationPolicyVersion": 2 if approved.deepResearch else 1,
            "approvalId": command.approvalId,
            "planHash": approved.planHash,
            "requestedMode": command.requestedMode,
            "attemptedEngine": attempted,
            "finalEngine": final_engine,
            "fallbackReason": fallback_reason,
            "adapter": final_adapter,
            "executedAt": executed_at,
        },
        "deepResearch": approved.deepResearch,
        "marketData": market_data,
        "macroAvailable": bool(macro_data.get("ok")),
        "sources": [
            {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "date": item.get("date", ""),
                "url": item.get("url", ""),
                "type": item.get("type", ""),
                "documentId": item.get("documentId", ""),
            }
            for item in evidence_items
        ],
        "memoryCount": len(memories),
        "docCount": len(evidence_items),
        "userContext": bool(approved.userContext),
        "personalOverlay": None,
    }
    return ApprovedGenerationOutcome(
        report=report,
        attemptedEngine=attempted,
        finalEngine=final_engine,
        fallbackReason=fallback_reason,
        adapter=final_adapter,
        generationMode=generation_mode,
        mode=mode,
    )
