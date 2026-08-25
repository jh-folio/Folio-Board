"""팩 경계는 워크스페이스를 따라가야 한다.

`read_pack()`의 허용 루트가 `ROOT`(체크아웃)와 `job-context` 둘뿐이었다. 사용자 자료는
`FOLIO_HOME`으로 체크아웃 밖에 둘 수 있으므로, 그러면 워크스페이스의 `agent-context`
팩이 전부 경계 밖으로 판정돼 `ValueError`가 났다.

실측: FolioOS_Sites가 이 체크아웃을 런타임으로 쓰고 `FOLIO_HOME`만 자기 workspace로
돌린 인스턴스에서, 예약 사전작업의 "화면용 시장 상태 스냅샷"이 매번 죽어
`market_state_snapshots`가 2026-08-20 이후 갱신되지 않았다. 팩은 전부 `prepared`에
멈춰 있었다 — CLI 실행과 writeback 다음의 `update_pack_status()` 안에서 터진 자리다.

**기본 `FOLIO_HOME`으로 도는 테스트로는 절대 안 잡힌다.** 그때는 워크스페이스가 곧
체크아웃이라 첫 번째 허용 루트에 걸리기 때문이다. 그래서 이 테스트는 워크스페이스를
체크아웃 밖으로 옮긴 상태를 직접 만든다.

브리핑 생성이 멀쩡했던 이유도 여기 있다 — durable job이라 팩이 `job-context/`에 들어가
이미 뚫려 있던 두 번째 경로에 걸렸다. non-durable 사전작업만 `agent-context/`를 쓴다.
"""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def workspace_outside_checkout(tmp_path, monkeypatch):
    """체크아웃 밖 워크스페이스. 모듈 상수가 import 시점에 잡히므로 다시 읽어들인다."""
    home = tmp_path / "workspace"
    (home / "data").mkdir(parents=True)
    monkeypatch.setenv("FOLIO_HOME", str(home))

    from features.common import workspace

    workspace.reset_cache()
    schema = importlib.reload(importlib.import_module("features.agent_mode.schema"))
    assert schema.CONTEXT_DIR.is_relative_to(home), "이 테스트의 전제는 워크스페이스가 밖이라는 것이다"
    yield schema, home

    monkeypatch.delenv("FOLIO_HOME", raising=False)
    workspace.reset_cache()
    importlib.reload(importlib.import_module("features.agent_mode.schema"))


def _write_pack(schema, task_type="market_memory_llm"):
    path = schema.task_dir(task_type) / "pack.json"
    path.write_text(
        json.dumps({"taskType": task_type, "packId": "p1", "artifactId": "a1", "status": "prepared"}),
        encoding="utf-8",
    )
    return path


def test_a_pack_in_the_moved_workspace_can_be_read(workspace_outside_checkout):
    schema, _ = workspace_outside_checkout

    assert schema.read_pack(_write_pack(schema))["status"] == "prepared"


def test_the_status_update_that_actually_failed_now_completes(workspace_outside_checkout):
    """팩이 `prepared`에 멈춰 있던 자리. writeback 뒤 이 호출이 터졌다."""
    schema, _ = workspace_outside_checkout
    path = _write_pack(schema)

    updated = schema.update_pack_status(path, status="done", result={"ok": True})

    assert updated["status"] == "done"
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "done"


def test_the_market_state_snapshot_pack_is_covered_too(workspace_outside_checkout):
    """실패한 예약 단계의 task type. 그 인스턴스에는 이 디렉터리조차 없었다."""
    schema, _ = workspace_outside_checkout
    path = _write_pack(schema, "market_state_snapshot")

    assert schema.update_pack_status(path, status="done")["status"] == "done"


def test_a_path_outside_the_workspace_is_still_rejected(workspace_outside_checkout):
    """허용 목록을 넓힌 것이지 경계를 없앤 것이 아니다."""
    schema, home = workspace_outside_checkout
    outsider = home.parent / "outside.json"
    outsider.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        schema.read_pack(outsider)


def test_other_files_in_the_data_folder_are_not_packs(workspace_outside_checkout):
    """`data/` 안이라고 다 읽어도 되는 것은 아니다. 팩 폴더 둘만 허용한다."""
    schema, home = workspace_outside_checkout
    portfolio = home / "data" / "portfolio.json"
    portfolio.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        schema.read_pack(portfolio)


def test_a_relative_path_cannot_escape(workspace_outside_checkout):
    schema, _ = workspace_outside_checkout

    with pytest.raises(ValueError):
        schema.read_pack("../../outside.json")


def test_job_context_packs_still_work(workspace_outside_checkout):
    """브리핑 생성이 쓰던 경로. 넓히면서 깨뜨리지 않는다."""
    schema, _ = workspace_outside_checkout
    from features.common.jobs import data_root

    job_pack = data_root() / "job-context" / "job1" / "pack.json"
    job_pack.parent.mkdir(parents=True, exist_ok=True)
    job_pack.write_text(json.dumps({"taskType": "briefing", "packId": "b1", "status": "prepared"}), encoding="utf-8")

    assert schema.update_pack_status(job_pack, status="done")["status"] == "done"
