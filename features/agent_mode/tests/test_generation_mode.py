import pytest
from features.agent_mode.generation_mode import llm_override_for_mode, normalize_generation_mode


def test_generation_mode_normalizes_new_and_legacy_inputs():
    assert normalize_generation_mode("rules") == "rules"
    with pytest.raises(ValueError, match="llm_api_removed"):
        normalize_generation_mode("llm-api")
    assert normalize_generation_mode("cli") == "llm_cli"
    assert normalize_generation_mode(None, use_llm=True) == "llm_cli"
    assert normalize_generation_mode(None, use_llm="0") == "rules"
    with pytest.raises(ValueError, match="llm_api_removed"):
        normalize_generation_mode(None, default="llm_api")


def test_llm_override_rejects_cli_mode():
    assert llm_override_for_mode("rules") is False
    with pytest.raises(ValueError, match="llm_api_removed"):
        llm_override_for_mode("llm_api")
    try:
        llm_override_for_mode("llm_cli")
    except ValueError:
        pass
    else:
        raise AssertionError("llm_cli must not enter the API LLM path")


if __name__ == "__main__":
    test_generation_mode_normalizes_new_and_legacy_inputs()
    test_llm_override_rejects_cli_mode()
