"""Q2 call-value tests for the shared briefing writer set."""

from pathlib import Path

from features.common.market_calendar import briefing_market_windows
from features.daily_briefing import service as daily_service
from features.daily_briefing.issue_selection import build_issue_coverage, documents_for_scope
from features.agent_mode import service as agent_service
from features.daily_briefing.selection import derive_market_drivers, prioritize_briefing_groups
from features.common.research_library.search.service import group_docs


DATE = "2026-06-10"


def _docs():
    """A cap-binding, four-market fixture with explicit market ownership.

    The explicit tags keep this test about call-value parity rather than the
    market keyword classifier. Twelve publishers per market exercise the real
    diversity/ranking path while binding both 24-row daily and 40-row weekly
    limits.
    """
    market_labels = {"us": "Nasdaq", "kr": "코스피", "jp": "니케이", "europe": "DAX"}
    market_companies = {
        "us": ("Nvidia", "NVDA"), "kr": ("삼성전자", "005930"),
        "jp": ("도요타", "7203"), "europe": ("SAP", "SAP"),
    }
    rows = []
    for market, label in market_labels.items():
        company, ticker = market_companies[market]
        for index in range(45):
            publisher = f"{market.upper()} Wire {index % 12}"
            driver = ("금리" if index % 3 == 0 else "반도체" if index % 3 == 1 else "실적")
            rows.append({
                "title": f"{label} {driver} update {index}: {company} shares react",
                "summary": f"{label} moved {1.0 + index / 100:.2f}% as {driver} changed; {company} reacted.",
                "content": f"{label} moved {1.0 + index / 100:.2f}% as {driver} changed; {company} reacted. Investors tracked the session reversal.",
                "source": publisher, "sourceWeight": 9, "date": "2026-06-09",
                "marketSessionDate": "2026-06-09",
                "path": f"research-inbox/rss/{market}-{index}.md",
                "url": f"https://example.com/{market}/{index}", "type": "article",
                "market": market.upper(),
                "companies": [{"name": company, "ticker": ticker, "market": market.upper()}],
                "sectors": ["Semiconductors" if index % 2 else "Technology"],
                "impactTags": [driver, "시장"],
                "marketRelevance": 80, "wordCount": 240,
            })
    return rows


def _market_inputs(docs, market, windows):
    market_docs = documents_for_scope(docs, market)
    groups = prioritize_briefing_groups(
        group_docs(market_docs), windows, limit=6, market_scope=market,
    )
    drivers = [{**driver, "market": market} for driver in derive_market_drivers(market_docs, windows, limit=4)]
    issues = build_issue_coverage(
        market_docs, market.upper(), windows, limit=10,
        coherence_policy=(market == "kr"),
    )
    return market_docs, groups, drivers, issues


def _capture_writer(original, sink):
    def wrapped(*args, **kwargs):
        context, docs = original(*args, **kwargs)
        sink["writer_ids"] = [row.get("sourceId") for row in docs]
        sink["excerpts"] = {row.get("sourceId"): row.get("writerExcerpt") for row in docs}
        sink["context"] = context
        return context, docs

    return wrapped


