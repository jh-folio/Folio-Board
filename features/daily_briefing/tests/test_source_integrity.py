import json

from features.daily_briefing.source_integrity import (
    MANIFEST_END,
    MANIFEST_START,
    extract_source_manifest,
    reconcile_source_ledger,
)
from features.daily_briefing.service import append_briefing_sources, strip_markdown_sources_section


def _sources():
    return [
        {"title": "Local A", "url": "https://example.com/a", "source": "Example", "date": "2026-08-24"},
        {"title": "Local B", "url": "https://example.com/b", "source": "Example", "date": "2026-08-24"},
    ]


def test_manifest_is_removed_and_declared_sources_become_ledger():
    _, candidates, _, _ = reconcile_source_ledger("body", _sources(), limit=10)
    source_id = candidates[0]["sourceId"]
    markdown = (
        "## 본문\n\n[Local A](https://example.com/a)\n\n"
        f"{MANIFEST_START}\n"
        f'{{"usedSourceIds":["{source_id}"],"externalSources":[],"claims":[]}}\n'
        f"{MANIFEST_END}"
    )

    cleaned, ledger, evidence, claims = reconcile_source_ledger(markdown, _sources(), limit=10)

    assert "FOLIO_BRIEFING_MANIFEST" not in cleaned
    # A valid manifest narrows declared use, but the existing reference list
    # keeps every writer-input source accessible to readers.
    assert [row["title"] for row in ledger] == ["Local A", "Local B"]
    assert evidence["status"] == "declared"
    assert evidence["declaredUsedSourceCount"] == 1
    assert evidence["accessibleSourceCount"] == 2
    assert claims["validation"]["status"] == "pass"


def test_missing_manifest_preserves_candidates_and_merges_visible_external_links():
    markdown = "## 본문\n\n[Official release](https://official.example/release)"

    cleaned, ledger, evidence, _ = reconcile_source_ledger(markdown, _sources(), limit=10)

    assert cleaned == markdown
    assert {row["url"] for row in ledger} == {
        "https://example.com/a",
        "https://example.com/b",
        "https://official.example/release",
    }
    assert evidence["status"] == "inferred_candidate_fallback"
    assert "manifest_missing" in evidence["errors"]


def test_manifest_rejects_source_ids_outside_candidate_whitelist():
    markdown = (
        "## 본문\n\n"
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":["src_not_allowed"],"externalSources":[],"claims":[]}\n'
        f"{MANIFEST_END}"
    )

    _, ledger, evidence, _ = reconcile_source_ledger(markdown, _sources(), limit=10)

    assert len(ledger) == 2
    assert "manifest_source_outside_whitelist" in evidence["errors"]


def test_duplicate_manifest_is_removed_but_not_trusted():
    block = f'{MANIFEST_START}\n{{"usedSourceIds":[],"externalSources":[],"claims":[]}}\n{MANIFEST_END}'
    cleaned, manifest, errors = extract_source_manifest(f"body\n{block}\n{block}")

    assert cleaned == "body"
    assert manifest == {}
    assert errors == ["manifest_count_invalid"]


def test_code_owns_daily_references_and_removes_all_model_sections():
    markdown = (
        "## 본문\n\n글\n\n"
        "## 참고자료 — 한국장\n\n- [Old](https://old.example)\n\n"
        "## Source & Data Notes\n\n- 노트\n\n"
        "## 7. 참고 자료 (2건)\n\n- [Old 2](https://old2.example)"
    )

    rendered = append_briefing_sources(markdown, _sources(), limit=10, kind="daily")

    assert rendered.count("## 참고자료") == 1
    assert "old.example" not in rendered and "old2.example" not in rendered
    assert "## Source & Data Notes" in rendered
    assert "https://example.com/a" in rendered


def test_weekly_removes_every_reference_section_but_keeps_notes():
    markdown = (
        "## 본문\n\n글\n\n"
        "## 참고자료 — 미국장\n\n- x\n\n"
        "## Source & Data Notes\n\n- 노트\n\n"
        "### Sources Used (2)\n\n- y"
    )

    cleaned = strip_markdown_sources_section(markdown)

    assert "참고자료" not in cleaned and "Sources Used" not in cleaned
    assert "## Source & Data Notes" in cleaned and "- 노트" in cleaned


def test_manifest_sources_accept_only_http_https_urls():
    markdown = (
        "body\n"
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":[],"externalSources":[{"title":"bad","url":"javascript:alert(1)"}],"claims":[]}\n'
        f"{MANIFEST_END}"
    )

    _, ledger, evidence, _ = reconcile_source_ledger(markdown, [], limit=10)

    assert ledger == []
    assert "manifest_external_source_invalid" in evidence["errors"]


