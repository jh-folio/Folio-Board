"""계획의 티커 위생 — 코드가 정한다.

플래너 프롬프트는 `candidateTickers`를 "yfinance 형식 심볼로" 요구하지만, 프롬프트는
부탁이지 제한이 아니다. 실측으로 모델이 **그룹 이름 → 티커 목록 문자열**을 돌려줬고
(`{"cloud_and_compute": "['AMZN', 'NVDA']"}`), 승인 계약이 그 키를 티커로 검증하다
`invalid_ticker`로 터져 60초짜리 계획 호출이 통째로 422가 됐다. 검색어 위생과 같은
자리·같은 이유다.
"""
from __future__ import annotations

import pytest

from features.topic_report.approved_schema import normalize_tickers  # 순환 import 진입점
from features.topic_report.topic_schema import _ticker_map


def _accepted(mapping: dict[str, str]) -> dict[str, str]:
    """승인 계약을 실제로 통과하는지 본다 — 여기서 통과해야 422가 사라진다."""
    return normalize_tickers(mapping)


def test_grouped_ticker_lists_are_harvested_not_rejected():
    plan = {
        "named_by_user": "['GOOGL', 'MSFT', 'ORCL', 'NET']",
        "cloud_and_compute": "['AMZN', 'NVDA']",
    }
    cleaned = _ticker_map(plan)
    assert list(cleaned) == ["GOOGL", "MSFT", "ORCL", "NET", "AMZN", "NVDA"]
    # 그룹 이름은 표시명으로 남는다 — 모델이 왜 묶었는지를 잃지 않는다.
    assert cleaned["AMZN"] == "cloud_and_compute"
    assert _accepted(cleaned)


def test_real_ticker_maps_pass_through_unchanged():
    plan = {"NVDA": "엔비디아", "005930.KS": "삼성전자", "BRK-B": "버크셔", "EURUSD=X": "환율"}
    assert _ticker_map(plan) == plan
    assert _accepted(plan)


def test_index_symbols_survive():
    """선행 `^`를 빼면 대표지수가 조용히 사라진다."""
    assert _ticker_map({"^GSPC": "S&P 500", "^KS11": "코스피"}) == {"^GSPC": "S&P 500", "^KS11": "코스피"}


def test_actual_lists_are_harvested_too():
    assert _ticker_map({"payments": ["V", "MA", "SHOP"]}) == {
        "V": "payments", "MA": "payments", "SHOP": "payments"
    }


def test_prose_labels_are_not_mined_for_fake_tickers():
    """리스트 모양일 때만 건진다. 산문에서 대문자 낱말을 티커로 오인하면 안 된다."""
    assert _ticker_map({"cloud_group": "AI and CPU demand"}) == {}


def test_junk_keys_are_dropped_without_killing_the_plan():
    assert _ticker_map({"^": "쓰레기", "이건 티커가 아니다": "라벨", "AAPL": "애플"}) == {"AAPL": "애플"}


def test_the_contract_cap_is_respected():
    plan = {"group": "[" + ", ".join(f"'T{i}'" for i in range(30)) + "]"}
    cleaned = _ticker_map(plan)
    assert len(cleaned) == 14
    assert _accepted(cleaned)


def test_labels_are_truncated_not_rejected():
    cleaned = _ticker_map({"NVDA": "가" * 400})
    assert len(cleaned["NVDA"]) == 160
    assert _accepted(cleaned)


@pytest.mark.parametrize("value", [None, "", [], "NVDA", 12])
def test_non_mapping_input_is_empty_not_an_error(value):
    assert _ticker_map(value) == {}
