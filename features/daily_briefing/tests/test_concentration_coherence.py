from features.daily_briefing.concentration.coherence import refine_clusters


def test_complete_link_breaks_transitive_a_b_c_chain() -> None:
    docs = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    scores = {frozenset(("a", "b")): 0.8, frozenset(("b", "c")): 0.8, frozenset(("a", "c")): 0.2}

    clusters = refine_clusters(
        [{"issueId": "union", "docs": docs}],
        similarity=lambda left, right: scores[frozenset((left["id"], right["id"]))],
    )

    assert sorted(len(row["docs"]) for row in clusters) == [1, 2]
    assert all(row["coherencePolicy"] == "complete_link" for row in clusters)


def test_complete_link_keeps_directly_coherent_cluster() -> None:
    docs = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    clusters = refine_clusters([{"docs": docs}], similarity=lambda _left, _right: 0.75)
    assert len(clusters) == 1
    assert [row["id"] for row in clusters[0]["docs"]] == ["a", "b", "c"]
