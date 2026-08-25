from features.agent_mode.service import _single_market_briefing as agent_single_market
from features.daily_briefing.builder import _single_market_briefing as builder_single_market
from features.daily_briefing.schema import briefing_scope_view


def _report():
    return {
        "date": "2026-08-24",
        "marketScope": "both",
        "briefings": {
            "us": {"markdown": "# US", "sources": []},
            "kr": {"markdown": "# KR", "sources": []},
        },
        "dataGaps": [
            {"market": "us", "message": "US heatmap missing"},
            {"market": "kr", "message": "KR tape missing"},
            {"market": "both", "message": "global input missing"},
        ],
    }


def _messages(report):
    return [row["message"] for row in report["dataGaps"]]


def test_builder_single_market_filters_foreign_gaps():
    assert _messages(builder_single_market(_report(), "us")) == ["US heatmap missing", "global input missing"]


def test_agent_single_market_filters_foreign_gaps():
    assert _messages(agent_single_market(_report(), "kr")) == ["KR tape missing", "global input missing"]


def test_schema_scope_view_filters_foreign_gaps_for_read_compatibility():
    assert _messages(briefing_scope_view(_report(), "us")) == ["US heatmap missing", "global input missing"]
