import json

from features.llm_settings import model_catalog


class FakeResponse:
    status = 200

    def __init__(self, body: str):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body.encode("utf-8")






def test_codex_fallback_is_newest_first_and_excludes_gpt_5_4():
    choices = model_catalog.CLI_MODEL_FALLBACKS["codex"]

    assert [item["value"] for item in choices] == [
        "gpt-6-astra", "gpt-6-sol", "gpt-6-luna",
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
        "gpt-5.5", "gpt-5.4-mini",
    ]
    assert "gpt-5.4" not in {item["value"] for item in choices}
    # The no-override default stays on a model older Codex CLIs still accept.
    assert model_catalog.CLI_DEFAULT_MODELS["codex"] == "gpt-5.6-sol"


def test_claude_fallback_lists_new_models_first_and_keeps_previous_ones():
    assert [item["value"] for item in model_catalog.CLI_MODEL_FALLBACKS["claude"]] == [
        "claude-opus-5-5", "claude-fable-5", "claude-sonnet-5", "claude-opus-5",
        "claude-haiku-4-5", "claude-opus-4-8", "claude-sonnet-4-6",
    ]


def test_every_listed_model_resolves_to_itself():
    # A newer model is an addition, not a replacement: rewriting a working
    # choice to a model the installed CLI does not know yet broke every
    # scheduled run until the CLI was updated (2026-09-23).
    assert model_catalog.DEPRECATED_MODEL_REPLACEMENTS == {}
    for provider, choices in model_catalog.CLI_MODEL_FALLBACKS.items():
        for item in choices:
            assert model_catalog.normalize_model_id(provider, item["value"]) == item["value"]


def test_cli_model_catalog_parses_stdout_and_keeps_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(model_catalog, "CACHE_PATH", tmp_path / "llm-model-cache.json")

    class Completed:
      returncode = 0
      stdout = "gpt-6.1\n- gpt-5.5\n"
      stderr = ""

    catalog = model_catalog.discover_cli_models(
        "codex",
        executable="codex",
        refresh=True,
        runner=lambda *_args, **_kwargs: Completed(),
        fallback=[{"value": "gpt-5.5", "label": "GPT-5.5"}],
    )

    assert catalog["source"] == "remote"
    assert [item["value"] for item in catalog["modelChoices"]] == ["gpt-6.1", "gpt-5.5"]


def test_claude_cli_catalog_uses_help_model_hints_when_list_commands_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(model_catalog, "CACHE_PATH", tmp_path / "llm-model-cache.json")

    class Completed:
        def __init__(self, returncode: int, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def runner(command, **_kwargs):
        if command == ["claude", "--help"]:
            return Completed(0, "--model <model> Provide an alias, e.g. 'fable', 'opus', or 'sonnet', or a full name like 'claude-fable-5'.")
        return Completed(1)

    catalog = model_catalog.discover_cli_models(
        "claude",
        executable="claude",
        refresh=True,
        runner=runner,
    )

    values = [item["value"] for item in catalog["modelChoices"]]
    assert catalog["source"] == "remote"
    assert "claude-fable-5" in values
    assert "claude-sonnet-5" in values
    assert "claude-opus-5" in values


def test_claude_catalog_keeps_active_models_from_existing_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "llm-model-cache.json"
    cache_path.write_text(json.dumps({
        "cli:claude:claude": {
            "provider": "claude",
            "transport": "cli",
            "source": "remote",
            "status": "available",
            "modelChoices": [
                {"value": "claude-opus-4-8", "label": "Claude Opus 4.8"},
                {"value": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
                {"value": "claude-opus-5", "label": "Claude Opus 5"},
            ],
        }
    }), encoding="utf-8")
    monkeypatch.setattr(model_catalog, "CACHE_PATH", cache_path)

    catalog = model_catalog.discover_cli_models("claude", executable="claude")

    # Curated choices come first (a cache can predate new models), then any
    # other discovered IDs; a cached older model is kept, not rewritten.
    assert [item["value"] for item in catalog["modelChoices"]] == [
        "claude-opus-5-5", "claude-fable-5", "claude-sonnet-5", "claude-opus-5",
        "claude-haiku-4-5", "claude-opus-4-8", "claude-sonnet-4-6",
    ]


def test_saved_previous_selections_are_not_rewritten():
    assert model_catalog.normalize_model_id("claude", "claude-opus-5") == "claude-opus-5"
    assert model_catalog.normalize_model_id("claude", "claude-opus-4-8") == "claude-opus-4-8"
    assert model_catalog.normalize_model_id("codex", "gpt-5.6-sol") == "gpt-5.6-sol"
