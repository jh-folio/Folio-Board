"""휴장일 표와 세션일 폴백의 회귀 테스트.

세 가지가 조용히 어긋나 있었다. 어느 쪽도 예외를 내지 않아 잘못된 세션일이 박힌
브리핑이 그대로 저장·발행된다.
"""
from __future__ import annotations

import datetime as dt

from features.common.market_calendar import (
    briefing_market_windows,
    kr_market_holidays,
    market_open_status,
    next_trading_day,
    previous_trading_day,
    publication_date_for_session,
    us_market_holidays,
)


# 이 파일의 KR/US 판정은 연결된 거래소 API(예: 증권사 오픈API)가 우선한다
# (`market_open_status`는 "API 우선, 정적 표는 폴백"이다). 로컬 `.env`에 그
# 자격증명이 있는 개발 환경에서는 이 회귀 테스트가 아래 정적 표가 아니라 그
# API가 그 순간 돌려주는 값을 검사하게 된다 — 그 API는 당해·익해 근미래에는
# 맞지만 몇 해 뒤 미래에는 아직 확정되지 않은 달력을 안다고 주장하며 틀린 답을
# 주기도 한다(실측: 2027-08-16을 개장으로 답했다. 법정 공휴일 대체휴일인데도).
# 이 파일이 검사하려는 대상은 그 API가 아니라 `kr_market_holidays()`/
# `us_market_holidays()` 정적 표이므로, 모든 시장 판정 호출에 "항상 API 없음"
# 폴백을 명시로 주입해 검사 대상을 고정한다(같은 관례가 이미
# `features/daily_briefing/tests/test_contracts.py`에 있다).
def _no_live_calendar(_day, _market):
    return None


# --- 한국 대체공휴일 -------------------------------------------------------
# KRX 연간 휴장일 안내(https://open.krx.co.kr) 기준.
# 설날·추석(관공서의 공휴일에 관한 규정 제3조 제1항 제2호)의 대체공휴일은
# **일요일**과 겹칠 때만 적용된다. 국경일·어린이날·부처님오신날·성탄절(같은 조
# 제1호)은 **토요일이나 일요일** 모두에 적용된다 — 기준이 다르다. 2026년 추석은
# 9/24(목)~9/26(토)로 일요일을 건드리지 않아 9/28은 대체휴일이 아니다(2026-09-13
# 시점 보도로 확인). 여기 넣었다가 실제로 열린 장을 휴장으로 판정해 세션일이
# 하루 밀린 채 브리핑이 나간 적이 있다 — 넣기 전에 일요일 겹침인지부터 본다.
KRX_SUBSTITUTE_HOLIDAYS = (
    ("2026-10-05", "개천절(10-03 토) 대체휴일"),
    ("2027-08-16", "광복절(08-15 일) 대체휴일"),
    ("2027-10-04", "개천절(10-03 일) 대체휴일"),
    ("2027-10-11", "한글날(10-09 토) 대체휴일"),
    ("2027-12-27", "성탄절(12-25 토) 대체휴일"),
)


def test_krx_substitute_holidays_are_closed():
    for text, reason in KRX_SUBSTITUTE_HOLIDAYS:
        day = dt.date.fromisoformat(text)
        assert day in kr_market_holidays(day.year), reason
        assert market_open_status(day, "KR", _no_live_calendar)["isOpen"] is False, reason


def test_a_substitute_holiday_is_not_described_as_a_closing_session():
    """열리지 않은 장을 '당일 정규장 마감 결과'로 서술하면 안 된다."""
    windows = briefing_market_windows(
        "2026-10-05", exchange_calendar_fetcher=_no_live_calendar, as_of="2026-10-05T18:00:00+09:00"
    )
    assert windows["krMarketOpenOnDate"] is False
    assert windows["krSessionPhase"] == "holiday"
    assert windows["krCurrentSessionDate"] == ""
    assert windows["analysisMode"] == "kr_holiday"
    # 직전 한국 거래일은 10-02(금)이다. 10-03 토, 10-04 일, 10-05 대체휴일.
    assert windows["krPreviousSessionDate"] == "2026-10-02"


def test_the_2026_local_election_is_a_krx_closure():
    """제9회 전국동시지방선거(2026-06-03 수).

    공직선거법 제34조의 임기만료 지방선거일이자 `관공서의 공휴일에 관한 규정`
    제2조 제10호의 법정 공휴일이라 KRX가 휴장한다(2025-06-03 대선과 같은 근거).
    표에 없으면 열리지 않은 장이 정규 거래일로 판정되어, 브리핑이 없는 마감을
    서술하고 세션일과 어긋난 yfinance 수치를 싣는다.
    """
    day = dt.date(2026, 6, 3)
    assert day.weekday() == 2  # 수요일 — 주말 때문에 닫히는 것이 아니다
    assert day in kr_market_holidays(2026)
    assert market_open_status(day, "KR", _no_live_calendar)["isOpen"] is False
    # 직전 한국 거래일은 6/2(화)다.
    assert previous_trading_day(dt.date(2026, 6, 4), "KR", _no_live_calendar) == dt.date(2026, 6, 2)


