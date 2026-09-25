"""사전작업은 화면이 보여주는 시장 내러티브까지 갱신한다."""
from __future__ import annotations

import pytest

import features.automation.service as service


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    monkeypatch.setattr(service, "import_rssarchive", lambda **kw: {"ok": True})
    monkeypatch.setattr(service, "run_rss_market_memory_update", lambda *a, **k: {"ok": True, "promotedCount": 2})
    monkeypatch.setattr(service, "_append_run", lambda row: None)
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: False)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: False)


def test_the_rule_based_pass_alone_is_not_enough(monkeypatch):
    """**규칙 기반 갱신은 화면을 바꾸지 않는다.**

    시장 내러티브 탭은 `market_state_snapshots`를 읽는데 `run_rss_market_memory_update()`는
    그것을 만들지 않는다 — `market_memory` 행과 regime 카운트만 갱신한다. 실측으로
    스냅샷 이력이 08-12·08-07·08-06으로 띄엄띄엄했고 그 시각에 자동화 기록이 없었다.
    전부 사용자가 버튼을 누른 것이었다.
    """
    calls = []
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda **kw: calls.append("snapshot") or {"ok": True})

    out = service.run_briefing_prerequisites()

    assert calls == ["snapshot"]
    assert out["marketMemory"]["stateSnapshot"] == {"ok": True}


def test_a_fresh_snapshot_is_not_rebuilt(monkeypatch):
    """최근에 돌았으면 건너뛴다. 예약마다 CLI를 다시 부르면 브리핑이 그만큼 늦어진다."""
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: True)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: True)
    calls = []
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda **kw: calls.append("snapshot"))

    out = service.run_briefing_prerequisites()

    assert calls == []
    assert out["marketMemory"]["skipped"] is True
    assert out["marketMemory"]["stateSnapshot"]["skipped"] is True


def test_a_fresh_memory_pass_does_not_hide_a_stale_screen(monkeypatch):
    """**두 신선도는 따로 본다.**

    규칙 갱신이 12시간 안에 돌았다는 이유로 화면 스냅샷까지 건너뛰면, 사전작업이
    도는 날에도 시장 내러티브 탭은 며칠 전 해석 그대로 남는다. 규칙 갱신은 스킵해도
    스냅샷이 오래됐으면 스냅샷은 새로 만든다.
    """
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: True)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: False)
    calls = []
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda **kw: calls.append("snapshot") or {"ok": True})

    out = service.run_briefing_prerequisites()

    assert calls == ["snapshot"]
    assert out["marketMemory"]["skipped"] is True
    assert out["marketMemory"]["stateSnapshot"] == {"ok": True}


def test_snapshot_freshness_reads_the_snapshot_itself(monkeypatch):
    """자동화 실행 기록이 아니라 스냅샷의 `as_of`를 읽는다.

    실행 기록으로 판정하면 사전작업이 스냅샷만 다시 만든 경우가 기록에 없어서
    다음 실행이 또 만든다. 스냅샷은 자기 시각을 알고 있다.
    """
    import datetime as dt

    now = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.timezone.utc)
    import features.market_memory.snapshot as snapshot_module

    monkeypatch.undo()  # 이 테스트는 판정 함수 자체를 본다

    monkeypatch.setattr(
        snapshot_module, "latest_market_state_snapshot_as_of", lambda *a, **k: "2026-08-20T04:00:00+00:00"
    )
    assert service.market_state_snapshot_recently_run(now=now, max_age_hours=12) is True

    monkeypatch.setattr(
        snapshot_module, "latest_market_state_snapshot_as_of", lambda *a, **k: "2026-08-19T18:00:00+00:00"
    )
    assert service.market_state_snapshot_recently_run(now=now, max_age_hours=12) is False

    monkeypatch.setattr(snapshot_module, "latest_market_state_snapshot_as_of", lambda *a, **k: None)
    assert service.market_state_snapshot_recently_run(now=now, max_age_hours=12) is False


