"""관련 새 소식(사실 projection)과 AI 다듬기의 대조 단어 등록 계약."""
import pytest

from features.thesis_tracking import reason_assist as assist
from features.thesis_tracking import reason_news
from features.thesis_tracking import reason_review as reviews
from features.thesis_tracking import service
from features.thesis_tracking import store
from features.thesis_tracking import workspace_view

CONDITION = "주요 고객이 자체 칩으로 빠르게 이동할 때"


def _save_checkpoint(path, *, item=CONDITION, evidence=None, keywords=("자체 칩", "custom chip")):
    conn = store.connect(path)
    try:
        current = store.get_thesis(conn, "NVDA")
        checkpoint = {
            "item": item, "direction": "challenging",
            "matchers": {"tickers": ["NVDA"], "keywords": list(keywords)},
            "status": "challenged", "createdAt": "2026-09-01T00:00:00Z",
            "lastVerdict": {"verdict": "challenged", "at": "2026-09-30T00:00:00Z", "evidence": evidence or []},
        }
        # 판정 pass처럼 같은 문장의 항목은 근거만 갈아 끼운다.
        kept = [row for row in (current.get("next_checkpoints") or []) if not (isinstance(row, dict) and row.get("item") == item)]
        store.save_thesis_checkpoints(conn, "NVDA", [*kept, checkpoint])
    finally:
        conn.close()


def _write_reason(path, **extra):
    return service.upsert_manual_thesis({"ticker": "NVDA", "company": "NVIDIA", "coreThesis": "수요가 오래 간다",
                                         "falsificationTriggers": [CONDITION], "conditionResponse": "written", **extra},
                                        db_path=path)


def _news(path):
    return workspace_view.thesis_workspace_payload("NVDA", db_path=path)["news"]


