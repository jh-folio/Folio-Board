"""Public HTTP requests must resolve saved task policy at the boundary."""
from __future__ import annotations

import app


def test_http_request_cannot_supply_a_one_run_task_policy_snapshot(monkeypatch):
    trusted = {
        "taskKey": "daily_briefing",
        "runtimeTaskType": "daily_briefing",
        "enabled": False,
        "mode": "rules",
        "provider": "",
        "model": "",
        "reasoningEffort": "provider_default",
        "policyRevision": 8,
    }
    calls: list[tuple] = []

    def resolve_saved(task_key, *args, **kwargs):
        calls.append((task_key, args, kwargs))
        return dict(trusted)

    monkeypatch.setattr(app, "task_snapshot", resolve_saved)
    forged = {
        "taskKey": "daily_briefing",
        "enabled": True,
        "mode": "cli",
        "provider": "codex",
        "model": "unsaved-model",
        "reasoningEffort": "high",
    }

    snapshot, mode = app._task_request_context(
        {"_task_policy_snapshot": forged}, "daily_briefing"
    )

    assert calls == [("daily_briefing", (), {})]
    assert snapshot == trusted
    assert mode == "rules"