def test_a_failed_snapshot_does_not_take_the_briefing_down(monkeypatch):
    """브리핑이 오늘의 결과물이고 스냅샷은 그 앞의 준비다."""
    def boom():
        raise RuntimeError("engine down")

    monkeypatch.setattr(service, "_refresh_market_state_snapshot", service._refresh_market_state_snapshot)
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    import features.agent_mode.bridge as bridge

    monkeypatch.setattr(bridge, "run_agent_task", lambda *a, **k: boom())

    out = service.run_briefing_prerequisites()

    assert out["marketMemory"]["stateSnapshot"]["ok"] is False
    assert out["marketMemory"]["stateSnapshot"]["errorType"] == "RuntimeError"


def test_rules_mode_says_why_instead_of_pretending(monkeypatch):
    """LLM이 시장 해석 문장을 쓰는 산출물이라 규칙으로 대신할 수 있는 것이 아니다."""
    monkeypatch.setattr(service, "default_generation_mode", lambda: "rules")

    result = service._refresh_market_state_snapshot()

    assert result == {"ok": False, "skipped": True, "reason": "rules_mode"}


def test_the_cli_snapshot_step_is_separate_from_medium_memory(monkeypatch):
    """사전작업은 memory 실패 뒤에도 snapshot을 따로 시도할 수 있어야 한다."""
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    seen = {}
    import features.agent_mode.bridge as bridge

    def fake(params=None, **kw):
        seen["params"] = params
        return {"snapshotId": "snap-1"}

    monkeypatch.setattr(bridge, "run_agent_task", lambda task, params=None, **kw: fake(params, task=task, **kw))

    result = service._refresh_market_state_snapshot()

    assert result["ok"] is True
    assert result["snapshotId"] == "snap-1"
    assert "date" in seen["params"]


def test_the_manual_prerequisite_path_shares_one_definition():
    """예약 경로만 스냅샷을 만들고 다른 경로는 안 만드는 식으로 갈라지면 안 된다.

    다만 사용자가 직접 부르는 경로는 신선도로 건너뛰지 않는다 — 눌러도 아무 일이
    없는 버튼이 되면 안 된다.
    """
    import inspect

    source = inspect.getsource(service.run_automation_once)

    assert "result = run_briefing_prerequisites(force=True)" in source
    assert "rss = import_rssarchive(run_collection=True)\n            memory = run_rss" not in source




def test_an_explicit_run_ignores_the_freshness_guard(monkeypatch):
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: True)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: True)
    calls = []
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda **kw: calls.append("snapshot") or {"ok": True})

    skipped = service.run_briefing_prerequisites()
    forced = service.run_briefing_prerequisites(force=True)

    assert skipped["marketMemory"].get("skipped") is True
    assert forced["marketMemory"].get("skipped") is not True
    assert calls == ["snapshot"]


def test_snapshot_step_is_always_snapshot_only(monkeypatch):
    """메모리가 신선하면 CLI 2단계 작업을 다시 돌리지 않는다.

    전체 작업은 중기 메모리 갱신까지 포함한다 — 가드가 방금 "최근이라 건너뛴다"고
    판정한 바로 그 작업이다. 그것을 다시 부르면 아끼려던 비용을 그대로 치른다.
    """
    calls = []
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    monkeypatch.setattr(service, "kst_date", lambda: "2026-08-21")

    import features.agent_mode.bridge as bridge

    monkeypatch.setattr(bridge, "run_agent_task", lambda task, params=None, **kw: calls.append(f"only:{task}") or {"snapshotId": "s1"})
    monkeypatch.setattr(bridge, "run_market_memory_update_task", lambda params=None, **kw: calls.append("full") or {"snapshotId": "s2"})

    fresh = service._refresh_market_state_snapshot(memory_is_fresh=True)
    assert fresh["snapshotId"] == "s1"
    assert calls == ["only:market_state_snapshot"]

    calls.clear()
    stale = service._refresh_market_state_snapshot()
    assert stale["snapshotId"] == "s1"
    assert calls == ["only:market_state_snapshot"]