def test_news_comes_only_from_checkpoints_that_match_the_written_condition(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    written = _write_reason(path)
    day = written["reasonRevision"]["recordedAt"][:10]
    _save_checkpoint(path, evidence=[
        {"docId": "https://example.com/a", "date": day, "title": "Big customer moves to custom chip"},
        {"docId": "local/file.md", "date": day, "title": "Second headline"},
        {"docId": "https://example.com/old", "date": "2000-01-01", "title": "Before the reason was written"},
    ])
    _save_checkpoint(path, item="다른 조건", evidence=[{"docId": "https://example.com/x", "date": day, "title": "Unrelated"}],
                     keywords=("다른",))
    news = _news(path)
    assert news["searchReady"] is True
    assert news["count"] == 2
    assert [row["title"] for row in news["items"]] == ["Second headline", "Big customer moves to custom chip"]
    # 파일 경로는 원문 링크가 아니다 — 화면은 "원문 없음"으로 보여 준다.
    assert {row["title"]: row["url"] for row in news["items"]} == {
        "Second headline": "", "Big customer moves to custom chip": "https://example.com/a"}
    assert news["keywords"] == ["자체 칩", "custom chip"]


def test_keep_decision_acknowledges_exactly_the_seen_news(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    written = _write_reason(path)
    day = written["reasonRevision"]["recordedAt"][:10]
    _save_checkpoint(path, evidence=[{"docId": "https://example.com/a", "date": day, "title": "Headline"}])
    seen = _news(path)["items"]
    reviews.complete_manual_review("NVDA", {
        "expectedRevisionId": written["reasonRevision"]["revisionId"], "outcome": "no_material_change",
        "checkedScope": ["관련 새 소식 1건 제목 확인"],
        "basisRefs": [{k: row[k] for k in ("key", "title", "date", "url")} for row in seen],
    }, db_path=path)
    news = _news(path)
    assert news["count"] == 0
    assert news["lastDecisionAt"]
    # 같은 제목이라도 다른 URL은 다른 소식이다.
    _save_checkpoint(path, evidence=[{"docId": "https://example.com/b", "date": day, "title": "Headline"}])
    assert _news(path)["count"] == 1


def test_editing_the_reason_with_attached_news_does_not_recount_them(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    written = _write_reason(path)
    day = written["reasonRevision"]["recordedAt"][:10]
    long_url = "https://example.com/" + "a" * 300
    _save_checkpoint(path, evidence=[{"docId": long_url, "date": day, "title": "Long url headline"},
                                     {"docId": "", "date": day, "title": "No url headline"}])
    items = _news(path)["items"]
    service.upsert_manual_thesis({
        "ticker": "NVDA", "coreThesis": "수요가 오래 가지만 고객 전환을 본다", "falsificationTriggers": [CONDITION],
        "conditionResponse": "written", "expectedRevisionId": written["reasonRevision"]["revisionId"],
        # 화면이 보내는 모양: id는 200자에서 잘리고 url은 따로 간다.
        "basisRefs": [{"id": row["key"][:200], "title": row["title"], **({"url": row["url"]} if row["url"] else {})} for row in items],
    }, db_path=path)
    assert _news(path)["count"] == 0


def test_shared_long_url_prefix_does_not_acknowledge_a_different_article(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    written = _write_reason(path)
    day = written["reasonRevision"]["recordedAt"][:10]
    prefix = "https://example.com/" + "a" * 250
    first, second = prefix + "-first", prefix + "-second"
    _save_checkpoint(path, evidence=[{"docId": first, "date": day, "title": "First"}])
    [seen] = _news(path)["items"]
    assert len(seen["key"]) < 200
    service.upsert_manual_thesis({
        "ticker": "NVDA", "coreThesis": "새 이유", "falsificationTriggers": [CONDITION],
        "conditionResponse": "written", "expectedRevisionId": written["reasonRevision"]["revisionId"],
        "basisRefs": [{"id": seen["key"], "title": seen["title"], "url": seen["url"]}],
    }, db_path=path)
    _save_checkpoint(path, evidence=[{"docId": second, "date": day, "title": "Second"}])
    assert [row["url"] for row in _news(path)["items"]] == [second]


def test_no_keywords_means_not_searching_rather_than_no_news(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    _write_reason(path)
    news = _news(path)
    assert news == {**news, "searchReady": False, "count": 0, "items": []}


def test_list_overview_counts_news_instead_of_process_status(tmp_path, monkeypatch):
    from features.thesis_tracking import overview

    path = tmp_path / "market-memory.sqlite3"
    written = _write_reason(path)
    _save_checkpoint(path, evidence=[{"docId": "https://example.com/a", "date": written["reasonRevision"]["recordedAt"][:10], "title": "H"}])
    monkeypatch.setattr(overview, "watchlist_overview", lambda: {"items": [{"item": "NVIDIA", "ticker": "NVDA"}]})
    monkeypatch.setattr(overview, "get_portfolio", lambda directory: {"positions": []})
    cards = overview.reason_watchlist_overview(db_path=path, data_path=tmp_path)["items"]
    assert cards[0]["reasonNewsCount"] == 1


def _fake_cli(monkeypatch, output, prompts=None):
    monkeypatch.setattr(assist, "ai_agent_enabled", lambda: True)
    monkeypatch.setattr(assist, "ai_agent_mode", lambda: "cli")
    monkeypatch.setattr(assist, "selected_cli_config", lambda: {"provider": "codex", "model": "m", "reasoningEffort": "high"})
    monkeypatch.setattr(assist.bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(assist, "_fundamentals_context", lambda ticker: {"source": "yfinance 분기 실적", "quarters": [
        {"quarter": "2026-07-31", "revenue": 100, "operatingIncome": 66, "operatingMarginPct": 66.0}]})
    monkeypatch.setattr(assist.bridge, "run_agent_prompt",
                        lambda prompt, **kwargs: (prompts.append(prompt) if prompts is not None else None) or {"output": output})


def test_ai_draft_uses_folio_data_and_approval_registers_condition_search(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    first = service.upsert_manual_thesis({"ticker": "NVDA", "company": "NVIDIA", "coreThesis": "돈을 잘 벌어서"}, db_path=path)
    token = first["reasonRevision"]["revisionId"]
    prompts: list = []
    _fake_cli(monkeypatch, '{"suggestedReason":"이익이 함께 커져서","reasonBasis":"영업이익률 66.0%",'
                           '"suggestedCondition":"분기 영업이익률이 두 분기 연속 낮아질 때",'
                           '"conditionBasis":"실적으로 확인. 두 분기는 제안",'
                           '"conditionKeywords":["NVDA","NVIDIA","margin","이익률 하락","x"]}', prompts)
    preview = assist.reason_assist("NVDA", {"phase": "draft", "expectedRevisionId": token,
                                            "draftReason": "돈을 잘 벌어서", "draftCondition": "남는 돈이 줄면"}, db_path=path)
    assert '"operatingMarginPct": 66.0' in prompts[0]
    assert preview["reasonBasis"] == "영업이익률 66.0%"
    # 티커·회사명과 한 글자 단어는 대조 단어가 될 수 없다.
    assert preview["conditionKeywords"] == ["margin", "이익률 하락"]
    body = {"expectedRevisionId": token, "previewToken": preview["previewToken"],
            "suggestedReason": preview["suggestedReason"], "suggestedCondition": preview["suggestedCondition"],
            "conditionKeywords": preview["conditionKeywords"],
            "coreThesis": preview["suggestedReason"], "conditionText": preview["suggestedCondition"]}
    with pytest.raises(ValueError, match="invalid_reason_preview"):
        assist.approve_reason_draft("NVDA", {**body, "conditionKeywords": ["위조"]}, db_path=path)
    assist.approve_reason_draft("NVDA", body, db_path=path)
    news = _news(path)
    assert news["searchReady"] is True
    assert news["keywords"] == ["margin", "이익률 하락"]
    payload = workspace_view.thesis_workspace_payload("NVDA", db_path=path)
    [checkpoint] = payload["checkpoints"]["structured"]
    # 생성 경로라 판정 상태를 물려받지 않는다.
    assert checkpoint["status"] == "open" and checkpoint["lastVerdict"] is None


def test_ai_reason_only_does_not_attach_suggestion_keywords_to_user_condition(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    first = _write_reason(path)
    token = first["reasonRevision"]["revisionId"]
    _fake_cli(monkeypatch, '{"suggestedReason":"수요가 이어진다","suggestedCondition":"이익률이 낮아질 때",'
                           '"conditionKeywords":["margin"]}')
    preview = assist.reason_assist("NVDA", {"phase": "draft", "expectedRevisionId": token,
                                           "draftReason": "수요가 오래 간다", "draftCondition": CONDITION}, db_path=path)
    assist.approve_reason_draft("NVDA", {
        "expectedRevisionId": token, "previewToken": preview["previewToken"],
        "suggestedReason": preview["suggestedReason"], "suggestedCondition": preview["suggestedCondition"],
        "conditionKeywords": preview["conditionKeywords"], "coreThesis": preview["suggestedReason"],
        "conditionText": CONDITION,
    }, db_path=path)
    assert _news(path)["searchReady"] is False
    conn = store.connect(path)
    try:
        assert not conn.execute("SELECT next_checkpoints_json FROM thesis WHERE ticker='NVDA'").fetchone()[0].count("margin")
    finally:
        conn.close()


def test_ai_approval_rolls_back_reason_if_condition_registration_fails(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    first = _write_reason(path)
    token = first["reasonRevision"]["revisionId"]
    _fake_cli(monkeypatch, '{"suggestedReason":"새 이유","suggestedCondition":"고객이 자체 칩으로 이동할 때",'
                           '"conditionKeywords":["custom chip"]}')
    preview = assist.reason_assist("NVDA", {"phase": "draft", "expectedRevisionId": token,
                                           "draftReason": "수요가 오래 간다", "draftCondition": CONDITION}, db_path=path)
    def fail_checkpoint(*args, **kwargs):
        raise OSError("checkpoint_write_failed")
    monkeypatch.setattr(store, "save_thesis_checkpoints", fail_checkpoint)
    with pytest.raises(OSError, match="checkpoint_write_failed"):
        assist.approve_reason_draft("NVDA", {
            "expectedRevisionId": token, "previewToken": preview["previewToken"],
            "suggestedReason": preview["suggestedReason"], "suggestedCondition": preview["suggestedCondition"],
            "conditionKeywords": preview["conditionKeywords"], "coreThesis": preview["suggestedReason"],
            "conditionText": preview["suggestedCondition"],
        }, db_path=path)
    current = workspace_view.thesis_workspace_payload("NVDA", db_path=path)
    assert current["reasonRevision"]["revisionId"] == token
    assert current["thesis"]["coreThesis"] == "수요가 오래 간다"


def test_news_key_prefers_url_then_date_and_title():
    assert reason_news.news_key({"docId": "https://a.example/x", "date": "2026-09-30", "title": "T"}) == "https://a.example/x"
    assert reason_news.news_key({"docId": "local/path.md", "date": "2026-09-30", "title": " T "}) == "2026-09-30|t"
