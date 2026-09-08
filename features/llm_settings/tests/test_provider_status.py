import urllib.error
from unittest.mock import Mock, patch

from features.llm_settings import provider_status


def _config(**overrides):
    config = {
        "apiKey": "openai-secret",
        "geminiApiKey": "gemini-secret",
        "anthropicApiKey": "claude-secret",
        "model": "gpt-5.6-sol",
        "geminiModel": "gemini-2.5-flash",
        "anthropicModel": "claude-sonnet-5",
    }
    config.update(overrides)
    return config


def test_check_provider_reports_model_access_without_generation():
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with (
        patch.object(provider_status, "openai_config", return_value=_config()),
        patch.object(provider_status.urllib.request, "urlopen", return_value=response) as urlopen,
    ):
        result = provider_status.check_provider("openai")
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.openai.com/v1/models/gpt-5.6-sol"
    assert result["available"] is True
    assert result["status"] == "available"


def test_gemini_key_is_sent_in_header_not_url():
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with (
        patch.object(provider_status, "openai_config", return_value=_config()),
        patch.object(provider_status.urllib.request, "urlopen", return_value=response) as urlopen,
    ):
        provider_status.check_provider("gemini")
    request = urlopen.call_args.args[0]
    assert "gemini-secret" not in request.full_url
    assert request.get_header("X-goog-api-key") == "gemini-secret"


def test_check_provider_accepts_explicit_model_without_generation():
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with (
        patch.object(provider_status, "openai_config", return_value=_config()),
        patch.object(provider_status.urllib.request, "urlopen", return_value=response) as urlopen,
    ):
        result = provider_status.check_provider("openai", model="gpt-6-astra")
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.openai.com/v1/models/gpt-6-astra"
    assert result["model"] == "gpt-6-astra"
    assert result["available"] is True


def test_invalid_credentials_returns_safe_status():
    error = urllib.error.HTTPError("https://api.openai.com/v1/models/gpt-5.6-sol", 401, "Unauthorized", {}, None)
    with (
        patch.object(provider_status, "openai_config", return_value=_config()),
        patch.object(provider_status.urllib.request, "urlopen", side_effect=error),
    ):
        result = provider_status.check_provider("openai")
    assert result["available"] is False
    assert result["status"] == "invalid_credentials"
    assert "openai-secret" not in str(result)


if __name__ == "__main__":
    test_check_provider_reports_model_access_without_generation()
    test_gemini_key_is_sent_in_header_not_url()
    test_invalid_credentials_returns_safe_status()