def test_a_failed_snapshot_is_not_retried_every_schedule(monkeypatch):
    """실패한 스냅샷을 예약마다 다시 시도하지 않는다.

    어댑터가 죽어 있으면 `market_state_snapshot_recently_run()`이 영원히 거짓이라,
    유예가 없으면 브리핑 예약이 돌 때마다 수십 초짜리 CLI가 무한히 재시도된다.
    """
    now = service.dt.datetime(2026, 8, 21, 12, 0, 0)
    runs = [{
        "kind": "marketStateSnapshot",
        "status": "failed",
        "finishedAt": "2026-08-21T09:00:00",
    }]

    assert service.market_state_snapshot_recently_failed(now=now, runs=runs) is True

    # 유예가 지나면 다시 시도한다.
    old = [{"kind": "marketStateSnapshot", "status": "failed", "finishedAt": "2026-08-20T09:00:00"}]
    assert service.market_state_snapshot_recently_failed(now=now, runs=old) is False

    # 성공한 기록은 유예 대상이 아니다.
    ok = [{"kind": "marketStateSnapshot", "status": "done", "finishedAt": "2026-08-21T09:00:00"}]
    assert service.market_state_snapshot_recently_failed(now=now, runs=ok) is False


def test_an_explicit_run_ignores_the_failure_backoff(monkeypatch):
    """사용자가 직접 누른 실행은 유예를 보지 않는다 — 눌러도 아무 일이 없으면 안 된다."""
    calls = []
    monkeypatch.setattr(service, "import_rssarchive", lambda run_collection=True: "rss-ok")
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: True)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: False)
    monkeypatch.setattr(service, "market_state_snapshot_recently_failed", lambda **kw: True)
    monkeypatch.setattr(service, "_run_market_state_snapshot_step", lambda **kw: calls.append("snapshot") or {"ok": True})
    monkeypatch.setattr(service, "run_rss_market_memory_update", lambda: {"ok": True})
    monkeypatch.setattr(service, "_append_run", lambda row: None)

    service.run_briefing_prerequisites(force=True)

    assert calls == ["snapshot"]




def test_stale_cli_prerequisite_runs_memory_then_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    import features.agent_mode.bridge as bridge

    monkeypatch.setattr(
        bridge,
        "run_agent_task",
        lambda task, *a, **k: calls.append(task) or {"ok": True, "snapshotId": "s1"},
    )
    monkeypatch.setattr(service, "_run_market_state_snapshot_step", service._run_market_state_snapshot_step)

    service.run_briefing_prerequisites()

    assert calls == ["market_memory_llm", "market_state_snapshot"]


def test_memory_failure_still_attempts_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    import features.agent_mode.bridge as memory_service

    monkeypatch.setattr(memory_service, "run_agent_task", lambda *a, **k: calls.append("memory") or {"ok": False})
    monkeypatch.setattr(service, "_run_market_state_snapshot_step", lambda **kw: calls.append("snapshot") or {"ok": True})

    out = service.run_briefing_prerequisites()

    assert calls == ["memory", "snapshot"]
    assert out["marketMemory"]["ok"] is False
    assert out["marketMemory"]["stateSnapshot"] == {"ok": True}


def test_stale_memory_still_runs_but_recent_snapshot_failure_skips_only_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    import features.agent_mode.bridge as memory_service

    monkeypatch.setattr(memory_service, "run_agent_task", lambda *a, **k: calls.append("memory") or {"ok": True})
    monkeypatch.setattr(service, "market_state_snapshot_recently_failed", lambda **kw: True)
    monkeypatch.setattr(service, "_run_market_state_snapshot_step", lambda **kw: calls.append("snapshot") or {"ok": True})

    out = service.run_briefing_prerequisites()

    assert calls == ["memory"]
    assert out["marketMemory"]["stateSnapshot"]["reason"] == "recent_failure"
    assert out["marketMemory"]["stateSnapshot"]["skipped"] is True
