"""기업분석이 본문 생성 밖에서 엔진을 부를 때 쓰는 호출.

실제 구현은 `features/common/engine_lookup.py`로 올라갔다(브리핑도 같은 것을 쓴다).
여기는 기업분석의 env 이름(`COMPANY_LOOKUP_*`)을 지키는 얇은 wrapper다 — 문서와
기존 설치가 그 이름을 알고 있다.
"""
from __future__ import annotations

from features.common.engine_lookup import LookupCall, configured_lookup_call as _common_lookup


def configured_lookup_call(*, adapter: str = "", job_id: str = "") -> LookupCall:
    """설정한 Agent CLI로 웹 조회를 한 번 수행한다."""
    return _common_lookup(
        adapter=adapter,
        job_id=job_id,
        cli_timeout_env="COMPANY_LOOKUP_CLI_TIMEOUT_SECONDS",
    )


__all__ = ["configured_lookup_call"]
