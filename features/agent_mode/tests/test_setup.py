import os
from unittest.mock import MagicMock, patch

from features.agent_mode import setup


def _saved_env(write_values):
    """실제 `write_env_values`는 `.env`와 함께 `os.environ`도 갱신한다.

    그래야 저장 직후 읽는 `configured_provider()`가 방금 저장한 값을 본다. 테스트가
    쓰기를 통째로 막으면 응답이 옛 환경을 비추므로, 여기서 같은 일을 흉내 낸다.
    """
    def fake(updates):
        write_values(updates)
        for key, value in updates.items():
            if value is not None:
                os.environ[key] = str(value)
    return fake


def test_save_settings_persists_provider_and_models(monkeypatch):
    """저장 응답은 **실제로 잰 상태**를 담는다.

    예전에는 탐지 비용을 아끼려고 모든 어댑터를 `installed: False`로 채운 자리표시자를
    돌려줬고, 화면은 그것을 그대로 "미설치"로 그렸다 — 저장할 때마다 설치돼 있는 CLI가
    사라졌다 나타났다. 재보지 않은 상태를 단언하느니 1초를 쓰는 편이 낫다.
    """
    write_values = MagicMock()
    monkeypatch.setattr(setup, "write_env_values", _saved_env(write_values))
    monkeypatch.setattr("features.agent_mode.bridge.invalidate_bridge_status", lambda: None)
    monkeypatch.setattr(setup, "bridge_status", None, raising=False)
    probed = {}

    def fake_payload(*, refresh=False):
        probed["refresh"] = refresh
        return {
            "provider": setup.configured_provider(),
            "available": True,
            "adapters": [
                {"id": key, "installed": True, "model": setup.configured_model(key)}
                for key in ("codex", "claude", "antigravity")
            ],
        }

    monkeypatch.setattr(setup, "settings_payload", fake_payload)

    result = setup.save_settings({
        "provider": "codex",
        "models": {"codex": "gpt-6.1", "claude": "claude-sonnet-4-6"},
    })

    assert result["provider"] == "codex"
    assert [item["id"] for item in result["adapters"]] == ["codex", "claude", "antigravity"]
    assert next(item for item in result["adapters"] if item["id"] == "codex")["model"] == "gpt-6.1"
    # 설치 상태는 다시 재되(캐시를 바로 위에서 버렸다) 모델 목록까지 CLI에 다시 묻지는
    # 않는다. `refresh=True`로 두면 어댑터마다 조회가 붙어 저장이 20초 걸린다.
    assert probed["refresh"] is False
    write_values.assert_called_once_with({
        "AGENT_CLI_PROVIDER": "codex",
        "FOLIO_AGENT_CLAUDE_MODEL": "claude-sonnet-4-6",
        "FOLIO_AGENT_CODEX_MODEL": "gpt-6.1",
    })


def test_save_settings_ignores_empty_model_values_from_unavailable_adapters(monkeypatch):
    write_values = MagicMock()
    monkeypatch.setattr(setup, "write_env_values", _saved_env(write_values))
    monkeypatch.setattr("features.agent_mode.bridge.invalidate_bridge_status", lambda: None)
    monkeypatch.setattr(setup, "settings_payload", lambda *, refresh=False: {
        "provider": setup.configured_provider(),
        "adapters": [{"id": "codex", "model": setup.configured_model("codex")}],
    })

    result = setup.save_settings({
        "provider": "codex",
        "models": {"codex": "gpt-6.1", "antigravity": ""},
    })

    assert result["provider"] == "codex"
    assert next(item for item in result["adapters"] if item["id"] == "codex")["model"] == "gpt-6.1"
    write_values.assert_called_once_with({
        "AGENT_CLI_PROVIDER": "codex",
        "FOLIO_AGENT_CODEX_MODEL": "gpt-6.1",
    })


def test_save_settings_rejects_space_containing_model():
    try:
        setup.save_settings({"provider": "codex", "models": {"codex": "gpt latest"}})
    except ValueError as exc:
        assert "Unsupported codex model" in str(exc)
    else:
        raise AssertionError("space-containing model should be rejected")


def test_settings_payload_preserves_unsupported_antigravity_status():
    status = {
        "available": False,
        "selectedAdapter": "",
        "adapters": [{
            "id": "antigravity",
            "label": "Antigravity CLI",
            "installed": True,
            "available": False,
            "authenticated": False,
            "executable": r"C:\Users\me\AppData\Local\agy\bin\agy.exe",
            "error": "Windows headless mode is unsupported.",
            "bridgeSupported": False,
        }],
    }
    with (
        patch("features.agent_mode.bridge.bridge_status", return_value=status),
        patch.object(setup, "discover_cli_models", side_effect=AssertionError("unsupported adapter should not refresh models")),
    ):
        result = setup.settings_payload(refresh=True)
    row = result["adapters"][0]
    assert row["bridgeSupported"] is False
    assert row["loginSupported"] is False
    assert row["installSupported"] is False
    assert row["modelChoices"] == []
    assert row["model"] == ""


if __name__ == "__main__":
    test_save_settings_persists_provider_and_models()
    test_save_settings_ignores_empty_model_values_from_unavailable_adapters()
    test_save_settings_rejects_space_containing_model()
    test_settings_payload_preserves_unsupported_antigravity_status()
