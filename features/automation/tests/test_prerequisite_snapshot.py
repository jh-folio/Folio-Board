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
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda: calls.append("snapshot") or {"ok": True})

    out = service.run_briefing_prerequisites()

    assert calls == ["snapshot"]
    assert out["marketMemory"]["stateSnapshot"] == {"ok": True}


def test_a_fresh_snapshot_is_not_rebuilt(monkeypatch):
    """최근에 돌았으면 건너뛴다. 예약마다 CLI를 다시 부르면 브리핑이 그만큼 늦어진다."""
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: True)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: True)
    calls = []
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda: calls.append("snapshot"))

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
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda: calls.append("snapshot") or {"ok": True})

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

    monkeypatch.setattr(bridge, "run_market_memory_update_task", lambda *a, **k: boom())

    out = service.run_briefing_prerequisites()

    assert out["marketMemory"]["stateSnapshot"]["ok"] is False
    assert out["marketMemory"]["stateSnapshot"]["errorType"] == "RuntimeError"


def test_rules_mode_says_why_instead_of_pretending(monkeypatch):
    """LLM이 시장 해석 문장을 쓰는 산출물이라 규칙으로 대신할 수 있는 것이 아니다."""
    monkeypatch.setattr(service, "default_generation_mode", lambda: "rules")

    result = service._refresh_market_state_snapshot()

    assert result == {"ok": False, "skipped": True, "reason": "rules_mode"}


def test_the_cli_path_uses_the_same_two_step_task_as_the_button(monkeypatch):
    """버튼과 다른 경로를 만들면 둘이 서로 다른 스냅샷을 만들게 된다."""
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm_cli")
    seen = {}
    import features.agent_mode.bridge as bridge

    def fake(params=None, **kw):
        seen["params"] = params
        return {"snapshotId": "snap-1"}

    monkeypatch.setattr(bridge, "run_market_memory_update_task", fake)

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


def test_the_api_path_uses_the_same_attempt_lifecycle_as_the_button(monkeypatch):
    """API(LLM) 모드도 버튼과 같은 attempt/watermark 라이프사이클을 탄다.

    바로 저장하면 attempt 기록이 없는 스냅샷이 남아 reconcile이 중단된 갱신을
    복구할 근거를 잃는다. scope는 예약이 고른 시장과 무관한 GLOBAL이다 — 화면의
    시장 내러티브는 시장별 보고서가 아니라 하나의 해석이다.
    """
    monkeypatch.setattr(service, "default_generation_mode", lambda: "llm")
    seen = {}

    class FakeService:
        def run_manual(self, command):
            seen["scope"] = command.scope
            seen["date"] = command.date
            return {"ok": True, "snapshot": {"id": "snap-9"}, "attempt": {"attemptId": "att-3"}}

    import features.market_memory.http_runtime as http_runtime

    monkeypatch.setattr(http_runtime, "create_market_state_service", lambda data_dir: FakeService())

    result = service._refresh_market_state_snapshot()

    assert result["ok"] is True
    assert result["snapshotId"] == "snap-9"
    assert result["attemptId"] == "att-3"
    assert str(seen["scope"]) == "GLOBAL"
    assert result["scope"] == "GLOBAL"


def test_an_explicit_run_ignores_the_freshness_guard(monkeypatch):
    monkeypatch.setattr(service, "market_memory_recently_run", lambda **kw: True)
    monkeypatch.setattr(service, "market_state_snapshot_recently_run", lambda **kw: True)
    calls = []
    monkeypatch.setattr(service, "_refresh_market_state_snapshot", lambda: calls.append("snapshot") or {"ok": True})

    skipped = service.run_briefing_prerequisites()
    forced = service.run_briefing_prerequisites(force=True)

    assert skipped["marketMemory"].get("skipped") is True
    assert forced["marketMemory"].get("skipped") is not True
    assert calls == ["snapshot"]
