"""Company analysis generation orchestration kept out of app.py.

자료 수집·컨텍스트 조립은 `generation_context.py`가, 계약 검증·점수 상한은
`finalize.py`가 소유한다. **CLI 경로(`agent_mode/service.py`)도 같은 둘을 쓴다** —
한쪽에만 붙인 장치가 다른 쪽에서 조용히 빠지는 일을 이미 겪었다.
"""
from __future__ import annotations

from features.common.change_intelligence.service import decorate_candidate
from features.common.utils import now_iso
from features.common.web_search_scope import audit_urls, load_source_scope
from features.company_analysis.finalize import finalize_report
from features.company_analysis.data_gap_resolver import resolve_company_analysis_gaps
from features.company_analysis.generation_context import build_generation_inputs, draft_artifact
from features.company_analysis.report_contract import missing_sections, render_section_retry
from features.company_analysis.report_rules import build_rule_report
from features.company_analysis.service import (
    DATA_DIR,
    analysis_status_message,
    company_analysis_sources,
    generate_llm_company_analysis,
    read_company_analysis_prompt,
)
from features.company_analysis.style import analysis_prompt_path, normalize_analysis_style
from features.llm_settings.client import selected_llm_config, use_web_search_for_analysis


def analyze_company(query, web_search_override=None, llm_override=None, analysis_style="beginner", *, runtime: dict | None = None):
    runtime = runtime or {}
    llm_fn = runtime.get("generate_llm_company_analysis", generate_llm_company_analysis)
    rule_fn = runtime.get("build_rule_report", build_rule_report)
    sources_fn = runtime.get("company_analysis_sources", company_analysis_sources)
    llm_config_fn = runtime.get("selected_llm_config", selected_llm_config)
    web_search_enabled_fn = runtime.get("use_web_search_for_analysis", use_web_search_for_analysis)
    analysis_style = normalize_analysis_style(analysis_style)
    web_search = bool(web_search_enabled_fn()) if web_search_override is None else bool(web_search_override)

    inputs = build_generation_inputs(
        query, analysis_style=analysis_style, web_search=web_search, runtime=runtime,
    )
    company = inputs.materials.get("company") or inputs.company

    def _generate(extra: str = ""):
        return llm_fn(
            query, inputs.docs, web_search_override=web_search_override, llm_override=llm_override,
            materials=inputs.materials, quality_preflight=inputs.preflight,
            analysis_style=analysis_style, depth_policy=inputs.depthPolicy,
            source_ledger=inputs.sourceLedger,
            context="\n\n".join(part for part in (inputs.context, extra) if part),
        )

    llm_result, llm_status = _generate()
    # 초안이 고정 9섹션을 어기면 **쓰기만** 한 번 더 시킨다. 실측 4건 중 3건이 계약과
    # 다른 제목을 썼는데, 보수 패스는 섹션 3개를 손볼 뿐이라 골격이 어긋난 초안을
    # 되살리지 못한다. 앞의 자료 수집·웹 조회는 재사용된다.
    draft_guard: dict = {}
    if llm_result and llm_result.get("markdown"):
        missing = missing_sections(str(llm_result["markdown"]))
        draft_guard = {"missing": missing, "retried": False, "outcome": ""}
        if missing:
            retry, retry_status = _generate(render_section_retry(missing))
            draft_guard["retried"] = True
            if retry and retry.get("markdown"):
                if len(missing_sections(str(retry["markdown"]))) < len(missing):
                    llm_result, llm_status = retry, retry_status
                    draft_guard["outcome"] = "retry_better"
                else:
                    # 재시도가 더 낫지 않으면 처음 것을 쓴다. 나쁜 초안이라도 없는 것보다 낫다.
                    draft_guard["outcome"] = "retry_no_gain"
            else:
                draft_guard["outcome"] = "retry_unavailable"

    # 설정이 아니라 실제 결과로 기록한다. 설정만 보면 CLI 모드·LLM 실패·자료 없음처럼
    # 웹 검색이 한 번도 돌지 않은 경로에서도 official_web_search가 "시도함"으로 남는다.
    gaps = resolve_company_analysis_gaps(
        inputs.materials, web_search_allowed=bool(llm_result and llm_result.get("webSearch")),
    )
    common = {
        **draft_artifact(inputs, query, analysis_style=analysis_style, data_gaps=gaps),
        "generatedAt": now_iso(),
        "qualityPreflight": inputs.preflight,
        "draftGuard": draft_guard or None,
    }
    if llm_result:
        generation = {
            "mode": "llm", "status": llm_status, "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""), "responseId": llm_result.get("responseId", ""),
            "sourceCount": len(llm_result.get("usedDocs", [])), "webSearch": bool(llm_result.get("webSearch")),
            "tokenUsage": llm_result.get("tokenUsage") or {},
        }
        generation["message"] = analysis_status_message(generation)
        report = {
            **common, "headline": f"{company['name']} 기업 분석", "markdown": llm_result["markdown"],
            "prompt": read_company_analysis_prompt(analysis_style),
            "promptPath": llm_result.get("promptPath") or str(analysis_prompt_path(analysis_style)),
            "generation": generation,
            "sources": sources_fn(inputs.materials, llm_result.get("usedDocs", [])[:14]),
            # 프롬프트로 부탁한 것과 실제로 지킨 것은 다르다. 무엇이 목록 밖이었는지
            # 남겨야 다음에 목록을 고칠 수 있다.
            "webSearchAudit": audit_urls(llm_result.get("markdown", ""), load_source_scope(company)),
        }
    else:
        generation = {"mode": "rules", "status": llm_status, "provider": llm_config_fn().get("provider", ""), "model": "", "sourceCount": 0}
        generation["message"] = analysis_status_message(generation)
        tags = [tag for doc in inputs.selected for tag in doc.get("impactTags", [])]
        report = {
            **common, "headline": f"{company['name']} 규칙 기반 기업 분석",
            "markdown": rule_fn(inputs.materials, analysis_style=analysis_style), "generation": generation,
            "sources": sources_fn(inputs.materials, inputs.materials.get("selectedDocs", inputs.docs[:10])[:14]),
        }
        report["analysisInputs"].update({
            "topTags": sorted(set(tags), key=tags.count, reverse=True)[:6],
            "recent": " ".join(doc.get("summary", "") for doc in inputs.selected[:5])
            or "선별된 보조 뉴스/리포트 자료가 없습니다.",
        })

    report = finalize_report(report, quote_sources=inputs.quoteSources)
    return decorate_candidate(
        "company_analysis", report, data_dir=DATA_DIR,
        native_context={"materials": inputs.materials}, generation_provenance=True,
    )


__all__ = ["analyze_company"]
