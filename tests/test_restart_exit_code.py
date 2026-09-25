"""재시작 신호가 uvicorn의 시작 실패 코드와 겹치지 않는다."""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_restart_signal_is_not_uvicorns_startup_failure():
    """**3을 쓰면 안 된다.** `uvicorn.config.STARTUP_FAILURE = 3`이라 포트 충돌을 비롯한
    모든 uvicorn 시작 실패가 같은 코드로 끝난다. 런처는 그것을 재시작 신호로 읽어
    무한히 다시 띄웠다 — 시작 → 바인드 실패 → `Restarting...` → 시작 → …
    """
    from uvicorn.config import STARTUP_FAILURE

    import app

    assert app.RESTART_EXIT_CODE != STARTUP_FAILURE
    assert app.RESTART_EXIT_CODE not in {0, 1, 2}


def test_both_launchers_wait_for_that_exact_code():
    """앱과 런처가 서로 다른 숫자를 보면 재시작 버튼이 그냥 종료가 된다."""
    import app

    code = app.RESTART_EXIT_CODE
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8-sig")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert f"-eq {code}" in ps1
    assert f'-eq {code}' in sh
    # 옛 계약이 남아 있으면 어느 쪽이 진짜인지 알 수 없다.
    assert "-eq 3" not in ps1
    assert "-eq 3 ]" not in sh


def test_the_restart_helper_uses_the_constant():
    import inspect

    import app

    source = inspect.getsource(app.schedule_server_restart)

    assert "os._exit(RESTART_EXIT_CODE)" in source
    assert "os._exit(3)" not in source


def test_a_busy_port_is_reported_instead_of_looping(monkeypatch):
    """무한 루프의 실제 원인은 포트 충돌이었다. 미리 확인해 사람이 읽을 문장을 낸다."""
    import app

    # 아무도 듣지 않는 포트: 빈 문자열이어야 서버가 그대로 뜬다.
    assert app._port_owner_message("127.0.0.1", 0) == ""

    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        message = app._port_owner_message("127.0.0.1", port)
    finally:
        holder.close()

    assert message
    assert str(port) in message
    # 우리 서버가 아니면 그렇게 말하고 다른 포트를 안내한다.
    assert "PORT=8788" in message


def test_the_launcher_holds_the_window_on_a_failed_start():
    """실패 메시지가 창과 함께 사라지면 사용자는 왜 안 되는지 알 수 없다."""
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8-sig")

    tail = ps1[ps1.index("$shouldRestart = ($exitCode"):]
    assert re.search(r"elseif \(\$exitCode -ne 0\)", tail)
    assert "Read-Host" in tail


@pytest.mark.parametrize("doc", ["AGENTS.md", "CLAUDE.md"])
def test_the_agent_docs_state_the_current_contract(doc):
    text = (ROOT / doc).read_text(encoding="utf-8")

    assert "종료 코드 3이 재시작 신호" not in text
    assert "docs/agent-guides/server-restart.md" in text
    contract = (ROOT / "docs/agent-guides/server-restart.md").read_text(encoding="utf-8")
    assert "RESTART_EXIT_CODE" in contract
    assert "재시작 신호는 7" in contract
