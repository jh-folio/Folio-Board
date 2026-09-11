"""Independent regressions for the source assembler, not claim truth tests."""
import json

from features.daily_briefing.finalize import _production_source_check
from features.daily_briefing.source_integrity import (
    MANIFEST_END, MANIFEST_START, reconcile_source_ledger,
)


def _run(candidates, *, external=None, ids=None, claims=None, body="Original writer body."):
    manifest = {
        "usedSourceIds": ids or [], "externalSources": external or [],
        "claims": claims if claims is not None else [],
    }
    markdown = f"{body}\n{MANIFEST_START}\n{json.dumps(manifest)}\n{MANIFEST_END}"
    cleaned, sources, evidence, ledger = reconcile_source_ledger(markdown, candidates, limit=24)
    assert cleaned == body
    check, _ = _production_source_check({
        "markdown": cleaned, "sources": sources,
        "generationEvidence": evidence, "claimLedger": ledger,
    })
    assert check["errors"] == []
    assert check["semanticVerifiedClaimCount"] is None
    assert evidence["verifiedSourceCount"] == 0
    return sources, evidence, ledger


def test_duplicate_candidate_url_maps_alias_to_actual_canonical_source():
    sources, _, ledger = _run([
        {"sourceId": "canonical", "title": "A", "url": "https://example.org/a"},
        {"sourceId": "alias", "title": "A duplicate", "url": "https://EXAMPLE.org/a/#anchor"},
    ], ids=["alias"], claims=[{"claim": "Original", "sourceIds": ["alias"]}])
    assert len(sources) == 1
    assert ledger["claims"][0]["sourceIds"] == ["canonical"]
    assert not ledger["claims"][0].get("unresolvedSourceIds")


def test_reader_cap_never_evicts_writer_inputs_or_visible_external_source():
    candidates = [
        {"sourceId": f"input_{i}", "title": f"Input {i}", "url": f"https://example.org/input/{i}"}
        for i in range(24)
    ]
    sources, _, ledger = _run(
        candidates,
        external=[{"sourceId": "web_a", "title": "Release", "url": "https://example.org/release"}],
        ids=["web_a"], claims=[{"claim": "Original", "sourceIds": ["web_a"]}],
        body="Original [release](https://example.org/release).",
    )
    assert {row["sourceId"] for row in sources} == {*(f"input_{i}" for i in range(24)), "web_a"}
    assert ledger["claims"][0]["sourceIds"] == ["web_a"]


def test_source_limit_is_not_a_claim_count_limit():
    claims = [{"claim": f"Original {i}", "sourceIds": ["a"]} for i in range(40)]
    _, _, ledger = _run(
        [{"sourceId": "a", "title": "A", "url": "https://example.org/a"}], claims=claims,
    )
    assert ledger["claims"] == claims


def test_id_collision_is_not_attributed_to_either_unrelated_source():
    sources, evidence, ledger = _run(
        [{"sourceId": "same", "source_id": "same", "title": "A", "url": "https://example.org/a"}],
        external=[{"sourceId": "same", "source_id": "same", "title": "B", "url": "https://example.org/b"}],
        ids=["same"], claims=[{"claim": "Original", "sourceIds": ["same"]}],
    )
    assert len({row["sourceId"] for row in sources}) == 2
    assert evidence["declaredUsedSourceCount"] == 0
    assert evidence["actualUsedSourceCount"] is None
    assert evidence["actualUsedStatus"] == "unknown"
    claim = ledger["claims"][0]
    assert claim["sourceIds"] == []
    assert claim["unresolvedSourceIds"] == ["same"]
    assert ledger["validation"]["status"] == "review"


def test_unknown_scalar_reference_preserves_claim_but_is_not_verified():
    _, _, ledger = _run([], claims=[{"claim": "Original", "sourceIds": "unknown-id"}])
    claim = ledger["claims"][0]
    assert claim["claim"] == "Original"
    assert not claim["sourceIds"]
    assert claim["unresolvedSourceIds"] == ["unknown-id"]
    assert ledger["validation"]["status"] == "review"


def test_existing_external_candidate_does_not_hide_new_visible_link():
    sources, _, _ = _run(
        [{"sourceId": "a", "title": "A", "url": "https://example.org/a", "external": True}],
        body="Original [new source](https://example.org/new).",
    )
    assert {row["url"] for row in sources} == {"https://example.org/a", "https://example.org/new"}


def test_duplicate_alias_survives_visible_link_merge():
    _, _, ledger = _run([
        {"sourceId": "a", "title": "A", "url": "https://example.org/a"},
        {"sourceId": "alias", "title": "A duplicate", "url": "https://example.org/a/"},
    ], claims=[{"claim": "Original", "sourceIds": ["alias"]}],
        body="Original [new source](https://example.org/new).")
    assert ledger["claims"][0]["sourceIds"] == ["a"]


def test_duplicate_url_alias_collision_cannot_resolve_to_an_unrelated_url():
    _, _, ledger = _run([
        {"sourceId": "a", "title": "A", "url": "https://example.org/a"},
        {"sourceId": "alias", "title": "A duplicate", "url": "https://example.org/a/"},
    ], external=[{"sourceId": "alias", "title": "B", "url": "https://example.org/b"}],
        claims=[{"claim": "Original", "sourceIds": ["alias"]}])
    assert ledger["claims"][0]["sourceIds"] == []
    assert ledger["claims"][0]["unresolvedSourceIds"] == ["alias"]


def test_existing_url_merge_cannot_reassign_another_candidates_id():
    _, _, ledger = _run([
        {"sourceId": "a", "title": "A", "url": "https://example.org/a"},
        {"sourceId": "b", "title": "B", "url": "https://example.org/b"},
    ], external=[{"sourceId": "a", "title": "B", "url": "https://example.org/b"}],
        claims=[{"claim": "Original", "sourceIds": ["a"]}])
    assert ledger["claims"][0]["sourceIds"] == []
    assert ledger["claims"][0]["unresolvedSourceIds"] == ["a"]
