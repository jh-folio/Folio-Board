from __future__ import annotations

from features.topic_report.material_requirements import material_gap_messages, resolve_material_requirements


def test_material_resolution_preserves_actual_observation_dates_and_typed_gaps() -> None:
    plan = {
        "requiredMarketData": ["SPY", "없는 지표"],
        "requiredMacroData": ["미국 10년물", "지원하지 않는 거시 지표"],
    }
    market = {"tickers": {"SPY": {"label": "S&P 500 ETF", "last": 650.0, "asOfDate": "2026-08-21"}}}
    macro = {"fred": {"series": {"DGS10": {"latest": 4.1, "latestDate": "2026-08-20"}}}}
    resolved = resolve_material_requirements(plan, market, macro, resolved_at="2026-08-24T00:00:00Z")
    assert resolved["market"][0]["asOfDate"] == "2026-08-21"
    assert resolved["macro"][0]["seriesId"] == "DGS10"
    assert resolved["macro"][0]["asOfDate"] == "2026-08-20"
    assert resolved["market"][1]["status"] == "unsupported"
    assert resolved["macro"][1]["status"] == "unsupported"
    assert len(material_gap_messages(resolved)) == 2


def test_supported_but_unreturned_series_is_failed_not_unsupported() -> None:
    resolved = resolve_material_requirements(
        {"requiredMarketData": [], "requiredMacroData": ["UNRATE"]},
        {"tickers": {}},
        {"fred": {"series": {}}},
        resolved_at="2026-08-24T00:00:00Z",
    )
    assert resolved["macro"][0]["status"] == "failed"
