from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import app

from features.agent_mode import bridge as agent_bridge
from features.agent_mode import cli as agent_cli
from features.agent_mode import schema as agent_schema
from features.common.quality_generation import report_format
from features.common.research_library.indexing.service import (
    canonical_news_source,
    rss_item_is_market_relevant,
)
from features.common.research_library.rss.relevance import (
    canonical_media,
    is_korean_media_link,
    should_archive_item,
)
from features.common.utils import normalize, read_json
from features.automation import service as automation_service
from features.company_analysis import sec_filings
from features.company_analysis.filing_items import readable_filing_text
from features.company_analysis.sec_filings import html_to_paragraphs
from features.daily_briefing import service as briefing_service
from features.llm_settings import client as llm_client
from features.llm_settings import model_catalog
from features.market_memory import digest as memory_digest
from features.market_memory import regime_v2
from features.market_memory import service as memory_service
from features.obsidian.workflow import validator as obsidian_validator
from features.obsidian.workflow.note_factory import safe_filename
from features.personal_overlay import service as overlay_service
from features.portfolio import service as portfolio_service
from features.thesis_tracking import delta as thesis_delta
from features.common.market_data import snapshot as market_snapshot


def test_html_cleaners_remove_malformed_script_and_style_end_tags() -> None:
    markup = (
        "<p>Visible market text</p>"
        "<script>alert('private')</script >"
        "<style>body{display:none}</style >"
        "<p>Visible conclusion with enough words to remain a filing paragraph after parsing.</p>"
    )

    assert "alert" not in normalize(markup)
    assert "display:none" not in readable_filing_text(markup)
    assert all("alert" not in paragraph and "display:none" not in paragraph for paragraph in html_to_paragraphs(markup))


def test_media_classification_uses_parsed_hostname_not_arbitrary_substrings() -> None:
    spoofed_wsj = "https://wsj.com.attacker.invalid/markets/story"
    spoofed_kr = "https://mk.co.kr.attacker.invalid/news/story"
    spoofed_reuters = "https://reuters.com.attacker.invalid/markets/companies/NVDA.OQ"

    assert canonical_media("Unknown", spoofed_wsj, "") == "Unknown"
    assert canonical_news_source("User Archive", spoofed_wsj, "") == "User Archive"
    assert not is_korean_media_link(spoofed_kr)
    assert rss_item_is_market_relevant("Lifestyle shopping roundup", "", spoofed_kr)
    assert should_archive_item("Nvidia earnings guidance lifts shares", "", spoofed_reuters)


def test_model_parsers_reject_unbounded_adversarial_identifiers_quickly() -> None:
    oversized_openai = "gpt-" + ("-" * 20_000)
    oversized_claude = "claude-" + ("-" * 20_000)

    started = time.perf_counter()
    assert model_catalog._parse_cli_models(oversized_openai) == []
    assert model_catalog._parse_claude_help_models(oversized_claude) == []
    assert time.perf_counter() - started < 1.0


def test_report_heading_scan_is_linear_for_adversarial_whitespace() -> None:
    markdown = "## title" + (" " * 300_000) + "\nbody"
    started = time.perf_counter()
    sections = report_format._main_sections(markdown)
    assert len(sections) == 1
    assert time.perf_counter() - started < 1.0


def test_portfolio_backtest_ids_cannot_escape_storage_root(tmp_path: Path, monkeypatch) -> None:
    storage = tmp_path / "portfolio-backtests"
    storage.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"id":"outside"}', encoding="utf-8")
    monkeypatch.setattr(portfolio_service, "BACKTESTS_DIR", storage)

    assert portfolio_service.get_portfolio_backtest("../outside") is None
    assert portfolio_service.delete_portfolio_backtest("../outside") == {
        "deleted": False,
        "id": "../outside",
    }
    assert outside.exists()


def test_portfolio_backtest_valid_id_stays_readable_and_deletable(tmp_path: Path, monkeypatch) -> None:
    storage = tmp_path / "portfolio-backtests"
    storage.mkdir()
    saved = storage / "valid-id_1.json"
    saved.write_text('{"id":"valid-id_1"}', encoding="utf-8")
    monkeypatch.setattr(portfolio_service, "BACKTESTS_DIR", storage)

    assert portfolio_service.get_portfolio_backtest("valid-id_1") == {"id": "valid-id_1"}
    assert portfolio_service.delete_portfolio_backtest("valid-id_1") == {
        "deleted": True,
        "id": "valid-id_1",
    }
    assert not saved.exists()


def test_obsidian_filename_rejects_dot_segments_and_control_characters() -> None:
    assert safe_filename(".") == "Untitled"
    assert safe_filename("..") == "Untitled"
    assert "\n" not in safe_filename("line\nbreak")


