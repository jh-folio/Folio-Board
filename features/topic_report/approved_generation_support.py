from __future__ import annotations

import urllib.error
from dataclasses import dataclass

from features.agent_mode import bridge as agent_bridge
from features.agent_mode import schema as agent_schema
from features.common.research_schema.evidence import evidence_items_from_list
from features.llm_settings.client import LlmRequestError, request_llm_text, selected_llm_config, use_llm_analysis
from features.topic_report.approved_schema import ApprovedRequest
from features.topic_report.data_fetcher import fetch_topic_market_data
from features.topic_report.macro_data import fetch_macro_data
from features.topic_report.topic_config import get_topic_config


@dataclass(frozen=True, slots=True)
class EngineUnavailableError(Exception):
    engine: str


@dataclass(frozen=True, slots=True)
class EngineFailedError(Exception):
    engine: str


@dataclass(frozen=True, slots=True)
class EngineOutput:
    markdown: str
    adapter: str
    provider: str
    model: str
    responseId: str


def _topic(approved: ApprovedRequest) -> dict:
    tickers = approved.customTickers or approved.topicPlan.candidateTickers
    topic = get_topic_config(
        "custom",
        custom_label=approved.topicPlan.topicLabel,
        custom_tickers=tickers,
    )
    topic["report_type"] = approved.topicPlan.reportType
    topic["theme_axes"] = [axis.label for axis in approved.topicPlan.analysisAxes]
    topic["search_keywords"] = list(approved.topicPlan.searchQueries)
    topic["memory_keywords"] = list(approved.topicPlan.memoryQueries)
    return topic


def _normalized_evidence(rows: list[dict]) -> list[dict]:
    normalized = evidence_items_from_list(
        rows,
        artifact_type="topic_report",
        default_type="news",
        limit=120,
    )
    by_id = {
        str(row.get("id") or ""): row
        for row in rows
        if str(row.get("id") or "")
    }
    for item in normalized:
        source = by_id.get(str(item.get("id") or ""))
        if source is None:
            continue
        item["documentId"] = str(source["documentId"])
        for key in ("researchQuestionId", "researchRound"):
            if source.get(key) is not None:
                item[key] = source[key]
    return normalized


def _materials(approved: ApprovedRequest, rows: list[dict]) -> tuple[dict, dict, dict]:
    topic = _topic(approved)
    try:
        market_data = fetch_topic_market_data(
            topic["tickers"],
            history_period=topic.get("history_period", "1y"),
        )
    except (OSError, ValueError):
        market_data = {"tickers": {}, "asOf": approved.asOfDate}
    try:
        from features.llm_settings.client import bok_api_key, fred_api_key

        macro_data = fetch_macro_data(
            fred_series=topic.get("fred_series", []),
            bok_series=topic.get("bok_series", []),
            fred_key=fred_api_key(),
            bok_key=bok_api_key(),
        )
    except (OSError, ValueError):
        macro_data = {"ok": False}
    return topic, market_data, macro_data


def attempt_direct(prompt: str, context: str, *, max_output_tokens: int = 9000, timeout_seconds: int | None = None) -> EngineOutput:
    config = selected_llm_config()
    if not use_llm_analysis() or not config.get("apiKey") or not prompt:
        raise EngineUnavailableError("api")
    try:
        text, response_id, _usage = request_llm_text(
            config,
            prompt,
            context,
            web_search=False,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            include_usage=True,
        )
    except (LlmRequestError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise EngineFailedError("api") from error
    if not str(text or "").strip():
        raise EngineFailedError("api")
    provider = str(config.get("provider") or "")
    adapters = {"openai": "openai_api", "gemini": "gemini_api", "claude": "claude_api"}
    return EngineOutput(
        markdown=str(text).strip(),
        adapter=adapters.get(provider, "openai_api"),
        provider=provider,
        model=str(config.get("model") or ""),
        responseId=str(response_id or ""),
    )


def attempt_cli(
    prompt: str,
    context: str,
    *,
    adapter: str,
    job_id: str,
    approved: ApprovedRequest,
    evidence_items: list[dict],
    timeout_seconds: int | None = None,
) -> EngineOutput:
    pack = agent_schema.build_pack(
        task_type="topic_report",
        artifact_type="topic_report",
        artifact_id=f"{approved.asOfDate}_{approved.planHash[:12]}",
        title=approved.topicPlan.topicLabel,
        prompt=prompt,
        context=context,
        output_contract={"format": "markdown", "reportType": approved.topicPlan.reportType},
        write_back_contract={"method": "job_commit", "target": "topic_report"},
        save_target="job-owned",
        metadata={"planHash": approved.planHash, "deepResearch": approved.deepResearch},
        evidence_items=evidence_items,
    )
    pack_path = agent_schema.write_pack(pack, owner_job_id=job_id)
    agent_prompt = "\n".join(
        [
            "Write the final Folio OS Topic Report from this approved context pack.",
            f"Read the UTF-8 pack at: {pack_path}",
            "Use only its approved plan, evidence, and context boundaries.",
            "Return final Markdown only and do not write files.",
        ]
    )
    try:
        result = agent_bridge.run_agent_prompt(
            agent_prompt, adapter=adapter, job_id=job_id, timeout=int(timeout_seconds or 0),
        )
    except RuntimeError as error:
        message = str(error).casefold()
        unavailable = (
            "unavailable" in message
            or "사용할 수 없습니다" in message
            or "찾을 수 없습니다" in message
        )
        if unavailable:
            raise EngineUnavailableError("cli") from error
        raise EngineFailedError("cli") from error
    output = str(result.get("output") or "").strip()
    if not output:
        raise EngineFailedError("cli")
    return EngineOutput(
        markdown=output,
        adapter=str(result.get("adapter") or adapter),
        provider="external_agent",
        model="",
        responseId="",
    )


__all__ = [
    "EngineFailedError",
    "EngineOutput",
    "EngineUnavailableError",
    "_materials",
    "_normalized_evidence",
    "_topic",
    "attempt_cli",
    "attempt_direct",
]
