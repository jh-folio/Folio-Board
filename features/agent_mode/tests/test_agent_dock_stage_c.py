"""Agent Dock Stage C: 완료된 답변을 전체 스레드 재조회 없이 단일 메시지로 읽을 수 있는지 검사한다.

`plan/AGENT_DOCK_CONVERSATION_UPGRADE_PLAN.md` Gate C의 "완료 후 답변 로드는
full-thread GET 없이 단일 bounded fetch로 끝난다"를 백엔드 쪽에서 검증한다:
job의 `result.assistantMessageId`가 실제로 그 메시지를 가리키는지, 새 단일 메시지
엔드포인트가 정확히 그 내용을 돌려주는지, 옛 job 레코드(이 필드가 없는)도 여전히
읽히는지.
"""
from __future__ import annotations

from pathlib import Path

from features.agent_mode import bridge, job_runtime
from features.agent_mode.consultation_store import append_user_message, create_session, get_message
from features.common import jobs
from features.common.shared_jobs_schema import CompanionProjection


REPLY_TEXT = "STAGE_C_REPLY_전력망_투자_확대_배경"


def _isolated_jobs(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(jobs, "JOBS_PATH", tmp_path / "jobs.json")
    jobs._LIFECYCLES.clear()
    return jobs._store()


def _submit_and_wait(tmp_path, session_id, message_id, *, timeout=5.0):
    job = job_runtime.submit_consultation_job(tmp_path, session_id, message_id)
    future = jobs.FUTURES[job["id"]]
    future.join(timeout=timeout)
    assert not future.is_alive(), "consultation job did not finish in time"
    return jobs.get_job(job["id"])


def test_job_result_names_the_exact_assistant_message_it_produced(monkeypatch, tmp_path):
    _isolated_jobs(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(bridge, "_select_adapter", lambda adapter: {"id": "codex", "executable": "codex"})
    monkeypatch.setattr(bridge, "_invoke_agent_cli", lambda *a, **k: REPLY_TEXT)

    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    appended = append_user_message(tmp_path, session["id"], "질문", operation_id="op-1")

    job = _submit_and_wait(tmp_path, session["id"], appended["message"]["id"])

    assistant_message_id = job["result"]["assistantMessageId"]
    assert assistant_message_id
    assert job["result"]["sessionId"] == session["id"]

    fetched = get_message(tmp_path, session["id"], assistant_message_id)
    assert fetched is not None
    assert fetched["content"] == REPLY_TEXT
    assert fetched["role"] == "assistant"


def test_get_message_returns_none_for_an_unknown_message(tmp_path):
    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    append_user_message(tmp_path, session["id"], "질문", operation_id="op-2")
    assert get_message(tmp_path, session["id"], "msg-does-not-exist") is None
    assert get_message(tmp_path, "session-does-not-exist", "msg-anything") is None


def test_companion_projection_without_stage_c_fields_still_validates():
    """Stage C 이전에 저장된 job 레코드(이 두 필드가 아예 없는)도 그대로 읽힌다."""
    dumped = {
        "status": "done", "requestedMode": "cli", "attemptedEngine": "cli", "finalEngine": "cli",
        "fallbackReason": None, "adapter": "codex", "mode": "answer", "proposalId": None,
    }
    restored = CompanionProjection.model_validate(dumped)
    assert restored.sessionId is None
    assert restored.assistantMessageId is None
