"""DCF가 모든 회사에 같은 답을 주지 않는지 못박는다."""
from __future__ import annotations

import pytest

from features.company_analysis import dcf as D


def _summary(rows: dict) -> dict:
    """연도 정렬된 companyfacts 요약. 최신 연도가 앞이다."""
    return {"rows": [
        {"metric": metric, "annual": [
            {"val": value, "fy": 2025 - offset, "end": f"{2025 - offset}-12-31", "form": "10-K"}
            for offset, value in enumerate(values)
        ]}
        for metric, values in rows.items()
    ]}


STEADY = _summary({
    "Revenue": [10_000, 9_000, 8_100, 7_290],
    "Operating Cash Flow": [2_400, 2_100, 1_900, 1_700],
    "Capital Expenditure": [400, 350, 320, 300],
    "Shares Diluted": [1_000, 1_000, 1_000, 1_000],
    "Long-Term Debt": [1_000, 1_000, 900, 900],
    "Short-Term Debt": [300, 250, 200, 200],
    "Cash & Equivalents": [800, 700, 600, 500],
    "Pretax Income": [2_000, 1_800, 1_600, 1_400],
    "Income Tax": [400, 360, 320, 280],
    "Interest Expense": [65, 60, 55, 50],
})


class TestNormalizedBase:
    def test_one_bad_year_does_not_set_the_whole_valuation(self):
        """예전에는 최근 1년이 기준이라 CapEx가 몰린 해가 회사 가치를 정했다."""
        spike = _summary({
            "Revenue": [10_000, 9_800, 9_600],
            "Operating Cash Flow": [2_400, 2_350, 2_300],
            "Capital Expenditure": [2_000, 400, 380],  # 최근 한 해만 급증
        })
        base = D.normalized_base_fcf(spike)
        assert base["method"] == "median_margin"
        assert base["recent"] == 400.0
        # 마진 중앙값이 받쳐 주므로 한 해 급증에 끌려가지 않는다.
        assert base["value"] > 1_500
        assert base["deviationFromRecent"] > 1.0

    def test_falls_back_and_says_which_way_it_fell(self):
        no_revenue = _summary({
            "Operating Cash Flow": [2_400, 2_100, 1_900],
            "Capital Expenditure": [400, 350, 320],
        })
        assert D.normalized_base_fcf(no_revenue)["method"] == "median_fcf"
        assert D.normalized_base_fcf(_summary({"Revenue": [1]})) == {}


class TestGrowthDriver:
    def test_revenue_leads_because_fcf_growth_contradicts_it(self):
        """실측 MSFT 매출 +10% vs FCF −3.0%, TSLA −1.0% vs +10%로 부호까지 어긋났다."""
        row = D.growth_driver(STEADY)
        assert row["basis"] == "revenue_cagr"
        assert row["rate"] == pytest.approx(0.1111, abs=0.001)

    def test_falls_back_to_fcf_when_revenue_is_missing(self):
        no_revenue = _summary({
            "Operating Cash Flow": [2_400, 2_000, 1_700],
            "Capital Expenditure": [400, 350, 300],
        })
        assert D.growth_driver(no_revenue)["basis"] == "fcf_cagr"

    def test_the_old_clamp_no_longer_pins_everyone_to_the_same_number(self):
        """`[-3%, +10%]`에 6개사 중 5개가 물려 성장률이 사실상 상수였다."""
        fast = _summary({"Revenue": [10_000, 5_000, 2_500]})
        assert D.growth_driver(fast)["rate"] > 0.10


class TestDiscountRate:
    def test_two_companies_do_not_get_the_same_rate(self):
        low = D.estimate_discount_rate(
            beta=0.8, tax_rate=0.20, debt_cost=0.03, market_cap=1_000_000, debt=100_000,
        )
        high = D.estimate_discount_rate(
            beta=1.8, tax_rate=0.20, debt_cost=0.07, market_cap=1_000_000, debt=500_000,
        )
        assert low["method"] == high["method"] == "wacc"
        assert high["rate"] > low["rate"] + 0.01

    def test_raw_beta_is_shrunk_toward_one(self):
        """조정 없이 CAPM에 넣으면 베타 2.12가 할인율 14.8%를 받아 어떤 성장률로도
        현재가가 설명되지 않는다 — 모델이 답을 못 내는 것이지 그만큼 위험한 게 아니다."""
        row = D.estimate_discount_rate(beta=2.12, tax_rate=0.2, debt_cost=0.04, market_cap=1e6, debt=0)
        assert row["beta"] == 2.12
        assert 1.0 < row["adjustedBeta"] < 2.12

    def test_missing_inputs_fall_back_and_say_so(self):
        row = D.estimate_discount_rate(beta=None, tax_rate=0.2, debt_cost=0.04, market_cap=1e6, debt=0)
        assert row["method"] == "fallback_fixed"
        assert row["rate"] == D.FALLBACK_DISCOUNT_RATE
        assert "beta" in row["missing"]

    def test_injected_risk_free_wins_and_is_labelled(self):
        assumed = D.estimate_discount_rate(beta=1.0, tax_rate=None, debt_cost=None, market_cap=1e6, debt=0)
        live = D.estimate_discount_rate(
            beta=1.0, tax_rate=None, debt_cost=None, market_cap=1e6, debt=0, risk_free=0.06,
        )
        assert assumed["riskFreeSource"] == "assumption_USD"
        assert live["riskFreeSource"] == "injected"
        assert live["rate"] > assumed["rate"]


