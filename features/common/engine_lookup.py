"""찾기 전용 엔진 호출 — 기업분석·브리핑이 공유한다.

웹 조회는 본문 생성과 **다른 과제**다(찾기 vs 쓰기). 쓰기 과제에 "필요하면 검색도
하라"를 얹는 방식은 실측 4회 모두 실패했다(새 URL 0~1건) — 모델은 팩에 근거가 있으면
충분하다고 판단한다. 같은 어댑터에 순수한 찾기 과제를 주면 곧바로 검색한다.

원래 `company_analysis/engine_calls.py`에 있었고 브리핑이 같은 것을 필요로 해서
올렸다(§13 — 공유 코드는 features/common). 기능별 타임아웃 env 이름은 호출자가 정한다.

테스트에서는 외부 엔진을 부르지 않는다. 스텁하지 않은 테스트가 실제 CLI를 실행해
스위트가 멈춰 선 적이 있다(딥 리서치에서 겪었다).
"""
from __future__ import annotations

import os
from collections.abc import Callable

from features.llm_settings.client import selected_cli_config

LookupCall = Callable[[str, str], str]


def configured_lookup_call(
    *,
    adapter: str = "",
    job_id: str = "",
    cli_timeout_env: str = "LOOKUP_CLI_TIMEOUT_SECONDS",
    default_cli_timeout: int = 600,
    max_output_tokens: int = 2_500,
    timeout_limit: Callable[[], float] | None = None,
) -> LookupCall:
    """설정한 Agent CLI로 웹 조회를 한 번 수행한다."""

    def invoke(prompt: str, context: str) -> str:
        def timeout_for(configured: int) -> float:
            return min(configured, timeout_limit()) if timeout_limit else configured
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise RuntimeError("external_lookup_disabled_in_tests")
        config = selected_cli_config()
        if not config.get("enabled"):
            raise RuntimeError("ai_disabled")
        # 최상단에서 가져오면 순환이 생긴다(bridge → agent_mode.service → 기능 조립기 → 여기).
        from features.agent_mode import bridge as agent_bridge

        result = agent_bridge.run_agent_prompt(
            prompt + "\n\n" + context,
            adapter=adapter or str(config.get("provider") or ""),
            model=str(config.get("model") or ""),
            reasoning_effort=str(config.get("reasoningEffort") or ""),
            job_id=job_id,
            timeout=timeout_for(max(60, int(os.environ.get(cli_timeout_env, str(default_cli_timeout))))),
            web_search=True,
            # 조회는 팩 준비 중에 불린다 — 그 시점은 run_agent_task가 _RUN_SEMAPHORE를
            # 쥐고 있다. 이미 소유한 직렬화 경계를 재사용한다.
            serialize=False,
            # This is evidence lookup, not the report's primary execution.
            diagnostic_primary=False,
        )
        # Additive passthrough: bridge.py may have observed whether the
        # adapter actually searched (its own structured CLI output). Callers
        # that care read this attribute right after invoking `invoke`.
        invoke.web_search_facts = result.get("webSearchFacts")
        return str(result.get("output") or "")

    return invoke


__all__ = ["LookupCall", "configured_lookup_call"]
