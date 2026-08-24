"""이야기 비중의 비교 기준은 하루가 아니라 직전 N거래일이다.

하루끼리 비교하면 그날 수집량이 흔들리는 것만으로 비중이 수십 %p 움직인다 — 유럽·일본은
하루 수집이 열몇 건이라 기사 두 건이 그 폭을 만든다. 직전 다섯 거래일을 합쳐 분모를 키우면
그 흔들림이 줄고, 남는 이동은 실제로 보도량이 옮겨간 것에 가깝다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.dashboard.story_share import (
    PREVIOUS_SESSION_WINDOW,
    build_story_share,
    previous_session_dates,
)


def _doc(date, title, market="US"):
    # 실제 수집물은 경로가 문서마다 다르다. 같은 경로를 쓰면 중복 제거가 서로 다른
    # 기사를 한 건으로 접어 이 테스트가 재는 것을 못 재게 된다.
    return {
        "date": date,
        "title": title,
        "content": title,
        "path": f"research-inbox/rss/{date}-{abs(hash(title)) % 10**8}.md",
        "source": "TestWire",
        "markets": [market],
    }


# ---------------------------------------------------------------- 창 계산


def test_the_window_is_five_trading_days_by_default():
    dates = previous_session_dates("2026-08-14", "US")

    assert len(dates) == PREVIOUS_SESSION_WINDOW == 5
    # 최신순이고, 오늘은 들어가지 않는다.
    assert dates == sorted(dates, reverse=True)
    assert "2026-08-14" not in dates


def test_the_window_skips_weekends():
    """달력 5일이 아니라 거래일 5일이다. 주말을 세면 수집 없는 날이 분모에 들어간다."""
    dates = previous_session_dates("2026-08-14", "US")

    for value in dates:
        import datetime as dt

        assert dt.date.fromisoformat(value).weekday() < 5, value


def test_a_holiday_week_stretches_the_calendar_span():
    """공휴일이 끼면 거래일 5개를 채우느라 달력으로는 5일보다 길어진다.

    2026-01-01(신정)이 낀 주. 거래일 판정이 그 날을 건너뛰므로 창의 시작이 더 뒤로 간다.
    """
    import datetime as dt

    dates = previous_session_dates("2026-01-08", "US")

    assert len(dates) == 5
    span = (dt.date.fromisoformat("2026-01-08") - dt.date.fromisoformat(dates[-1])).days
    assert span >= 5
    assert "2026-01-01" not in dates


def test_a_holiday_anchor_falls_back_to_the_latest_session():
    """오늘이 휴장일이면 '직전'은 최근 거래일의 그 이전 거래일이다."""
    saturday = previous_session_dates("2026-08-15", "US")
    friday = previous_session_dates("2026-08-14", "US")

    # 토요일 기준 창은 금요일부터가 아니라 금요일의 직전부터다(금요일이 최근 거래일).
    assert "2026-08-15" not in saturday
    assert saturday[0] <= friday[0] or saturday[0] == "2026-08-13"


def test_one_session_reproduces_the_old_behavior():
    """창 길이를 1로 주면 예전 계산과 같다. 되돌릴 수 있는 형태로 둔다."""
    assert previous_session_dates("2026-08-14", "US", 1) == ["2026-08-13"]


# ---------------------------------------------------------------- 합산 비중


def test_the_baseline_sums_the_window_instead_of_averaging_days():
    """날짜별 비중을 평균 내지 않는다.

    평균을 내면 수집이 적은 날이 많은 날과 같은 무게를 갖게 되어, 줄이려던 흔들림이
    그대로 돌아온다. 여기서는 기준 창의 한 날에만 금리 기사가 몰려 있고 나머지 날은
    반도체뿐이다 — 합산 분모에서 금리 비중은 낮게 나와야 한다.
    """
    dates = previous_session_dates("2026-08-14", "US")
    documents = [_doc("2026-08-14", "Fed rate cut expectations grow")]
    # 가장 오래된 기준일에만 금리 2건, 나머지 네 날은 반도체 4건씩.
    documents.append(_doc(dates[-1], "Treasury yields fall on rate bets"))
    documents.append(_doc(dates[-1], "Fed policy rate debate"))
    for day in dates[:-1]:
        documents.extend(_doc(day, f"Nvidia AI chip demand surges {n}") for n in range(4))

    payload = build_story_share(documents, "2026-08-14", "us")

    assert payload["previousSessionCount"] == 5
    assert payload["previousCollectedCount"] == 18
    rate_row = next((row for row in payload["items"] if row["label"] == "금리"), None)
    assert rate_row is not None
    # 합산 기준 2/18 ≈ 11%. 날짜 평균이었다면 (100% + 0*4)/5 = 20%가 됐을 것이다.
    assert rate_row["previousShare"] is not None
    assert rate_row["previousShare"] < 0.15


def test_the_payload_names_the_period_it_compared():
    documents = [_doc("2026-08-14", "Nvidia AI chip demand surges")]

    payload = build_story_share(documents, "2026-08-14", "us")

    assert payload["schemaVersion"] == 2
    assert len(payload["previousDates"]) == 5
    # 옛 화면 호환: 단일 날짜 필드는 창의 시작일로 남는다.
    assert payload["previousDate"] == payload["previousDates"][0]
    assert payload["previousDates"] == sorted(payload["previousDates"])


def test_the_small_baseline_warning_scales_with_the_window():
    """하루 12건 기준을 5일 합산에 그대로 쓰면 이 경고가 사실상 꺼진다."""
    documents = [_doc("2026-08-14", "Nvidia AI chip demand surges")]
    dates = previous_session_dates("2026-08-14", "US")
    # 하루 3건씩 5일 = 15건. 하루 기준(12)이면 충분해 보이지만 창 기준(60)에는 한참 못 미친다.
    for day in dates:
        documents.extend(_doc(day, f"Nvidia AI chip demand {n}") for n in range(3))

    payload = build_story_share(documents, "2026-08-14", "us")

    assert payload["previousCollectedCount"] == 15
    assert "small_previous_sample" in payload["warnings"]


def test_the_driver_basis_is_declared():
    """동인은 고정 어휘표다. 표에 없는 주제는 아무리 보도돼도 막대에 없다."""
    payload = build_story_share([_doc("2026-08-14", "Nvidia AI chip demand")], "2026-08-14", "us")

    assert payload["driverBasis"]["kind"] == "fixed_vocabulary"
    assert payload["driverBasis"]["count"] >= 9
