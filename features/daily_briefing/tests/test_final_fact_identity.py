from features.daily_briefing.finalize import validate_briefing_candidate, finalize_briefing_candidate, _writer_facts
import pytest


@pytest.mark.parametrize("text", [
    "코스피는 전일보다 346.16포인트(4.61%) 오른 7,346.16에 마감했다.",
    "7일 코스피 종가는 7,346.16, 등락률은 +4.61%다.",
])
def test_calendar_and_point_delta_are_not_closing_price(text):
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": text,
              "koreaMarketData": {"indices": {"KOSPI": {"close": 7346.16, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = text.replace("7,346.16", "7,000.00")
    assert any(row["kind"] == "value_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_rules_generation_does_not_validate_unused_api_settings(monkeypatch):
    from features.daily_briefing import service
    def invalid_api():
        raise AssertionError("unused API configuration accessed")
    monkeypatch.setattr(service, "selected_llm_config", invalid_api)
    assert service.generate_llm_briefing("2026-09-07", "2026-09-07", [], [], llm_override=False) == (None, "disabled")


def test_index_name_digits_are_not_index_values():
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": "KOSPI200: 1,105.19 (+4.00%)", "koreaMarketData": {"indices": {"KOSPI200": {"close": 1105.19, "changePct": 4, "asOfDate": "2026-09-07"}}}}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "KOSPI200: 1,100.00 (+4.00%)"
    assert validate_briefing_candidate(report)["contradictions"]


def test_fx_quote_unit_resolves_to_currency_and_rejects_wrong_currency():
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": "USDKRW: 1,341.73원", "marketTape": {"items": [{"symbol": "USDKRW", "value": 1341.73, "priceUnit": "quote", "asOfDate": "2026-09-07"}]}}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "USDKRW: 1,341.73달러"
    assert any(row["kind"] == "unit_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_structured_session_return_is_not_overridden_by_article_return():
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": "KOSPI +4.61% 상승 마감했다.", "koreaMarketData": {"indices": {"KOSPI": {"changePct": 4.61, "asOfDate": "2026-09-07"}}}, "sources": [{"sourceId": "test", "date": "2026-09-07", "writerExcerpt": "KOSPI 3.00% 상승"}]}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "KOSPI +3.00% 상승 마감했다."
    assert validate_briefing_candidate(report)["contradictions"]


def test_writer_percentage_must_follow_its_own_nearby_subject():
    report = {"marketScope": "kr", "sources": [{"writerExcerpt": "수익률은 102.7%였다. KOSPI와 KOSDAQ을 비교한다.\nKOSPI 시장을 본다. 다른 자산은 3.0%다."}]}
    assert not [fact for fact in _writer_facts(report) if fact.change_pct is not None]


def test_etf_price_is_not_cash_index_price():
    report = {"marketScope": "us", "date": "2026-09-04", "markdown": "S&P 500은 1.64% 상승했다.", "marketSnapshot": {"tickers": {"SPY": {"label": "S&P 500 ETF", "oneDayPct": 1.60, "asOfDate": "2026-09-04"}}}}
    result = validate_briefing_candidate(report)
    assert not result["contradictions"]
    assert not result["verifiedClaims"]


def test_month_return_is_not_week_return_and_real_visual_week_is_checked():
    report = {"marketScope": "us", "kind": "weekly", "weekEnd": "2026-09-06", "markdown": "NVDA 5.00% 상승했다.", "marketSnapshot": {"tickers": {"NVDA": {"periodPct": 20, "fiveDayPct": 12, "asOfDate": "2026-09-04"}}}}
    assert not validate_briefing_candidate(report)["contradictions"]
    visual = {"snapshots": {"week": {"market": "US", "series": [{"ticker": "NVDA", "label": "NVIDIA", "weeklyReturn": 5, "weeklyEndDate": "2026-09-04", "weeklyReturnReason": None}]}}}
    result = finalize_briefing_candidate(report, visual_context=visual)
    assert result["finalValidation"]["verifiedClaimCount"] >= 1
    assert "_validationVisuals" not in result


def test_flow_sign_is_local_to_each_investor_clause():
    candidate = {"marketScope": "kr", "date": "2026-09-04", "sources": [{"sourceId": "test", "date": "2026-09-04", "writerExcerpt": "외국인은 5034억원 순매수, 기관은 1조6690억원 순매도했다."}]}
    facts = {fact.key.rsplit(":", 1)[-1]: fact.value for fact in _writer_facts(candidate) if ":flow:" in fact.key}
    assert facts["foreign"] == 5034 * 100000000
    assert facts["institution"] == -16690 * 100000000


def test_intraday_article_number_does_not_override_close_fact():
    candidate = {"marketScope": "kr", "date": "2026-09-04", "markdown": "KOSPI +1.64% 상승 마감했다.", "koreaMarketData": {"indices": {"KOSPI": {"changePct": 1.64, "asOfDate": "2026-09-04"}}}, "sources": [{"sourceId": "test", "date": "2026-09-04", "writerExcerpt": "장중 KOSPI는 2.95% 상승했다."}]}
    assert not validate_briefing_candidate(candidate)["contradictions"]


def test_known_cash_index_is_required_but_etf_is_not_substituted():
    candidate = {"marketScope": "us", "date": "2026-09-04", "markdown": "오늘 시장을 정리합니다.", "marketSnapshot": {"tickers": {"^GSPC": {"label": "S&P 500", "oneDayPct": 1.64, "asOfDate": "2026-09-04"}}}}
    result = finalize_briefing_candidate(candidate)
    assert "+1.64%" in result["markdown"]
    assert result["finalValidation"]["repairCount"] == 1


def test_unsigned_decline_is_not_a_mismatch_but_a_wrong_direction_still_is():
    report = {"marketScope": "kr", "date": "2026-09-03", "markdown": "코스닥은 790.21로 1.71% 하락 마감했다.",
              "koreaMarketData": {"indices": {"KOSDAQ": {"close": 790.21, "changePct": -1.71, "asOfDate": "2026-09-03"}}}}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "코스닥은 790.21로 1.71% 상승 마감했다."
    assert any(row["kind"] == "direction_mismatch" for row in validate_briefing_candidate(report)["contradictions"])
    report["markdown"] = "코스닥은 790.21로 2.50% 하락 마감했다."
    assert any(row["kind"] == "value_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_fx_change_amount_is_not_the_fx_level():
    item = {"symbol": "USDKRW", "label": "원·달러 환율", "value": 1341.73, "priceUnit": "quote", "asOf": "2026-09-07"}
    report = {"marketScope": "kr", "date": "2026-09-07", "marketTape": {"items": [item]},
              "markdown": "원·달러 환율은 전일 대비 22.0원 하락한 1,341.73원에 마감했다."}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = report["markdown"].replace("1,341.73원에", "1,300.00원에")
    assert any(row["kind"] == "value_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_direction_word_and_number_belong_to_their_own_subject():
    report = {"marketScope": "kr", "date": "2026-09-03", "markdown": "삼성전자는 0.20% 하락했지만, 코스피는 상승 마감했다.",
              "koreaMarketData": {"indices": {"KOSPI": {"changePct": 0.26, "asOfDate": "2026-09-03"}}}}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "코스피는 하락 마감했다."
    assert any(row["kind"] == "direction_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_conditional_clause_is_not_a_direction_claim():
    item = {"symbol": "USDKRW", "label": "원·달러 환율", "value": 1351.36, "changePct": -0.52,
            "priceUnit": "quote", "asOf": "2026-09-04"}
    report = {"marketScope": "kr", "date": "2026-09-04", "marketTape": {"items": [item]},
              "markdown": "원·달러 환율이 다시 상승하면 외국인 부담이 커진다."}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "원·달러 환율은 상승 마감했다."
    assert any(row["kind"] == "direction_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_label_and_value_split_by_a_colon_still_verifies():
    report = {"marketScope": "kr", "date": "2026-09-07",
              "markdown": "- KOSPI: 6,995.39 / +4.61% / 거래대금 확인 안 됨 (2026-09-07)",
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert result["verifiedClaims"] and not result["contradictions"] and not result["requiredOmissions"]


def test_opening_print_and_point_change_are_not_the_session_close():
    report = {"marketScope": "kr", "date": "2026-09-07",
              "markdown": "KOSPI는 6,910.78로 3.34% 상승 출발한 뒤, 308.18포인트 오른 6,995.39에 마감했다.",
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert result["verifiedClaims"] and not result["contradictions"]
    report["markdown"] = report["markdown"].replace("6,995.39에", "6,500.00에")
    assert any(row["kind"] == "value_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_round_threshold_is_not_a_price_claim():
    report = {"marketScope": "kr", "date": "2026-09-07",
              "markdown": "코스피가 7,000선에 접근하거나 넘어설 때 참여 업종이 늘어나는지 본다.",
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    assert not validate_briefing_candidate(report)["contradictions"]
    report["markdown"] = "KOSPI는 7,000.00로 4.61% 상승 마감했다."
    assert any(row["kind"] == "value_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


@pytest.mark.parametrize("text", [
    "코스피는 6,910.78에 출발해 6,995.39로 마감했다.",
    "코스피는 전 거래일보다 3.34% 높은 수준에서 거래를 시작한 뒤, 종가 기준 상승률을 4.61%까지 확대했다.",
])
def test_opening_transition_still_checks_the_closing_claim(text):
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": text,
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert not result["contradictions"] and not result["downgradedContradictions"]
    assert result["verifiedClaims"]
    report["markdown"] = text.replace("6,995.39", "6,500.00").replace("4.61%", "9.99%")
    assert any(row["kind"] == "value_mismatch" for row in validate_briefing_candidate(report)["contradictions"])


def test_threshold_and_opening_facts_need_no_global_mismatch_downgrade():
    text = "코스피는 6,910.78에 출발해 6,995.39로 마감했다.\n코스피가 7,000선에 접근하거나 넘어설 때 업종 확산을 본다."
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": text,
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert not result["contradictions"] and not result["downgradedContradictions"]
    assert any(row["kind"] == "value" for row in result["verifiedClaims"])


def test_a_correct_number_elsewhere_does_not_excuse_a_wrong_closing_claim():
    report = {"marketScope": "kr", "date": "2026-09-07",
              "markdown": "KOSPI는 6,995.39로 4.61% 상승 마감했다.\n\nKOSPI 종가는 6,500.00이다.",
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert result["status"] == "reject"
    assert result["contradictions"] and not result["downgradedContradictions"]
    repaired = finalize_briefing_candidate(report)
    assert "6,500.00" not in repaired["markdown"]
    assert repaired["finalValidation"]["contradictionCount"] == 0
    report["markdown"] = "KOSPI 종가는 6,500.00이다."
    assert validate_briefing_candidate(report)["contradictions"]


def test_a_wrong_direction_still_blocks_even_when_the_value_is_verified():
    """부호 없는 크기 비교를 통과시킨 뒤 방향만이 유일한 검사다.  강등하면 구멍이 뚫린다."""
    report = {"marketScope": "kr", "date": "2026-09-07",
              "markdown": "KOSPI는 6,995.39로 4.61% 상승 마감했다.\n\n코스피는 1.00% 하락했다.",
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert result["status"] == "reject"
    assert any(row["kind"] == "direction_mismatch" for row in result["contradictions"])


def test_a_missing_required_number_is_a_warning_not_a_rejection():
    """수치가 빠진 것은 틀린 수치를 쓴 것과 다르다 — 독자가 손해를 보지 않는다."""
    report = {"marketScope": "kr", "date": "2026-09-07", "markdown": "오늘 시장은 반도체가 이끌었다.",
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    result = validate_briefing_candidate(report)
    assert result["status"] == "warn"
    assert result["requiredOmissions"] and not result["contradictions"]