def test_the_same_closure_is_in_the_calendar_adapter_table():
    """두 표가 갈라지면 세션 판정과 캘린더 화면이 다른 말을 한다."""
    from features.market_calendar.adapters.exchange import KRX_HOLIDAYS

    assert "2026-06-03" in {text for text, _label in KRX_HOLIDAYS[2026]}


def test_regular_korean_trading_days_stay_open():
    """대체휴일을 넣다가 정상 거래일을 닫아버리지 않았는지 확인한다."""
    # 2026-09-28: 추석 연휴가 토요일까지만 걸치고 일요일과 겹치지 않아 대체휴일이
    # 아니다 — KRX_SUBSTITUTE_HOLIDAYS 위 주석 참고.
    for text in ("2026-10-06", "2026-09-28", "2026-09-29", "2027-08-17", "2027-12-28"):
        assert market_open_status(dt.date.fromisoformat(text), "KR", _no_live_calendar)["isOpen"] is True, text


# --- 미국 관측일(observed) 보정 -------------------------------------------
def test_christmas_observes_in_both_directions():
    """NYSE는 성탄절이 토요일이면 직전 금요일, 일요일이면 다음 월요일에 휴장한다."""
    assert dt.date(2027, 12, 24) in us_market_holidays(2027)  # 12-25 토
    assert market_open_status(dt.date(2027, 12, 24), "US", _no_live_calendar)["isOpen"] is False
    assert dt.date(2033, 12, 26) in us_market_holidays(2033)  # 12-25 일
    assert market_open_status(dt.date(2033, 12, 26), "US", _no_live_calendar)["isOpen"] is False


def test_new_year_only_observes_forward():
    """신정만은 토요일 보정이 없다 — NYSE는 전년 12/31에 휴장하지 않는다.

    2021-12-31은 실제로 정규 거래일이었다(2022-01-01이 토요일).
    """
    assert dt.date(2021, 12, 31) not in us_market_holidays(2021)
    assert market_open_status(dt.date(2021, 12, 31), "US", _no_live_calendar)["isOpen"] is True
    assert dt.date(2023, 1, 2) in us_market_holidays(2023)  # 01-01 일 → 월 휴장
    assert market_open_status(dt.date(2023, 1, 2), "US", _no_live_calendar)["isOpen"] is False


def test_juneteenth_only_closes_the_nyse_from_2022():
    """연방 공휴일 지정(2021-06-17)이 NYSE 휴장으로 이어진 것은 2022년부터다.

    2021-06-18(금)은 실제 정규 거래일이었다. 그 날을 휴장으로 내면 과거 백테스트의
    거래일과 세션일 판정이 하루씩 틀린다.
    출처: NYSE Holidays & Trading Hours https://www.nyse.com/markets/hours-calendars
    """
    assert dt.date(2021, 6, 18) not in us_market_holidays(2021)
    assert market_open_status(dt.date(2021, 6, 18), "US", _no_live_calendar)["isOpen"] is True
    # 2022-06-19는 일요일이라 06-20(월)이 첫 준수 휴장일이었다.
    assert dt.date(2022, 6, 20) in us_market_holidays(2022)
    assert market_open_status(dt.date(2022, 6, 20), "US", _no_live_calendar)["isOpen"] is False
    assert dt.date(2026, 6, 19) in us_market_holidays(2026)


def test_a_christmas_substitute_does_not_shift_the_us_session_date():
    """12-24가 휴장이면 12-27 브리핑의 미국 세션일은 12-23이다."""
    windows = briefing_market_windows("2027-12-27", exchange_calendar_fetcher=_no_live_calendar)
    assert windows["usRegularSessionDate"] == "2027-12-23"


# --- 표 없는 연도(coverage_expired)의 세션일 ------------------------------
def test_an_expired_table_never_names_a_weekend_session():
    """모른다를 어제로 바꾸지 않는다. 주말은 표 없이도 아는 사실이다."""
    sessions = briefing_market_windows("2027-03-08")["marketSessions"]
    for scope in ("europe", "jp"):
        session_date = dt.date.fromisoformat(sessions[scope]["sessionDate"])
        assert session_date.weekday() < 5, f"{scope}: {session_date} 는 주말이다"
        assert sessions[scope]["provider"] == "coverage_expired"


def test_expired_coverage_still_reports_the_expiry():
    """세션일을 채운다고 개장 판정이 되살아나면 안 된다."""
    sessions = briefing_market_windows("2027-03-08")["marketSessions"]
    for scope in ("europe", "jp"):
        assert sessions[scope]["openOnBriefingDate"] is False
        assert sessions[scope]["coverage"] == "coverage_expired"


def test_trading_day_fallbacks_skip_weekends():
    # 2027-03-08은 월요일. 표가 없으면 직전 평일인 03-05(금)로 물러난다.
    assert previous_trading_day(dt.date(2027, 3, 8), "EUROPE") == dt.date(2027, 3, 5)
    # 2027-03-12는 금요일. 다음 평일은 03-15(월)이다.
    assert next_trading_day(dt.date(2027, 3, 12), "EUROPE") == dt.date(2027, 3, 15)


def test_publication_date_for_an_expired_year_is_not_a_weekend():
    published = publication_date_for_session("2027-05-14", ["europe"])  # 금요일 세션
    assert dt.date.fromisoformat(published).weekday() < 5
