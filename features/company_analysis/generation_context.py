"""기업분석 생성 입력을 **한 곳에서** 만든다 — API 경로와 CLI 경로가 함께 쓴다.

기업분석에는 생성 경로가 둘이다.

    API   app.py → analyze_company()
    CLI   app.py → submit_agent_task() → agent_mode/service.py::prepare_company_analysis_pack()

두 경로가 자료 수집과 컨텍스트 조립을 **각자** 하고 있었고, 그래서 실제로 갈렸다:

- 산출물 계약(분량·근거 인용·서술 요구·웹 조회·검증)을 API 경로에만 붙였더니 CLI로 만든
  보고서에는 하나도 적용되지 않았다. 사용자는 CLI를 쓰고 있었다.
- 자료 수집도 갈려 있었다. API는 회사를 먼저 해석하고 그 회사의 표기들로 검색해 합치는데
  (`search_company_documents`), CLI는 사용자가 친 문자열 하나로 검색했다. 실측으로 같은
  티커에서 **NVDA는 문서 겹침 8/30, AMD는 17/30**이었고, CLI 상위 3건에는 엔비디아 기사가
  하나도 없었다(세레브라스·SanDisk·CoreWeave).

CLAUDE.md는 이 함정을 브리핑 절에서 이미 네 번 경고했다 — "규칙 생성과 Agent 생성 두
경로가 모두 …해야 한다". 경고를 다섯 번째 적는 대신 **조립기를 하나로 만든다.**

경계:
- 여기서는 자료를 모으고 컨텍스트 블록을 만들 뿐, 본문을 생성하지 않는다. 생성은
  경로마다 다르다(API는 함수 호출, CLI는 팩을 써서 외부 프로세스가 실행).
- 웹 조회는 호출이 하나 늘지만 자료가 넉넉하면 부르지 않는다. CLI 경로에서는 잡 워커
  안에서 돌므로 HTTP 요청을 막지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from features.common.company_lookup import infer_requested_company
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.prompt_hints import render_prompt_hints
from features.common.quality_generation.preflight_enrichment import build_preflight_evidence_context
from features.common.quality_generation.quality_targets import render_quality_target_context
from features.common.research_library.indexing.service import load_index
from features.common.research_library.search.service import search_documents
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.common.web_search_scope import load_source_scope, render_scope_instruction
from features.company_analysis import web_lookup as company_web
from features.company_analysis.company_search import search_company_documents
from features.company_analysis.data_gap_resolver import resolve_company_analysis_gaps
from features.company_analysis.depth_policy import build_depth_policy, render_length_contract
from features.company_analysis.engine_calls import configured_lookup_call
from features.company_analysis.report_contract import (
    render_quality_requirements,
    render_source_contract,
)
from features.company_analysis.service import (
    build_company_analysis_charts,
    build_company_analysis_materials,
    company_analysis_sources,
    company_external_search_context,
)
from features.company_analysis.style import normalize_analysis_style


@dataclass(frozen=True, slots=True)
class GenerationInputs:
    """두 경로가 함께 쓰는 생성 입력."""

    company: dict
    docs: list
    materials: dict
    selected: list
    charts: list
    preflight: dict
    depthPolicy: dict
    sourceLedger: list
    dataGaps: dict
    webRow: dict = field(default_factory=dict)
    contextBlocks: list = field(default_factory=list)

    @property
    def context(self) -> str:
        """자료 컨텍스트에 계약 블록을 이어 붙인 전체."""
        return "\n\n".join(block for block in self.contextBlocks if block)

    @property
    def quoteSources(self) -> list:
        return company_web.speaker_sources(self.webRow) if self.webRow else []

    @property
    def webSummary(self) -> dict | None:
        return company_web.lookup_summary(self.webRow) if self.webRow else None

    def resolve_gaps(self, *, web_search_ran: bool) -> dict:
        """최종 데이터 갭. **설정이 아니라 실제로 웹 검색이 돌았는지**로 정한다 —
        설정만 보면 CLI 모드·LLM 실패·자료 없음처럼 검색이 한 번도 돌지 않은 경로에서도
        `official_web_search`가 "시도함"으로 남는다."""
        return resolve_company_analysis_gaps(self.materials, web_search_allowed=bool(web_search_ran))

    def analysis_inputs(self) -> dict:
        return {
            "secFactsOk": bool((self.materials.get("secFacts") or {}).get("ok")),
            "rankedFilingOk": bool((self.materials.get("rankedFiling") or {}).get("ok")),
            "rankedParagraphs": len((self.materials.get("rankedFiling") or {}).get("paragraphs") or []),
        }


def build_generation_inputs(
    query: str,
    *,
    analysis_style: str = "beginner",
    web_search: bool = False,
    runtime: dict | None = None,
) -> GenerationInputs:
    """자료를 모으고 계약 블록까지 붙인 생성 입력을 만든다.

    `runtime`은 테스트가 의존을 갈아끼우는 통로다. 두 경로가 같은 키를 쓴다.
    """
    runtime = runtime or {}
    load_index_fn = runtime.get("load_index", load_index)
    search_documents_fn = runtime.get("search_documents", search_documents)
    infer_company_fn = runtime.get("infer_requested_company", infer_requested_company)
    materials_fn = runtime.get("build_company_analysis_materials", build_company_analysis_materials)
    charts_fn = runtime.get("build_company_analysis_charts", build_company_analysis_charts)
    lookup_call_fn = runtime.get("configured_lookup_call", configured_lookup_call)
    analysis_style = normalize_analysis_style(analysis_style)

    index = load_index_fn()
    # 회사를 먼저 해석하고 **그 회사의 표기들로** 찾는다. 원문 문자열 하나로 찾으면
    # 티커만 아는 회사의 한글·영문 기사가 전부 빠진다(실측: NVDA 겹침 8/30).
    company = infer_company_fn(query, search_documents_fn(index, query=query, company=query, limit=8))
    docs = search_company_documents(index, search_documents_fn, company, query, limit=30)
    materials = materials_fn(query, docs, company)
    selected = materials.get("selectedDocs", [])
    charts = charts_fn(materials)

    preflight = preflight_from_context("company_analysis", {}, {
        "sourceCount": len(selected) or len(docs),
        "documentCount": len(docs),
        "analysisInputs": {
            "secFactsOk": bool((materials.get("secFacts") or {}).get("ok")),
            "rankedFilingOk": bool((materials.get("rankedFiling") or {}).get("ok")),
        },
    })
    depth_policy = build_depth_policy(
        document_count=len(docs),
        sec_facts_ok=bool((materials.get("secFacts") or {}).get("ok")),
        ranked_filing_ok=bool((materials.get("rankedFiling") or {}).get("ok")),
    )
    source_ledger = source_ledger_from_items(
        selected or docs, artifact_type="company_analysis", limit=60,
    )

    # 웹 조회 — 자료 공백은 로컬로 못 메운다. 갭 판정을 먼저 해서 발동 여부를 정한다.
    early_gaps = resolve_company_analysis_gaps(materials, web_search_allowed=False)
    web_row: dict = {}
    if web_search and company_web.needs_web_lookup(document_count=len(docs), data_gaps=early_gaps):
        try:
            web_row = company_web.assign_source_ids(
                company_web.lookup_company(
                    company,
                    render_scope_instruction(load_source_scope(company)),
                    lookup_call_fn(),
                )
            )
        except Exception:  # noqa: BLE001 - 조회 실패가 보고서를 죽이지 않는다
            web_row = {}
    web_items = company_web.web_source_items(web_row) if web_row else []
    if web_items:
        source_ledger = [*source_ledger, *web_items]

    blocks = [
        # 자료가 하나도 없으면 이 키가 없을 수 있다. 없는 것과 빈 것을 가르지 않는다.
        str(materials.get("context") or ""),
        render_quality_target_context(
            "company_analysis",
            preflight=preflight,
            context={"extraRoutes": [
                f"현재 로컬 filings/reports/articles/rss 개수: {materials.get('counts', {})}",
                f"로컬 IR/실적발표 감지 수: {materials.get('localIrEarningsCount', 0)}",
                "공식 숫자가 없으면 웹 검색보다 먼저 dataGap으로 남기고, 웹 검색 사용 시 공식 IR·SEC·DART를 우선한다.",
            ]},
        ),
        build_preflight_evidence_context(
            "company_analysis",
            preflight=preflight,
            artifact={
                "sources": selected,
                "analysisInputs": {
                    "secFactsOk": bool((materials.get("secFacts") or {}).get("ok")),
                    "rankedFilingOk": bool((materials.get("rankedFiling") or {}).get("ok")),
                },
                "dataGaps": [],
            },
        ),
        render_prompt_hints(preflight),
        # 계약은 프롬프트가 아니라 **이 요청의 숫자와 목록**으로 준다.
        render_length_contract(depth_policy),
        render_quality_requirements(),
        render_source_contract(source_ledger),
        company_external_search_context(materials) if web_search else "",
        company_web.render_lookup(web_row) if web_row else "",
    ]
    return GenerationInputs(
        company=company,
        docs=docs,
        materials=materials,
        selected=selected,
        charts=charts,
        preflight=preflight,
        depthPolicy=depth_policy,
        sourceLedger=source_ledger,
        dataGaps=early_gaps,
        webRow=web_row,
        contextBlocks=[block for block in blocks if block],
    )


def draft_artifact(inputs: GenerationInputs, query: str, *, analysis_style: str, data_gaps: dict | None = None) -> dict:
    """두 경로가 공유하는 보고서 뼈대. 어느 쪽이든 같은 필드를 갖는다."""
    company = inputs.materials.get("company") or inputs.company
    gaps = inputs.dataGaps if data_gaps is None else data_gaps
    return {
        "saved": False,
        "query": query,
        "company": company,
        "documentCount": len(inputs.docs),
        "analysisStyle": normalize_analysis_style(analysis_style),
        "dataGaps": gaps,
        "resolutionAttempts": gaps.get("gaps", []),
        "analysisCharts": inputs.charts,
        "analysisInputs": inputs.analysis_inputs(),
        "sources": company_analysis_sources(inputs.materials, inputs.selected[:14]),
        "depthPolicy": inputs.depthPolicy,
        "sourceLedger": inputs.sourceLedger,
        "webLookup": inputs.webSummary,
    }


__all__ = ["GenerationInputs", "build_generation_inputs", "draft_artifact"]
