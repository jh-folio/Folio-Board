"""테스트는 Agent CLI 프로세스를 띄우지 않는다.

`features/topic_report/tests/conftest.py`가 같은 이유로 `run_agent_prompt`를 막고
있었지만, 그것은 **프롬프트 한 번을 보내는 경로 하나**만 덮는다. Agent task는
`run_agent_task` → `_invoke_agent_cli`로 내려가므로 그 밑으로 빠져나갔다.

실제로 사전작업이 화면 스냅샷까지 만들도록 바꾼 뒤, 아무것도 stub하지 않은 기존
테스트가 진짜 CLI를 실행해 **사용자의 `market-memory.sqlite3`에 스냅샷을 하나 썼다**
(`mss_20260813T021212...`). 테스트가 사용자 자료를 바꾸는 것은 어떤 이유로도 안 된다.

그래서 프로세스 경계 하나에서 막는다. CLI 경로를 정말 확인하려는 테스트는
`_invoke_agent_cli`나 그 위 함수를 자기 손으로 monkeypatch한다.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_agent_cli_process(monkeypatch):
    from features.agent_mode import bridge

    def refuse(*_args, **_kwargs):
        raise AssertionError(
            "테스트가 Agent CLI 프로세스를 띄우려 했습니다. "
            "필요하면 `_invoke_agent_cli`(또는 그 위 함수)를 stub하세요."
        )

    monkeypatch.setattr(bridge, "_invoke_agent_cli", refuse)


@pytest.fixture(autouse=True)
def no_user_task_settings(monkeypatch, tmp_path):
    """Task routing tests must never inherit a developer's saved overrides."""
    from features.llm_settings import task_policy
    monkeypatch.setattr(task_policy, "data_dir", lambda: tmp_path)
