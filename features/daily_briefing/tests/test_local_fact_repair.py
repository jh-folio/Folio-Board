from copy import deepcopy

import pytest

from features.daily_briefing.finalize import BriefingFinalizationError, finalize_briefing_candidate, validate_briefing_candidate
from features.common.quality_generation.call_budget import SharedRepairBudget


def _report(text):
    return {"date": "2026-09-07", "marketScope": "kr", "markdown": text,
            "generation": {"mode": "agent", "model": "codex"},
            "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}


@pytest.mark.parametrize("bad", [
    "KOSPI 종가는 6,500.00이다.",
    "KOSPI는 -4.61% 하락했다.",
    "오늘 KOSPI 종가는 6,995.39 (2026-09-06)이다.",
])
@pytest.mark.parametrize("model_repairs", [0, 1])
def test_only_faulty_sentence_changes_and_no_model_repair_is_spent(bad, model_repairs):
    first = "이 문장은 그대로 둡니다. "
    last = " 다른 근거 설명도 그대로 둡니다.\n\n## Source & Data Notes\n참고 자료 보존."
    report = _report(first + bad + last)
    original = deepcopy(report)
    budget = SharedRepairBudget(max_repairs=model_repairs)
    result = finalize_briefing_candidate(report, repair_budget=budget)
    assert result["markdown"].startswith(first) and result["markdown"].endswith(last)
    assert report == original
    assert result["generation"] == report["generation"]
    assert result["finalValidation"]["contradictionCount"] == 0
    assert result["finalValidation"]["localCorrectionPassCount"] == 1
    assert result["finalValidation"]["localCorrectedPassageCount"] == 1
    assert budget.used == 0
    assert not validate_briefing_candidate(result)["contradictions"]
    again = finalize_briefing_candidate(result, repair_budget=budget)
    assert again["markdown"] == result["markdown"]
    assert again["finalValidation"]["localCorrectedPassageCount"] == 1


def test_correct_occurrence_does_not_leave_wrong_occurrence_in_published_body():
    first = "KOSPI 종가는 6,995.39다.\n\n"
    result = finalize_briefing_candidate(_report(first + "KOSPI 종가는 6,500.00이다."))
    assert result["markdown"].startswith(first)
    assert "6,500" not in result["markdown"]
    assert result["finalValidation"]["localCorrectedPassageCount"] == 1


def test_already_spent_model_repair_slot_does_not_prevent_local_correction():
    budget = SharedRepairBudget(max_repairs=1)
    budget.claim("quality")
    result = finalize_briefing_candidate(_report("KOSPI 종가는 6,500.00이다."), repair_budget=budget)
    assert result["finalValidation"]["localCorrectedPassageCount"] == 1
    assert budget.used == 1


def test_exchange_unit_is_corrected_from_known_quote_currency():
    report = {"date": "2026-09-07", "marketScope": "kr", "markdown": "USDKRW는 1,341.73달러다.",
              "marketTape": {"items": [{"symbol": "USDKRW", "value": 1341.73, "priceUnit": "quote", "asOfDate": "2026-09-07"}]}}
    result = finalize_briefing_candidate(report)
    assert "1,341.73원" in result["markdown"] and "달러다" not in result["markdown"]
    assert result["finalValidation"]["contradictionCount"] == 0


def test_disagreeing_inputs_are_not_arbitrarily_selected_for_correction():
    report = _report("KOSPI 종가는 6,500.00이다.")
    report["marketTape"] = {"items": [{"symbol": "KOSPI", "value": 7001.00, "priceUnit": "points", "asOfDate": "2026-09-07"}]}
    with pytest.raises(BriefingFinalizationError):
        finalize_briefing_candidate(report)


def test_no_repair_and_cancellation_remain_explicit_boundaries():
    report = _report("KOSPI 종가는 6,500.00이다.")
    with pytest.raises(BriefingFinalizationError):
        finalize_briefing_candidate(report, allow_repair=False)
    with pytest.raises((BriefingFinalizationError, RuntimeError)):
        finalize_briefing_candidate(report, repair_budget=SharedRepairBudget(cancelled=lambda: True))


@pytest.mark.parametrize("bad, expected", [
    ("| KOSPI | **6,500.00** | +4.61% | 설명 유지 |", "| KOSPI | **6,995.39포인트** | +4.61% | 설명 유지 |"),
    ("| KOSPI | 6,995.39 | -4.61% | 설명 유지 |", "| KOSPI | 6,995.39 | +4.61% | 설명 유지 |"),
    ("| KOSPI | 하락 | 4.61% | 설명 유지 |", "| KOSPI | 상승 | 4.61% | 설명 유지 |"),
    ("| KOSPI | 하락 | -4.61% | 설명 유지 |", "| KOSPI | 상승 | +4.61% | 설명 유지 |"),
])
def test_table_correction_preserves_columns_and_other_cells(bad, expected):
    heading = "| 지표 | 값 | 등락률 | 메모 |\n| --- | --- | --- | --- |\n"
    result = finalize_briefing_candidate(_report(heading + bad))
    assert result["markdown"] == heading + expected
    assert result["finalValidation"]["contradictionCount"] == 0


def test_summary_prefix_survives_and_old_metadata_does_not_survive_changed_body():
    result = finalize_briefing_candidate(_report("**한 줄 결론:** KOSPI 종가는 6,500.00이다."))
    assert result["markdown"].startswith("**한 줄 결론:** ")
    result["markdown"] = "KOSPI 종가는 6,995.39다. 새 본문이다."
    changed = finalize_briefing_candidate(result)
    assert not changed["finalValidation"].get("localCorrectedPassageCount")


def test_cancel_during_local_pass_preserves_original_candidate():
    report = _report("KOSPI 종가는 6,500.00이다.")
    original = deepcopy(report)
    states = iter([False, True])
    with pytest.raises(BriefingFinalizationError) as raised:
        finalize_briefing_candidate(report, repair_budget=SharedRepairBudget(cancelled=lambda: next(states)))
    assert "cancelled" in raised.value.validation["reasonCodes"]
    assert report == original
