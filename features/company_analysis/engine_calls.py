"""기업분석이 본문 생성 밖에서 엔진을 부를 때 쓰는 호출.

웹 조회는 본문 생성과 **다른 과제**다(찾기 vs 쓰기). 그래서 호출도 따로 만든다 —
JSON을 받고, 토큰 한도가 작고, 웹 검색을 켠다.

테스트에서는 외부 엔진을 부르지 않는다. 스텁하지 않은 테스트가 실제 CLI를 실행해
스위트가 멈춰 선 적이 있다(딥 리서치에서 겪었다).
"""
from __future__ import annotations

import os
from collections.abc import Callable

from features.llm_settings.client import request_llm_text, selected_llm_config, use_llm_analysis

LookupCall = Callable[[str, str], str]


def configured_lookup_call(*, adapter: str = "", job_id: str = "") -> LookupCall:
    """웹 조회 한 번. API 키가 있으면 그것을, 없으면 Agent CLI를 쓴다."""

    def invoke(prompt: str, context: str) -> str:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise RuntimeError("external_lookup_disabled_in_tests")
        config = selected_llm_config()
        if use_llm_analysis() and config.get("apiKey"):
            text, _response_id = request_llm_text(
                config,
                prompt,
                context,
                web_search=True,
                max_output_tokens=2_500,
                json_mode=True,
                timeout_seconds=max(60, int(os.environ.get("COMPANY_LOOKUP_API_TIMEOUT_SECONDS", "240"))),
            )
            return str(text or "")
        # 모듈 최상단에서 가져오면 순환이 생긴다(조립기를 두 경로가 공유하기 때문).
        from features.agent_mode import bridge as agent_bridge

        result = agent_bridge.run_agent_prompt(
            prompt + "\n\n" + context,
            adapter=adapter,
            job_id=job_id,
            timeout=max(60, int(os.environ.get("COMPANY_LOOKUP_CLI_TIMEOUT_SECONDS", "600"))),
            web_search=True,
        )
        return str(result.get("output") or "")

    return invoke


__all__ = ["configured_lookup_call"]
