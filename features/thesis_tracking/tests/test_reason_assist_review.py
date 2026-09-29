"""R2/R3 bounded proposal and exact-review contracts, without a real CLI."""
import pytest

from features.thesis_tracking import reason_assist as assist
from features.thesis_tracking import reason_history as history
from features.thesis_tracking import reason_review as reviews
from features.thesis_tracking import service
from features.thesis_tracking import workspace_view


def _fake_cli(monkeypatch, output):
    monkeypatch.setattr(assist, "ai_agent_enabled", lambda: True)
    monkeypatch.setattr(assist, "ai_agent_mode", lambda: "cli")
    monkeypatch.setattr(assist, "selected_cli_config", lambda: {"provider": "codex", "model": "gpt-6-sol", "reasoningEffort": "high"})
    monkeypatch.setattr(assist.bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(assist.bridge, "run_agent_prompt", lambda prompt, **kwargs: {"output": output})
    # 실적 참고 자료는 네트워크 조회라 테스트에서 막는다.
    monkeypatch.setattr(assist, "_fundamentals_context", lambda ticker: {})


def test_ai_question_is_one_at_a_time_and_does_not_write(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    _fake_cli(monkeypatch, '{"question":"무엇이 바뀌면 생각이 달라질까요?"}')
    result = assist.reason_assist("AMD", {"phase": "question", "expectedRevisionId": "",
                                          "draftReason": "제품이 좋아서", "draftCondition": "", "answers": []}, db_path=path)
    assert result["question"] == "무엇이 바뀌면 생각이 달라질까요?"
    assert service.get_thesis("AMD", db_path=path) is None


def test_ai_uses_one_global_cli_configuration(tmp_path, monkeypatch):
    _fake_cli(monkeypatch, '{"question":"한 가지만 묻습니다"}')
    calls = []
    monkeypatch.setattr(assist.bridge, "run_agent_prompt", lambda prompt, **kwargs: calls.append(kwargs) or {"output": '{"question":"한 가지만 묻습니다"}'})
    assist.reason_assist("AMD", {"phase": "question", "expectedRevisionId": "", "draftReason": "원문"},
                         db_path=tmp_path / "market-memory.sqlite3")
    assert calls == [{"web_search": False, "max_output_chars": 5000, "adapter": "codex",
                      "model": "gpt-6-sol", "reasoning_effort": "high"}]


def test_ai_prescriptive_output_is_rejected_without_a_write(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    _fake_cli(monkeypatch, '{"suggestedReason":"지금 매수하세요", "suggestedCondition":""}')
    with pytest.raises(ValueError, match="prescriptive_reason_assist_output"):
        assist.reason_assist("AMD", {"phase": "draft", "expectedRevisionId": "", "draftReason": "원문"}, db_path=path)
    assert service.get_thesis("AMD", db_path=path) is None


def test_ai_preview_approval_is_explicit_and_cas_protected(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    first = service.upsert_manual_thesis({"ticker": "AMD", "coreThesis": "원문"}, db_path=path)
    token = first["reasonRevision"]["revisionId"]
    _fake_cli(monkeypatch, '{"suggestedReason":"원문을 조금 정리", "suggestedCondition":"고객이 떠나면", "uncertainties":["해지율"]}')
    preview = assist.reason_assist("AMD", {"phase": "draft", "expectedRevisionId": token,
                                           "draftReason": "원문", "draftCondition": "", "answers": []}, db_path=path)
    assert service.get_thesis("AMD", db_path=path)["core_thesis"] == "원문"
    body = {"expectedRevisionId": token, "previewToken": preview["previewToken"],
            "suggestedReason": preview["suggestedReason"], "suggestedCondition": preview["suggestedCondition"],
            "coreThesis": "사용자가 고친 제안", "conditionText": "고객이 떠나면"}
    with pytest.raises(ValueError, match="invalid_reason_preview"):
        assist.approve_reason_draft("AMD", {**body, "suggestedReason": "위조"}, db_path=path)
    approved = assist.approve_reason_draft("AMD", body, db_path=path)
    assert approved["thesis"]["reasonRevision"]["editSource"] == "agent_approved"
    assert service.get_thesis("AMD", db_path=path)["core_thesis"] == "사용자가 고친 제안"
    with pytest.raises(history.ReasonRevisionConflictError):
        assist.approve_reason_draft("AMD", body, db_path=path)


def test_ai_approval_saves_user_edited_advanced_fields(tmp_path, monkeypatch):
    path = tmp_path / "market-memory.sqlite3"
    first = service.upsert_manual_thesis({"ticker": "AMD", "coreThesis": "원문"}, db_path=path)
    token = first["reasonRevision"]["revisionId"]
    _fake_cli(monkeypatch, '{"suggestedReason":"원문 정리","suggestedCondition":""}')
    preview = assist.reason_assist("AMD", {"phase": "draft", "expectedRevisionId": token,
                                          "draftReason": "원문", "draftCondition": ""}, db_path=path)
    approved = assist.approve_reason_draft("AMD", {
        "expectedRevisionId": token, "previewToken": preview["previewToken"],
        "suggestedReason": preview["suggestedReason"], "suggestedCondition": preview["suggestedCondition"],
        "coreThesis": "원문 정리", "conditionText": "", "keyAssumptions": ["새 가정"],
        "conviction": "high", "reviewCycle": "monthly",
    }, db_path=path)["thesis"]
    assert approved["key_assumptions"] == ["새 가정"]
    assert approved["conviction"] == "high"
    assert approved["review_cycle"] == "monthly"


def test_manual_review_attaches_exact_revision_and_read_does_not_complete(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = service.upsert_manual_thesis({"ticker": "AMD", "coreThesis": "A"}, db_path=path)
    token = first["reasonRevision"]["revisionId"]
    assert workspace_view.thesis_workspace_payload("AMD", db_path=path)["reasonStatus"] == "unreviewed"
    event = reviews.complete_manual_review("AMD", {"expectedRevisionId": token,
                                                   "outcome": "no_new_material", "checkedScope": ["로컬 뉴스"]}, db_path=path)
    assert event["reasonRevisionId"] == token
    assert event["checkedScope"] == ["로컬 뉴스"]
    assert workspace_view.thesis_workspace_payload("AMD", db_path=path)["reasonStatus"] == "evidence_gap"
    second = service.upsert_manual_thesis({"ticker": "AMD", "coreThesis": "B", "expectedRevisionId": token}, db_path=path)
    assert workspace_view.thesis_workspace_payload("AMD", db_path=path)["reasonStatus"] == "unreviewed"
    with pytest.raises(history.ReasonRevisionConflictError):
        reviews.complete_manual_review("AMD", {"expectedRevisionId": token,
                                               "outcome": "reviewed", "checkedScope": ["로컬 뉴스"]}, db_path=path)
    assert second["reasonRevision"]["revisionId"] != token


def test_review_requires_actual_scope_and_keeps_reason_intact(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    first = service.upsert_manual_thesis({"ticker": "AMD", "coreThesis": "원문"}, db_path=path)
    with pytest.raises(ValueError, match="invalid_checked_scope"):
        reviews.complete_manual_review("AMD", {"expectedRevisionId": first["reasonRevision"]["revisionId"],
                                               "outcome": "reviewed", "checkedScope": []}, db_path=path)
    assert service.get_thesis("AMD", db_path=path)["core_thesis"] == "원문"
