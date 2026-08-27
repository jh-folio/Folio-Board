"""브리핑 문체 실측 — 검사만 하고 산출물을 되돌리지 않는다.

저장 브리핑 16건을 딥 리서치와 같은 잣대로 재니 **8건이 위반**이었다(2026-08-27 실측).
최다 표현도 딥 리서치와 같은 `수 있다`(08-14.us에서 4.8천자에 11회)다. 밀도 0.2~0.5인
무리와 2.7~4.0인 무리로 갈리는 이분포인데, 저장 JSON이 작성 어댑터를 기록하지 않아
원인 변수를 귀속할 수 없었다 — 그래서 지금 단계는 **측정을 저장물에 남기는 것**이고,
에디터 같은 비싼 처방은 어댑터별 실측이 쌓인 뒤 판단한다.

경계:
- 어느 결과도 브리핑을 되돌리거나 재작성시키지 않는다. 브리핑은 예약 발행물이라
  문체 때문에 발행이 막히면 안 된다.
- 잣대는 공통 눈금(`common/report_prose`)을 그대로 쓴다. 기능마다 다른 임계를 두면
  같은 문장이 기능에 따라 합격·불합격으로 갈린다.
"""
from __future__ import annotations

from features.common.report_prose import (
    HEDGE_DENSITY_LIMIT,
    HEDGE_REPEAT_DENSITY,
    HEDGE_REPEAT_MIN,
    hedge_stats,
)

# 데이터 한계 서술이 그 섹션의 일이다(딥 리서치·기업분석과 같은 규칙).
STYLE_EXEMPT_SECTIONS = ("Source & Data Notes",)


def briefing_style_check(markdown: str) -> dict:
    """유보 밀도·쏠림 실측. `violations`가 비면 통과다."""
    text = str(markdown or "")
    if not text.strip():
        return {}
    stats = hedge_stats(text, exempt=STYLE_EXEMPT_SECTIONS)
    violations = []
    if stats["per1000"] > HEDGE_DENSITY_LIMIT:
        violations.append("hedge_overuse")
    if stats["topCount"] >= HEDGE_REPEAT_MIN and stats["topPer1000"] > HEDGE_REPEAT_DENSITY:
        violations.append("hedge_repetition")
    return {
        "hedgePer1000": stats["per1000"],
        "topPhrase": stats["topPhrase"],
        "topCount": stats["topCount"],
        "violations": violations,
    }


__all__ = ["briefing_style_check", "STYLE_EXEMPT_SECTIONS"]
