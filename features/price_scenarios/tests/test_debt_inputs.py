from copy import deepcopy

from features.price_scenarios.debt_inputs import dart_debt_inputs, sec_debt_inputs
from features.price_scenarios.decimal_ops import fingerprint


def history(*ends, currency="USD", basis="us-gaap"):
    return {"currency": currency, "basis": basis, "rows": [{"period": {"start": end[:4] + "-01-01", "end": end}}
                                                         for end in ends]}


def sec_packet(**concepts):
    return {"facts": {"us-gaap": {name: {"units": {"USD": rows}} for name, rows in concepts.items()}}}


def fact(value, end="2025-12-31", *, filed="2026-02-01", form="10-K", acc="annual"):
    return {"val": value, "end": end, "filed": filed, "form": form, "accn": acc}


def test_same_period_complete_position_wins_without_double_counting_current_ltd():
    packet = sec_packet(LongTermDebt=[fact("100")], LongTermDebtCurrent=[fact("20")],
                        ShortTermBorrowings=[fact("0")], CashAndCashEquivalentsAtCarryingValue=[fact("30")])
    original = deepcopy(packet)
    result = sec_debt_inputs(packet, history("2025-12-31"), as_of="2026-10-01")
    assert result["position"]["totalDebt"] == "100" and result["position"]["netDebt"] == "70"
    assert result["position"]["complete"] is True and result["position"]["basis"] == "long_term_plus_short"
    assert len(result["position"]["sources"]) == 3
    assert packet == original and len(fingerprint(result)) == 64


def test_complete_older_year_beats_latest_partial_and_quarterly_balance_is_excluded():
    packet = sec_packet(LongTermDebt=[fact("100"), fact("200", "2024-12-31")],
                        ShortTermBorrowings=[fact("10", "2024-12-31")],
                        CashAndCashEquivalentsAtCarryingValue=[fact("30"), fact("40", "2024-12-31"),
                                                              fact("99", "2026-06-30", form="10-Q")])
    result = sec_debt_inputs(packet, history("2024-12-31", "2025-12-31"), as_of="2026-10-01")
    assert result["position"]["asOf"] == "2024-12-31" and result["position"]["netDebt"] == "170"
    assert all(row["periodEnd"] != "2026-06-30" for row in result["observations"])
    with_latest = history("2024-12-31", "2025-12-31")
    with_latest["rows"].append({"metric": "Long-Term Debt", "period": {"start": None, "end": "2025-12-31"}})
    selected = sec_debt_inputs(packet, with_latest, as_of="2026-10-01")["position"]
    assert selected["asOf"] == "2025-12-31" and selected["complete"] is False
    assert selected["netDebt"] == "70"


def test_debt_and_cash_are_not_mixed_between_periods_or_future_filings():
    packet = sec_packet(LongTermDebt=[fact("100")], CashAndCashEquivalentsAtCarryingValue=[fact("30", "2024-12-31")])
    assert sec_debt_inputs(packet, history("2024-12-31", "2025-12-31"), as_of="2026-10-01")["ok"] is False
    packet['facts']['us-gaap']['CashAndCashEquivalentsAtCarryingValue']['units']['USD'] = [
        fact("30"), fact("31", filed="2027-02-01", acc="future")]
    result = sec_debt_inputs(packet, history("2025-12-31"), as_of="2026-10-01")
    assert result["position"]["cash"] == "30" and result["position"]["complete"] is False
    assert sec_debt_inputs({"facts": {"ifrs-full": {}}}, history("2025-12-31"), as_of="2026-10-01")["ok"] is False


def dart(account, name, value, *, statement="BS", acc="20260323000001", **extra):
    return {"account_id": account, "account_nm": name, "thstrm_amount": value, "rcept_no": acc,
            "sj_div": statement, "currency": "KRW", **extra}


