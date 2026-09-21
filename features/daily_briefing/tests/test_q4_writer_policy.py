from unittest.mock import Mock, patch

import pytest

from features.daily_briefing import service
from features.agent_mode import bridge
from features.common.quality_generation.call_budget import SharedRepairBudget, bind_briefing_budget


@pytest.mark.parametrize("provider", ["codex", "antigravity", "claude"])
def test_cli_writer_does_not_inherit_lookup_permission(monkeypatch, provider):
    monkeypatch.setattr(service, "selected_cli_config", lambda: {
        "enabled": True, "apiKey": "test-only", "provider": provider, "model": "test",
    })
    monkeypatch.setattr(service, "read_briefing_prompt", lambda *a: "Write only supplied facts")
    context = Mock(return_value=("fixed input", []))
    monkeypatch.setattr(service, "build_llm_context", context)
    request = Mock(return_value=("# 미국장\n\n확인된 자료가 없습니다.", "test", {}))
    monkeypatch.setattr(service, "request_cli_text", request)
    service.generate_llm_briefing("2026-09-04", "2026-09-03", [], [], web_search_override=True, market_scope="us")
    assert context.call_args.kwargs["web_search"] is True
    assert request.call_args.kwargs["web_search"] is False


def test_codex_briefing_writer_explicitly_disables_inherited_search():
    adapter = {"id": "codex", "executable": "codex"}
    with patch("features.agent_mode.setup.configured_model", return_value="test"), patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset()):
        with bridge._briefing_codex_tool_policy("briefing", adapter):
            assert 'web_search="disabled"' in bridge._adapter_command(adapter)
            lookup = bridge._adapter_command(adapter, web_search=True)
            assert 'web_search="live"' in lookup
            assert 'web_search="disabled"' not in lookup
        assert 'web_search="disabled"' not in bridge._adapter_command(adapter)


def test_claude_writer_tools_require_explicit_lookup_permission():
    adapter = {"id": "claude", "executable": "claude"}
    with patch("features.agent_mode.setup.configured_model", return_value="test"):
        with bind_briefing_budget(SharedRepairBudget()):
            writer = bridge._adapter_command(adapter)
            lookup = bridge._adapter_command(adapter, web_search=True)
            assert writer[writer.index("--tools") + 1] == "Read,Glob,Grep"
            assert lookup[lookup.index("--tools") + 1] == "Read,Glob,Grep,WebSearch"
            assert "--strict-mcp-config" in writer
        ordinary = bridge._adapter_command(adapter)
        assert ordinary[ordinary.index("--tools") + 1] == "Read,Glob,Grep"


@pytest.mark.parametrize("kind", ["daily", "weekly"])
def test_lookup_receives_market_session_and_weekly_window(monkeypatch, kind):
    lookup = Mock(return_value=("", {}))
    monkeypatch.setattr(service, "briefing_web_supplement", lookup)
    window = {"weekStart": "2026-08-24", "weekEnd": "2026-08-30"}
    service._web_supplement_block("us", "2026-09-04", {}, {}, web_search=True, lookup=None, sink={},
        kind=kind, weekly_window=window, market_windows={"usRegularSessionDate": "2026-09-03"})
    assert lookup.call_args.args[:2] == ("us", "2026-09-03")
    assert lookup.call_args.kwargs["kind"] == kind
    assert lookup.call_args.kwargs["weekly_window"] == window