def test_quality_fallback_does_not_expose_internal_exception_text(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_EXCEPTION_DETAIL"
    monkeypatch.setattr(app, "resolve_briefing", lambda *_args, **_kwargs: {"id": "2026-07-27"})
    monkeypatch.setattr(
        app,
        "evaluate_research_quality_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    payload = app.api_get_briefing("2026-07-27")

    assert marker not in str(payload)


def test_unhandled_http_exception_returns_stable_public_error(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_HTTP_EXCEPTION_DETAIL"

    response = app.unhandled_exception_handler(None, RuntimeError(marker))

    assert response.status_code == 500
    assert json.loads(response.body) == {"error": "internal_server_error"}
    assert marker not in response.body.decode("utf-8")


def test_common_json_reader_rejects_paths_outside_explicit_root(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"private":true}', encoding="utf-8")

    assert read_json(outside, None, root=root) is None


def test_briefing_reader_rejects_paths_outside_briefings_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "briefings"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"private":true}', encoding="utf-8")
    monkeypatch.setattr(briefing_service, "BRIEFINGS_DIR", root)

    assert briefing_service._read_briefing_json(outside) is None


def test_agent_scrubber_covers_credential_keys_and_bearer_values() -> None:
    marker = "SYNTHETIC_PRIVATE_AGENT_CREDENTIAL"
    payload = {
        "credential": marker,
        "nested": {"message": f"request failed with Authorization: Bearer {marker}"},
    }

    scrubbed = agent_schema.scrub_secrets(payload)

    assert marker not in json.dumps(scrubbed)
    assert scrubbed["credential"] == "[redacted]"


def test_agent_cli_never_prints_credential_shaped_payload(capsys) -> None:
    marker = "SYNTHETIC_PRIVATE_CLI_CREDENTIAL"

    agent_cli._print_json({"credential": marker})

    assert marker not in capsys.readouterr().out


def test_agent_bridge_probe_does_not_return_raw_exception_text(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_BRIDGE_EXCEPTION_DETAIL"
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _binary: "/usr/bin/codex")
    monkeypatch.setattr(
        agent_bridge.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    payload = agent_bridge._probe_adapter("codex")

    assert marker not in json.dumps(payload)
    assert payload["error"] == "CLI 상태를 확인하지 못했습니다."


def test_sec_cache_does_not_persist_raw_fetch_exception(tmp_path: Path, monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_SEC_FETCH_EXCEPTION_DETAIL"
    cache_path = tmp_path / "sec-cache.json"
    monkeypatch.setattr(
        sec_filings.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    text, error = sec_filings.fetch_text("https://www.sec.gov/example", cache_path)

    assert text == ""
    assert marker not in error
    assert marker not in cache_path.read_text(encoding="utf-8")


def test_api_keys_are_written_to_secret_store_not_dotenv(tmp_path: Path, monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_FRED_API_KEY"
    stored: dict[str, str] = {}
    monkeypatch.setattr(llm_client, "ROOT", tmp_path)
    monkeypatch.setattr(
        llm_client,
        "_store_secret_value",
        lambda key, value: stored.__setitem__(key, value),
        raising=False,
    )

    llm_client.write_env_values({
        "FRED_API_KEY": marker,
        "SEC_USER_AGENT": "release-test@example.invalid",
    })

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert stored["FRED_API_KEY"] == marker
    assert marker not in env_text
    assert "FRED_API_KEY=" not in env_text
    assert "SEC_USER_AGENT=release-test@example.invalid" in env_text


def test_secret_store_loads_without_dotenv_file(tmp_path: Path, monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_STORED_API_KEY"
    monkeypatch.setattr(llm_client, "ROOT", tmp_path)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_client,
        "_load_secret_value",
        lambda key: marker if key == "FRED_API_KEY" else "",
    )

    llm_client.load_dotenv()

    assert llm_client.os.environ["FRED_API_KEY"] == marker


def test_legacy_dotenv_secrets_migrate_to_secret_store(tmp_path: Path, monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_LEGACY_API_KEY"
    stored: dict[str, str] = {}
    (tmp_path / ".env").write_text(
        f"FRED_API_KEY={marker}\nSEC_USER_AGENT=release-test@example.invalid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_client, "ROOT", tmp_path)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_client,
        "_store_secret_value",
        lambda key, value: stored.__setitem__(key, value),
    )
    monkeypatch.setattr(llm_client, "_load_secret_value", lambda _key: "")

    llm_client.load_dotenv()

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert stored["FRED_API_KEY"] == marker
    assert marker not in env_text
    assert "FRED_API_KEY=" not in env_text
    assert "SEC_USER_AGENT=release-test@example.invalid" in env_text


def test_portfolio_price_cache_path_is_one_bounded_child(monkeypatch, tmp_path: Path) -> None:
    cache_root = tmp_path / "portfolio-price-cache"
    monkeypatch.setattr(portfolio_service, "PORTFOLIO_PRICE_CACHE_DIR", cache_root)

    path = portfolio_service._series_cache_path(
        "AAPL",
        "../../outside",
        "2026-01-01/../../escaped",
    )

    assert path.parent == cache_root
    assert ".." not in path.name


def test_failed_secret_migration_preserves_legacy_dotenv_value(tmp_path: Path, monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_UNMIGRATED_API_KEY"
    (tmp_path / ".env").write_text(
        f"FRED_API_KEY={marker}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_client, "ROOT", tmp_path)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_client,
        "_store_secret_value",
        lambda _key, _value: (_ for _ in ()).throw(RuntimeError("credential store unavailable")),
    )
    monkeypatch.setattr(llm_client, "_load_secret_value", lambda _key: "")

    llm_client.load_dotenv()

    assert marker in (tmp_path / ".env").read_text(encoding="utf-8")
    assert llm_client.os.environ["FRED_API_KEY"] == marker


def test_automation_result_does_not_expose_raw_exception(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_AUTOMATION_EXCEPTION_DETAIL"
    monkeypatch.setattr(
        automation_service,
        "import_rssarchive",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )
    monkeypatch.setattr(automation_service, "_append_run", lambda _row: None)

    payload = automation_service.run_automation_once("rss")

    assert marker not in json.dumps(payload)
    assert payload["error"] == "automation_failed"


def test_personal_overlay_status_does_not_expose_raw_exception(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_OVERLAY_EXCEPTION_DETAIL"
    monkeypatch.setattr(
        overlay_service,
        "selected_cli_config",
        lambda: {"enabled": True, "provider": "codex", "model": "test"},
    )
    monkeypatch.setattr(overlay_service, "read_prompt", lambda: "prompt")
    monkeypatch.setattr(
        overlay_service,
        "request_cli_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    _overlay, status = overlay_service.generate_overlay(
        {"markdown": "canonical"},
        [{"title": "hypothesis"}],
        llm_override=True,
    )

    assert marker not in status
    assert status == "generation_failed"


def test_thesis_delta_status_does_not_expose_raw_exception(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_THESIS_EXCEPTION_DETAIL"
    monkeypatch.setattr(
        thesis_delta,
        "gather_local_evidence",
        lambda *_args, **_kwargs: ([{"title": "evidence"}], {"periodDays": 90, "cutoff": "2026-01-01"}),
    )
    monkeypatch.setattr(
        thesis_delta,
        "selected_cli_config",
        lambda: {"enabled": True, "provider": "codex", "model": "test"},
    )
    monkeypatch.setattr(thesis_delta, "read_prompt", lambda: "prompt")
    monkeypatch.setattr(
        thesis_delta,
        "request_cli_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    payload, status = thesis_delta.generate_delta({"ticker": "TEST"}, llm_override=True)

    assert marker not in json.dumps(payload)
    assert status == "generation_failed"


def test_market_memory_results_do_not_expose_raw_exceptions(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_MEMORY_EXCEPTION_DETAIL"
    monkeypatch.setattr(
        memory_service,
        "selected_cli_config",
        lambda: {"enabled": True, "provider": "codex", "model": "test"},
    )
    monkeypatch.setattr(memory_service, "read_market_memory_prompt", lambda: "prompt")
    monkeypatch.setattr(memory_service, "build_memory_llm_context", lambda _date: ("context", [], "2026-01-01"))
    monkeypatch.setattr(
        memory_service,
        "request_cli_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )
    monkeypatch.setattr(
        regime_v2,
        "refresh_all_regimes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    llm_payload = memory_service.run_llm_market_memory("2026-01-01")
    digest_payload = memory_digest.run_rss_market_memory_update(items=[])

    assert marker not in json.dumps(llm_payload)
    assert marker not in json.dumps(digest_payload)
    assert llm_payload["status"] == "generation_failed"
    assert digest_payload["regimeRefresh"]["error"] == "regime_refresh_failed"


def test_portfolio_and_market_snapshot_errors_are_stable(monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_MARKET_PROVIDER_EXCEPTION_DETAIL"
    fake_yfinance = SimpleNamespace(
        Ticker=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    portfolio_payload = portfolio_service.resolve_portfolio_ticker("TEST")
    snapshot_payload = market_snapshot.fetch_market_snapshot()

    assert marker not in json.dumps(portfolio_payload)
    assert marker not in json.dumps(snapshot_payload)
    assert portfolio_payload["error"] == "quote_provider_unavailable"
    assert all(
        item.get("error") == "market_data_unavailable"
        for item in snapshot_payload["tickers"].values()
    )


def test_obsidian_validation_does_not_expose_parser_exception(tmp_path: Path, monkeypatch) -> None:
    marker = "SYNTHETIC_PRIVATE_OBSIDIAN_EXCEPTION_DETAIL"
    note = tmp_path / "note.md"
    note.write_text("---\ntype: company_thesis\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(obsidian_validator, "_require_vault", lambda: tmp_path)
    monkeypatch.setattr(
        obsidian_validator,
        "validate_note",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    payload = obsidian_validator.validate_vault()

    assert marker not in json.dumps(payload)
    assert payload["notes"][0]["issues"][0]["message"] == "노트를 읽거나 파싱하지 못했습니다."
