from pathlib import Path
from unittest.mock import patch

from features.llm_settings import settings_service
from features.llm_settings.client import TOSS_OPEN_API_DEFAULT_BASE_URL
from features.llm_settings.reasoning import reasoning_choices




def test_save_settings_persists_ai_agent_policy(monkeypatch):
    updates = {}

    def fake_write_env_values(next_updates):
        updates.update(next_updates)

    monkeypatch.setattr(settings_service, "write_env_values", fake_write_env_values)
    monkeypatch.setattr(settings_service, "public_settings", lambda refresh=False: {"ok": True})

    result = settings_service.save_settings({"agent": {"enabled": False, "mode": "cli"}})

    assert result == {"ok": True}
    assert updates["AI_AGENT_ENABLED"] == "0"
    assert updates["USE_LLM_BRIEFING"] == "0"
    assert updates["USE_LLM_ANALYSIS"] == "0"
    assert updates["AI_AGENT_MODE"] == "cli"


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