class TestFadeAndTerminal:
    def test_growth_does_not_cliff_into_the_terminal_year(self):
        path = D.fade_path(0.30, 0.025, years=10)
        assert path[0] == 0.30 and path[-1] == pytest.approx(0.025)
        assert all(a >= b for a, b in zip(path, path[1:]))  # 단조 감소

    def test_terminal_growth_stays_below_the_discount_rate(self):
        assert D.terminal_growth_for("USD", 0.045) < 0.045
        assert D.terminal_growth_for("JPY", 0.09) == 0.010  # 통화별 상한이 이긴다

    def test_a_longer_horizon_moves_value_out_of_the_terminal(self):
        """5년이면 터미널 비중이 65~75%라 DCF가 사실상 터미널 베팅이다."""
        args = (1_000.0, 500.0, 100.0, 0.15, 0.09, 0.025)
        short = D.dcf_value(*args, 5)
        long = D.dcf_value(*args, 10)
        assert long["terminalShare"] < short["terminalShare"]

    def test_terminal_share_is_always_reported(self):
        row = D.dcf_value(1_000.0, 0.0, 100.0, 0.10, 0.09, 0.025)
        assert 0 < row["terminalShare"] < 1


class TestImpliedGrowth:
    def test_it_answers_what_the_price_assumes_instead_of_judging(self):
        """모델이 "62% 고평가"라고 판정하는 것보다 "시장은 연 23%를 가격에 넣고
        있다"가 정보다 — 그 숫자가 말이 되는지는 사업을 아는 사람이 판단한다."""
        row = D.dcf_value(1_000.0, 0.0, 100.0, 0.10, 0.09, 0.025)
        solved = D.implied_growth(row["perShare"], 1_000.0, 0.0, 100.0, 0.09, 0.025)
        assert solved["status"] == "solved"
        assert solved["growth"] == pytest.approx(0.10, abs=0.005)

    def test_out_of_range_says_so_rather_than_guessing(self):
        assert D.implied_growth(1e12, 1_000.0, 0.0, 100.0, 0.09, 0.025)["status"] == "above_range"
        assert D.implied_growth(0.01, 1_000.0, 0.0, 100.0, 0.09, 0.025)["status"] == "below_range"

    def test_no_price_means_no_answer(self):
        assert D.implied_growth(0.0, 1_000.0, 0.0, 100.0, 0.09, 0.025) == {}


class TestNetDebt:
    def test_short_term_borrowings_are_not_dropped(self):
        row = D.net_debt_from(STEADY)
        assert row["shortTermDebt"] == 300.0
        assert row["totalDebt"] == 1_300.0
        assert row["netDebt"] == 500.0  # 1000 + 300 - 800


class TestBuildDcf:
    def test_it_assembles_everything_and_separates_the_two_kinds_of_assumption(self):
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000, currency="USD")
        assert model["ok"]
        rates = {row["name"]: row["growth"] for row in model["scenarios"]}
        # 시나리오는 사업 가정(성장률)만 흔든다. 평가 가정은 전부 같아야 한다.
        assert rates["보수"] < rates["기준"] < rates["낙관"]
        assert len({row["discount"] for row in model["scenarios"]}) == 1
        assert len({row["terminal"] for row in model["scenarios"]}) == 1

    def test_the_optimistic_case_never_collapses_into_the_base(self):
        """추정 상한과 시나리오 상한을 같이 쓰던 시절 NVDA는 둘 다 30.0%였다."""
        fast = _summary({
            **{k: v for k, v in (("Revenue", [10_000, 4_000, 1_600]),)},
            "Operating Cash Flow": [3_000, 1_200, 500],
            "Capital Expenditure": [300, 120, 50],
            "Shares Diluted": [1_000, 1_000, 1_000],
        })
        model = D.build_dcf(fast, price=30.0, beta=1.5, market_cap=30_000)
        rates = {row["name"]: row["growth"] for row in model["scenarios"]}
        assert rates["낙관"] > rates["기준"]

    def test_missing_inputs_refuse_rather_than_invent(self):
        assert D.build_dcf(_summary({"Revenue": [100]}))["ok"] is False
        assert D.render_dcf_context({}) == ""

    def test_context_hands_over_the_assumptions_with_the_numbers(self):
        block = D.render_dcf_context(D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000))
        assert "터미널 비중" in block
        assert "역산 성장률" in block
        assert "고평가·저평가라고 단정하지 마세요" in block
        assert "다시 계산하지 마세요" in block
