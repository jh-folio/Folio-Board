"""대화가 세션을 넘어 이어져야 한다.

Task 7.6의 요구: 세션이 종료되었다가 다시 돌아와도 Agent가 앞선 대화를 context로
쓸 수 있어야 한다. 도크 대화가 브라우저 localStorage에만 있던 예전 구조에서는
서버에 기록이 없어 원천적으로 불가능했다.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from features.agent_mode import bridge, job_runtime
from features.agent_mode import consultation_store as store


@pytest.fixture
def cli(monkeypatch):
    captured: dict = {}

    # 실제 시그니처는 `adapter`도 받는다 — 이 대화만 다른 CLI로 돌리는 경로다.
    # `**_kwargs`는 `on_phase` 같은 additive 키워드 인자를 흡수한다.
    def run(prompt, adapter="", model="", job_id="", **_kwargs):
        captured.setdefault("prompts", []).append(prompt)
        return {"adapter": "test-cli", "output": "전력 공급 제약이 병목입니다."}

    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(bridge, "run_agent_prompt", run)
    return captured


def _turn(root, session_id, text):
    appended = store.append_user_message(root, session_id, text)
    job_runtime.run_consultation_job(root, session_id, appended["message"]["id"])
    return appended


def test_a_turn_is_saved_on_the_server(tmp_path, cli):
    session = store.create_session(tmp_path, {"title": "대화", "scope": {"kind": "general"}})
    _turn(tmp_path, session["id"], "AI 전력 병목이 뭐야?")

    saved = store.get_session(tmp_path, session["id"])

    assert [row["role"] for row in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][1]["content"]


def test_the_next_turn_sees_the_earlier_conversation(tmp_path, cli):
    """이것이 요구의 핵심 — 앞 맥락 없이는 "아까 그거"에 답할 수 없다."""
    session = store.create_session(tmp_path, {"title": "대화", "scope": {"kind": "general"}})
    _turn(tmp_path, session["id"], "AI 전력 병목이 뭐야?")
    _turn(tmp_path, session["id"], "아까 그거 계속 설명해줘")

    second = cli["prompts"][-1]

    assert "AI 전력 병목이 뭐야?" in second, "앞선 질문이 다음 턴에 실려야 한다"
    assert "전력 공급 제약" in second, "앞선 답변도 실려야 한다"
    assert "<conversation>" in second


def test_the_conversation_stays_hypothesis(tmp_path, cli):
    """대화는 가설이지 근거가 아니다. 프롬프트가 그 경계를 말해야 한다."""
    session = store.create_session(tmp_path, {"title": "대화", "scope": {"kind": "general"}})
    _turn(tmp_path, session["id"], "이건 내 생각인데")
    _turn(tmp_path, session["id"], "확인해줘")

    assert "evidence가 아니다" in cli["prompts"][-1]
    saved = store.get_session(tmp_path, session["id"])
    assert saved["reuseAsEvidence"] is False
    assert all(row.get("reuseAsEvidence") is False for row in saved["messages"])


def test_the_prompt_does_not_grow_with_every_turn(tmp_path, cli):
    """전체 transcript를 보내면 대화가 길어질수록 비용과 지연이 늘고 상한을 넘는다."""
    session = store.create_session(tmp_path, {"title": "긴 대화", "scope": {"kind": "general"}})
    for index in range(12):
        _turn(tmp_path, session["id"], f"질문 {index} " + "내용 " * 40)

    lengths = [len(prompt) for prompt in cli["prompts"]]

    assert lengths[-1] < lengths[0] * 4, "턴 수에 비례해 커지면 상한 있는 pack이 아니다"
    assert lengths[-1] < 32_000 + 8_000, "pack 상한을 크게 넘지 않아야 한다"


def test_an_answer_survives_a_cli_failure(tmp_path, monkeypatch):
    """CLI가 죽어도 turn은 저장된다 — 질문을 잃지 않아야 재시도할 수 있다."""
    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": True})
    monkeypatch.setattr(bridge, "run_agent_prompt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cli died")))
    session = store.create_session(tmp_path, {"title": "대화", "scope": {"kind": "general"}})

    _turn(tmp_path, session["id"], "질문")

    saved = store.get_session(tmp_path, session["id"])
    assert [row["role"] for row in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][1]["engine"] == "rules"
