"""Topic report generation: market data + memory + docs → LLM report."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from features.common.utils import kst_date, now_iso
from features.common.canonical_identity import (
    CanonicalIdentityError,
    CanonicalNotFoundError,
    ReportKind,
    resolve_exact_report_path,
)
from features.common.canonical_report_state import load_report
from features.common.canonical_report_types import WriteKind
from features.common.canonical_reports import commit_sync, prepare
from features.common.change_intelligence.service import decorate_candidate, project_committed_report
from features.common.market_data.tape import build_market_tape
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.common.research_schema.data_gaps import data_gaps_from_messages
from features.common.research_schema.evidence import evidence_items_from_list
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.preflight_enrichment import build_preflight_evidence_context
from features.common.quality_generation.prompt_hints import render_prompt_hints
from features.common.quality_generation.quality_targets import render_quality_target_context
from features.common.quality_generation.telemetry import normalize_token_usage
from features.llm_settings.client import (
    LlmRequestError,
    request_llm_text,
    selected_llm_config,
    strip_llm_citation_markers,
    use_llm_analysis,
    use_web_search_for_analysis,
)
from features.topic_report.data_fetcher import fetch_topic_market_data, market_data_to_markdown
from features.topic_report.evaluation import evaluate_report
from features.topic_report.evidence import build_evidence_pack, evidence_pack_summary
from features.topic_report.axis_analysis import render_axis_briefs
from features.topic_report.thesis import render_thesis
from features.topic_report.evidence_text import select_bodies
from features.topic_report.macro_data import fetch_macro_data, macro_data_to_markdown, resolve_fred_series
from features.topic_report.planner import apply_deep_research_plan, build_topic_plan
from features.topic_report.source_ledger import build_source_ledger
from features.topic_report.templates import compose_prompt
from features.topic_report.topic_config import PRESET_TOPICS, get_topic_config
from features.topic_report.topic_schema import body_sections
from features.topic_report.report_rules import build_rule_report
from features.common.generation_engine import engine_detail, engine_label
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = data_dir()
REPORTS_DIR = DATA_DIR / "topic-reports"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"
FEATURES_DIR = ROOT / "features"
PROMPT_PATH = FEATURES_DIR / "topic_report" / "prompt.md"


def _read_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def _search_docs(query_keywords: list[str], limit: int = 12) -> list[dict]:
    """Search research-inbox for topic-relevant documents (RSS + articles first).

    질의는 이어 붙이지 않고 하나씩 검색해 RRF로 합친다. 이어 붙이면 FTS5가 토큰을
    OR로 풀어 어느 한 단어만 스친 문서가 상위로 온다. 보도자료는 근거에서 뺀다.
    """
    try:
        from features.common.research_library.indexing.service import load_index
        from features.common.research_library.search.filters import drop_press_releases
        from features.common.research_library.search.multi_query import fuse_search_results
        from features.common.research_library.search.service import search_documents
        index = load_index()
        queries = [str(q).strip() for q in (query_keywords or [])[:6] if str(q).strip()]
        if not queries:
            return []

        def run_one(query: str, per_query_limit: int) -> list[dict]:
            docs = search_documents(index, query=query, limit=per_query_limit, scope="news")
            if len(docs) < 5:
                docs = docs + search_documents(index, query=query, limit=per_query_limit, scope="all")
            return drop_press_releases(docs)

        return fuse_search_results(queries, run_one, limit=limit, per_query_limit=max(limit, 12))
    except Exception:
        return []


def _search_memories(keywords: list[str], limit: int = 20) -> list[dict]:
    """Fetch market memory entries relevant to the topic, grouped by story family."""
    try:
        from features.market_memory.memory import list_memory
        all_memories = list_memory(MARKET_MEMORY_DB_PATH, limit=100)
        if not keywords:
            return all_memories[:limit]
        kws = [k.lower() for k in keywords]
        scored = []
        for mem in all_memories:
            hay = " ".join([
                mem.get("title", ""),
                mem.get("summary", ""),
                mem.get("storyThesis", ""),
                mem.get("story", ""),
                mem.get("storyFamily", ""),
                " ".join(mem.get("tags", [])),
            ]).lower()
            score = sum(1 for k in kws if k in hay)
            if score > 0:
                scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Pick top 3 per story family for diversity, then fill remaining slots
        seen_families: dict[str, int] = {}
        primary: list[dict] = []
        overflow: list[dict] = []
        for _, mem in scored:
            family = mem.get("storyFamily") or mem.get("story") or "__ungrouped__"
            count = seen_families.get(family, 0)
            if count < 3:
                primary.append(mem)
                seen_families[family] = count + 1
            else:
                overflow.append(mem)
        combined = primary + overflow
        return combined[:limit]
    except Exception:
        return []


def _build_llm_context(
    topic: dict,
    market_data: dict,
    macro_data: dict,
    docs: list,
    memories: list,
    user_context: str,
    date: str,
    data_gaps: list | None = None,
    topic_plan: dict | None = None,
    axis_briefs: list | None = None,
    thesis: dict | None = None,
) -> str:
    axes = topic.get("theme_axes") or topic.get("report_sections", [])
    body_headings = body_sections((topic_plan or {}).get("expectedSections") or [])
    asked = str((topic_plan or {}).get("topic") or "").strip()
    research_questions = [str(q).strip() for q in ((topic_plan or {}).get("researchQuestions") or []) if str(q).strip()]
    lines = []
    if asked:
        # 사용자가 실제로 친 질문. 40자로 줄인 주제어가 제목·검색을 지배하는 동안 원문은
        # 컨텍스트 한 줄로 밀려 있었고, 보고서가 질문의 절반(정책이 겪는 어려움)과
        # 사례 하나(2021~2022)를 통째로 빠뜨렸다(실측: 본문에 '2021' 0회).
        lines += [
            "=" * 60,
            "## 이 보고서가 반드시 답해야 할 질문 (사용자 원문)",
            asked,
            "",
            "- 이 질문의 **모든 부분**에 답해야 한다. 사용자가 든 사례·구간은 각각 본문에서 다룬다.",
            "- 질문에 없는 주제로 옮겨 가지 마라. 더 흥미로운 주제가 보여도 질문이 우선이다.",
            "- 결론은 이 질문에 **사용자가 쓴 말로** 답한다.",
            "",
        ]
        if research_questions:
            lines += [
                "이 질문을 나눈 하위 질문 (본문에서 모두 답할 것):",
                *[f"- {question}" for question in research_questions],
                "",
            ]
    lines += [
        f"보고서 주제: {topic['label']} ({topic.get('description', '')})",
        f"보고서 날짜: {date}",
        "",
        "[분석 축] — 이 보고서가 답해야 할 것들:",
        *[f"- {s}" for s in axes],
        "",
    ]
    if body_headings:
        # 본문 섹션은 계획이 정한다. 모델이 제목을 바꾸면 검증이 결함으로 잡으므로
        # 여기서 정확한 문구를 준다.
        lines += [
            "[본문 섹션] — 아래 제목을 그대로, 순서대로 `##` 헤더로 쓰고 각각 그 질문에 답하세요:",
            *[f"- {heading}" for heading in body_headings],
            "",
        ]

    if user_context and user_context.strip():
        lines += [
            "=" * 60,
            "## 사용자 추가 컨텍스트 (관심 방향 — 사실/근거 아님)",
            "아래 내용은 사용자의 질문 의도와 관심 방향을 이해하기 위한 자료입니다.",
            "사용자 전제를 사실로 간주하지 말고, 외부 자료와 충돌하면 충돌을 명시하며, 반대 근거도 함께 제시하세요.",
            user_context.strip(),
            "",
        ]

    lines += [
        "=" * 60,
        "## 시장 데이터 (yfinance)",
        market_data_to_markdown(market_data),
        "",
    ]

    if macro_data.get("ok"):
        lines += [
            "=" * 60,
            "## 경제 지표 (FRED + BOK ECOS)",
            macro_data_to_markdown(macro_data),
            "",
        ]

    if memories:
        lines += [
            "=" * 60,
            f"## 관련 시장 흐름 기록 ({len(memories)}건)",
            "아래는 이 주제와 관련해 과거에 기록된 시장 흐름 메모입니다. 현재 상황과 연결해서 설명하세요.",
            "",
        ]
        for mem in memories:
            bias = mem.get("stateBias") or mem.get("bias", "")
            importance = mem.get("importance", "")
            lines.append(
                f"- [{mem.get('date', '')}] **{mem.get('title', '')}** "
                f"| 방향={bias} 중요도={importance}\n"
                f"  주요 판단: {mem.get('storyThesis', '') or mem.get('summary', '')}"
            )
        lines.append("")

    if docs:
        # 저장된 기사 본문을 관련도 상위부터 예산 안에서 함께 싣는다. 스니펫 400자만
        # 보내던 시절 모델이 받은 것은 보유 본문의 13%였다.
        bodies = select_bodies(list(docs))
        lines += [
            "=" * 60,
            f"## 관련 뉴스·자료 ({len(docs)}건, RSS + research-inbox)",
            "아래 자료에 없는 수치나 사실은 추정임을 명시하세요.",
            "관련도 상위 자료에는 저장된 기사 본문을 함께 실었습니다. 본문 앞에 사이트 메뉴 같은"
            " 군더더기가 섞일 수 있으니 기사 내용만 사용하세요.",
            "",
        ]
        for i, d in enumerate(docs, 1):
            title = str(d.get("title", ""))[:200]
            source = d.get("source", "")
            date_d = d.get("date", "")
            summary = str(d.get("summary") or d.get("searchSnippet") or d.get("content") or "")[:500]
            url = d.get("url", "")
            role = d.get("evidenceRole", "")
            axis = d.get("axisKey", "")
            evidence_id = str(d.get("id") or f"item_{i}")
            meta = f"[{evidence_id}] {source} | {date_d}"
            if role:
                meta += f" | 역할={role}"
            if axis:
                meta += f" | 분석축={axis}"
            block = (
                f"{meta}\n"
                f"제목: {title}\n"
                f"요약: {summary}\n"
                f"URL: {url or '(local)'}\n"
            )
            body = bodies.get(evidence_id, "")
            if body:
                block += f"본문: {body}\n"
            lines.append(block)
    else:
        lines += [
            "=" * 60,
            "## 관련 뉴스·자료",
            "로컬 자료에서 관련 문서를 찾지 못했습니다. 시장 데이터와 내러티브만으로 분석하세요.",
            "",
        ]

    if data_gaps:
        lines += [
            "=" * 60,
            "## 데이터 부족 가능성 (보고서의 '데이터 한계'에 반영할 것)",
            *[f"- {gap}" for gap in data_gaps[:8]],
            "",
        ]

    deep = (topic_plan or {}).get("deepResearch") or {}
    if deep.get("enabled"):
        lines += [
            "=" * 60,
            "## 딥 리서치 모드",
            f"- 리서치 라운드 상한: {deep.get('maxRounds', 2)}회",
            "- 아래 하위 질문별 커버리지와 남은 갭을 보고서의 '심층 리서치 커버리지' 또는 Source & Data Notes에 반영하세요.",
        ]
        for question in (deep.get("subQuestions") or [])[:12]:
            lines.append(f"- R{question.get('round', 1)} · {question.get('question', '')}")
        lines += [
            "- 위 하위 질문들은 본문 섹션 안에서 **답해져야** 합니다. 커버리지만 적고 넘어가지 마세요.",
            "- 산출물에는 시나리오(기본/우호/악화), 반대 논지, 반증 조건, 정량 근거표를 포함하세요.",
            "",
        ]

    brief_block = render_axis_briefs(axis_briefs or [])
    if brief_block:
        lines.append(brief_block)

    # 논지는 축 블록 뒤다. 재료보다 프레임이 뒤에 와야 프레임이 이긴다.
    thesis_block = render_thesis(thesis or {})
    if thesis_block:
        lines.append(thesis_block)

    return "\n".join(lines)


REQUIRED_TAIL_SECTIONS = (
    "앞으로 확인할 체크포인트",
    "결론",
    "Source & Data Notes",
)


def _has_markdown_heading(markdown: str, title: str) -> bool:
    return bool(re.search(rf"(?im)^##\s+(?:\d+\.\s*)?{re.escape(title)}\s*$", str(markdown or "")))


def _topic_report_has_complete_tail(markdown: str) -> bool:
    text = str(markdown or "")
    if not all(_has_markdown_heading(text, section) for section in REQUIRED_TAIL_SECTIONS):
        return False
    matches = list(re.finditer(r"(?im)^##\s+(?:\d+\.\s*)?Source & Data Notes\s*$", text))
    if not matches:
        return False
    tail = matches[-1].start()
    return len(text[tail:].strip()) >= 40


def _topic_report_looks_cut(markdown: str) -> bool:
    text = str(markdown or "").strip()
    if not text:
        return True
    if not _topic_report_has_complete_tail(text):
        return True
    # A trailing partial table row, bullet, or sentence is a common symptom of
    # provider-side output truncation.
    last = text.splitlines()[-1].strip()
    if re.match(r"^[-*]\s*$", last):
        return True
    if last.count("|") in {1, 2} and not last.endswith("|"):
        return True
    return False


def _continuation_context(topic: dict, date: str, markdown: str) -> str:
    tail = str(markdown or "")[-5000:]
    return "\n\n".join([
        f"보고서 주제: {topic.get('label', '')}",
        f"보고서 날짜: {date}",
        "아래 보고서는 모델 출력 길이 제한 때문에 후반부가 누락되었거나 중간에서 끊겼을 수 있습니다.",
        "기존 내용을 반복하지 말고, 끊긴 지점부터 이어서 작성하세요.",
        "반드시 남은 섹션을 완성하세요: 9. 앞으로 확인할 체크포인트, 10. 결론, 11. Source & Data Notes.",
        "최종 답변에는 이어지는 Markdown 본문만 출력하세요.",
        "",
        "## 기존 보고서 마지막 부분",
        tail,
    ])


def _append_topic_report_continuation(markdown: str, continuation: str) -> str:
    base = str(markdown or "").rstrip()
    extra = strip_llm_citation_markers(str(continuation or "")).strip()
    if not extra:
        return base
    extra = re.sub(r"^#\s+.+?\n+", "", extra, count=1).strip()
    return f"{base}\n\n{extra}".strip()


def generate_topic_report(
    topic_key: str,
    custom_label: str = "",
    user_context: str = "",
    web_search_override=None,
    llm_override=None,
    date: str = "",
    use_planner: bool = True,
    custom_tickers: dict | None = None,
    quality_mode: str = "diagnose_only",
    deep_research: bool = False,
) -> dict:
    date = date or kst_date()
    topic = get_topic_config(topic_key, custom_label=custom_label or None, custom_tickers=custom_tickers)

    # 0. Topic Plan (v2) — custom 주제는 planner가 검색어/축/티커를 만든다.
    #    프리셋은 기존 설정 기반 plan(backward compatible)을 그대로 쓴다.
    topic_plan = None
    if use_planner:
        try:
            topic_plan = build_topic_plan(
                topic_key,
                custom_label=custom_label,
                user_context=user_context,
                llm_override=llm_override,
                preset_config=topic if topic_key != "custom" else None,
            )
        except Exception:
            topic_plan = None
    if deep_research and not topic_plan:
        try:
            topic_plan = build_topic_plan(
                topic_key,
                custom_label=custom_label,
                user_context=user_context,
                llm_override=False,
                preset_config=topic if topic_key != "custom" else None,
            )
        except Exception:
            topic_plan = None
    if topic_plan and topic_key == "custom":
        # 기존 label.split() 검색을 planner 산출물로 대체 (설계 04 §7.1)
        if topic_plan.get("searchQueries"):
            topic["search_keywords"] = topic_plan["searchQueries"]
        if topic_plan.get("memoryQueries"):
            topic["memory_keywords"] = topic_plan["memoryQueries"]
        if topic_plan.get("analysisAxes"):
            topic["theme_axes"] = [axis["label"] for axis in topic_plan["analysisAxes"]]
        if topic_plan.get("reportType"):
            topic["report_type"] = topic_plan["reportType"]
        # 계획이 요청한 거시 시리즈를 실제로 조회한다 (허용 목록으로 거른 뒤).
        topic["fred_series"] = resolve_fred_series(
            topic_plan.get("requiredMacroData"),
            fallback=topic.get("fred_series"),
        )
        # 명시 customTickers가 없을 때만 planner 후보 티커로 기본 티커를 보강
        if not custom_tickers and topic_plan.get("candidateTickers"):
            merged = dict(topic_plan["candidateTickers"])
            for ticker, name in topic["tickers"].items():
                if ticker not in merged and len(merged) < 12:
                    merged[ticker] = name
            topic["tickers"] = merged
    if topic_plan and deep_research:
        topic_plan = apply_deep_research_plan(topic_plan)

    # 1. Fetch enriched market data
    market_data = fetch_topic_market_data(topic["tickers"], history_period=topic.get("history_period", "1y"))

    # 2. Fetch structured economic data (FRED + BOK)
    from features.llm_settings.client import fred_api_key, bok_api_key
    macro_data = fetch_macro_data(
        fred_series=topic.get("fred_series", []),
        bok_series=topic.get("bok_series", []),
        fred_key=fred_api_key(),
        bok_key=bok_api_key(),
    )

    # 3~4. Evidence Pack — 축별 검색으로 근거 구조화 (plan 없으면 기존 검색 경로)
    evidence_pack = None
    source_ledger = []
    if topic_plan:
        evidence_pack = build_evidence_pack(
            topic_plan,
            search_docs=lambda queries, limit=12: _search_docs(list(queries), limit=limit),
            search_memories=lambda keywords, limit=20: _search_memories(list(keywords), limit=limit),
            date=date,
            deep_research=deep_research,
        )
        docs = evidence_pack["items"]
        memories = evidence_pack["marketMemory"]
        source_ledger = build_source_ledger(docs)
    else:
        docs = _search_docs(topic["search_keywords"])
        memories = _search_memories(topic["memory_keywords"])

    quality_preflight = preflight_from_context("topic_report", {}, {
        "artifactId": f"{date}:{topic['key']}",
        "sourceCount": len(docs),
        "sourceLedger": source_ledger,
        "evidenceItems": docs,
        "dataGaps": (evidence_pack or {}).get("dataGaps") or [],
    })

    # 4. LLM generation — 공통 prompt + report_type별 지침 결합 (Phase 3)
    cfg = selected_llm_config()
    prompt = _read_prompt()
    report_type = (topic_plan or {}).get("reportType") or topic.get("report_type", "")
    if prompt:
        prompt = compose_prompt(prompt, report_type)
    generation = {"mode": "rules", "provider": cfg.get("provider", ""), "model": "", "webSearch": False, "message": ""}

    llm_on = use_llm_analysis() if llm_override is None else bool(llm_override)
    markdown = None
    if llm_on and cfg.get("apiKey") and prompt:
        context = _build_llm_context(
            topic, market_data, macro_data, docs, memories, user_context, date,
            data_gaps=evidence_pack["dataGaps"] if evidence_pack else None,
            topic_plan=topic_plan,
        )
        target_block = render_quality_target_context(
                "topic_report",
                preflight=quality_preflight,
                context={"extraRoutes": [
                    "Evidence Pack의 analysisAxes별 빈 축은 dataGap으로 처리하고 본문에서 한계로 명시한다.",
                    "marketData/FRED/BOK가 없으면 해당 수치를 만들지 말고 Source & Data Notes에 남긴다.",
                    "deepResearch가 켜져 있으면 하위 질문 커버리지·반증 조건·정량 근거표를 반드시 포함한다.",
                ]},
            )
        context = "\n\n".join([context, target_block])
        context = "\n\n".join([
            context,
            build_preflight_evidence_context(
                "topic_report",
                preflight=quality_preflight,
                artifact={
                    "sourceLedger": source_ledger,
                    "evidenceItems": docs,
                    "dataGaps": (evidence_pack or {}).get("dataGaps") or [],
                },
            ),
        ])
        hint_block = render_prompt_hints(quality_preflight)
        if hint_block:
            context = "\n\n".join([context, hint_block])

        use_web = use_web_search_for_analysis() if web_search_override is None else bool(web_search_override)

        # Web search only as supplement — try local first
        try:
            max_tokens = int(os.environ.get("TOPIC_REPORT_MAX_OUTPUT_TOKENS", "9000"))
            text, response_id, usage = request_llm_text(
                cfg, prompt, context,
                web_search=use_web,
                max_output_tokens=max_tokens,
                include_usage=True,
            )
            if text:
                markdown = strip_llm_citation_markers(text)
                continuation_count = 0
                continuation_usage = {}
                if _topic_report_looks_cut(markdown):
                    try:
                        cont_context = _continuation_context(topic, date, markdown)
                        cont_text, _cont_response_id, continuation_usage = request_llm_text(
                            cfg,
                            prompt,
                            cont_context,
                            web_search=False,
                            max_output_tokens=int(os.environ.get("TOPIC_REPORT_CONTINUATION_TOKENS", "5000")),
                            include_usage=True,
                        )
                        if cont_text:
                            markdown = _append_topic_report_continuation(markdown, cont_text)
                            continuation_count = 1
                    except Exception:
                        continuation_count = 0
                generation = {
                    "mode": "llm",
                    "provider": cfg["provider"],
                    "model": cfg["model"],
                    "responseId": response_id,
                    "webSearch": use_web,
                    "continued": continuation_count,
                    "mayBeTruncated": bool(_topic_report_looks_cut(markdown)),
                    "message": _llm_status_message(cfg["provider"], cfg["model"], use_web),
                    "tokenUsage": normalize_token_usage(usage, prompt=prompt, context=context, output=markdown, max_output_tokens=max_tokens),
                }
                if continuation_usage:
                    generation["continuationTokenUsage"] = normalize_token_usage(
                        continuation_usage,
                        prompt=prompt,
                        context=locals().get("cont_context", ""),
                        output=locals().get("cont_text", ""),
                        max_output_tokens=int(os.environ.get("TOPIC_REPORT_CONTINUATION_TOKENS", "5000")),
                    )
                if generation["mayBeTruncated"]:
                    generation["message"] += " · 후반 섹션이 일부 누락됐을 수 있습니다."
        except LlmRequestError:
            generation["message"] = f"{cfg.get('provider', '')} LLM 호출 실패로 규칙 기반 보고서로 대체했습니다."
        except Exception:
            generation["message"] = "LLM 호출에 실패했습니다."
    elif not cfg.get("apiKey"):
        generation["message"] = f"{cfg.get('provider', '')} API 키가 없어 규칙 기반 보고서를 생성했습니다."
    elif not llm_on:
        generation["message"] = "LLM이 꺼져 있어 규칙 기반 보고서를 생성했습니다."

    # Fallback to rule-based
    if not markdown:
        markdown = build_rule_report(
            topic, market_data, macro_data, docs, memories, user_context,
            topic_plan=topic_plan,
            data_gaps=evidence_pack["dataGaps"] if evidence_pack else None,
            as_of=date,
        )
        if not generation["message"]:
            generation["message"] = "규칙 기반 보고서를 생성했습니다."
        generation["mode"] = "rules"

    # 5. Quality Gate (Phase 4) — 생성된 보고서를 규칙 기반으로 자동 평가
    evidence_summary = evidence_pack_summary(evidence_pack) if evidence_pack else None
    data_gaps = data_gaps_from_messages(
        (evidence_pack or {}).get("dataGaps") or [],
        artifact_type="topic_report",
        category="evidence",
        source_section="Evidence Pack",
    )
    evidence_items = evidence_items_from_list(docs, artifact_type="topic_report", default_type="news")
    source_ledger = source_ledger_from_items(source_ledger or docs, artifact_type="topic_report")
    checkpoints = checkpoints_from_markdown(
        markdown,
        artifact_type="topic_report",
        scope="market",
        topic=topic["label"],
        headings=["앞으로 확인할 체크포인트", "체크포인트", "다음 체크포인트"],
    )
    if not checkpoints and not any(g.get("category") == "checkpoint" for g in data_gaps):
        data_gaps.append({
            "id": "gap_topic_report_checkpoints",
            "artifactType": "topic_report",
            "artifactId": "",
            "category": "checkpoint",
            "message": "보고서에서 구조화 가능한 체크포인트 섹션을 찾지 못했습니다.",
            "severity": "low",
            "suggestedAction": "보고서를 재생성하거나 '앞으로 확인할 체크포인트' 섹션을 bullet 목록으로 작성하세요.",
            "sourceSection": "markdown extractor",
        })
    market_tape = build_market_tape(date=date, topic_market_data=market_data)
    quality = evaluate_report(
        markdown,
        evidence_summary=evidence_summary,
        topic_plan=topic_plan,
        user_context_present=bool(user_context and user_context.strip()),
        checkpoints=checkpoints,
        source_ledger=source_ledger,
        evidence_items=evidence_items,
        data_gaps=data_gaps,
        market_tape=market_tape,
        artifact_type="topic_report",
    )

    return {
        "saved": False,
        "generatedAt": now_iso(),
        "date": date,
        "topicKey": topic["key"],
        "topicLabel": topic["label"],
        "title": f"{topic['label']} 분석 리포트 — {date}",
        "markdown": markdown,
        "topicPlan": topic_plan,
        "evidencePackSummary": evidence_summary,
        "evidenceItems": evidence_items,
        "sourceLedger": source_ledger,
        "checkpoints": checkpoints,
        "dataGaps": data_gaps,
        "marketTape": market_tape,
        "quality": quality,
        "qualityPreflight": quality_preflight,
        "generation": generation,
        "deepResearch": bool(deep_research),
        "marketData": market_data,
        "macroAvailable": macro_data.get("ok", False),
        "sources": _doc_sources(docs),
        "memoryCount": len(memories),
        "docCount": len(docs),
        "userContext": bool(user_context and user_context.strip()),
        "personalOverlay": None,
    }


def _llm_status_message(provider: str, model: str, web_search: bool) -> str:
    suffix = " · 웹 검색 보완 사용" if web_search else " · 로컬 자료(RSS+내러티브) 기반"
    return f"LLM 보고서 생성 완료: {provider} / {model}{suffix}"


def _doc_sources(docs: list) -> list:
    seen = set()
    rows = []
    for d in docs:
        key = d.get("url") or d.get("path") or d.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append({
            "title": d.get("title", ""),
            "source": d.get("source", ""),
            "date": d.get("date", ""),
            "url": d.get("url", ""),
            "type": d.get("type", ""),
        })
    return rows[:14]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def _stable_topic_id(date: str, topic_key: str, label: str, *, discriminator: str = "") -> str:
    # (날짜, 주제 키, 라벨) 기준 안정적 id — 같은 주제를 같은 날 재생성하면 최신본으로
    # 덮어써서 자동 저장이 파일을 무한정 쌓지 않게 한다.
    # 라벨은 `topic_subject()`가 40자로 끊은 주제어라 같은 주제로 시작하는 다른 질문이
    # 같은 라벨이 된다. 승인 경로는 planHash를 판별자로 넘겨 서로 덮어쓰지 않게 한다.
    # 판별자가 없으면 예전 키와 같은 문자열이라 기존 저장 파일의 id가 그대로 재현된다.
    parts = f"{date}:{topic_key}:{label}"
    if discriminator:
        parts = f"{parts}:{discriminator}"
    key = parts.encode("utf-8")
    return hashlib.sha256(key).hexdigest()[:8]


def save_topic_report(report: dict) -> dict:
    date = report.get("date", kst_date())
    topic_key = re.sub(r"[^a-z0-9_]", "_", report.get("topicKey", "report"))
    report_id = report.get("id") or _stable_topic_id(date, topic_key, report.get("topicLabel", ""))
    filename = f"{date}_{topic_key}_{report_id}.json"
    saved = {**report, "id": report_id, "saved": True, "filename": filename}
    for field_name in ("checkpoints", "dataGaps", "sourceLedger", "evidenceItems"):
        for item in saved.get(field_name) or []:
            if isinstance(item, dict) and not item.get("artifactId"):
                item["artifactId"] = report_id
    path = _reports_dir() / filename
    saved = decorate_candidate("topic_report", saved, data_dir=DATA_DIR, generation_provenance=True)
    prepared = prepare(
        report_kind=ReportKind.TOPIC_REPORT,
        exact_path=path,
        write_kind=WriteKind.CANONICAL,
        candidate=saved,
    )
    commit_sync(prepared)
    projection = project_committed_report(MARKET_MEMORY_DB_PATH, path)
    committed = load_report(path)
    if committed is None:
        raise RuntimeError("canonical topic report commit did not persist the report")
    committed["changeIntelligence"] = {**(committed.get("changeIntelligence") or {}), "projectionStatus": projection.get("status"), "invalidationToken": projection.get("invalidationToken") or (committed.get("changeIntelligence") or {}).get("invalidationToken")}
    return committed


def list_topic_reports() -> list:
    try:
        rows = []
        for p in sorted(_reports_dir().glob("*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                rows.append({
                    "id": data.get("id", p.stem),
                    "filename": p.name,
                    "date": data.get("date", ""),
                    "topicKey": data.get("topicKey", ""),
                    "topicLabel": data.get("topicLabel", ""),
                    "title": data.get("title", ""),
                    "generatedAt": data.get("generatedAt", ""),
                    "mode": data.get("generation", {}).get("mode", ""),
                    "engine": engine_label(data.get("generation")),
                    "engineDetail": engine_detail(data.get("generation")),
                })
            except Exception:
                continue
        return rows
    except Exception:
        return []


def _find_report_path(report_id: str) -> Path | None:
    try:
        return resolve_exact_report_path(REPORTS_DIR.parent, ReportKind.TOPIC_REPORT, report_id)
    except CanonicalNotFoundError:
        return None
    except CanonicalIdentityError as exc:
        raise ValueError("topic report identifier is invalid") from exc


def get_topic_report(report_id: str) -> dict | None:
    path = _find_report_path(report_id)
    if not path:
        return None
    try:
        return load_report(path)
    except Exception:
        return None


def delete_topic_report(report_id: str) -> dict:
    from features.agent_mode.report_delete import DeleteRequest, execute_report_delete
    from features.common.canonical_reports import (
        CanonicalIdentityError,
        CanonicalNotFoundError,
        ReportKind,
        resolve_exact_report_path,
    )

    try:
        path = resolve_exact_report_path(REPORTS_DIR.parent, ReportKind.TOPIC_REPORT, report_id)
    except CanonicalNotFoundError:
        return {"deleted": False, "id": report_id}
    except CanonicalIdentityError as exc:
        raise ValueError("topic report identifier is invalid") from exc
    outcome = execute_report_delete(DeleteRequest(
        root=REPORTS_DIR,
        identity=f"topic:{report_id}",
        primary_names=(path.name,),
        target_names=(path.name,),
    ))
    return {"deleted": outcome.deleted, "id": report_id}


def preset_topics_list() -> list:
    return [
        {"key": k, "label": v["label"], "description": v["description"]}
        for k, v in PRESET_TOPICS.items()
    ]


# ---------------------------------------------------------------------------
# Phase 4 — Quality Gate (저장된 보고서 재평가)
# ---------------------------------------------------------------------------

def evaluate_topic_report(report_id: str) -> dict:
    """저장된 보고서를 재평가하고 quality 필드를 갱신해 저장한다."""
    path = _find_report_path(report_id)
    if not path:
        raise FileNotFoundError(f"Topic report not found: {report_id}")
    report = load_report(path)
    if report is None:
        raise FileNotFoundError(f"Topic report not found: {report_id}")
    quality = evaluate_report(
        report.get("markdown", ""),
        evidence_summary=report.get("evidencePackSummary"),
        topic_plan=report.get("topicPlan"),
        user_context_present=bool(report.get("userContext")),
        checkpoints=report.get("checkpoints") or [],
        source_ledger=report.get("sourceLedger") or [],
        evidence_items=report.get("evidenceItems") or [],
        data_gaps=report.get("dataGaps") or [],
        market_tape=report.get("marketTape") or {},
        artifact_type="topic_report",
    )
    report["quality"] = quality
    commit_sync(prepare(
        report_kind=ReportKind.TOPIC_REPORT,
        exact_path=path,
        write_kind=WriteKind.CANONICAL,
        candidate=report,
    ))
    return {"ok": True, "id": report_id, "quality": quality}


# ---------------------------------------------------------------------------
# Phase 5 — Personal Overlay 연결 (Step 2 personal_overlay 재사용)
# ---------------------------------------------------------------------------

def attach_overlay_to_topic_report(report_id: str, *, llm_override=None, web_search_override=None) -> dict:
    """저장된 테마 보고서에 Personal Overlay를 생성·저장한다.

    기본 보고서 markdown은 수정하지 않는다(Step 2 with_overlay 규칙 재사용).
    candidateTickers가 있으면 해당 ticker hypothesis를, 없으면 전체 hypothesis를 연결한다.
    """
    from features.personal_overlay.service import (
        _gather_hypotheses,
        generate_overlay,
        with_overlay,
    )
    from features.obsidian.importer.service import list_hypotheses, scan_vault

    path = _find_report_path(report_id)
    if not path:
        raise FileNotFoundError(f"Topic report not found: {report_id}")
    canonical = load_report(path)
    if canonical is None:
        raise FileNotFoundError(f"Topic report not found: {report_id}")

    # 테마 보고서는 단일 티커가 아니므로, plan의 candidateTickers로 노트를 모으고
    # 없으면 전체 hypothesis를 연결한다.
    tickers = list((canonical.get("topicPlan") or {}).get("candidateTickers") or {})
    hyps: list = []
    try:
        scan_vault()
    except Exception:
        pass
    seen: set[str] = set()
    try:
        if tickers:
            for ticker in tickers:
                for note in list_hypotheses(ticker=ticker):
                    nid = note.get("note_id") or note.get("rel_path")
                    if nid and nid not in seen:
                        seen.add(nid)
                        hyps.append(note)
        if not hyps:
            hyps = _gather_hypotheses("topic", canonical)
    except Exception:
        hyps = _gather_hypotheses("topic", canonical)

    overlay, status = generate_overlay(
        canonical, hyps, kind="topic",
        llm_override=llm_override, web_search_override=web_search_override,
    )
    updated = with_overlay(canonical, overlay, status=status)
    commit_sync(prepare(
        report_kind=ReportKind.TOPIC_REPORT,
        exact_path=path,
        write_kind=WriteKind.OVERLAY,
        candidate={"personalOverlay": updated["personalOverlay"]},
    ))
    return {"ok": True, "status": status, "personalOverlay": updated["personalOverlay"]}
