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

    def test_a_genuine_multiyear_trend_weights_toward_the_recent_margin(self):
        """중앙값은 상승 추세에서 항상 한두 해 뒤처진다 — 최근 연도 가중으로 따라잡는다."""
        trending = _summary({
            "Revenue": [10_000, 9_000, 8_000],
            "Operating Cash Flow": [2_300, 1_760, 1_300],
            "Capital Expenditure": [500, 500, 500],
        })
        base = D.normalized_base_fcf(trending)
        assert base["method"] == "trend_weighted_margin"
        assert base["marginTrend"] == "increasing"
        # 마진 중앙값(0.14)보다 최근 마진(0.18)에 더 가깝게 나와야 한다.
        assert base["usedMargin"] > 0.14
        # median_margin이면 -22.2%가 났을 자리다 — 실제에 더 가까워야 한다.
        assert base["deviationFromRecent"] > -0.20

    def test_a_declining_trend_also_gets_weighted_not_just_growth(self):
        """추세는 방향과 무관하다 — 악화 추세도 중앙값 대신 최근 연도로 당긴다."""
        declining = _summary({
            "Revenue": [10_000, 9_000, 8_000],
            "Operating Cash Flow": [1_300, 1_760, 2_300],  # 위 증가 케이스의 시간 역순
            "Capital Expenditure": [500, 500, 500],
        })
        base = D.normalized_base_fcf(declining)
        assert base["method"] == "trend_weighted_margin"
        assert base["marginTrend"] == "decreasing"

    def test_the_spike_case_still_falls_back_to_median(self):
        """한 구간이 마진 폭을 지배하는 스파이크는 추세로 보지 않는다(회귀 방지)."""
        spike = _summary({
            "Revenue": [10_000, 9_800, 9_600],
            "Operating Cash Flow": [2_400, 2_350, 2_300],
            "Capital Expenditure": [2_000, 400, 380],
        })
        base = D.normalized_base_fcf(spike)
        assert base["method"] == "median_margin"
        assert base["marginTrend"] == "flat"


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

    def test_the_terminal_and_implied_wording_tracks_the_real_horizon(self):
        """`fadePath`는 10년인데 문구가 "6년차 이후"라고 박혀 있었다 — 10년 명시
        예측 모델에서 터미널은 11년차부터다. 역산 성장률도 1년차 값일 뿐 여러 해
        유지되는 요구 성장률이 아니다."""
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000)
        years = len(model["fadePath"])
        block = D.render_dcf_context(model)
        assert "6년차" not in block
        assert f"명시 예측 기간({years}년) 이후" in block
        # 역산 성장률은 1년차 값이고 이후 감쇠한다고 밝힌다.
        assert "1년차 FCF 성장률 한 값만" in block
        assert "여러 해 유지되는" in block

    def test_a_shorter_horizon_moves_the_wording_with_it(self):
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000)
        model["fadePath"] = model["fadePath"][:5]
        block = D.render_dcf_context(model)
        assert "명시 예측 기간(5년) 이후" in block


class TestAssumptionSensitivity:
    """§9.4 — 두 입력을 더 정확하게 만드는 것보다 그 입력이 답을 얼마나 지배하는지
    보이는 쪽이 먼저다. 실측 ERP 4~6%가 MSFT 내재가치를 37% 흔들었다."""

    def test_wacc_path_exposes_the_erp_and_risk_free_band(self):
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000, currency="USD")
        rows = model["assumptionSensitivity"]
        assert rows, "WACC 경로에서 감도표가 비면 §9.4가 무효다"
        axes = {row["axis"] for row in rows}
        assert axes == {"base", "riskFree", "erp"}
        # ERP가 크면 할인율이 오르고 내재가치가 내린다 — 방향이 틀리면 표가 독자를 속인다.
        by_erp = {row["equityRiskPremium"]: row for row in rows if row["axis"] in {"base", "erp"}}
        erps = sorted(by_erp)
        assert by_erp[erps[0]]["perShare"] > by_erp[erps[-1]]["perShare"]
        assert by_erp[erps[0]]["discountRate"] < by_erp[erps[-1]]["discountRate"]

    def test_implied_growth_comes_as_a_band_when_price_is_known(self):
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000, currency="USD")
        implied = [row.get("impliedGrowth") for row in model["assumptionSensitivity"]]
        solved = [value for value in implied if value is not None]
        assert len(solved) >= 2
        assert max(solved) > min(solved)  # 가정에 따라 "시장이 넣은 성장률"이 달라진다

    def test_fixed_rate_fallback_has_no_sensitivity_table(self):
        """고정 할인율은 무위험·ERP를 읽지 않으므로 감도표가 거짓 정밀이 된다."""
        model = D.build_dcf(STEADY, price=20.0, beta=None, market_cap=None, currency="USD")
        assert model["assumptionSensitivity"] == []

    def test_context_and_rows_share_the_base_assumptions(self):
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000, currency="USD")
        base_rows = [row for row in model["assumptionSensitivity"] if row["axis"] == "base"]
        assert len(base_rows) == 1
        assert base_rows[0]["discountRate"] == model["discountRate"]["rate"]
        block = D.render_dcf_context(model)
        assert "가정 감도" in block

    def test_injected_erp_is_recorded_not_the_constant(self):
        row = D.estimate_discount_rate(
            beta=1.0, tax_rate=None, debt_cost=None, market_cap=1e6, debt=0,
            equity_risk_premium=0.06,
        )
        assert row["equityRiskPremium"] == 0.06

    def test_risk_free_meta_dict_injects_the_rate_and_lands_in_the_result(self):
        """호출부 두 곳이 각자 사후 주입하던 시절, 한쪽은 markdown만 반환하는 함수라
        기록이 어디에도 남지 않았다. build_dcf가 meta를 직접 받아 싣는다."""
        meta = {"rate": 0.055, "source": "fred_DGS10", "asOf": "2026-08-29T00:00:00+00:00"}
        model = D.build_dcf(STEADY, price=20.0, beta=1.2, market_cap=20_000, risk_free=meta)
        assert model["riskFreeMeta"] == meta
        assert model["discountRate"]["riskFree"] == 0.055
        assert model["discountRate"]["riskFreeSource"] == "injected"

    def test_collapsed_band_is_named_not_presented_as_a_range(self):
        """모든 행이 상·하한에 물리면 "범위로 읽으세요"가 거짓말이 된다."""
        rows = [
            {"axis": "base", "discountRate": 0.16, "clamped": True},
            {"axis": "erp", "discountRate": 0.16, "clamped": True},
        ]
        assert D.sensitivity_band_collapsed(rows) is True
        assert D.sensitivity_band_collapsed([{**rows[0], "clamped": False}]) is False

    def test_row_labels_come_from_one_owner(self):
        assert D.assumption_row_label({"axis": "base"}) == "기준"
        assert D.assumption_row_label({"axis": "riskFree", "riskFree": 0.042}) == "무위험 4.2%"
        assert D.assumption_row_label({"axis": "erp", "equityRiskPremium": 0.045}) == "ERP 4.5%"
