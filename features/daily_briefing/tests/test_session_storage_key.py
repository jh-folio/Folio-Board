"""저장 키는 그 시장이 다루는 세션일이다.

예전에는 발행일로 저장했다. 그래서 같은 세션이 생성 시각에 따라 다른 이름으로 흩어졌다 —
07:45 예약이 만든 08-10 한국장 세션이 `2026-08-11.kr.json`에, 그날 저녁 백필이 만든 같은
세션이 `2026-08-10.kr.json`에 있었고, 아카이브에는 같은 제목의 카드가 두 장 보였다.
"""
from __future__ import annotations

import pytest

from features.daily_briefing.archive import BriefingArchiveIndex


def _item(session_date, report_date, scope):
    return {
        "sessionDate": session_date,
        "reportDate": report_date,
        "marketScope": scope,
    }


def test_the_same_session_under_two_keys_is_one_card():
    """이관 중에는 옛 발행일 파일과 새 세션 파일이 공존한다."""
    legacy = _item("2026-08-10", "2026-08-11", "kr")
    migrated = _item("2026-08-10", "2026-08-10", "kr")

    assert BriefingArchiveIndex._row_key(legacy) == BriefingArchiveIndex._row_key(migrated)


def test_two_different_sessions_stay_two_cards():
    assert BriefingArchiveIndex._row_key(_item("2026-08-10", "2026-08-10", "kr")) != (
        BriefingArchiveIndex._row_key(_item("2026-08-11", "2026-08-11", "kr"))
    )


def test_the_same_session_in_two_markets_stays_two_cards():
    """한 순간이 두 시장에서 같은 세션일을 가리킬 수 있다."""
    assert BriefingArchiveIndex._row_key(_item("2026-08-11", "2026-08-11", "kr")) != (
        BriefingArchiveIndex._row_key(_item("2026-08-11", "2026-08-12", "us"))
    )


def test_an_aggregate_card_still_groups_by_report_date():
    """종합 카드에는 세션일이 하나로 정해지지 않는다."""
    assert BriefingArchiveIndex._row_key(
        {"sessionDate": "", "reportDate": "2026-08-11", "marketScope": "both"}
    ) == ("2026-08-11", "both", "daily")


def test_a_row_without_a_session_falls_back_to_the_report_date():
    """세션일을 못 읽는 옛 보고서도 목록에서 사라지면 안 된다."""
    assert BriefingArchiveIndex._row_key(_item("", "2026-08-11", "kr")) == ("2026-08-11", "kr", "daily")


def test_a_weekly_card_does_not_collide_with_the_daily_card():
    """주간의 구간 끝은 그 시장의 세션일과 같은 날일 수 있다.

    종류가 키에 없으면 둘 중 하나가 조용히 사라진다 — 일요일 주간과 그날 일간이
    같은 카드로 뭉개진다.
    """
    daily = _item("2026-08-23", "2026-08-23", "kr")
    weekly = {**_item("2026-08-23", "2026-08-23", "kr"), "kind": "weekly"}

    assert BriefingArchiveIndex._row_key(daily) != BriefingArchiveIndex._row_key(weekly)


@pytest.mark.parametrize(
    ("anchor", "market", "expected"),
    [
        # 발행 앵커 06-10(수)의 미국 세션은 직전 거래일 06-09다.
        ("2026-06-10", "us", "2026-06-09"),
        # 한국은 앵커 당일 장이 이미 끝났다면 그 날짜 그대로다.
        ("2026-06-10", "kr", "2026-06-10"),
    ],
)
def test_the_session_key_is_what_the_market_actually_covers(anchor, market, expected):
    from features.common.market_calendar import briefing_market_windows
    from features.daily_briefing.builder import _scope_session_date

    windows = briefing_market_windows(anchor)

    assert _scope_session_date(market, windows) == expected


@pytest.mark.parametrize(
    ("time_of_day", "expected"),
    [
        # 08:00은 아직 개장 전이라 직전 완료 세션이다.
        ("08:00", "2026-08-12"),
        # 11:00은 장중이다. 진행 중인 세션이 곧 이 브리핑의 세션이다.
        ("11:00", "2026-08-13"),
        ("18:00", "2026-08-13"),
    ],
)
def test_a_japanese_intraday_briefing_does_not_take_the_previous_session_key(time_of_day, expected):
    """장중 생성분이 전날 파일로 커밋되면 그 세션의 마감 브리핑이 덮어써진다.

    `marketSessions.jp.sessionDate`는 장중일 때 직전 **완료** 세션을 담는다. 그 값을
    저장 키로 쓰던 동안 08-13 11:00 생성분이 `2026-08-12.jp.json`으로 갔고, 제목은
    이미 끝난 `2026.08.12`를 `장중`이라고 말했다.
    """
    from features.common.market_calendar import briefing_market_windows
    from features.daily_briefing.builder import _scope_session_date

    windows = briefing_market_windows("2026-08-13", as_of=f"2026-08-13T{time_of_day}:00+09:00")

    assert _scope_session_date("jp", windows) == expected
    # 일본은 한국과 같은 시간대라 나란히 흘러야 한다.
    assert _scope_session_date("jp", windows) == _scope_session_date("kr", windows)


def test_an_intraday_japanese_title_names_the_session_in_progress():
    from features.common.market_calendar import briefing_market_windows
    from features.daily_briefing.schema import briefing_market_title

    windows = briefing_market_windows("2026-08-13", as_of="2026-08-13T11:00:00+09:00")
    title = briefing_market_title(
        "2026-08-13", "jp", session_mode="jp_intraday", market_windows=windows,
    )

    assert "2026.08.13" in title and "장중" in title


def test_europe_is_untouched_by_the_intraday_rule():
    """유럽은 한국시간 자정 이후 마감이라 `phase` 키 자체가 없다."""
    from features.common.market_calendar import briefing_market_windows
    from features.daily_briefing.builder import _scope_session_date

    windows = briefing_market_windows("2026-08-13", as_of="2026-08-13T11:00:00+09:00")
    session = (windows.get("marketSessions") or {})["europe"]

    assert _scope_session_date("europe", windows) == session["sessionDate"]


def test_both_save_paths_use_the_session_key():
    """규칙 경로와 Agent 경로가 같은 키를 써야 한다.

    두 경로는 이미 세 번 갈렸다 — 세션 창 미전달, 한국 수치 캐시의 죽은 TTL, 자료 창.
    한쪽만 옮기면 같은 세션이 생성 엔진에 따라 다른 파일이 된다.
    """
    import inspect

    from features.agent_mode import service as agent_service
    from features.daily_briefing import builder

    for module in (builder, agent_service):
        source = inspect.getsource(module)
        # 주간은 발행일로 저장하므로 조건 분기가 붙었다. 두 경로가 **같은 식**을 쓰는지가
        # 이 테스트의 요지다.
        assert 'kind == "weekly" else (_scope_session_date(' in source, module.__name__
        assert "briefing_file_name(session_key, scope, kind)" in source, module.__name__
        assert "visual_sidecar_gzip_file_name(session_key, scope, kind)" in source, module.__name__
