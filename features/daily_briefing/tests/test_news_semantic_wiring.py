"""Focused wiring tests for semantic news selection on both briefing paths."""

from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from features.agent_mode import bridge, service as agent_service
from features.daily_briefing import builder, news_selection_runtime, news_semantic_engine
from features.daily_briefing.tests.test_builder import DOCS, _visuals
from features.daily_briefing.tests.test_briefing import WINDOWS


def _selection_context():
    return {"mode": "shadow", "analysisAsOf": "2026-06-10T00:00:00+00:00"}


def _identity_selection(prepare):
    def run(documents, *_args, **_kwargs):
        prepare(*_args, **_kwargs)
        return {"operationalCandidates": list(documents)}

    return run


def _patch_builder(monkeypatch, *, config, callback=None):
    factory = Mock(return_value=callback)
    prepare = Mock()
    monkeypatch.setattr(builder, "build_index", lambda **_kwargs: {})
    monkeypatch.setattr(builder, "load_index", lambda: {"documents": DOCS})
    monkeypatch.setattr(builder, "cached_market_snapshot", lambda **_kwargs: {"ok": False})
    monkeypatch.setattr(builder, "cached_korea_market_data", lambda *args, **_kwargs: {"ok": False})
    monkeypatch.setattr(builder, "list_briefing_memories", lambda *args, **_kwargs: [])
    monkeypatch.setattr(builder, "load_prev_briefing", lambda *args, **_kwargs: None)
    monkeypatch.setattr(builder, "collect_briefing_visuals", _visuals)
    monkeypatch.setattr(builder, "apply_quality_loop", lambda _kind, artifact, **_kwargs: artifact)
    monkeypatch.setattr(builder, "generate_llm_briefing", lambda *args, **_kwargs: (None, "disabled"))
    monkeypatch.setattr(builder, "selected_cli_config", lambda: config)
    monkeypatch.setattr(news_semantic_engine, "make_news_semantic_engine", factory)
    monkeypatch.setattr(
        news_selection_runtime,
        "prepare_selection_candidates",
        _identity_selection(prepare),
    )
    return factory, prepare


def test_builder_passes_factory_callback_to_real_selection_call(monkeypatch):
    callback = object()
    factory, prepare = _patch_builder(
        monkeypatch,
        config={"enabled": True, "apiKey": "test-key"},
        callback=callback,
    )

    builder.build_briefing(
        "2026-06-10",
        strict_date=True,
        persist=False,
        market_scope="us",
        selection_context=_selection_context(),
    )

    assert factory.call_args.kwargs["engine"] == "cli"
    assert prepare.call_args.kwargs["semantic_callback"] is callback


@pytest.mark.parametrize(
    "config, llm_override",
    [
        ({"enabled": True, "apiKey": "test-key"}, False),
        ({"enabled": False}, None),
    ],
    ids=["llm-off", "ai-disabled"],
)
def test_builder_uses_rules_and_no_semantic_callback_when_cli_is_disabled(
    monkeypatch, config, llm_override
):
    factory, prepare = _patch_builder(monkeypatch, config=config, callback=None)

    builder.build_briefing(
        "2026-06-10",
        strict_date=True,
        llm_override=llm_override,
        persist=False,
        market_scope="us",
        selection_context=_selection_context(),
    )

    assert factory.call_args.kwargs["engine"] == "rules"
    assert prepare.call_args.kwargs["semantic_callback"] is None


