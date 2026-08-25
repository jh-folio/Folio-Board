"""계획이 요청한 자료가 실제로 실리는지 — 거시 시리즈·장기 시계열·기사 본문 계약."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.common.research_quality.evaluator import evaluate_report
from features.topic_report import evidence_text as T
from features.topic_report.data_fetcher import _quarterly_closes, _window_length, market_data_to_markdown
from features.topic_report.macro_data import (
    FRED_SERIES_META,
    _observation_a_year_before,
    _quarterly_history,
    macro_data_to_markdown,
    resolve_fred_series,
)


# --------------------------------------------------------------------- 거시 시리즈

def test_plan_macro_series_are_resolved_not_dropped():
    # 계획이 요청한 기대인플레이션·실질금리를 그대로 조회해야 한다. 예전에는 계획에
    # 적어 화면에 보여주고서 custom 고정값 3종만 조회했다.
    requested = ["FEDFUNDS", "DGS10", "T10YIE", "DFII10", "CPILFESL"]
    assert resolve_fred_series(requested) == requested


def test_unknown_series_are_filtered_out():
    # requiredMacroData는 LLM이 쓴 자유 텍스트다. 모르는 ID를 네트워크로 보내지 않는다.
    assert resolve_fred_series(["DGS10", "MADE_UP_SERIES"]) == ["DGS10"]


def test_all_unknown_falls_back_to_defaults():
    assert resolve_fred_series(["MADE_UP"], fallback=["FEDFUNDS", "UNRATE"]) == ["FEDFUNDS", "UNRATE"]


def test_breakeven_and_real_rate_series_are_known():
    for series_id in ("T10YIE", "T5YIE", "T5YIFR", "DFII10", "DGS30"):
        assert series_id in FRED_SERIES_META, f"{series_id} 라벨이 없으면 컨텍스트에 원시 ID가 실린다"


def test_year_over_year_uses_dates_not_index():
    # 일간 시리즈에서 obs[12]는 12영업일이지 1년이 아니다.
    obs = [(f"2026-08-{day:02d}", "4.7") for day in range(24, 4, -1)] + [("2025-08-20", "3.9")]
    assert _observation_a_year_before(obs, "2026-08-24") == ("2025-08-20", "3.9")


def test_year_over_year_is_empty_when_history_is_short():
    assert _observation_a_year_before([("2026-08-24", "4.7")], "2026-08-24") == (None, None)


def test_quarterly_history_keeps_last_observation_of_each_quarter():
    obs = [
        ("2026-08-24", "4.7"),
        ("2026-07-01", "4.4"),
        ("2026-03-31", "4.3"),
        ("2026-01-02", "4.1"),
    ]
    assert _quarterly_history(obs) == [["2026Q1", "4.3"], ["2026Q3", "4.7"]]


def test_macro_markdown_renders_the_trend_line():
    macro = {
        "ok": True,
        "fred": {
            "ok": True,
            "series": {
                "T10YIE": {
                    "label": FRED_SERIES_META["T10YIE"],
                    "latest": 2.4,
                    "latestDate": "2026-08-20",
                    "changeMoM": 0.02,
                    "changeYoY": 0.1,
                    "history": [("2025Q3", "2.3"), ("2025Q4", "2.3"), ("2026Q1", "2.35"), ("2026Q2", "2.4")],
                }
            },
            "errors": [],
        },
    }
    rendered = macro_data_to_markdown(macro)
    assert "분기별 추이" in rendered
    assert "2025Q3 2.3" in rendered


# --------------------------------------------------------------------- 장기 시계열

def test_stats_window_stays_at_the_requested_period():
    # 긴 구간을 받아도 통계·상관관계 창은 history_period 그대로여야 한다 —
    # 창을 늘리면 "1년 상관계수" 같은 기존 해석의 의미가 조용히 바뀐다.
    assert _window_length("1y", available=2500) == 252
    assert _window_length("3y", available=2500) == 756
    assert _window_length("1y", available=100) == 100, "자료가 짧으면 있는 만큼만"


def test_quarterly_closes_cover_past_episodes():
    dated = [("2021-12-31", 1.51), ("2022-03-31", 2.33), ("2022-06-30", 2.97), ("2026-08-24", 4.71)]
    assert _quarterly_closes(dated) == [
        ["2021Q4", 1.51],
        ["2022Q1", 2.33],
        ["2022Q2", 2.97],
        ["2026Q3", 4.71],
    ]


def test_market_markdown_renders_quarterly_history():
    data = {
        "ok": True,
        "asOf": "2026-08-24",
        "period": "1y",
        "longPeriod": "10y",
        "tickers": {
            "^TNX": {
                "label": "미국 10년물",
                "last": 4.71,
                "changes": {},
                "stats": {},
                "quarterlyHistory": [("2021Q4", 1.51), ("2022Q1", 2.33), ("2022Q2", 2.97), ("2026Q3", 4.71)],
            }
        },
        "correlations": [],
    }
    rendered = market_data_to_markdown(data)
    assert "분기별 종가 추이" in rendered
    assert "2022Q1 2.33" in rendered


# --------------------------------------------------------------------- 기사 본문

def test_evidence_body_reads_full_text(tmp_path, monkeypatch):
    inbox = tmp_path / "research-inbox"
    (inbox / "rss").mkdir(parents=True)
    article = inbox / "rss" / "sample.md"
    article.write_text(
        '---\ntitle: "t"\n---\n\n## Summary\n\n짧은 요약\n\n## Full Text\n\n' + ("본문 " * 400),
        encoding="utf-8",
    )
    monkeypatch.setattr(T, "research_inbox_dir", lambda: inbox)
    body = T.read_evidence_body("research-inbox/rss/sample.md", limit=100)
    assert body.startswith("본문")
    assert len(body) == 100


def test_evidence_body_refuses_paths_outside_the_inbox(tmp_path, monkeypatch):
    inbox = tmp_path / "research-inbox"
    (inbox / "rss").mkdir(parents=True)
    outside = tmp_path / "secret.md"
    outside.write_text("## Full Text\n\n비밀", encoding="utf-8")
    monkeypatch.setattr(T, "research_inbox_dir", lambda: inbox)
    assert T.read_evidence_body("research-inbox/rss/../../secret.md") == ""


def test_body_budget_limits_total_and_document_count(tmp_path, monkeypatch):
    inbox = tmp_path / "research-inbox"
    (inbox / "rss").mkdir(parents=True)
    docs = []
    for index in range(6):
        name = f"a{index}.md"
        (inbox / "rss" / name).write_text("## Full Text\n\n" + ("가" * 3000), encoding="utf-8")
        docs.append({"id": f"ev_{index:03d}", "path": f"research-inbox/rss/{name}", "relevance": 1 - index / 10, "summary": ""})
    monkeypatch.setattr(T, "research_inbox_dir", lambda: inbox)
    monkeypatch.setenv("TOPIC_EVIDENCE_BODY_CHARS", "1000")
    monkeypatch.setenv("TOPIC_EVIDENCE_BODY_BUDGET", "2500")
    bodies = T.select_bodies(docs)
    assert sum(len(v) for v in bodies.values()) <= 2500
    assert list(bodies) == ["ev_000", "ev_001", "ev_002"], "관련도 상위부터 채운다"


# --------------------------------------------------------------------- 품질 눈금

_REPORT = """# 리포트

