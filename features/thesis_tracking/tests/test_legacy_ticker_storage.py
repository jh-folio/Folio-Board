"""Upgrade compatibility must preserve existing Thesis keys and history."""
import pytest

from features.thesis_tracking import model, service, store


@pytest.mark.parametrize("legacy,canonical", [("BRK.B", "BRK-B"), ("005930.KS", "005930")])
def test_legacy_key_history_and_owner_survive_update_and_reopen(tmp_path, legacy, canonical):
    path = tmp_path / "memory.sqlite3"
    with store.connect(path) as conn:
        conn.execute("INSERT INTO thesis(ticker, source, core_thesis) VALUES (?, 'obsidian', 'old')", (legacy,))
        conn.execute("INSERT INTO thesis_delta(delta_id, ticker, summary) VALUES ('old-delta', ?, 'original')", (legacy,))
        conn.commit()
    result = service.upsert_manual_thesis({"ticker": canonical, "coreThesis": "updated"}, db_path=path)
    assert result["ticker"] == legacy and result["source"] == "obsidian"
    with store.connect(path) as conn:
        assert len(store.list_theses(conn)) == 1
        assert store.get_thesis(conn, legacy) == store.get_thesis(conn, canonical)
        assert store.get_thesis(conn, canonical)["core_thesis"] == "updated"
        assert store.latest_delta(conn, canonical)["deltaId"] == "old-delta"
        assert store.list_deltas(conn, canonical)[0]["summary"] == "original"
        saved = store.save_delta(conn, canonical, {"deltaId": "new-delta", "generatedAt": "2026-09-22"})
        assert saved["ticker"] == legacy
        assert store.latest_delta(conn, canonical)["deltaId"] == "new-delta"


def test_distinct_existing_keys_are_never_merged_or_overwritten():
    with store.connect(":memory:") as conn:
        conn.executemany("INSERT INTO thesis(ticker, core_thesis) VALUES (?, ?)",
                         [("BRK.B", "legacy"), ("BRK-B", "canonical")])
        assert store.get_thesis(conn, "BRK.B")["core_thesis"] == "legacy"
        store.upsert_thesis(conn, model.Thesis(ticker="BRK.B", core_thesis="changed"))
        assert store.get_thesis(conn, "BRK-B")["core_thesis"] == "canonical"
        assert len(store.list_theses(conn)) == 2


def test_ambiguous_legacy_alias_does_not_choose_an_owner():
    with store.connect(":memory:") as conn:
        conn.executemany("INSERT INTO thesis(ticker) VALUES (?)", [("005930.KS",), ("005930.KQ",)])
        with pytest.raises(ValueError, match="기존 티커"):
            store.upsert_thesis(conn, model.Thesis(ticker="005930"))
        assert len(store.list_theses(conn)) == 2


def test_watchlist_projection_keeps_the_requested_legacy_authority(tmp_path):
    from features.thesis_tracking.workspace_view import thesis_workspace_payload
    path = tmp_path / "memory.sqlite3"
    with store.connect(path) as conn:
        conn.executemany("INSERT INTO thesis(ticker, core_thesis) VALUES (?, ?)",
                         [("BRK.B", "legacy"), ("BRK-B", "canonical")])
        conn.commit()
        store.save_delta(conn, "BRK.B", {"deltaId": "legacy-delta"})
        store.save_delta(conn, "BRK-B", {"deltaId": "canonical-delta"})
    projection = thesis_workspace_payload("BRK.B", db_path=path)
    assert projection["ticker"] == "BRK.B"
    assert projection["thesis"]["coreThesis"] == "legacy"
    assert [item["deltaId"] for item in projection["deltaHistory"]] == ["legacy-delta"]


def test_rules_delta_requested_by_alias_uses_thesis_storage_key(tmp_path, monkeypatch):
    path = tmp_path / "memory.sqlite3"
    service.upsert_manual_thesis({"ticker": "005930.KS", "coreThesis": "hypothesis"}, db_path=path)
    monkeypatch.setattr(service.D, "gather_local_evidence", lambda *a, **k: ([], {}))
    monkeypatch.setattr(service.D, "generate_delta", lambda *a, **k:
                        ({"generatedAt": "2026-09-22T00:00:00Z", "verdict": "insufficient_evidence"}, "generated"))
    result = service.run_thesis_delta("005930.KS", {"useLlm": False}, db_path=path)
    assert result["delta"]["ticker"] == "005930"
    with store.connect(path) as conn:
        assert store.latest_delta(conn, "005930")["deltaId"] == result["delta"]["deltaId"]
        assert store.list_deltas(conn, "005930.KS")[0]["deltaId"] == result["delta"]["deltaId"]