def test_api_and_real_prepare_pack_use_same_writer_ids_and_excerpt_values(monkeypatch, tmp_path):
    docs = _docs()
    windows = briefing_market_windows(DATE)
    api_capture, cli_capture, api_request = {}, {}, {}
    original_context = daily_service.build_llm_context
    monkeypatch.setattr(agent_service, "build_llm_context", _capture_writer(original_context, cli_capture))

    monkeypatch.setattr(daily_service, "selected_cli_config", lambda: {
        "enabled": True, "apiKey": "test", "provider": "openai", "model": "gpt-test",
    })
    monkeypatch.setattr(daily_service, "read_briefing_prompt", lambda *args, **kwargs: "Write briefing")
    monkeypatch.setattr(daily_service, "use_web_search_for_briefing", lambda: False)
    def fake_request(_cfg, _prompt, context, **_kwargs):
        api_request["context"] = context
        return "# Market Briefing — 2026.06.09\n\n## 0. 오늘의 시장 성격\n본문", "resp", {}

    monkeypatch.setattr(daily_service, "request_cli_text", fake_request)
    monkeypatch.setattr(daily_service, "build_llm_context", _capture_writer(original_context, api_capture))
    api_results = {}
    for market in ("us", "kr"):
        market_docs, groups, drivers, issues = _market_inputs(docs, market, windows)
        api_result, api_status = daily_service.generate_llm_briefing(
            DATE, "2026-06-10", market_docs, groups, market_drivers=drivers,
            issue_coverage=issues, market_windows=windows,
            market_scope=market, markets=[market], llm_override=True,
        )
        api_results[market] = (api_result, api_status, dict(api_capture))
        api_capture.clear()
        assert api_status == "ok_local_only" and api_result
    api_writer_ids = [source_id for market in ("us", "kr") for source_id in api_results[market][2]["writer_ids"]]
    api_excerpts = {
        source_id: excerpt
        for market in ("us", "kr")
        for source_id, excerpt in api_results[market][2]["excerpts"].items()
    }

    # Exercise the real Agent prepare function; only external/data boundaries
    # are fixed so no provider, CLI, server, or persistent user data is used.
    monkeypatch.setattr(agent_service, "build_index", lambda incremental=True: None)
    monkeypatch.setattr(agent_service, "load_index", lambda: {"documents": docs})
    monkeypatch.setattr(agent_service, "news_documents", lambda index: list(docs))
    monkeypatch.setattr(agent_service, "select_briefing_docs", lambda *args, **kwargs: (list(docs), "2026-06-10", windows))
    monkeypatch.setattr(agent_service, "scope_session_documents", lambda rows, *args, **kwargs: list(rows))
    monkeypatch.setattr(agent_service, "infer_market_session_date", lambda doc, windows: doc.get("date"))
    monkeypatch.setattr(agent_service, "prepare_concentration", lambda groups, **kwargs: (groups, None))
    monkeypatch.setattr(agent_service, "collect_briefing_visuals", lambda *args, **kwargs: {
        "visualRecommendations": [], "visualSnapshots": [], "sidecar": {}, "warnings": [],
    })
    monkeypatch.setattr(agent_service, "cached_market_snapshot", lambda **kwargs: {"ok": False})
    monkeypatch.setattr(agent_service, "cached_korea_market_data", lambda *args, **kwargs: {"ok": False})
    monkeypatch.setattr(agent_service, "build_market_tape", lambda **kwargs: {})
    monkeypatch.setattr(agent_service, "preflight_from_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(agent_service, "list_briefing_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(agent_service, "load_prev_briefing", lambda *args, **kwargs: {})
    monkeypatch.setattr(agent_service, "read_briefing_prompt", lambda *args, **kwargs: "Write briefing")
    monkeypatch.setattr(agent_service, "use_web_search_for_briefing", lambda: False)
    monkeypatch.setattr(agent_service.A, "write_pack", lambda pack, **kwargs: Path(tmp_path) / "pack.json")

    pack, _ = agent_service.prepare_briefing_pack(
        DATE, markets=["us", "kr"], market_scope="both", web_search=False,
    )

    assert api_writer_ids == cli_capture["writer_ids"]
    assert api_excerpts == cli_capture["excerpts"]
    for market in ("us", "kr"):
        api_result, _api_status, capture = api_results[market]
        assert [row.get("sourceId") for row in api_result["usedDocs"]] == capture["writer_ids"]
        assert {row.get("sourceId"): row.get("writerExcerpt") for row in api_result["usedDocs"]} == capture["excerpts"]
        assert len(capture["writer_ids"]) == 24
    assert set(pack["internal"]["sourcesByMarket"]) == {"us", "kr"}
    market_ids = {
        row.get("sourceId")
        for rows in pack["internal"]["sourcesByMarket"].values()
        for row in rows
    }
    assert market_ids <= set(cli_capture["writer_ids"])
    assert all(f"sourceId={source_id}" in cli_capture["context"] for source_id in cli_capture["writer_ids"])
    assert all(f'"sourceId":"{source_id}"' in pack["context"] for source_id in cli_capture["writer_ids"])
    assert all(excerpt in cli_capture["context"] for excerpt in cli_capture["excerpts"].values())
    us_ids = {row.get("sourceId") for row in pack["internal"]["sourcesByMarket"]["us"]}
    kr_ids = {row.get("sourceId") for row in pack["internal"]["sourcesByMarket"]["kr"]}
    assert us_ids.isdisjoint(kr_ids)
    assert len(us_ids) == len(kr_ids) == 24
    assert all(row.get("writerExcerpt") for row in pack["sources"])
    assert all(f"research-inbox/rss/{market}-" not in pack["context"] for market in ("jp", "europe"))

    # The same value check covers a non-legacy pair as well.  This catches an
    # implementation that special-cases `both`/US+KR while still combining JP
    # and Europe into one shared capped pool.
    api_capture.clear()
    api_results = {}
    for market in ("europe", "jp"):
        market_docs, groups, drivers, issues = _market_inputs(docs, market, windows)
        api_result, api_status = daily_service.generate_llm_briefing(
            DATE, "2026-06-10", market_docs, groups, market_drivers=drivers,
            issue_coverage=issues, market_windows=windows,
            market_scope=market, markets=[market], llm_override=True,
        )
        api_results[market] = (api_result, api_status, dict(api_capture))
        api_capture.clear()
        assert api_status == "ok_local_only" and api_result
    jp_eu_api_ids = [source_id for market in ("europe", "jp") for source_id in api_results[market][2]["writer_ids"]]
    jp_eu_api_excerpts = {
        source_id: excerpt
        for market in ("europe", "jp")
        for source_id, excerpt in api_results[market][2]["excerpts"].items()
    }
    cli_capture.clear()
    pack_jp_eu, _ = agent_service.prepare_briefing_pack(
        DATE, markets=["jp", "europe"], market_scope="multi", web_search=False,
    )
    assert jp_eu_api_ids == cli_capture["writer_ids"], (jp_eu_api_ids, cli_capture["writer_ids"])
    assert jp_eu_api_excerpts == cli_capture["excerpts"]
    assert set(pack_jp_eu["internal"]["sourcesByMarket"]) == {"jp", "europe"}
    jp_ids = {row.get("sourceId") for row in pack_jp_eu["internal"]["sourcesByMarket"]["jp"]}
    eu_ids = {row.get("sourceId") for row in pack_jp_eu["internal"]["sourcesByMarket"]["europe"]}
    assert jp_ids.isdisjoint(eu_ids)
    assert len(jp_ids) == len(eu_ids) == 24
    assert all(f"research-inbox/rss/{market}-" not in pack_jp_eu["context"] for market in ("us", "kr"))


def test_legacy_weak_key_sources_remain_accessible():
    rows = daily_service.source_refs([
        {"title": "URL source", "url": "https://example.com/u"},
        {"title": "Path source", "path": "research-inbox/rss/p.md"},
        {"title": "Title source"},
    ], limit=10)

    assert [row["title"] for row in rows] == ["URL source", "Path source", "Title source"]
    assert all(row.get("sourceId", "").startswith("src_") for row in rows)


def test_writer_cap_is_per_market_for_weekly_context():
    docs = _docs()
    windows = briefing_market_windows(DATE)
    weekly_window = {
        "publicationDate": DATE,
        "weekStart": "2026-06-08",
        "weekEnd": "2026-06-14",
        "previewStart": "2026-06-15",
        "previewEnd": "2026-06-19",
    }
    for market in ("us", "kr"):
        market_docs, groups, drivers, issues = _market_inputs(docs, market, windows)
        _context, writer_docs = daily_service.build_llm_context(
            DATE, "2026-06-08~2026-06-14", market_docs, groups,
            market_drivers=drivers, issue_coverage=issues,
            market_windows=windows, market_scope=market, markets=[market],
            kind="weekly", weekly_window=weekly_window,
        )
        assert len(writer_docs) == 40