## 1. Executive Summary
현재 판단: 장기금리는 높다. 10년물 4.73%, 30년물 5.27%, 2년물 3.71%.

## 2. 질문 정의와 분석 범위
분석 범위는 미국 금리다.

## 7. 반론과 리스크
반대 근거: 물가 둔화가 이어지면 틀릴 수 있다.

## 8. 시나리오
10년물이 4.75%를 넘으면 악화.

## 9. 앞으로 확인할 체크포인트
10년물 4.5% 이하.

## 11. Source & Data Notes
데이터 한계가 있다.
"""


def _quality(axis_levels: list[str]) -> dict:
    axis_coverage = {
        f"axis_{i}": {"label": f"축 {i}", "count": 5 if level == "high" else 0, "level": level}
        for i, level in enumerate(axis_levels)
    }
    return evaluate_report(
        _REPORT,
        evidence_summary={"axisCoverage": axis_coverage, "totalDocs": 29, "deepResearch": {"enabled": False}},
        artifact_type="topic_report",
    )


def test_empty_axes_cap_the_score():
    # 축 5개 중 3개가 0건인 보고서가 87점 A- pass를 받은 적이 있다. 잘 쓴 문장이
    # 없는 근거를 대신하지 못한다.
    mostly_empty = _quality(["high", "high", "none", "none", "none"])
    assert mostly_empty["score"] <= 59
    assert mostly_empty["status"] != "pass"
    assert mostly_empty["coverageCeiling"]["applied"] is True


def test_one_empty_axis_still_loses_the_top_grades():
    one_empty = _quality(["high", "high", "high", "high", "none"])
    assert one_empty["score"] <= 74
    assert one_empty["coverageCeiling"]["applied"] is True


def test_full_coverage_is_not_capped():
    full = _quality(["high"] * 5)
    assert full["coverageCeiling"]["applied"] is False
    assert full["score"] > 74


def test_history_rows_survive_canonical_serialization():
    """분기 시계열은 보고서 JSON에 실리므로 정규화 직렬화기를 통과해야 한다.

    tuple로 두면 보고서를 다 만들어 놓고 저장 직전에 죽는다 — 실측으로 잡이 진행률
    90%에서 `internal_error`로 끝났고, CLI 수 분과 그 결과물이 통째로 버려졌다.
    """
    from features.common.canonical_json import canonical_json_bytes

    rows = _quarterly_closes([("2021-12-31", 1.51), ("2022-03-31", 2.33)])
    macro_rows = _quarterly_history([("2026-08-24", "4.7"), ("2026-03-31", "4.3")])
    canonical_json_bytes({"quarterlyHistory": rows, "history": macro_rows})


def test_index_series_change_is_a_percentage_not_index_points():
    """지수·수준값의 변화는 %여야 한다.

    절대 차이를 단위 없이 내보냈더니 모델이 근원 CPI 지수의 1년 차이 8.11포인트를
    "전년 대비 +8.11%"로 읽어 보고서 본문에 실었다(실제는 약 2.5%).
    """
    from features.topic_report.macro_data import change_unit

    assert change_unit("CPILFESL") == "%"
    assert change_unit("PAYEMS") == "%"
    assert change_unit("DGS10") == "%p", "금리는 이미 퍼센트라 차이가 %p다"
    assert change_unit("T10YIE") == "%p"


def test_macro_markdown_prints_the_change_unit():
    macro = {
        "ok": True,
        "fred": {
            "ok": True,
            "series": {
                "CPILFESL": {
                    "label": "미국 근원 CPI",
                    "latest": 336.789,
                    "latestDate": "2026-07-01",
                    "changeMoM": 0.22,
                    "changeYoY": 2.47,
                    "changeUnit": "%",
                    "history": [],
                }
            },
            "errors": [],
        },
    }
    rendered = macro_data_to_markdown(macro)
    assert "+2.47%" in rendered
    assert "1년 전 대비" in rendered, "'전년 대비'는 지수 차이와 상승률을 구분하지 못한다"
