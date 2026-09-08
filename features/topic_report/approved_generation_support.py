from __future__ import annotations

import os
import urllib.error
from dataclasses import dataclass

from features.agent_mode import bridge as agent_bridge
from features.agent_mode import schema as agent_schema
from features.common.research_schema.evidence import evidence_items_from_list
from features.llm_settings.client import (
    LlmRequestError,
    request_llm_text,
    selected_llm_config,
    use_llm_analysis,
    use_web_search_for_analysis,
)
from features.topic_report.approved_schema import ApprovedRequest
from features.topic_report.axis_analysis import AxisCall
from features.topic_report.data_fetcher import fetch_topic_market_data
from features.topic_report.macro_data import fetch_macro_data, resolve_fred_series
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
    # 계획이 요청한 거시 시리즈를 실제로 받아온다. 예전에는 requiredMacroData를 계획에
    # 적어 화면에 보여주기까지 하고서 custom 고정값 3종(FEDFUNDS/UNRATE/DGS10)만 조회했다.
    topic["fred_series"] = resolve_fred_series(
        approved.topicPlan.requiredMacroData,
        fallback=topic.get("fred_series"),
    )
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
            web_search=use_web_search_for_analysis(),
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
    model: str = "",
    reasoning_effort: str = "",
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
    # 팩 안의 웹 검색 허가를 겉 지시가 덮지 않도록 같은 말을 밖에서도 한다.
    web_search_enabled = use_web_search_for_analysis()
    boundary = (
        "Use its approved plan, evidence, and context boundaries. If the pack contains a "
        "`## 웹 검색 사용` section, follow it: you may search the web within the listed sources "
        "and must cite the URL for anything found there."
        if web_search_enabled
        else "Use only its approved plan, evidence, and context boundaries."
    )
    agent_prompt = "\n".join(
        [
            "Write the final Folio Board Topic Report from this approved context pack.",
            f"Read the UTF-8 pack at: {pack_path}",
            boundary,
            "Return final Markdown only and do not write files.",
        ]
    )
    try:
        result = agent_bridge.run_agent_prompt(
            agent_prompt,
            adapter=adapter,
            model=model,
            reasoning_effort=reasoning_effort,
            job_id=job_id,
            timeout=int(timeout_seconds or 0),
            web_search=web_search_enabled,
        )
    except agent_bridge.AgentRateLimitError as error:
        # 사용량 한도는 코드 결함이 아니다. 이유를 보존해야 화면이 "한도, 리셋 뒤 다시"라고
        # 말할 수 있고, 재개 체크포인트가 남아 다음 실행이 이어받는다.
        raise EngineFailedError("cli_rate_limited") from error
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
        model=str(model or ""),
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


def configured_editor_call(
    approved: ApprovedRequest,
    *,
    requested_mode: str,
    adapter: str,
    job_id: str,
    model: str = "",
    reasoning_effort: str = "",
) -> AxisCall:
    """리서치 에디터 호출. 축 분석과 같은 엔진이되 세 가지가 다르다.

    - 출력이 보고서 전문이라 토큰 한도가 훨씬 크다(축 브리프는 2,500이면 족하다).
    - JSON이 아니라 Markdown을 받는다.
    - **웹 검색을 끈다.** 에디터는 사실을 더할 수 없다. 검색을 열어 두면 계약이
      금지한 새 수치를 가져올 통로가 생기고, 그러면 편집본이 통째로 버려진다.
    """

    def invoke(prompt: str, context: str) -> str:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise RuntimeError("external_editor_disabled_in_tests")
        if requested_mode == "direct":
            config = selected_llm_config()
            if not use_llm_analysis() or not config.get("apiKey"):
                raise EngineUnavailableError("api")
            text, _response_id = request_llm_text(
                config,
                prompt,
                context,
                web_search=False,
                max_output_tokens=16_000,
                timeout_seconds=max(120, int(os.environ.get("TOPIC_EDITOR_API_TIMEOUT_SECONDS", "600"))),
            )
            return str(text or "")
        result = agent_bridge.run_agent_prompt(
            prompt + "\n\n" + context,
            adapter=adapter,
            model=model,
            reasoning_effort=reasoning_effort,
            job_id=job_id,
            timeout=max(120, int(os.environ.get("TOPIC_EDITOR_CLI_TIMEOUT_SECONDS", "1200"))),
            web_search=False,
        )
        return str(result.get("output") or "")

    return invoke


def configured_axis_call(
    approved: ApprovedRequest,
    *,
    requested_mode: str,
    adapter: str,
    job_id: str,
    web_search: bool | None = None,
    model: str = "",
    reasoning_effort: str = "",
) -> AxisCall:
    """축별 분석 호출. 보고서 본문 생성과 같은 엔진을 쓰되 팩 없이 프롬프트만 보낸다.

    **웹 검색 여부는 두 분기에 같은 값이 도착해야 한다.** 예전에는 API 분기만
    `web_search=False`로 박혀 있고 CLI 분기는 설정을 읽었다. 같은 호출자가 이 콜러블을
    `lookup_axis()`에도 넘기는데 — 그 패스의 일이 바로 웹에서 찾아오는 것이다 — API 키
    설치에서는 "웹에서 사실을 찾아 출처 URL을 붙이라"는 지시를 검색 도구 없이 받았다.
    모델은 기억으로 답하고 `_rows`는 `http`로 시작하면 받으므로, 지어낸 URL이 `web_001`로
    원장에 등재된다(§6 규칙 14 — 확인은 구조가 아니라 값으로 한다).
    """
    resolved_web_search = use_web_search_for_analysis() if web_search is None else bool(web_search)

    def invoke(prompt: str, context: str) -> str:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise RuntimeError("external_axis_analysis_disabled_in_tests")
        if requested_mode == "direct":
            config = selected_llm_config()
            if not use_llm_analysis() or not config.get("apiKey"):
                raise EngineUnavailableError("api")
            text, _response_id = request_llm_text(
                config,
                prompt,
                context,
                web_search=resolved_web_search,
                max_output_tokens=2_500,
                json_mode=True,
                timeout_seconds=max(60, int(os.environ.get("TOPIC_AXIS_API_TIMEOUT_SECONDS", "240"))),
            )
            return str(text or "")
        result = agent_bridge.run_agent_prompt(
            prompt + "\n\n" + context,
            adapter=adapter,
            model=model,
            reasoning_effort=reasoning_effort,
            job_id=job_id,
            timeout=max(60, int(os.environ.get("TOPIC_AXIS_CLI_TIMEOUT_SECONDS", "600"))),
            web_search=resolved_web_search,
        )
        return str(result.get("output") or "")

    return invoke
