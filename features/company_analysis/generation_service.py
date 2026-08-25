"""Company analysis generation orchestration kept out of app.py."""
from __future__ import annotations

from features.common.change_intelligence.service import decorate_candidate
from features.common.company_lookup import infer_requested_company
from features.common.quality_generation.preflight import preflight_from_context
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.company_analysis.depth_policy import build_depth_policy
from features.company_analysis.report_contract import validate_company_report
from features.common.web_search_scope import audit_urls, load_source_scope
from features.common.research_library.indexing.service import load_index
from features.common.research_library.search.service import search_documents
from features.common.utils import now_iso
from features.company_analysis.company_search import search_company_documents
from features.company_analysis.data_gap_resolver import resolve_company_analysis_gaps
from features.company_analysis.report_rules import build_rule_report
from features.company_analysis.service import (
    DATA_DIR,
    analysis_status_message,
    build_company_analysis_charts,
    build_company_analysis_materials,
    company_analysis_sources,
    generate_llm_company_analysis,
    read_company_analysis_prompt,
)
from features.company_analysis.style import analysis_prompt_path, normalize_analysis_style
from features.llm_settings.client import selected_llm_config


def analyze_company(query, web_search_override=None, llm_override=None, analysis_style="beginner", *, runtime: dict | None = None):
    runtime = runtime or {}
    load_index_fn = runtime.get("load_index", load_index)
    search_documents_fn = runtime.get("search_documents", search_documents)
    infer_company_fn = runtime.get("infer_requested_company", infer_requested_company)
    materials_fn = runtime.get("build_company_analysis_materials", build_company_analysis_materials)
    charts_fn = runtime.get("build_company_analysis_charts", build_company_analysis_charts)
    llm_fn = runtime.get("generate_llm_company_analysis", generate_llm_company_analysis)
    rule_fn = runtime.get("build_rule_report", build_rule_report)
    sources_fn = runtime.get("company_analysis_sources", company_analysis_sources)
    llm_config_fn = runtime.get("selected_llm_config", selected_llm_config)
    analysis_style = normalize_analysis_style(analysis_style)
    index = load_index_fn()
    # 회사를 먼저 해석하고 그 회사의 표기들로 찾는다. 원문 문자열 하나로 찾으면
    # 티커만 아는 회사의 한글·영문 기사가 전부 빠진다.
    company = infer_company_fn(query, search_documents_fn(index, query=query, company=query, limit=8))
    docs = search_company_documents(index, search_documents_fn, company, query, limit=30)
    materials = materials_fn(query, docs, company)
    selected = materials.get("selectedDocs", [])
    tags = [tag for doc in selected for tag in doc.get("impactTags", [])]
    top_tags = sorted(set(tags), key=tags.count, reverse=True)[:6]
    recent = " ".join(doc.get("summary", "") for doc in selected[:5]) or "선별된 보조 뉴스/리포트 자료가 없습니다."
    charts = charts_fn(materials)
    preflight = preflight_from_context("company_analysis", {}, {
        "sourceCount": len(selected) or len(docs), "documentCount": len(docs),
        "analysisInputs": {
            "secFactsOk": bool(materials.get("secFacts", {}).get("ok")),
            "rankedFilingOk": bool(materials.get("rankedFiling", {}).get("ok")),
        },
    })
    # 분량과 근거 인용은 계약이다. 지금까지는 프롬프트에만 있고 산출물을 아무도 확인하지
    # 않아, 섹션이 통째로 빠지고(실측 4건 중 3건) 근거 태그가 0개였다.
    sec_facts_ok = bool(materials.get("secFacts", {}).get("ok"))
    ranked_filing_ok = bool(materials.get("rankedFiling", {}).get("ok"))
    depth_policy = build_depth_policy(
        document_count=len(docs), sec_facts_ok=sec_facts_ok, ranked_filing_ok=ranked_filing_ok,
    )
    source_ledger = source_ledger_from_items(
        selected or docs, artifact_type="company_analysis", limit=60,
    )
    llm_result, llm_status = llm_fn(
        query, docs, web_search_override=web_search_override, llm_override=llm_override,
        materials=materials, quality_preflight=preflight, analysis_style=analysis_style,
        depth_policy=depth_policy, source_ledger=source_ledger,
    )
    # 설정이 아니라 실제 결과로 기록한다. 설정만 보면 CLI 모드·LLM 실패·자료 없음처럼
    # 웹 검색이 한 번도 돌지 않은 경로에서도 official_web_search가 "시도함"으로 남는다.
    gaps = resolve_company_analysis_gaps(
        materials, web_search_allowed=bool(llm_result and llm_result.get("webSearch"))
    )
    common = {
        "saved": False, "generatedAt": now_iso(), "query": query, "company": company,
        "documentCount": len(docs), "analysisStyle": analysis_style, "dataGaps": gaps,
        "resolutionAttempts": gaps.get("gaps", []), "analysisCharts": charts,
        "analysisInputs": {
            "secFactsOk": bool(materials.get("secFacts", {}).get("ok")),
            "rankedFilingOk": bool(materials.get("rankedFiling", {}).get("ok")),
            "rankedParagraphs": len(materials.get("rankedFiling", {}).get("paragraphs", [])),
        },
        "qualityPreflight": preflight,
        "depthPolicy": depth_policy,
        "sourceLedger": source_ledger,
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
            "sources": sources_fn(materials, llm_result.get("usedDocs", [])[:14]),
            # 프롬프트로 부탁한 것과 실제로 지킨 것은 다르다. 무엇이 목록 밖이었는지
            # 남겨야 다음에 목록을 고칠 수 있다.
            "webSearchAudit": audit_urls(llm_result.get("markdown", ""), load_source_scope(company)),
        }
    else:
        generation = {"mode": "rules", "status": llm_status, "provider": llm_config_fn().get("provider", ""), "model": "", "sourceCount": 0}
        generation["message"] = analysis_status_message(generation)
        report = {
            **common, "headline": f"{company['name']} 규칙 기반 기업 분석",
            "markdown": rule_fn(materials, analysis_style=analysis_style), "generation": generation,
            "sources": sources_fn(materials, materials.get("selectedDocs", docs[:10])[:14]),
        }
        report["analysisInputs"].update({"topTags": top_tags, "recent": recent})
    # 프롬프트로 부탁한 계약을 산출물에서 확인한다. 어느 결함도 보고서를 되돌리지
    # 않는다 — 기업분석에는 후보·재시도 구조가 없어 차단하면 사용자가 아무것도 받지
    # 못한다. 점수 상한과 보수 대상 지정으로만 쓴다.
    report["contractValidation"] = validate_company_report(
        str(report.get("markdown") or ""),
        depth_policy=depth_policy,
        source_ledger=source_ledger,
    )
    return decorate_candidate(
        "company_analysis", report, data_dir=DATA_DIR,
        native_context={"materials": materials}, generation_provenance=True,
    )
