from unittest.mock import patch

from features.llm_settings import task_policy_check


def test_api_task_check_uses_selected_model_without_generation():
    provider_result = {
        "provider": "openai",
        "model": "gpt-6-astra",
        "status": "available",
        "available": True,
        "message": "모델 접근 확인",
        "checkedAt": "2026-09-07T00:00:00+00:00",
    }
    with patch.object(task_policy_check, "check_provider", return_value=provider_result) as check:
        result = task_policy_check.check_task_policy({
            "mode": "api", "provider": "openai", "model": "gpt-6-astra", "reasoningEffort": "high",
        })
    check.assert_called_once_with("openai", model="gpt-6-astra")
    assert result["model"] == "gpt-6-astra"
    assert result["modelAccessVerified"] is True
    assert result["generationAttempted"] is False


def test_cli_task_check_reports_adapter_only_and_does_not_claim_model_access():
    with patch.object(task_policy_check, "bridge_status", return_value={"adapters": [{
        "id": "codex", "label": "Codex CLI", "available": True, "bridgeSupported": True,
    }]}):
        result = task_policy_check.check_task_policy({
            "mode": "cli", "provider": "codex", "model": "gpt-5.6-sol", "reasoningEffort": "xhigh",
        })
    assert result["status"] == "cli_ready_model_unverified"
    assert result["available"] is True
    assert result["model"] == "gpt-5.6-sol"
    assert result["modelAccessVerified"] is False
    assert result["generationAttempted"] is False
