"""제안서가 지적한 넷을 못박는다 — 밸류에이션 이중장부·항등식·내부 용어·매입의 질."""
from __future__ import annotations

from features.company_analysis.buyback import build_buyback_quality, render_buyback_quality
from features.company_analysis.report_contract import INTERNAL_TERMS, validate_company_report
from features.company_analysis.service import _clean_classification
from features.company_analysis.valuation import build_valuation_scenarios, render_valuation_contract


def _summary(rows: dict) -> dict:
    return {"rows": [
        {"metric": metric, "annual": [
            {"val": value, "fy": 2025 - offset, "end": f"{2025 - offset}-12-31", "form": "10-K"}
            for offset, value in enumerate(values)
        ]}
        for metric, values in rows.items()
    ]}


class TestValuationSingleSource:
    def test_base_case_is_the_current_price_not_a_tautology(self):
        """기본 시나리오가 현재가여야 한다.

        forward EPS에 trailing PER을 곱하던 시절 기본가는 정의상 `현재가×(1+성장률)`이라
        어떤 회사든 "기본 시나리오는 상승"으로 나왔다.
        """
        v = build_valuation_scenarios(trailing_eps=3.71, price=269.34, growth=0.10)
        base = next(row for row in v["scenarios"] if row["label"] == "기본")
        assert abs(base["price"] - v["currentPrice"]) < 0.01
        assert base["changePct"] == 0.0

    def test_growth_moves_the_multiple_not_the_base_price(self):
        low = build_valuation_scenarios(trailing_eps=4.0, price=200.0, growth=0.02)
        high = build_valuation_scenarios(trailing_eps=4.0, price=200.0, growth=0.30)
        assert low["scenarios"][1]["price"] == high["scenarios"][1]["price"] == 200.0
        assert high["eps"]["value"] > low["eps"]["value"]
        assert high["forwardPe"] < low["forwardPe"]

    def test_contract_hands_the_numbers_over_and_forbids_recomputing(self):
        block = render_valuation_contract(
            build_valuation_scenarios(trailing_eps=3.71, price=269.34, growth=0.10)
        )
        assert "다시 계산하지 마세요" in block
        assert "가정" in block  # 배수의 출처를 숨기지 않는다
        assert "66.0배" in block

    def test_missing_inputs_yield_nothing_rather_than_a_guess(self):
        assert build_valuation_scenarios(trailing_eps=None, price=200.0, growth=0.1) == {}
        assert build_valuation_scenarios(trailing_eps=-1.0, price=200.0, growth=0.1) == {}
        assert render_valuation_contract({}) == ""


class TestBuybackQuality:
    def test_amount_alone_is_not_the_answer(self):
        quality = build_buyback_quality(
            _summary({
                "Share Repurchases": [700_000_000],
                "Stock-Based Compensation": [73_000_000],
                "Shares Diluted": [406_000_000, 410_000_000],
            }),
            price=188.0,
        )
        assert quality["offsetRatio"] == round(73 / 700, 3)
        assert quality["dilutedSharesChangePct"] < 0
        assert quality["buybackYieldPct"] > 0
        assert "희석주식수" in render_buyback_quality(quality)

    def test_offset_heavy_when_compensation_eats_the_buyback(self):
        quality = build_buyback_quality(
            _summary({
                "Share Repurchases": [1_000_000_000],
                "Stock-Based Compensation": [900_000_000],
                "Shares Diluted": [500_000_000, 495_000_000],
            }),
        )
        assert quality["offsetHeavy"] is True
        assert quality["dilutedSharesChangePct"] > 0
        assert "줄지 않았습니다" in render_buyback_quality(quality)

    def test_average_price_only_when_the_company_disclosed_share_count(self):
        """`TreasuryStockSharesAcquired`를 등재하지 않는 회사가 많다(실측 HWM)."""
        without = build_buyback_quality(_summary({"Share Repurchases": [700_000_000]}))
        assert "averagePrice" not in without
        block = render_buyback_quality(without)
        assert "계산하지 않았습니다" in block
        # 구조화 자료에 없다는 것을 회사 미공시로 바꿔 말하지 않는다 (계획 §12 B).
        assert "공시하지 않았다고 쓰지 말고" in block

        with_shares = build_buyback_quality(_summary({
            "Share Repurchases": [700_000_000],
            "Shares Repurchased": [4_000_000],
        }))
        assert with_shares["averagePrice"] == 175.0

    def test_no_buyback_means_no_block(self):
        assert build_buyback_quality(_summary({"Revenue": [1_000]})) == {}
        assert render_buyback_quality({}) == ""


class TestInternalTermLeak:
    def test_state_vocabulary_never_reaches_the_reader(self):
        body = (
            "## 기업 개요와 사업 구조\n분석 범위는 이렇습니다.\n\n"
            "## 자료 한계와 참고자료\n**Thesis가 바뀌는 trigger**: partial 상태입니다.\n"
        )
        codes = [row["code"] for row in validate_company_report(body)["defects"]]
        assert "internal_term_leak" in codes

    def test_plain_korean_passes(self):
        body = (
            "## 기업 개요와 사업 구조\n분석 범위는 이렇습니다.\n\n"
            "## 자료 한계와 참고자료\n판단이 바뀌는 조건: 일부만 확인했습니다.\n"
        )
        codes = [row["code"] for row in validate_company_report(body)["defects"]]
        assert "internal_term_leak" not in codes

    def test_the_terms_are_named_so_the_prompt_can_teach_them(self):
        assert "partial" in INTERNAL_TERMS
        assert "thesis" in INTERNAL_TERMS


class TestClassificationTaxonomy:
    def test_sic_raw_text_is_cleaned_not_printed_as_is(self):
        """SIC 서술은 연속 공백을 그대로 갖고 온다(실측 HWM)."""
        assert _clean_classification("Rolling Drawing & Extruding of  Nonferrous Metals") == (
            "Rolling Drawing & Extruding of Nonferrous Metals"
        )

    def test_placeholder_classifications_become_empty(self):
        assert _clean_classification("Unclassified") == ""
        assert _clean_classification(None) == ""
