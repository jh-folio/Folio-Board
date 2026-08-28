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
    configured_editor_call,
    configured_axis_call,
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
from features.topic_report.axis_analysis import axis_brief_summary, axis_evidence, build_axis_briefs
from features.topic_report.draft_guard import better_draft, draft_problems, retry_directive
from features.topic_report.editor import edit_report, editor_summary
from features.topic_report.thesis import select_thesis, thesis_summary
from features.topic_report.web_lookup import (
    MAX_LOOKUPS,
    lookup_axis,
    lookup_summary,
    assign_source_ids,
    needs_web_lookup,
    render_lookup,
    web_source_items,
)
from features.topic_report.evaluation import evaluate_report
from features.topic_report.evidence import evidence_pack_summary
from features.common.web_search_scope import (
    audit_urls,
    load_source_scope,
    render_scope_instruction,
    render_web_search_directive,
)
from features.llm_settings.client import use_web_search_for_analysis
from features.topic_report.data_fetcher import market_data_to_markdown
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
        sections=list(approved.topicPlan.expectedSections),
    )
    # 웹 검색 범위는 축별 분석보다 **먼저** 정한다. 축 패스도 같은 허가·목록을 받아야
    # 하고, 예외를 삼키는 블록 안에서 이름을 처음 쓰면 NameError가 보이지 않는다
    # (실측: 그 때문에 축별 분석이 통째로 건너뛰어졌다).
    source_scope = load_source_scope() if use_web_search_for_analysis() else None
    web_directive = (
        render_scope_instruction(source_scope) + "\n\n" + render_web_search_directive(source_scope)
        if source_scope is not None
        else ""
    )
    # 웹 조회 — **찾기와 쓰기를 분리한다.** 브리프 호출에 "필요하면 검색도 하라"를 얹는
    # 방식은 네 번 시도해 모두 실패했다(웹에서 온 URL 0~1건). 그건 쓰기 과제라 모델이
    # 팩에 근거가 있으면 충분하다고 판단한다. 같은 어댑터에 순수한 찾기 과제를 주면
    # 곧바로 검색한다(실측: 닛케이 12.4%, 31,458.42, URL 2건).
    web_lookups: list[dict] = []
    if approved.deepResearch and source_scope is not None and not command.preview.zeroEvidence.required:
        subquestions = list(approved.topicPlan.deepResearch.subQuestions)
        # 이 콜러블은 `lookup_axis()`가 쓴다 — 웹에서 찾아오는 것이 그 패스의 일이므로
        # 검색을 명시로 켠다. 설정에 맡기면 API 분기가 조용히 꺼진 채로 "찾아오라"는
        # 지시만 받아 지어낸 URL을 원장에 등재한다.
        axis_call = configured_axis_call(
            approved,
            requested_mode=command.requestedMode,
            adapter=command.adapter,
            job_id=job_id,
            web_search=True,
        )
        for axis in approved.topicPlan.analysisAxes:
            if len(web_lookups) >= MAX_LOOKUPS:
                break
            axis_key = axis.key
            questions = [q.question for q in subquestions if q.axisKey == axis_key] or list(axis.questions)
            local = axis_evidence(axis_key, {q.id for q in subquestions if q.axisKey == axis_key}, rows)
            if not needs_web_lookup(
                {"key": axis_key, "label": axis.label}, questions, len(local), as_of=approved.asOfDate
            ):
                continue
            try:
                web_lookups.append(
                    lookup_axis(
                        {"key": axis_key, "label": axis.label},
                        questions,
                        approved.topicPlan.topic,
                        render_scope_instruction(source_scope),
                        axis_call,
                    )
                )
            except Exception:  # noqa: BLE001 - 조회 실패가 보고서를 죽이지 않는다
                continue
    web_lookups = assign_source_ids(web_lookups)
    web_facts = render_lookup(web_lookups)

    # 축별 분석 — 하위 질문에 실제로 답하게 하고, 그 결과가 본문 섹션의 뼈대가 된다.
    # 한 축이 실패해도 보고서를 죽이지 않는다(그 축은 status로 남고 본문은 근거로 쓴다).
    axis_briefs: list[dict] = []
    if approved.deepResearch and not command.preview.zeroEvidence.required:
        try:
            axis_briefs = build_axis_briefs(
                approved.topicPlan.model_dump(mode="json"),
                rows,
                run_call=configured_axis_call(
                    approved,
                    requested_mode=command.requestedMode,
                    adapter=command.adapter,
                    job_id=job_id,
                ),
                material_context=market_data_to_markdown(market_data)[:4000],
                web_directive="\n\n".join(part for part in (web_directive, web_facts) if part),
            )
        except Exception:
            axis_briefs = []

    # 핵심 논지 — 축별 발견을 **하나의 판단**으로 모은다. 이 단계가 없으면 본문이
    # 축을 병렬로 늘어놓고 끝나고(실측: 인플레 → 금리 → 엔캐리 → 정책 → 한국 시장),
    # 중심이 없으니 꼬리 섹션 넷이 같은 말을 되풀이한다.
    thesis: dict = {}
    if axis_briefs:
        try:
            thesis = select_thesis(
                approved.topicPlan.model_dump(mode="json"),
                axis_briefs,
                run_call=configured_axis_call(
                    approved,
                    requested_mode=command.requestedMode,
                    adapter=command.adapter,
                    job_id=job_id,
                ),
                material_context=market_data_to_markdown(market_data)[:2000],
            )
        except Exception:  # noqa: BLE001 - 논지 선정 실패가 보고서를 죽이지 않는다
            thesis = {}
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
        axis_briefs=axis_briefs,
        thesis=thesis,
    )
    if approved.deepResearch:
        context = "\n\n".join([
            context,
            "## Deep Research generation contract",
            f"Visible Markdown target: {depth_policy['recommendedMinChars']}~{depth_policy['recommendedMaxChars']} characters; safety max {depth_policy['safetyMaxChars']}.",
            f"Section character budgets (treat each as a floor, not a ceiling — fill at least 70%): {depth_policy['sectionBudgets']}",
            "Section list (write each exactly once, in this order, as H2): "
            + " | ".join(approved.topicPlan.expectedSections),
            "Body section titles come from the approved plan — do not rename, merge, or drop them.",
            # 한 사례가 두 섹션을 먹는 것을 막는다. 실측으로 전이 경로 섹션이 2021~2022와
            # 2024년 8월을 예시로 끌어와 전개했는데, 그 둘은 바로 뒤에 각자 2,000자 넘는
            # 섹션을 갖고 있었다. 축 브리프끼리 서로를 모르므로 본문 계약이 함께 말해야 한다.
            "Each body section owns its own subject. When another section's case is needed to make "
            "a point, cite its conclusion in one line and move on — do not re-tell its sequence, "
            "figures, or narrative. Redundancy across sections is a defect, not thoroughness.",
            "At the end of every evidence-bearing H2 section add one hidden tag like <!-- folio-source-ids: ev_001, market_SPY, macro_DGS10 -->.",
            "Use only source IDs present in the supplied evidence/material context. Never use userContext as a source.",
            f"Material resolution: {material_resolution}",
        ])
    if source_scope is not None:
        # 허용 목록만 주면 금지문으로 읽힌다. 쓰라는 지시를 함께 준다.
        context = "\n\n".join([
            context,
            render_scope_instruction(source_scope),
            render_web_search_directive(source_scope),
        ])
    if web_facts:
        context = "\n\n".join([context, web_facts])
    context = "\n\n".join([context, render_market_state_projection(command.marketState)])
    attempted = "none" if command.preview.zeroEvidence.required else "api" if command.requestedMode == "direct" else "cli"
    fallback_reason = "confirmed_zero_evidence" if attempted == "none" else None
    output: EngineOutput | None = None

    def _generate(extra: str = "") -> EngineOutput | None:
        """쓰기 호출 하나. 재시도가 같은 경로를 타야 컨텍스트가 갈리지 않는다."""
        nonlocal fallback_reason
        full = "\n\n".join([context, extra]) if extra else context
        if attempted == "api":
            try:
                supports_deep_options = "timeout_seconds" in inspect.signature(attempt_direct).parameters
                return (
                    attempt_direct(prompt, full, max_output_tokens=14_000, timeout_seconds=600)
                    if approved.deepResearch and supports_deep_options
                    else attempt_direct(prompt, full)
                )
            except EngineUnavailableError:
                fallback_reason = "engine_unavailable"
            except EngineFailedError:
                fallback_reason = "engine_failed"
            return None
        if attempted == "cli":
            try:
                cli_args = {
                    "adapter": command.adapter,
                    "job_id": job_id,
                    "approved": approved,
                    "evidence_items": evidence_items,
                }
                if approved.deepResearch:
                    cli_args["timeout_seconds"] = 1800
                return attempt_cli(prompt, full, **cli_args)
            except EngineUnavailableError:
                fallback_reason = "engine_unavailable"
            except EngineFailedError:
                fallback_reason = "engine_failed"
        return None

    output = _generate()
    # 초안이 못 쓸 물건이면 **쓰기만** 한 번 더 시킨다. 딥 실행에서 값비싼 것은 쓰기가
    # 아니라 그 앞이다(근거 팩·웹 조회·축 브리프·논지 선정). 실측으로 같은 질문 4회 중
    # 2회가 못 쓸 초안이었고, 그중 한 번은 9분을 쓰고 아무것도 남기지 못했다.
    draft_guard_note: dict = {}
    if approved.deepResearch and output is not None:
        problems = draft_problems(output.markdown, min_chars=depth_policy["recommendedMinChars"])
        draft_guard_note = {"problems": problems, "retried": False, "outcome": ""}
        if problems:
            # `_generate`는 `fallback_reason`을 `nonlocal`로 쓴다. 재시도가 실패하면 그
            # 값이 "engine_failed"로 덮이는데, 이 분기는 **첫 초안이 이미 성공했을 때만**
            # 돈다 — 그러면 실제로는 LLM이 만든 보고서에 엔진 실패가 기록되고 Work Log가
            # 실패한 실행으로 보여준다. 재시도 결과를 버릴 때는 이유도 되돌린다.
            reason_before_retry = fallback_reason
            retry = _generate(retry_directive(
                problems,
                min_chars=int(depth_policy["recommendedMinChars"]),
                sections=list(approved.topicPlan.expectedSections),
            ))
            draft_guard_note["retried"] = True
            if retry is not None:
                chosen, reason = better_draft(
                    output.markdown, retry.markdown, min_chars=depth_policy["recommendedMinChars"],
                )
                draft_guard_note["outcome"] = reason
                if chosen == retry.markdown:
                    output = retry
                else:
                    # 첫 초안을 쓰기로 했으면 그 실행의 이유를 그대로 둔다.
                    fallback_reason = reason_before_retry
            else:
                draft_guard_note["outcome"] = "retry_unavailable"
                fallback_reason = reason_before_retry
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
    # 리서치 에디터 — 분석가가 사실을 정하고 에디터는 전달 방식을 정한다.
    # 한 호출이 두 역할을 겸하면 안전한 쪽으로 기운다(실측: 문단마다 유보 표현,
    # 꼬리 섹션 넷의 반복, 파월·월러 발언의 익명화). 금지는 코드가 집행하며
    # 계약을 어긴 편집본은 통째로 버리고 초안을 쓴다.
    edit_result: dict = {}
    if approved.deepResearch and output is not None:
        edit_result = edit_report(
            markdown,
            run_call=configured_editor_call(
                approved,
                requested_mode=command.requestedMode,
                adapter=command.adapter,
                job_id=job_id,
            ),
            thesis=thesis,
            section_budgets=depth_policy.get("sectionBudgets"),
        )
        markdown = str(edit_result.get("markdown") or markdown)

    material_items = material_source_items(material_resolution, market_data, macro_data)
    # 웹에서 찾은 사실도 원장에 올린다. 계약이 "제공된 source ID만 쓰라"고 하므로,
    # 등재하지 않으면 모델은 그것을 인용할 자격이 없는 자료로 본다(실측: 사실 12건을
    # 찾아 놓고 본문에 쓴 것은 1건).
    web_items = web_source_items(web_lookups)
    source_ledger = source_ledger_from_items(
        [*evidence_items, *material_items, *web_items], artifact_type="topic_report", limit=160,
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
        "axisAnalysis": axis_brief_summary(axis_briefs) if axis_briefs else None,
        "coreThesis": thesis_summary(thesis) if thesis else None,
        "editorPass": editor_summary(edit_result) if edit_result else None,
        "draftGuard": draft_guard_note or None,
        "webLookup": lookup_summary(web_lookups) if web_lookups else None,
        # 웹 검색을 켰다면 무엇을 봤는지 남긴다. 목록 밖 도메인이 있으면 그대로 기록해
        # 다음에 목록을 고칠 근거로 쓴다 — 조용히 지우지 않는다.
        "webSearchAudit": (
            {
                "requested": True,
                "engine": generation_mode,
                # 웹 근거가 **쓰였는지**는 태그로 잰다. URL 인쇄 여부로 재면 본문에 그대로
                # 서술된 사실도 0건으로 나온다(실측: CPI 7.0%·6.5%가 본문에 있는데 fromWeb=1).
                "citedSourceIds": sorted(
                    {
                        source_id
                        for ids in source_usage["sectionUsage"].values()
                        for source_id in ids
                        if str(source_id).startswith("web_")
                    }
                ),
                "availableSourceIds": [str(item.get("sourceId") or "") for item in web_items],
                # URL 인쇄는 독자가 검증할 수 있는가의 문제라 따로 센다.
                "printedUrls": sorted(
                    {
                        row["url"]
                        for row in audit_urls(markdown, source_scope)["allowed"]
                        if row["url"] not in {str(item.get("url") or "") for item in evidence_items}
                    }
                ),
                **audit_urls(markdown, source_scope),
            }
            if source_scope is not None
            else {"requested": False}
        ),
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
