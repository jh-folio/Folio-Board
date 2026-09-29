"""R0 reason history contracts; every database lives under tmp_path."""
import json
import sqlite3

import pytest

from features.thesis_tracking import reason_history as history
from features.thesis_tracking import service, store, workspace_view, model, overview


def _save(path, text, token=None, **extra):
    body = {"ticker": "AMD", "coreThesis": text, **extra}
    if token is not None:
        body["expectedRevisionId"] = token
    return service.upsert_manual_thesis(body, db_path=path)["reasonRevision"]


def test_previous_words_conditions_refs_and_times_survive_restart(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = _save(path, "돈을 잘 벌어서", conditionResponse="written",
                  falsificationTriggers=["현금흐름 악화"], basisRefs=[{"id": "filing-1", "revision": "v1"}],
                  userStatedAt="2026-09-01")
    second = _save(path, "현금흐름도 좋아서", first["revisionId"],
                   changeReason="자료를 다시 읽음", basisRefs=[{"id": "filing-2", "revision": "v2"}])
    assert second["previousRevisionId"] == first["revisionId"]
    assert second["userStatedAt"] == "2026-09-01"
    assert second["recordedAt"] != "2026-09-01"
    old = service.reason_revision_payload("AMD", first["revisionId"], db_path=path)
    assert old["content"]["core_thesis"] == "돈을 잘 벌어서"
    assert old["content"]["falsification_triggers"] == ["현금흐름 악화"]
    assert old["basisRefs"] == [{"id": "filing-1", "revision": "v1"}]
    assert second["changeReason"] == "자료를 다시 읽음"
    assert service.thesis_detail_payload("AMD", db_path=path, sync=False)["reasonRevision"]["revisionId"] == second["revisionId"]


def test_duplicate_save_and_machine_checkpoint_do_not_change_reason(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = _save(path, "제품이 좋아서")
    again = _save(path, "제품이 좋아서", first["revisionId"])
    assert again["revisionId"] == first["revisionId"]
    conn = store.connect(path)
    try:
        before = store.get_thesis(conn, "AMD")["updated_at"]
        store.save_thesis_checkpoints(conn, "AMD", [{"id": "cp-1", "item": "고객 이탈", "status": "challenged"}])
        assert store.get_thesis(conn, "AMD")["updated_at"] == before
        assert history.latest(conn, "AMD")["revisionId"] == first["revisionId"]
    finally:
        conn.close()


def test_stale_edit_is_rejected_without_partial_write(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = _save(path, "A")
    second = _save(path, "B", first["revisionId"])
    with pytest.raises(history.ReasonRevisionConflictError) as caught:
        _save(path, "lost", first["revisionId"])
    assert caught.value.current["revisionId"] == second["revisionId"]
    assert service.get_thesis("AMD", db_path=path)["core_thesis"] == "B"


def test_delta_generated_for_old_reason_does_not_review_new_reason(tmp_path, monkeypatch):
    from features.thesis_tracking import delta
    path = tmp_path / "market-memory.sqlite3"
    first = _save(path, "A")
    second = {}

    def generate(thesis, **_kwargs):
        second.update(_save(path, "B", first["revisionId"]))
        return {"deltaId": "delta-for-A", "summary": "A의 검토", "verdict": "maintained",
                "generatedAt": "2026-09-28T00:00:00Z"}, "rules"

    monkeypatch.setattr(delta, "gather_local_evidence", lambda *_args, **_kwargs: ([], {}))
    monkeypatch.setattr(delta, "generate_delta", generate)
    service.run_thesis_delta("AMD", {"useLlm": False}, db_path=path)
    current = workspace_view.thesis_workspace_payload("AMD", db_path=path)
    assert current["reasonRevision"]["revisionId"] == second["revisionId"]
    assert current["reasonStatus"] == "unreviewed"
    assert next(row for row in current["reasonConnections"] if row["kind"] == "delta")["relationship"] == "company_change_only"


def test_vault_removing_condition_creates_new_unanswered_revision(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    conn = store.connect(path)
    try:
        store.upsert_thesis(conn, model.Thesis(ticker="AMD", core_thesis="A",
                                               falsification_triggers=["조건"], source="obsidian"))
        first = history.latest(conn, "AMD")
        store.upsert_thesis(conn, model.Thesis(ticker="AMD", core_thesis="B",
                                               falsification_triggers=[], source="obsidian"))
        second = history.latest(conn, "AMD")
        assert second["revisionId"] != first["revisionId"]
        assert second["conditionResponse"] == "unanswered"
        assert store.get_thesis(conn, "AMD")["core_thesis"] == "B"
    finally:
        conn.close()


def test_portfolio_only_foreign_symbol_retains_market_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(overview, "watchlist_overview", lambda: {"items": []})
    monkeypatch.setattr(overview, "get_portfolio", lambda _path: {
        "positions": [{"ticker": "7203.T", "quantity": 1, "name": "Toyota"}]})
    card = overview.reason_watchlist_overview(db_path=tmp_path / "market-memory.sqlite3",
                                               data_path=tmp_path)["items"][0]
    assert card["ticker"] == card["item"] == "7203.T"


def test_condition_response_and_unprovided_fields_are_distinct(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = _save(path, "한 줄", conditionResponse="unknown")
    assert first["conditionResponse"] == "unknown"
    assert first["fieldPresence"] == {"conviction": False, "review_cycle": False}
    second = _save(path, "한 줄", first["revisionId"], conditionResponse="skipped")
    assert second["conditionResponse"] == "skipped"
    assert second["revisionId"] != first["revisionId"]
    third = _save(path, "한 줄", second["revisionId"], conditionResponse="written",
                  falsificationTriggers=["경쟁 제품으로 이탈"])
    assert third["conditionResponse"] == "written"
    assert third["content"]["falsification_triggers"] == ["경쟁 제품으로 이탈"]


def test_legacy_backup_restores_and_first_revision_preserves_row(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    conn = store.connect(path)
    try:
        conn.execute("INSERT INTO thesis(ticker,core_thesis,source) VALUES ('AMD','예전 문장','obsidian')")
        conn.execute("INSERT INTO thesis_delta(delta_id,ticker,summary) VALUES ('delta-1','AMD','old delta')")
        conn.execute("DROP TABLE reason_revision")
        conn.commit()
    finally:
        conn.close()
    reopened = store.connect(path)
    try:
        assert store.get_thesis(reopened, "AMD")["core_thesis"] == "예전 문장"
        imported = history.latest(reopened, "AMD")
        assert imported["content"]["core_thesis"] == "예전 문장"
        assert imported["editSource"] == "legacy_import"
        assert imported["conditionResponse"] == "legacy_unknown"
        assert store.latest_delta(reopened, "AMD")["deltaId"] == "delta-1"
    finally:
        reopened.close()
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as restored:
        assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert restored.execute("SELECT core_thesis FROM thesis WHERE ticker='AMD'").fetchone()[0] == "예전 문장"
        assert restored.execute("SELECT summary FROM thesis_delta WHERE delta_id='delta-1'").fetchone()[0] == "old delta"


def test_current_holdings_change_display_kind_without_rewriting_reason(tmp_path, monkeypatch):
    from features.portfolio import service as portfolio
    from features.thesis_tracking import overview

    path = tmp_path / "market-memory.sqlite3"
    positions = []
    monkeypatch.setattr(portfolio, "get_portfolio", lambda directory=None: {"positions": positions})
    monkeypatch.setattr(overview, "get_portfolio", lambda directory=None: {"positions": positions})
    monkeypatch.setattr(overview, "watchlist_overview", lambda: {"items": [{"item": "AMD", "ticker": "AMD", "companyName": "AMD"}]})
    first = _save(path, "관심 이유")
    assert first["kindAtWrite"] == "interest"
    positions.append({"ticker": "AMD", "quantity": 1, "name": "AMD"})
    cards = overview.reason_watchlist_overview(db_path=path, data_path=tmp_path)["items"]
    assert cards[0]["reasonKind"] == "investment"
    assert cards[0]["reasonRevisionId"] == first["revisionId"]
    assert service.thesis_detail_payload("AMD", db_path=path, sync=False)["reasonRevision"]["kindAtWrite"] == "interest"


def test_no_signal_checkpoint_does_not_become_reason_maintenance(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = _save(path, "고객이 남아 있어서", conditionResponse="written",
                  falsificationTriggers=["고객 이탈"])
    conn = store.connect(path)
    try:
        store.save_thesis_checkpoints(conn, "AMD", [{
            "id": "cp-1", "item": "고객 이탈", "direction": "challenging",
            "matchers": {"tickers": ["AMD"], "keywords": ["고객 이탈"]},
            "status": "open", "createdAt": "2026-09-01T00:00:00Z",
            "lastVerdict": {"verdict": "no_signal", "at": "2026-09-28T00:00:00Z", "evidence": []},
        }])
    finally:
        conn.close()
    payload = workspace_view.thesis_workspace_payload("AMD", db_path=path)
    match = next(row for row in payload["reasonConnections"] if row["kind"] == "checkpoint")
    assert match["status"] == "no_signal"
    assert match["relationship"] == "exact_condition"
    assert match["reasonRevisionId"] == first["revisionId"]
    assert payload["reasonStatus"] == "unreviewed"
