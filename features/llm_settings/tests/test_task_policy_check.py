from unittest.mock import patch

from features.llm_settings import task_policy_check




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