def test_external_manifest_id_is_preserved_and_not_evicted_by_reader_cap():
    candidates = [
        {"sourceId": "src_a", "title": "Input", "url": "https://example.org/input"},
        {"sourceId": "src_b", "title": "Input B", "url": "https://example.org/input-b"},
    ]
    markdown = (
        "본문\n"
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":["src_a"],"externalSources":['
        '{"sourceId":"web_a","title":"Public release","url":"https://example.org/release",'
        '"publisher":"Example"}],"claims":[{"claim":"release","sourceIds":["web_a"]}]}\n'
        f"{MANIFEST_END}"
    )

    cleaned, ledger, evidence, claims = reconcile_source_ledger(markdown, candidates, limit=2)

    assert cleaned == "본문"
    assert {row["sourceId"] for row in ledger} == {"src_a", "src_b", "web_a"}
    assert claims["claims"][0]["sourceIds"] == ["web_a"]
    assert evidence["accessibleSourceCount"] == 3
    assert evidence["readerSourceLimit"] == 2
    assert evidence["sourceLedgerSemantics"] == "complete_safe_writer_ledger"
    rendered = append_briefing_sources(
        "본문 [release](https://example.org/release)", ledger, limit=2, kind="daily"
    )
    assert "https://example.org/release" in rendered


def test_duplicate_candidate_url_aliases_canonicalize_claims_without_losing_alias():
    candidates = [
        {"sourceId": "src_a", "title": "A", "url": "https://EXAMPLE.org/a/"},
        {"sourceId": "alias_a", "title": "A alias", "url": "https://example.org/a"},
    ]
    markdown = (
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":["alias_a"],"externalSources":[],'
        '"claims":[{"claim":"A","supportingSourceIds":["alias_a"]}]}\n'
        f"{MANIFEST_END}"
    )

    _, ledger, evidence, claims = reconcile_source_ledger(markdown, candidates, limit=1)

    assert [row["sourceId"] for row in ledger] == ["src_a"]
    assert evidence["errors"] == []
    assert claims["claims"][0]["supportingSourceIds"] == ["src_a"]
    assert claims["validation"] == {"status": "pass", "reasonCodes": []}


def test_different_url_reuse_of_candidate_alias_is_ambiguous_not_attributed():
    candidates = [
        {"sourceId": "same", "title": "A", "url": "https://example.org/a"},
        {"sourceId": "candidate_alias", "title": "A alias", "url": "https://example.org/a"},
    ]
    markdown = (
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":["candidate_alias"],"externalSources":['
        '{"sourceId":"candidate_alias","title":"B","url":"https://example.org/b"}],'
        '"claims":[{"claim":"B","sourceIds":["candidate_alias"]}]}\n'
        f"{MANIFEST_END}"
    )

    _, ledger, evidence, claims = reconcile_source_ledger(markdown, candidates, limit=2)

    assert {row["url"] for row in ledger} == {"https://example.org/a", "https://example.org/b"}
    assert evidence["actualUsedStatus"] == "unknown"
    assert evidence["actualUsedSourceCount"] is None
    assert evidence["ambiguousSourceIds"] == ["candidate_alias"]
    assert claims["claims"][0].get("sourceIds") == []
    assert claims["validation"]["status"] == "review"
    assert "source_id_ambiguous" in claims["validation"]["reasonCodes"]


def test_alias_registration_does_not_overwrite_existing_id_mapping():
    candidates = [
        {"sourceId": "a", "title": "A", "url": "https://example.org/a"},
        {"sourceId": "b", "title": "B", "url": "https://example.org/b"},
    ]
    markdown = (
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":["a"],"externalSources":['
        '{"sourceId":"a","title":"B duplicate","url":"https://example.org/b"}],'
        '"claims":[{"claim":"A","sourceIds":["a"]}]}\n'
        f"{MANIFEST_END}"
    )

    _, ledger, evidence, claims = reconcile_source_ledger(markdown, candidates, limit=2)

    assert {row["sourceId"] for row in ledger} == {"a", "b"}
    assert evidence["ambiguousSourceIds"] == ["a"]
    assert claims["claims"][0]["sourceIds"] == []
    assert claims["claims"][0]["unresolvedSourceIds"] == ["a"]


def test_claim_metadata_is_all_normalized_instead_of_silently_capped():
    claims = [{"claim": str(index), "sourceIds": ["src_a"]} for index in range(25)]
    markdown = (
        f"{MANIFEST_START}\n"
        f'{{"usedSourceIds":["src_a"],"externalSources":[],"claims":{json.dumps(claims)}}}\n'
        f"{MANIFEST_END}"
    )

    _, _, _, claim_ledger = reconcile_source_ledger(
        markdown,
        [{**_sources()[0], "sourceId": "src_a"}, {**_sources()[1], "sourceId": "src_b"}],
        limit=2,
    )

    assert len(claim_ledger["claims"]) == 25
    assert all(row["sourceIds"] == ["src_a"] for row in claim_ledger["claims"])


def test_trailing_rule_strip_matches_the_old_regex_without_backtracking():
    import random
    import re
    import time

    from features.daily_briefing.service import _strip_trailing_rules

    old = re.compile(r"(?:\n\s*---\s*)+$")
    rng = random.Random(7)
    pieces = ["\n", "---", " ", "\t", "x", "----", "\n\n", "-- -"]
    for _ in range(4000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 12)))
        assert _strip_trailing_rules(text).rstrip() == old.sub("", text).rstrip(), repr(text)

    hostile = "body" + "\n---\n" * 40 + "x"
    started = time.perf_counter()
    assert _strip_trailing_rules(hostile) == hostile
    assert time.perf_counter() - started < 0.1
