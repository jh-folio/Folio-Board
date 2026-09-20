"""저장이 CLI 상태를 어떻게 보고하는가, 그리고 agy를 언제 여는가."""
import features.agent_mode.bridge as bridge
import features.agent_mode.setup as setup


def test_saving_reports_the_measured_status_not_a_placeholder(monkeypatch):
    """예전에는 탐지 비용을 아끼려고 모든 어댑터를 `installed: False`로 채운 자리표시자를
    돌려줬다. 화면은 그것을 그대로 "미설치"로 그려서, 설정을 저장할 때마다 설치돼 있는
    CLI가 사라졌다 나타났다.
    """
    monkeypatch.setattr(setup, "write_env_values", lambda updates: None)
    monkeypatch.setattr(setup, "invalidate_bridge_status", lambda: None, raising=False)
    seen = {}

    def fake_payload(*, refresh=False):
        seen["refresh"] = refresh
        return {"adapters": [{"id": "claude", "installed": True, "authenticated": True}], "provider": "claude"}

    monkeypatch.setattr(setup, "settings_payload", fake_payload)

    result = setup.save_settings({"provider": "claude", "models": {}})

    assert result["adapters"][0]["installed"] is True
    # 모델 목록까지 다시 물으면 CLI마다 조회가 붙어 저장이 20초 걸린다.
    assert seen["refresh"] is False


def test_the_placeholder_payload_is_gone():
    assert not hasattr(setup, "_saved_settings_payload")


def test_the_version_gate_is_gone():
    """**버전 숫자로 능력을 판정하지 않는다.**

    예전에는 `AGY_HEADLESS_FIXED = (1, 1, 7)` 이상이면 브리지를 열었다. 그 근거는 짧은
    프롬프트 하나가 stdout으로 돌아온 것이었는데, 정작 Folio Board의 Agent task는 전부
    컨텍스트 팩 **파일을 읽는 것으로 시작**한다. 그 경로는 재보지 않았고 1.1.12는 그
    읽기를 거부한다 — 버전 비교로는 볼 수 없는 종류의 문제였다.

    게이트를 연 뒤 실행된 Agent 잡 두 건이 모두 실패했고, 그전까지 antigravity로 성공한
    잡은 한 건도 없었다. 지금은 `agy_capability`가 실제로 파일을 읽혀 보고 그 결과로만
    연다. 게이트를 둘 두면 "재봤더니 되는데 버전 때문에 막는" 모순이 생긴다.
    """
    assert not hasattr(bridge, "AGY_HEADLESS_FIXED")
    assert not hasattr(bridge, "_agy_headless_works")


def test_the_capability_is_measured_not_assumed():
    """조회는 실제 팩과 같은 폴더에서 한다 — 실측으로 갈린 것은 크기가 아니라 위치다."""
    from features.agent_mode import agy_capability

    assert agy_capability.PROBE_DIR.name == "agent-context"
    # 재본 적이 없으면 `None`이고, `None`은 "된다"가 아니다.
    assert agy_capability.cached_file_reads("없는버전-0.0.0") is None


def test_the_offered_agy_models_carry_an_effort_step():
    """agy는 모델 이름에 노력 단계를 함께 담는다(`...-high`).

    단계 없는 예전 이름(`gemini-3.5-pro`)은 1.1.7이 "not recognized"로 거부하는데,
    실시간 목록에 기본값이 덧붙어 선택지에 남아 있었다 — 고르면 실행 시점에 실패한다.
    """
    from features.llm_settings.model_catalog import CLI_MODEL_FALLBACKS

    values = [choice["value"] for choice in CLI_MODEL_FALLBACKS["antigravity"]]

    assert "gemini-3.5-pro" not in values
    assert all(value.count("-") >= 2 for value in values), values


def test_a_conversation_can_pick_its_own_cli_without_touching_the_default():
    """도크의 선택은 그 대화에만 적용된다.

    전역 기본(설정 탭·상단바)은 예약 브리핑과 기업분석이 쓴다. 도크에서 한 번 다른
    CLI로 물어봤다고 내일 아침 예약이 그 CLI로 돌면 안 된다.
    """
    from features.agent_mode.companion import normalize_agent_options

    assert normalize_agent_options({"adapter": "codex"})["adapter"] == "codex"
    assert normalize_agent_options({"adapter": "CLAUDE"})["adapter"] == "claude"
    # 비어 있으면 전역 기본을 따른다.
    assert normalize_agent_options({})["adapter"] == ""
    # 아는 어댑터가 아니면 무시한다 — 틀린 이름 때문에 전역 기본까지 못 쓰면 안 된다.
    assert normalize_agent_options({"adapter": "nope"})["adapter"] == ""


def test_the_chat_run_hands_the_conversation_adapter_to_the_cli():
    """옵션에만 담기고 실행에 안 넘어가면 화면은 고른 척만 한다."""
    import inspect

    from features.agent_mode import chat

    source = inspect.getsource(chat._run_with_images)

    assert 'adapter=options.get("adapter", "")' in source


def test_the_dock_never_saves_a_conversation_choice_as_the_default():
    """도크가 override 중에 전역 설정을 저장하면 `이 대화에만`이 거짓이 된다."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[3].joinpath(
        "web", "src", "app", "ReactAgentDock.tsx"
    ).read_text(encoding="utf-8")

    assert "if (providerOverride || !adapter?.id || !nextModel) return;" in source
    # Agent Dock Stage E: searchPolicy joined the same per-conversation options
    # object (not a separately-saved global setting).
    assert "options: { model, effort, adapter: providerOverride, searchPolicy }" in source
