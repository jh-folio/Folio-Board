from copy import deepcopy

import pytest

from features.daily_briefing.finalize import BriefingFinalizationError, finalize_briefing_candidate
from features.daily_briefing.reader_hygiene import strip_provider_operational_notes
from features.daily_briefing.service import korea_market_data_to_markdown


WARNING = "Toss Open API가 설정돼 있으나 집계 시장 데이터는 여전히 yfinance 기준으로 제공된다는 provider 경고가 있었다."
RAW_WARNING = "Toss Open API configured; aggregate market payload remains on yfinance (native chart uses Toss market-indicator candles)"


@pytest.mark.parametrize("ok", [True, False])
def test_writer_context_does_not_expose_operational_warnings(ok):
    data = {"ok": ok, "provider": "yfinance", "date": "2026-09-07", "warnings": [RAW_WARNING],
            "fx": {"USDKRW": {"close": 1341.73, "asOfDate": "2026-09-07", "source": "yfinance"}}}
    original = deepcopy(data)
    text = korea_market_data_to_markdown(data)
    assert RAW_WARNING not in text and "provider 경고" not in text
    assert "1,341.73" in text and "2026-09-07" in text and "yfinance" in text
    assert data == original


def test_only_operational_note_is_removed_and_legitimate_attribution_stays():
    source = "- 원·달러 환율은 yfinance 기준 1,341.73원(2026-09-07)을 사용했다.\n"
    text = "## Source & Data Notes\n" + source + "- " + WARNING + "\n- 다음 자료 설명은 유지한다.\n"
    cleaned, count = strip_provider_operational_notes(text)
    assert count == 1 and WARNING not in cleaned
    assert source in cleaned and cleaned.endswith("- 다음 자료 설명은 유지한다.\n")
    assert strip_provider_operational_notes(cleaned) == (cleaned, 0)


def test_shared_finalizer_cleans_body_and_reader_section_without_changing_diagnostics():
    body = "## 시장 요약\n\n정상 분석 본문은 유지한다."
    report = {"date": "2026-09-07", "marketScope": "kr", "markdown": f"{WARNING}\n\n{body}",
              "briefings": {"kr": {"markdown": f"{WARNING}\n\n{body}"}},
              "koreaMarketData": {"warnings": [RAW_WARNING]},
              "generation": {"mode": "agent", "model": "claude"}}
    original = deepcopy(report)
    result = finalize_briefing_candidate(report)
    assert result["markdown"].strip() == body
    assert result["briefings"]["kr"]["markdown"].strip() == body
    assert result["koreaMarketData"] == report["koreaMarketData"]
    assert result["generation"] == report["generation"]
    assert report == original


def test_shared_finalizer_rejects_warning_only_as_empty():
    report = {"date": "2026-09-07", "marketScope": "kr", "markdown": WARNING,
              "briefings": {"kr": {"markdown": WARNING}},
              "koreaMarketData": {"warnings": [RAW_WARNING]}}

    with pytest.raises(BriefingFinalizationError) as raised:
        finalize_briefing_candidate(report)

    assert "format_empty" in raised.value.validation["reasonCodes"]


def test_provider_news_without_operational_state_is_not_removed():
    text = "토스증권은 신규 상품을 공개했다. 공급망 변화가 실적에 미치는 영향을 살핀다."
    assert strip_provider_operational_notes(text) == (text, 0)


def test_neighboring_sentences_remain_when_warning_shares_a_line():
    first, last = "정상 분석이다. ", " 다른 분석은 유지한다."
    cleaned, count = strip_provider_operational_notes(first + WARNING + last)
    assert count == 1
    assert cleaned.strip() == first.strip() + last


def test_removing_last_sentence_keeps_the_next_line_separate():
    text = "정상 분석이다. " + WARNING + "\n- 다음 항목이다.\n"
    assert strip_provider_operational_notes(text) == ("정상 분석이다.\n- 다음 항목이다.\n", 1)