def _patch_agent_prepare(monkeypatch, tmp_path, *, callback=None):
    factory = Mock(return_value=callback)
    prepare = Mock()
    monkeypatch.setattr(agent_service, "build_index", lambda **_kwargs: {})
    monkeypatch.setattr(agent_service, "load_index", lambda: {"documents": DOCS})
    monkeypatch.setattr(agent_service, "news_documents", lambda _index: DOCS)
    monkeypatch.setattr(
        agent_service,
        "select_briefing_docs",
        lambda *_args, **_kwargs: (DOCS, "2026-06-10", WINDOWS),
    )
    monkeypatch.setattr(agent_service, "scope_session_documents", lambda *_args, **_kwargs: DOCS)
    monkeypatch.setattr(agent_service, "cached_market_snapshot", lambda **_kwargs: {"ok": False})
    monkeypatch.setattr(agent_service, "cached_korea_market_data", lambda *args, **_kwargs: {"ok": False})
    monkeypatch.setattr(agent_service, "build_market_tape", lambda **_kwargs: {})
    monkeypatch.setattr(agent_service, "preflight_from_context", lambda *args, **_kwargs: {})
    monkeypatch.setattr(agent_service, "list_briefing_memories", lambda *args, **_kwargs: [])
    monkeypatch.setattr(agent_service, "collect_briefing_visuals", _visuals)
    monkeypatch.setattr(agent_service, "build_llm_context", lambda *args, **_kwargs: ("context", DOCS))
    monkeypatch.setattr(agent_service, "read_briefing_prompt", lambda *args, **_kwargs: "prompt")
    monkeypatch.setattr(agent_service, "_write_pack", lambda *_args, **_kwargs: tmp_path / "pack.json")
    monkeypatch.setattr(agent_service, "prepare_concentration", lambda groups, **_kwargs: (groups, {}))
    monkeypatch.setattr(
        news_semantic_engine,
        "make_news_semantic_engine",
        factory,
    )
    monkeypatch.setattr(
        news_selection_runtime,
        "prepare_selection_candidates",
        _identity_selection(prepare),
    )
    return factory, prepare


def test_standalone_prepare_pack_does_not_call_model_or_cli(monkeypatch, tmp_path):
    factory, prepare = _patch_agent_prepare(monkeypatch, tmp_path)
    model_call = Mock(side_effect=AssertionError("standalone prepare_pack called a model"))
    monkeypatch.setattr(agent_service, "run_agent_prompt", model_call, raising=False)

    agent_service.prepare_pack(
        "briefing",
        date="2026-06-10",
        market_scope="us",
        markets=["us"],
        selection_context=_selection_context(),
        web_search=False,
    )

    assert factory.call_args.kwargs["engine"] == "rules"
    assert prepare.call_args.kwargs["semantic_callback"] is None
    model_call.assert_not_called()


def test_prepare_pack_passes_explicit_cli_adapter_and_model_to_factory(monkeypatch, tmp_path):
    factory, _prepare = _patch_agent_prepare(monkeypatch, tmp_path)

    agent_service.prepare_pack(
        "briefing",
        date="2026-06-10",
        market_scope="us",
        markets=["us"],
        selection_context=_selection_context(),
        semantic_adapter="claude",
        semantic_model="claude-test-model",
        web_search=False,
    )

    assert factory.call_args.kwargs["engine"] == "cli"
    assert factory.call_args.kwargs["adapter"] == "claude"
    assert factory.call_args.kwargs["model"] == "claude-test-model"


def test_bridge_forwards_selected_cli_values_to_prepare_pack(monkeypatch, tmp_path):
    class StopAfterPrepare(Exception):
        pass

    prepare = Mock(return_value=({"outputContract": {}}, tmp_path / "pack.json"))
    monkeypatch.setattr(bridge.agent_service, "prepare_pack", prepare)
    monkeypatch.setattr("features.agent_mode.setup.configured_model", lambda _adapter: "claude-test-model")
    monkeypatch.setattr(bridge, "_observed_tool_policy", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(bridge, "_agent_prompt", Mock(side_effect=StopAfterPrepare))

    with pytest.raises(StopAfterPrepare):
        bridge._run_agent_task_locked(
            "briefing",
            {"market_scope": "us", "markets": ["us"], "selection_context": _selection_context()},
            selected={"id": "claude"},
            durable=False,
            progress=lambda *_args, **_kwargs: None,
            job_id="",
        )

    assert prepare.call_args.kwargs["semantic_adapter"] == "claude"
    assert prepare.call_args.kwargs["semantic_model"] == "claude-test-model"
