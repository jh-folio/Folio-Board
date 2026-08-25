"""검색 결과에 적용하는 자료 성격 필터.

`source_type`을 아는 곳을 하나로 둔다. 브리핑은 `is_news_document()`로, RSS 화면은
전용 SQL로 보도자료를 이미 걸러 왔지만, **텍스트 질의가 있는 검색 경로**는 경로
접두(`research-inbox/rss/`)만 보고 성격을 보지 않았다 — 그래서 금리 리포트의 근거
2번에 프랑스 강관회사의 월간 의결권 공시(GlobeNewswire)가 실렸다.

하이브리드 검색 결과는 문서 필드가 아니라 `metadata` 아래에 `sourceType`을 싣는다.
두 모양을 한 함수가 읽어야 다음에 한쪽만 바뀌는 일이 없다.
"""
from __future__ import annotations

PRESS_RELEASE = "press_release"


def source_type_of(row) -> str:
    """문서/검색히트 어느 모양이든 source_type을 읽는다."""
    if not isinstance(row, dict):
        return ""
    for holder in (row, row.get("metadata") if isinstance(row.get("metadata"), dict) else {}):
        for field in ("sourceType", "source_type"):
            value = str((holder or {}).get(field) or "").strip()
            if value:
                return value
    return ""


def is_press_release(row) -> bool:
    """기업이 스스로 낸 보도자료인가.

    보도자료는 발행처가 1곳뿐이라 교차 보도량으로 이슈를 고르는 경로에서는 노이즈이고,
    주제 리서치에서는 주제와 무관한 정기 공시가 상위로 올라온다. 같은 문서는 워치리스트
    종목 뉴스와 기업분석 보조자료에서는 계속 쓰인다.
    """
    return source_type_of(row) == PRESS_RELEASE


def drop_press_releases(rows):
    return [row for row in rows or [] if not is_press_release(row)]


__all__ = ["PRESS_RELEASE", "drop_press_releases", "is_press_release", "source_type_of"]