def test_measured_korean_debt_components_keep_march_end_and_zero_short_debt():
    rows = [dart("ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "30"),
            dart("ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "장기차입금", "100"),
            dart("ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "사채", "20"),
            dart("-표준계정코드 미사용-", "단기차입금", "0"),
            dart("ifrs-full_OtherCurrentFinancialLiabilities", "기타유동금융부채", "99"),
            dart("dart_ProceedsFromLongTermBorrowings", "장기차입금", "99", statement="CF")]
    batches = [{"basis": "CFS", "periodEnd": "2025-03-31", "rows": rows},
               {"basis": "OFS", "periodEnd": "2025-03-31", "rows": [dart("ifrs-full_CashAndCashEquivalents", "현금", "999")]}]
    result = dart_debt_inputs(batches, history("2025-03-31", currency="KRW", basis="CFS"), as_of="2026-10-01")
    assert result["position"]["asOf"] == "2025-03-31" and result["position"]["totalDebt"] == "120"
    assert result["position"]["cash"] == "30" and result["position"]["complete"] is True
    assert len(result["observations"]) == 4


def test_missing_debt_is_not_zero_and_latest_same_account_correction_wins():
    cash = dart("ifrs-full_CashAndCashEquivalents", "현금", "30")
    h = history("2025-12-31", currency="KRW", basis="CFS")
    assert dart_debt_inputs([{"basis": "CFS", "periodEnd": "2025-12-31", "rows": [cash]}], h,
                            as_of="2026-10-01")["ok"] is False
    loan = dart("ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "장기차입금", "100")
    fixed = {**loan, "thstrm_amount": "110", "rcept_no": "20260401000001"}
    result = dart_debt_inputs([{"basis": "CFS", "periodEnd": "2025-12-31", "rows": [cash, loan, fixed]}], h,
                              as_of="2026-10-01")
    assert result["position"]["totalDebt"] == "110" and result["position"]["complete"] is False
    conflict = dart_debt_inputs([{"basis": "CFS", "periodEnd": "2025-12-31", "rows": [cash, loan, {**loan, "thstrm_amount": "120"}]}], h,
                                as_of="2026-10-01")
    assert conflict["ok"] is False and conflict["ambiguousPeriodEnds"] == ["2025-12-31"]


def test_long_term_aggregate_does_not_add_its_component_loans_and_bonds():
    rows = [dart("ifrs-full_CashAndCashEquivalents", "현금", "30"),
            dart("ifrs-full_LongtermBorrowings", "사채및장기차입금", "100"),
            dart("ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "장기차입금", "60"),
            dart("ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "사채", "40"),
            dart("-표준계정코드 미사용-", "단기차입금", "10")]
    result = dart_debt_inputs([{"basis": "CFS", "periodEnd": "2025-12-31", "rows": rows}],
                              history("2025-12-31", currency="KRW", basis="CFS"), as_of="2026-10-01")
    assert result["position"]["totalDebt"] == "110" and len(result["position"]["sources"]) == 3


def test_ifrs_borrowing_current_portion_is_only_usable_after_official_definition_proof():
    packet = sec_packet(Borrowings=[fact("100", form="20-F")], ShorttermBorrowings=[fact("10", form="20-F")],
                        CurrentPortionOfLongtermBorrowings=[fact("20", form="20-F")],
                        CashAndCashEquivalents=[fact("30", form="20-F")])
    packet["facts"]["ifrs-full"] = packet["facts"].pop("us-gaap")
    source = history("2025-12-31", basis="ifrs-full")
    assert sec_debt_inputs(packet, source, as_of="2026-10-01")["ok"] is False
    definition = {"basis": "includes_current_maturities_excludes_shortterm", "source": "sec_annual_debt_note", "accession": "proof"}
    result = sec_debt_inputs(packet, source, as_of="2026-10-01", borrowings_definition=definition)
    assert result["position"]["totalDebt"] == "110" and result["position"]["netDebt"] == "80"
    assert result["position"]["borrowingsDefinition"] == definition


def test_conflicting_sec_values_are_not_selected_by_source_order():
    packet = sec_packet(LongTermDebt=[fact("100"), fact("110")],
                        CashAndCashEquivalentsAtCarryingValue=[fact("30")])
    result = sec_debt_inputs(packet, history("2025-12-31"), as_of="2026-10-01")
    assert result["ok"] is False and result["ambiguousPeriodEnds"] == ["2025-12-31"]
    packet["facts"]["us-gaap"]["LongTermDebt"]["units"]["USD"].append(fact("120", filed="2026-03-01", acc="corrected"))
    result = sec_debt_inputs(packet, history("2025-12-31"), as_of="2026-10-01")
    assert result["position"]["totalDebt"] == "120" and result["ambiguousPeriodEnds"] == []
