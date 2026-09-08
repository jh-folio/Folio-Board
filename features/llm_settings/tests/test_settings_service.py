from pathlib import Path
from unittest.mock import patch

from features.llm_settings import settings_service
from features.llm_settings.client import TOSS_OPEN_API_DEFAULT_BASE_URL
from features.llm_settings.reasoning import reasoning_choices


def test_public_settings_exposes_provider_model_choices():
    config = {
        "provider": "openai",
        "enabled": True,
        "apiKey": "",
        "geminiApiKey": "",
        "anthropicApiKey": "",
        "model": "gpt-5.6-sol",
        "geminiModel": "gemini-2.5-flash",
        "anthropicModel": "claude-sonnet-5",
    }
    with (
        patch.object(settings_service, "openai_config", return_value=config),
        patch.object(settings_service, "use_llm_analysis", return_value=True),
        patch.object(settings_service, "dart_api_key", return_value=""),
        patch.object(settings_service, "fred_api_key", return_value=""),
        patch.object(settings_service, "bok_api_key", return_value=""),
        patch.object(settings_service, "public_notion_settings", return_value={}),
        patch.object(settings_service, "ai_agent_enabled", return_value=True),
        patch.object(settings_service, "ai_agent_mode", return_value="cli"),
    ):
        result = settings_service.public_settings()
    providers = result["llm"]["providers"]
    assert providers["openai"]["setupUrl"] == "https://platform.openai.com/api-keys"
    assert providers["gemini"]["setupUrl"] == "https://aistudio.google.com/app/apikey"
    assert providers["claude"]["setupUrl"] == "https://console.anthropic.com/settings/keys"
    assert [item["value"] for item in providers["openai"]["modelChoices"]] == [
        "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini",
    ]
    assert [item["value"] for item in providers["claude"]["modelChoices"]] == [
        "claude-fable-5", "claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5",
        "claude-opus-4-8", "claude-sonnet-4-6",
    ]
    assert providers["openai"]["reasoningChoices"] == [
        {"value": "provider_default", "label": "제공자 기본값"},
    ]
    assert "xhigh" not in {
        choice["value"] for choice in reasoning_choices("cli", "claude", "claude-sonnet-4-6")
    }
    assert {choice["value"] for choice in reasoning_choices("cli", "claude", "claude-sonnet-5")} >= {
        "provider_default", "low", "medium", "high", "xhigh", "max",
    }
    assert {choice["value"] for choice in providers["openai"]["reasoningByModel"]["gpt-6-astra"]} >= {
        "provider_default", "low", "medium", "high", "xhigh", "max",
    }
    assert result["agent"] == {"enabled": True, "mode": "cli"}


def test_save_settings_persists_ai_agent_policy(monkeypatch):
    updates = {}

    def fake_write_env_values(next_updates):
        updates.update(next_updates)

    monkeypatch.setattr(settings_service, "write_env_values", fake_write_env_values)
    monkeypatch.setattr(settings_service, "public_settings", lambda refresh=False: {"ok": True})

    result = settings_service.save_settings({"agent": {"enabled": False, "mode": "api"}})

    assert result == {"ok": True}
    assert updates["AI_AGENT_ENABLED"] == "0"
    assert updates["USE_LLM_BRIEFING"] == "0"
    assert updates["USE_LLM_ANALYSIS"] == "0"
    assert updates["AI_AGENT_MODE"] == "api"


def test_save_settings_can_enable_toss_and_store_credentials_from_settings(monkeypatch):
    updates = {}

    monkeypatch.setattr(settings_service, "write_env_values", lambda next_updates: updates.update(next_updates))
    monkeypatch.setattr(settings_service, "public_settings", lambda refresh=False: {"ok": True})

    settings_service.save_settings({
        "toss": {
            "enabled": True,
            "clientId": "client-id",
            "clientSecret": "secret-value",
            "baseUrl": "https://example.invalid",
        }
    })

    assert updates["FOLIO_ENABLE_TOSS_OPEN_API"] == "true"
    assert updates["TOSS_OPEN_API_CLIENT_ID"] == "client-id"
    assert updates["TOSS_OPEN_API_CLIENT_SECRET"] == "secret-value"
    assert updates["TOSS_OPEN_API_BASE_URL"] == "https://example.invalid"


def test_save_settings_can_disable_toss_without_clearing_credentials(monkeypatch):
    updates = {}

    monkeypatch.setattr(settings_service, "write_env_values", lambda next_updates: updates.update(next_updates))
    monkeypatch.setattr(settings_service, "public_settings", lambda refresh=False: {"ok": True})

    settings_service.save_settings({"toss": {"enabled": False}})

    assert updates == {"FOLIO_ENABLE_TOSS_OPEN_API": "false"}


def test_env_example_declares_disabled_toss_opt_in_and_pinned_default_origin():
    example = (Path(__file__).resolve().parents[3] / ".env.example").read_text(encoding="utf-8")

    assert "FOLIO_ENABLE_TOSS_OPEN_API=false" in example
    assert f"TOSS_OPEN_API_BASE_URL={TOSS_OPEN_API_DEFAULT_BASE_URL}" in example


if __name__ == "__main__":
    test_public_settings_exposes_provider_model_choices()
