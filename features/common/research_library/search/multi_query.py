"""질의를 하나로 이어 붙이지 않고, 질의별로 검색해 순위를 합친다.

FTS5는 토큰을 OR로 푼다. 검색어 여러 개를 공백으로 이어 붙이면 어느 한 토큰만
스친 문서가 상위로 올라온다 — 실측으로 금리 리포트의 근거 목록에 인도 중앙은행,
터키 물가 전망, 프랑스 강관회사 의결권 공시가 실렸다("기대인플레이션 연준 긴축
2021 2022 Fed hikes 2024 August yen carry unwind"를 한 번에 던진 결과다).

질의별로 따로 검색하고 RRF(k=60)로 합치면 두 가지가 달라진다.
- 여러 질의에 함께 걸린 문서가 위로 간다. 축의 검색어가 "term premium"과
  "fiscal supply"라면 둘 다 걸린 문서가 한쪽만 스친 문서를 이긴다.
- 질의 하나가 아무것도 못 찾아도 나머지 질의의 순위가 그대로 남는다.

k=60은 하이브리드 검색(`research_index.hybrid_search`)이 FTS·벡터 순위를 합칠 때
쓰는 값과 같다. 같은 저장소 안에서 순위 합산 상수를 두 개 두지 않는다.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

RRF_K = 60


def default_result_key(doc: dict) -> str:
    """문서 동일성 키. url → path → id → title 순으로 내려간다."""
    for field in ("url", "path", "id", "documentId"):
        value = str((doc or {}).get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    title = str((doc or {}).get("title") or "").strip()
    return f"title:{title}" if title else ""


def fuse_search_results(
    queries: Iterable[str],
    run_one: Callable[[str, int], list[dict]],
    *,
    limit: int,
    per_query_limit: int | None = None,
    key: Callable[[dict], str] = default_result_key,
) -> list[dict]:
    """질의별 검색 결과를 RRF로 합쳐 상위 `limit`건을 돌려준다.

    `run_one(query, limit)`은 호출자가 주입한다(하이브리드 검색이든 인덱스
    검색이든 이 모듈은 알 필요가 없다). 정렬은 완전 결정적이다 — 승인 경로가
    `selectedEvidenceIds`로 근거 구성을 재검증하므로 같은 입력이 같은 순서를
    내야 한다.
    """
    cap = max(0, int(limit or 0))
    if not cap:
        return []
    unique_queries: list[str] = []
    for raw in queries or []:
        text = str(raw or "").strip()
        if text and text not in unique_queries:
            unique_queries.append(text)
    if not unique_queries:
        return []
    each = int(per_query_limit or cap)
    each = max(1, each)

    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    hit_count: dict[str, int] = {}
    docs: dict[str, dict] = {}
    order: dict[str, int] = {}

    for query in unique_queries:
        try:
            rows = run_one(query, each)
        except Exception:
            rows = []
        for rank, row in enumerate(rows or [], start=1):
            if not isinstance(row, dict):
                continue
            row_key = key(row)
            if not row_key:
                continue
            scores[row_key] = scores.get(row_key, 0.0) + 1.0 / (RRF_K + rank)
            hit_count[row_key] = hit_count.get(row_key, 0) + 1
            if row_key not in best_rank or rank < best_rank[row_key]:
                best_rank[row_key] = rank
                docs[row_key] = row
            order.setdefault(row_key, len(order))

    ranked = sorted(
        scores,
        key=lambda k: (-scores[k], best_rank.get(k, 10**6), order.get(k, 10**6), k),
    )
    fused: list[dict] = []
    for row_key in ranked[:cap]:
        row = dict(docs[row_key])
        row["fusedScore"] = round(scores[row_key], 6)
        row["matchedQueryCount"] = hit_count.get(row_key, 0)
        fused.append(row)
    return fused


__all__ = ["RRF_K", "default_result_key", "fuse_search_results"]
