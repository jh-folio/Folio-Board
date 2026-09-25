"""Agent Dock Stage A: job이 실제 phase/타이밍/fallback 원인을 정직하게 보여주는지 검사한다.

`plan/AGENT_DOCK_CONVERSATION_UPGRADE_PLAN.md` Stage A Gate 세 가지를 그대로 검사한다.
1) queue wait(wait_engine)와 CLI time(generate)의 합이 total과 설명 가능하게 맞는다.
2) rules fallback이 `done + finalEngine=rules + fallbackReason`으로 식별된다.
3) transcript/질문/검색어/stdout/stderr가 jobs/Work Log에 없다는 canary 테스트가 통과한다.

`bridge._invoke_agent_cli`만 가짜로 바꿔 실제 `run_agent_prompt()`(세마포어·진단
스테이지 포함)가 그대로 돌게 한다 — Stage A가 추가한 배선(job_runtime.py의
`progress()` 호출, `jobs.stage_timing_summary()`)까지 실측한다.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from features.agent_mode import bridge, job_runtime
from features.agent_mode.consultation_store import append_user_message, create_session
from features.agent_mode.work_log_schema import WorkLogFilter
from features.agent_mode.work_log_store import WorkLogStore
from features.agent_mode.work_log_view import WorkLogView
from features.common import jobs


QUESTION_CANARY = "STAGE_A_QUESTION_CANARY_전력망_병목_상세_질문"
REPLY_CANARY = "STAGE_A_REPLY_CANARY_전력_공급_제약이_병목입니다"

TIMING_KEYS = ("queueWaitMs", "contextMs", "cliMs", "postprocessMs", "totalMs")


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


def _delayed_cli(output: str, *, delay: float = 0.01, fail: bool = False):
    def invoke(selected, prompt, timeout, job_id="", **_kwargs):
        time.sleep(delay)
        if fail:
            raise RuntimeError("cli exploded")
        return output
    return invoke


def test_a_successful_cli_answer_reports_explainable_timing(monkeypatch, tmp_path):
    _isolated_jobs(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(bridge, "_select_adapter", lambda adapter: {"id": "codex", "executable": "codex"})
    monkeypatch.setattr(bridge, "_invoke_agent_cli", _delayed_cli(REPLY_CANARY, delay=0.05))

    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    appended = append_user_message(tmp_path, session["id"], QUESTION_CANARY, operation_id="op-timing")

    job = _submit_and_wait(tmp_path, session["id"], appended["message"]["id"])

    assert job["status"] == "done"
    assert job["finalEngine"] == "cli"
    assert job["adapter"] == "codex"
    assert job["fallbackReason"] is None
    for key in TIMING_KEYS:
        assert isinstance(job[key], int) and job[key] >= 0, key
    assert job["totalMs"] >= job["queueWaitMs"] + job["contextMs"] + job["cliMs"] + job["postprocessMs"]
    # The fake CLI itself sleeps 50ms inside the "generate" diagnostic boundary
    # — a wide margin so this doesn't flake under a loaded full-suite run.
    assert job["cliMs"] >= 25


def test_a_cli_failure_reports_rules_fallback_honestly(monkeypatch, tmp_path):
    _isolated_jobs(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(bridge, "_select_adapter", lambda adapter: {"id": "codex", "executable": "codex"})
    monkeypatch.setattr(bridge, "_invoke_agent_cli", _delayed_cli("unused", delay=0.0, fail=True))

    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    appended = append_user_message(tmp_path, session["id"], "질문", operation_id="op-fail")

    job = _submit_and_wait(tmp_path, session["id"], appended["message"]["id"])

    # Before Stage A this always showed the untouched defaults (adapter: auto,
    # finalEngine: null) even though a real CLI failure had just happened.
    assert job["status"] == "done"
    assert job["finalEngine"] == "rules"
    assert job["adapter"] == "rules"
    assert job["fallbackReason"] == "engine_failed"


def test_question_and_reply_never_appear_in_the_job_or_work_log(monkeypatch, tmp_path):
    store = _isolated_jobs(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(bridge, "_select_adapter", lambda adapter: {"id": "codex", "executable": "codex"})
    monkeypatch.setattr(bridge, "_invoke_agent_cli", _delayed_cli(REPLY_CANARY, delay=0.0))

    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    appended = append_user_message(tmp_path, session["id"], QUESTION_CANARY, operation_id="op-canary")

    job = _submit_and_wait(tmp_path, session["id"], appended["message"]["id"])
    job_text = json.dumps(job, ensure_ascii=False)
    assert QUESTION_CANARY not in job_text
    assert REPLY_CANARY not in job_text

    control_store = WorkLogStore(tmp_path / "agent-work-log.json", clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    view = WorkLogView(store, control_store, tmp_path / "agent-proposals")
    listing = view.list(limit=50, offset=0, kind=WorkLogFilter.ALL)
    work_log_text = json.dumps(listing, ensure_ascii=False)
    assert QUESTION_CANARY not in work_log_text
    assert REPLY_CANARY not in work_log_text

    entry = listing["entries"][0]
    assert entry["jobId"] == job["id"]
    for key in ("queueWaitMs", "contextMs", "cliMs", "postprocessMs", "totalMs"):
        assert key in entry
