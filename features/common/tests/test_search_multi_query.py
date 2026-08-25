"""질의별 검색·보도자료 필터 계약."""
from __future__ import annotations

from features.common.research_library.search.filters import (
    drop_press_releases,
    is_press_release,
    source_type_of,
)
from features.common.research_library.search.multi_query import fuse_search_results


def _doc(doc_id: str, **extra) -> dict:
    return {"id": doc_id, "url": f"https://example.test/{doc_id}", "title": doc_id, **extra}


def test_each_query_runs_separately() -> None:
    # 이어 붙여 한 번 검색하면 어느 한 토큰만 스친 문서가 상위로 온다.
    seen: list[str] = []

    def run_one(query: str, limit: int) -> list[dict]:
        seen.append(query)
        return [_doc(f"{query}-1")]

    fuse_search_results(["term premium", "fiscal supply"], run_one, limit=5)
    assert seen == ["term premium", "fiscal supply"]


def test_document_matching_more_queries_ranks_higher() -> None:
    def run_one(query: str, limit: int) -> list[dict]:
        if query == "a":
            return [_doc("only_a"), _doc("both")]
        return [_doc("only_b"), _doc("both")]

    fused = fuse_search_results(["a", "b"], run_one, limit=3)
    assert fused[0]["id"] == "both"
    assert fused[0]["matchedQueryCount"] == 2


def test_failing_query_does_not_lose_the_others() -> None:
    def run_one(query: str, limit: int) -> list[dict]:
        if query == "boom":
            raise RuntimeError("search failed")
        return [_doc("survivor")]

    fused = fuse_search_results(["boom", "ok"], run_one, limit=3)
    assert [row["id"] for row in fused] == ["survivor"]


def test_ranking_is_deterministic() -> None:
    def run_one(query: str, limit: int) -> list[dict]:
        return [_doc("x"), _doc("y"), _doc("z")]

    first = fuse_search_results(["q1", "q2"], run_one, limit=3)
    second = fuse_search_results(["q1", "q2"], run_one, limit=3)
    assert [row["id"] for row in first] == [row["id"] for row in second]


def test_duplicate_and_blank_queries_are_collapsed() -> None:
    calls: list[str] = []

    def run_one(query: str, limit: int) -> list[dict]:
        calls.append(query)
        return []

    fuse_search_results(["같은 질의", " 같은 질의 ", "", None], run_one, limit=5)
    assert calls == ["같은 질의"]


def test_press_release_is_read_from_either_shape() -> None:
    assert is_press_release({"sourceType": "press_release"}) is True
    assert is_press_release({"metadata": {"sourceType": "press_release"}}) is True
    assert is_press_release({"source_type": "news"}) is False
    assert source_type_of({"metadata": {"sourceType": "news"}}) == "news"


def test_press_releases_are_dropped_from_results() -> None:
    rows = [
        _doc("news", metadata={"sourceType": "news"}),
        _doc("wire", metadata={"sourceType": "press_release"}),
    ]
    assert [row["id"] for row in drop_press_releases(rows)] == ["news"]
