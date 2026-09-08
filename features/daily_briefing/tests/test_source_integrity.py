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
