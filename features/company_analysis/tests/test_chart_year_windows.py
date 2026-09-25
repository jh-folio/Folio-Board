"""손익 차트가 현금흐름만 가진 해까지 라벨로 물고 와 빈 점을 그렸다.

`build_company_analysis_charts()`는 예전에 6개 지표(매출·매출총이익·영업이익·
순이익·영업활동현금흐름·설비투자) 전체의 union으로 `years` 하나를 잡았다.
영업활동현금흐름·설비투자는 yfinance `cashflowRows`로 보강되어 손익 4종보다
한 해 더 먼 과거를 갖는 경우가 실측됐다(000660 SK하이닉스 — DART 손익은
2023년부터, 보강된 현금흐름은 2022년부터). 그 결과 "실적 추이"·"마진 추이"
차트가 2022년을 라벨에 포함하면서 값은 전부 null인 빈 점을 그렸다 — 실제로는
그 해 자료가 없는 게 아니라, 다른 지표군의 자료 폭을 억지로 빌려온 것이었다.
"""
from __future__ import annotations

from features.company_analysis.service import build_company_analysis_charts


def _sec_rows(**by_metric):
    return {
        "ok": True,
        "currency": "USD",
        "rows": [
            {
                "metric": metric,
                "annual": [{"end": f"{year}-12-31", "val": value} for year, value in values.items()],
            }
            for metric, values in by_metric.items()
        ],
    }


def _charts():
    sec = _sec_rows(**{
        "Revenue": {"2023": 100.0, "2024": 120.0, "2025": 150.0},
        "Gross Profit": {"2023": 40.0, "2024": 50.0, "2025": 60.0},
        "Operating Income": {"2023": 20.0, "2024": 25.0, "2025": 30.0},
        "Net Income": {"2023": 15.0, "2024": 18.0, "2025": 22.0},
        # 현금흐름 두 지표만 2022년을 한 해 더 갖는다 — 실측된 000660 패턴.
        "Operating Cash Flow": {"2022": 10.0, "2023": 25.0, "2024": 30.0, "2025": 35.0},
        "Capital Expenditure": {"2022": 5.0, "2023": 8.0, "2024": 9.0, "2025": 10.0},
    })
    market = {
        "ok": True, "ticker": "X", "price": 50.0, "currency": "USD",
        "sharesOutstanding": 1_000_000_000, "cashflowRows": [],
    }
    payload = build_company_analysis_charts(
        {"secFacts": sec, "company": {"ticker": "X"}, "marketFinancialData": market})
    return {chart["id"]: chart for chart in payload["charts"]}


def test_performance_years_do_not_borrow_the_deeper_cashflow_history():
    charts = _charts()
    assert charts["performance"]["years"] == ["2023", "2024", "2025"]
    assert charts["performance"]["revenue"] == [100.0, 120.0, 150.0]
    assert None not in charts["performance"]["revenue"]


def test_margins_years_match_performance_not_cashflow():
    charts = _charts()
    assert charts["margins"]["years"] == ["2023", "2024", "2025"]


def test_cashflow_years_keep_their_own_deeper_history():
    charts = _charts()
    assert charts["cashflow"]["years"] == ["2022", "2023", "2024", "2025"]
    assert charts["cashflow"]["operatingCashFlow"] == [10.0, 25.0, 30.0, 35.0]
    assert None not in charts["cashflow"]["operatingCashFlow"]


def test_fcf_margin_denominator_realigns_to_the_cashflow_year_window():
    """FCF는 cashflow_years(4개년) 폭인데, 매출을 performance_years(3개년) 폭
    그대로 zip하면 2022 자리에 2023 매출이 밀려 들어가 한 칸씩 어긋난다."""
    charts = _charts()
    free_cash_flow = charts["cashflow"]["freeCashFlow"]
    assert free_cash_flow == [5.0, 17.0, 21.0, 25.0]

    fcf_margin = charts["cashflow"]["fcfMargin"]
    # 2022년은 매출 자료가 없어 마진을 계산할 수 없다 — 0이나 다른 해의 값이 아니라 null.
    assert fcf_margin[0] is None
    assert fcf_margin[1:] == [17.0 / 100.0, 21.0 / 120.0, 25.0 / 150.0]
