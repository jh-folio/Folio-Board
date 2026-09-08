"""Provider-boundary contracts without credentials or paid generation."""
import pytest

from features.llm_settings import client


def capture_request(monkeypatch, payload=None):
    captured = {}

    def post(url, body, headers, timeout):
        captured.update(url=url, body=body, timeout=timeout)
        return payload if payload is not None else {
            "status": "completed", "id": "resp_test",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": '{"entries": []}'}
            ]}],
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(client, "post_json", post)
    monkeypatch.delenv("OPENAI_ASTRA_REASONING_EFFORT", raising=False)
    return captured


def test_astra_request_preserves_report_contract(monkeypatch):
    captured = capture_request(monkeypatch)
    result = client.request_llm_text(
        {"provider": "openai", "model": "gpt-6-astra", "apiKey": "test"},
        "Keep the report schema and evidence hierarchy.", "supplied evidence",
        web_search=True, json_mode=True, max_output_tokens=2600,
        include_usage=True, timeout_seconds=180,
    )
    body = captured["body"]
    assert captured["url"] == client.OPENAI_RESPONSES_URL
    assert captured["timeout"] == 180
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 2600
    assert body["text"] == {"format": {"type": "json_object"}}
    assert "JSON" in body["input"]
    assert body["instructions"] == "Keep the report schema and evidence hierarchy."
    assert body["tools"][0]["type"] == "web_search"
    assert not {"temperature", "top_p", "top_logprobs"}.intersection(body)
    assert result[:2] == ('{"entries": []}', "resp_test")
    assert result[2]["totalTokens"] == 30


@pytest.mark.parametrize("effort,expected", [("none", "low"), ("minimal", "low"), ("high", "high"), ("max", "max")])
def test_astra_effort_migration(monkeypatch, effort, expected):
    captured = capture_request(monkeypatch)
    monkeypatch.setenv("OPENAI_ASTRA_REASONING_EFFORT", effort)
    client.request_openai({"model": "gpt-6-astra", "apiKey": "test"}, "prompt", "context")
    assert captured["body"]["reasoning"]["effort"] == expected


def test_astra_per_call_override_and_invalid_effort(monkeypatch):
    captured = capture_request(monkeypatch)
    monkeypatch.setenv("OPENAI_ASTRA_REASONING_EFFORT", "invalid")
    cfg = {"model": "gpt-6-astra", "apiKey": "test"}
    with pytest.raises(ValueError, match="Invalid OPENAI_ASTRA"):
        client.request_openai(cfg, "prompt", "context")
    assert not captured
    client.request_openai({**cfg, "reasoningEffort": "medium"}, "prompt", "context")
    assert captured["body"]["reasoning"]["effort"] == "medium"


@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-4.1"])
def test_existing_models_keep_request_parameters(monkeypatch, model):
    captured = capture_request(monkeypatch)
    monkeypatch.setenv("OPENAI_ASTRA_REASONING_EFFORT", "high")
    client.request_openai({"model": model, "apiKey": "test"}, "prompt", "context")
    assert "reasoning" not in captured["body"]
    assert "tools" not in captured["body"]


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "output_text": "private partial report", "incomplete_details": {"reason": "max_output_tokens"}},
    {"status": "failed", "error": {"message": "private context"}},
    {"status": "completed", "output": []},
    {"status": "completed", "output": [{"content": [{"type": "refusal", "refusal": "private context"}]}]},
])
def test_partial_empty_and_refused_outputs_are_not_reports(monkeypatch, payload):
    capture_request(monkeypatch, payload)
    with pytest.raises(RuntimeError) as exc:
        client.request_openai({"model": "gpt-6-astra", "apiKey": "test"}, "prompt", "context")
    assert "private" not in str(exc.value)
