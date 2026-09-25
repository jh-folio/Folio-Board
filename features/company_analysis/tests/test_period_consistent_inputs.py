"""재무 입력은 값과 함께 **기간·정의**가 맞아야 한다 (계획 §12 A, HWM 2026-09 실측).

HWM 저장본에서 세 값이 어긋났다: 배당은 2015년 태그($223M)가 2025년 주주환원처럼,
이자비용은 2023년 값이 2025년 부채와 나뉘어 차입비용으로, 순부채는 인수 차입 전인
2025년 말 잔액($2.31B, 실제 2026-06-30 $3.94B)으로 쓰였다. 고정 fixture로 재현한다 —
특정 HWM 숫자에 맞추지 않고 규칙을 검사한다.
"""
from __future__ import annotations

from features.company_analysis import dcf as D
from features.company_analysis import financial_engine as FE
from features.company_analysis import report_rules as R
from features.company_analysis import sec_companyfacts as S


def _instant(end: str, val: float, form: str = "10-Q", filed: str = "") -> dict:
    return {"end": end, "val": val, "form": form, "filed": filed or end}


def _concepts(**series) -> dict:
    return {name: {"units": {"USD": rows}} for name, rows in series.items()}


class TestDebtPosition:
    def test_total_debt_tag_at_the_latest_date_wins(self):
        concepts = _concepts(
            DebtLongtermAndShorttermCombinedAmount=[_instant("2026-06-30", 4_501), _instant("2025-12-31", 3_050, "10-K")],
            LongTermDebt=[_instant("2025-12-31", 3_050, "10-K")],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2026-06-30", 563), _instant("2025-12-31", 742, "10-K")],
            CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents=[_instant("2026-06-30", 564)],
        )
        row = S.debt_position(concepts)
        assert row["ok"] and row["asOf"] == "2026-06-30"
        assert row["totalDebt"] == 4_501 and row["cash"] == 563 and row["netDebt"] == 3_938
        # 제한성 현금을 뺀 값을 먼저 쓴다.
        assert row["cashConcept"] == "CashAndCashEquivalentsAtCarryingValue"
        assert row["cashIncludesRestricted"] is False

    def test_long_term_debt_already_includes_current_maturities(self):
        """`LongTermDebt`에 `LongTermDebtCurrent`를 더하면 유동분이 두 번 들어간다."""
        concepts = _concepts(
            LongTermDebt=[_instant("2025-12-31", 3_050, "10-K")],
            LongTermDebtCurrent=[_instant("2025-12-31", 191, "10-K")],
            ShortTermBorrowings=[_instant("2025-12-31", 0, "10-K")],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2025-12-31", 742, "10-K")],
        )
        row = S.debt_position(concepts)
        assert row["basis"] == "long_term_plus_short"
        assert row["totalDebt"] == 3_050  # 0으로 **보고된** 단기차입은 더해도 된다

    def test_unreported_short_term_borrowings_are_flagged_not_zero_filled(self):
        concepts = _concepts(
            LongTermDebt=[_instant("2025-12-31", 3_050, "10-K")],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2025-12-31", 742, "10-K")],
        )
        row = S.debt_position(concepts)
        assert row["ok"] and row["complete"] is False
        assert row["basis"] == "long_term_only"

    def test_debt_and_cash_must_share_one_date(self):
        """차입금은 6월 말, 현금은 12월 말뿐이면 12월 말 조합으로 내려간다."""
        concepts = _concepts(
            DebtLongtermAndShorttermCombinedAmount=[_instant("2026-06-30", 4_501)],
            LongTermDebt=[_instant("2025-12-31", 3_050, "10-K")],
            ShortTermBorrowings=[_instant("2025-12-31", 0, "10-K")],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2025-12-31", 742, "10-K")],
        )
        row = S.debt_position(concepts)
        assert row["asOf"] == "2025-12-31" and row["totalDebt"] == 3_050

    def test_duration_rows_and_other_forms_are_not_balances(self):
        concepts = _concepts(
            DebtLongtermAndShorttermCombinedAmount=[
                {"start": "2026-01-01", "end": "2026-06-30", "val": 9_999, "form": "10-Q"},
                {"end": "2026-06-30", "val": 8_888, "form": "8-K"},
            ],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2026-06-30", 563)],
        )
        assert S.debt_position(concepts)["ok"] is False

    def test_later_filing_of_the_same_date_wins(self):
        concepts = _concepts(
            DebtLongtermAndShorttermCombinedAmount=[
                _instant("2026-06-30", 4_400, filed="2026-08-01"),
                _instant("2026-06-30", 4_501, filed="2026-08-06"),
            ],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2026-06-30", 563)],
        )
        assert S.debt_position(concepts)["totalDebt"] == 4_501


