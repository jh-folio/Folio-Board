"""Agent Dock Stage D: the documented USE_WEB_SEARCH_FOR_* toggles must actually gate web search.

Before this fix, `use_web_search_for_briefing()` read `USE_LLM_BRIEFING` (the
legacy LLM-enable flag `ai_agent_enabled()` also reads) and
`use_web_search_for_analysis()` just returned `use_llm_analysis()` outright —
so the documented `USE_WEB_SEARCH_FOR_BRIEFING`/`USE_WEB_SEARCH_FOR_ANALYSIS`
variables (`features/llm_settings/README.md`, `.env.example`) had no effect.
"""
from __future__ import annotations

from features.llm_settings.client import use_web_search_for_analysis, use_web_search_for_briefing


def _pin_llm_enabled(monkeypatch, enabled: bool):
    """Pin the LLM-enable state explicitly rather than deleting it.

    `load_dotenv()` only fills in a variable when it is *not already* in
    `os.environ` — so merely `delenv`-ing `AI_AGENT_ENABLED` lets it leak back
    in from this machine's real `.env` file (confirmed: that leakage broke an
    earlier version of this test). Pinning makes these tests independent of
    local configuration.
    """
    monkeypatch.setenv("AI_AGENT_ENABLED", "1" if enabled else "0")
    for key in ("USE_LLM_BRIEFING", "USE_OPENAI_BRIEFING", "USE_LLM_ANALYSIS"):
        monkeypatch.delenv(key, raising=False)


def test_use_web_search_for_briefing_defaults_to_enabled_when_unset(monkeypatch):
    _pin_llm_enabled(monkeypatch, True)
    monkeypatch.delenv("USE_WEB_SEARCH_FOR_BRIEFING", raising=False)
    assert use_web_search_for_briefing() is True


def test_use_web_search_for_briefing_now_actually_reads_its_own_variable(monkeypatch):
    """Regression: setting this used to do nothing because the resolver read
    USE_LLM_BRIEFING instead."""
    _pin_llm_enabled(monkeypatch, True)
    monkeypatch.setenv("USE_WEB_SEARCH_FOR_BRIEFING", "0")
    assert use_web_search_for_briefing() is False


def test_use_web_search_for_briefing_stays_off_when_llm_itself_is_disabled(monkeypatch):
    """Web search obviously cannot run without the LLM path enabled at all."""
    _pin_llm_enabled(monkeypatch, False)
    monkeypatch.setenv("USE_WEB_SEARCH_FOR_BRIEFING", "1")
    assert use_web_search_for_briefing() is False


def test_use_web_search_for_analysis_defaults_to_enabled_when_unset(monkeypatch):
    _pin_llm_enabled(monkeypatch, True)
    monkeypatch.delenv("USE_WEB_SEARCH_FOR_ANALYSIS", raising=False)
    assert use_web_search_for_analysis() is True


def test_use_web_search_for_analysis_now_actually_reads_its_own_variable(monkeypatch):
    _pin_llm_enabled(monkeypatch, True)
    monkeypatch.setenv("USE_WEB_SEARCH_FOR_ANALYSIS", "0")
    assert use_web_search_for_analysis() is False


def test_use_web_search_for_analysis_stays_off_when_llm_itself_is_disabled(monkeypatch):
    _pin_llm_enabled(monkeypatch, False)
    monkeypatch.setenv("USE_WEB_SEARCH_FOR_ANALYSIS", "1")
    assert use_web_search_for_analysis() is False
