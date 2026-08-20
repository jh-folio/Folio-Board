"""브리핑 선별 파이프라인의 개수 상한을 한 곳에 모은다.

예전에는 `limit=14`가 기본 인자 여섯 곳과 호출부 전부에 흩어져 있었다. 어느 하나를
고쳐도 나머지가 그대로라 실제로는 아무것도 달라지지 않았고, 실제로 그 상태에서
**프롬프트는 24건을 보는데 독자에게는 14건만 보였다** — 근거로 쓰였을 수 있는 열 건이
출처 목록에 없었다. 근거를 숨기는 것은 source-grounding 원칙과 어긋난다.

그래서 참고자료 상한은 컨텍스트 상한과 **같은 값**이다. 표시 개수를 따로 설정하게
만들지 않는다 — 일치가 기본이면 설정할 것이 없다(2026-08-20 사용자 결정).

상한 사슬:

    이슈 10개  →  다양성 선발 18건  →  컨텍스트 CONTEXT_DOC_LIMIT
                                    →  참고자료 SOURCE_REF_LIMIT(= 컨텍스트)
                                    →  다시장 병합 = 시장 수 × 시장당 상한
"""
from __future__ import annotations

WEEKLY = "weekly"

# 한 시장 브리핑이 프롬프트에 싣는 문서 수. 참고자료도 같은 값이다.
CONTEXT_DOC_LIMIT = 24
SOURCE_REF_LIMIT = CONTEXT_DOC_LIMIT

# 주간은 하루가 아니라 7일 창이라 같은 상한으로는 한 주가 하루처럼 보인다.
WEEKLY_CONTEXT_DOC_LIMIT = 40
WEEKLY_SOURCE_REF_LIMIT = WEEKLY_CONTEXT_DOC_LIMIT

# 컨텍스트를 채우기 전 최소 확보 수. 이 아래면 점수 상위 자료로 패딩한다.
CONTEXT_DOC_FLOOR = 18
# 이슈 커버리지에서 뽑는 다양성 선발 수.
DIVERSE_SELECTION_LIMIT = 18
# 이슈 클러스터 수.
ISSUE_COVERAGE_LIMIT = 10
# 같은 매체가 한 목록을 채우지 못하게 하는 soft cap과 목표 매체 수.
PER_PUBLISHER_CAP = 4
MINIMUM_PUBLISHERS = 5


def _is_weekly(kind) -> bool:
    return str(kind or "").strip().lower() == WEEKLY


def context_doc_limit(kind: str = "daily") -> int:
    return WEEKLY_CONTEXT_DOC_LIMIT if _is_weekly(kind) else CONTEXT_DOC_LIMIT


def source_ref_limit(kind: str = "daily") -> int:
    return WEEKLY_SOURCE_REF_LIMIT if _is_weekly(kind) else SOURCE_REF_LIMIT


def merged_source_limit(market_count: int, kind: str = "daily") -> int:
    """다시장 종합 보고서의 병합 출처 상한.

    고정 28은 이미 잘라먹고 있었다 — 네 시장이면 시장당 14건만 해도 56건이라
    절반이 사라졌고, 잘린 쪽은 뒤에 오는 시장이라 **특정 시장 출처가 통째로**
    빠졌다. 시장 수에서 산출한다.
    """
    count = max(1, int(market_count or 1))
    return count * source_ref_limit(kind)