def _annual(metric: str, pairs: list[tuple[int, float]]) -> dict:
    return {"metric": metric, "annual": [
        {"val": value, "end": f"{year}-12-31", "form": "10-K"} for year, value in pairs
    ]}


def _summary(*rows: dict, position: dict | None = None) -> dict:
    out = {"ok": True, "currency": "USD", "rows": list(rows)}
    if position is not None:
        out["debtPosition"] = position
    return out


BASE_ROWS = (
    _annual("Revenue", [(2025, 8_252), (2024, 7_430), (2023, 6_640)]),
    _annual("Net Income", [(2025, 1_508), (2024, 1_155), (2023, 765)]),
    _annual("Operating Cash Flow", [(2025, 1_884), (2024, 1_298), (2023, 901)]),
    _annual("Long-Term Debt", [(2025, 3_050), (2024, 3_315), (2023, 3_710)]),
    _annual("Cash & Equivalents", [(2025, 743), (2024, 565), (2023, 610)]),
)


class TestNetDebtSource:
    def test_newer_balance_date_replaces_the_year_end_rows(self):
        position = S.debt_position(_concepts(
            DebtLongtermAndShorttermCombinedAmount=[_instant("2026-06-30", 4_501)],
            CashAndCashEquivalentsAtCarryingValue=[_instant("2026-06-30", 563)],
        ))
        row = D.net_debt_from(_summary(*BASE_ROWS, position=position))
        assert row["netDebt"] == 3_938 and row["asOf"] == "2026-06-30"
        # 합계 태그만 있는 날은 장·단기 구분을 0으로 지어내지 않는다.
        assert row["longTermDebt"] is None and row["shortTermDebt"] is None

    def test_an_older_position_does_not_override_the_annual_rows(self):
        stale = {"ok": True, "asOf": "2024-12-31", "totalDebt": 1.0, "cash": 0.0, "netDebt": 1.0,
                 "components": {"LongTermDebt": 1.0}, "complete": True, "basis": "long_term_only"}
        row = D.net_debt_from(_summary(*BASE_ROWS, position=stale))
        assert row["basis"] == "annual_rows" and row["netDebt"] == 3_050 - 743

    def test_without_a_position_the_annual_path_is_kept(self):
        row = D.net_debt_from(_summary(*BASE_ROWS))
        assert row["basis"] == "annual_rows" and row["asOf"] == "2025-12-31"


class TestCurrentYearValues:
    def test_a_stale_tag_is_history_not_a_current_input(self):
        summary = _summary(*BASE_ROWS, _annual("Dividends Paid", [(2015, 223)]))
        assert FE.current_year_value(summary, "Dividends Paid") == (None, "2025", "2015")

    def test_a_current_value_passes_with_its_year(self):
        summary = _summary(*BASE_ROWS, _annual("Dividends Paid", [(2025, 181), (2024, 109)]))
        assert FE.current_year_value(summary, "Dividends Paid") == (181, "2025", "")

    def test_debt_cost_uses_same_year_interest_and_debt(self):
        stale = _summary(*BASE_ROWS, _annual("Interest Expense", [(2023, 218)]))
        assert FE.derived_financials(stale)["debtCost"] is None
        current = _summary(*BASE_ROWS, _annual("Interest Expense", [(2025, 176), (2024, 195)]))
        assert abs(FE.derived_financials(current)["debtCost"] - 176 / 3_050) < 1e-9

    def test_quality_table_names_the_stale_year_instead_of_the_amount(self):
        summary = _summary(*BASE_ROWS, _annual("Dividends Paid", [(2015, 223_000_000)]))
        text = R.build_financial_quality_analysis(summary, {})
        assert "2015년" in text and "223" not in text


class TestCandidateTags:
    def test_current_dividend_and_interest_tags_are_read(self):
        concepts = _concepts(
            PaymentsOfDividends=[{"start": "2015-01-01", "end": "2015-12-31", "val": 223, "form": "10-K"}],
            PaymentsOfOrdinaryDividends=[{"start": "2025-01-01", "end": "2025-12-31", "val": 181, "form": "10-K"}],
            InterestExpense=[{"start": "2023-01-01", "end": "2023-12-31", "val": 218, "form": "10-K"}],
            InterestExpenseNonoperating=[{"start": "2025-01-01", "end": "2025-12-31", "val": 150, "form": "10-K"}],
        )
        assert S._facts_for_metric(concepts, "Dividends Paid")[0] == "PaymentsOfOrdinaryDividends"
        assert S._facts_for_metric(concepts, "Interest Expense")[0] == "InterestExpenseNonoperating"

    def test_net_interest_is_a_different_definition_and_is_not_read(self):
        concepts = _concepts(
            InterestIncomeExpenseNonoperatingNet=[{"start": "2025-01-01", "end": "2025-12-31", "val": -151, "form": "10-K"}],
        )
        assert S._facts_for_metric(concepts, "Interest Expense") == ("", [])
