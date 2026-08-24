"""날짜를 주고 여러 시장을 고르면 발행일이 갈린다. 그때 실행을 나눈다.

예전에는 발행일 하나로 합쳐서, 금요일(2026-08-07)을 고르고 미국장·한국장을 함께
만들면 미국장은 08-07 장을, 한국장은 08-10 장을 다뤘다. 한국장은 발행일을 곧 자기
세션일로 읽기 때문이다. 사용자는 고르지 않은 날의 브리핑을 아무 경고 없이 받았고,
제목만 보고 "한국장이 안 만들어졌다"고 읽었다.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def briefing_app(monkeypatch: pytest.MonkeyPatch):
    import app

    calls = []

    def fake_build(date, **kwargs):
        calls.append({"date": date, "markets": list(kwargs.get("markets") or [])})
        return {"id": f"report-{date}", "date": date, "marketScope": kwargs.get("market_scope")}

    monkeypatch.setattr(app, "read_automation_settings", lambda: {})
    monkeypatch.setattr(app, "request_generation_mode", lambda _body: "rules")
    monkeypatch.setattr(app, "build_briefing", fake_build)
    return app, calls


def test_one_market_runs_once_and_returns_the_report(briefing_app):
    app, calls = briefing_app

    result = app.api_create_briefing({"date": "2026-08-07", "markets": ["us"]})

    assert calls == [{"date": "2026-08-10", "markets": ["us"]}]
    assert result["id"] == "report-2026-08-10"
    assert "reports" not in result


def test_mixed_markets_run_once_per_publication_date(briefing_app):
    app, calls = briefing_app

    result = app.api_create_briefing({"date": "2026-08-07", "markets": ["us", "kr"]})

    assert calls == [
        {"date": "2026-08-07", "markets": ["kr"]},
        {"date": "2026-08-10", "markets": ["us"]},
    ]
    assert [row["id"] for row in result["reports"]] == ["report-2026-08-07", "report-2026-08-10"]


def test_markets_sharing_a_publication_date_stay_in_one_run(briefing_app):
    """미국·유럽은 같은 규칙이라 나눌 이유가 없다."""
    app, calls = briefing_app

    app.api_create_briefing({"date": "2026-08-07", "markets": ["us", "europe"]})

    assert calls == [{"date": "2026-08-10", "markets": ["us", "europe"]}]


def test_a_dateless_request_is_unchanged(briefing_app):
    """오늘 생성은 그룹이 하나다. marketScope=both로 도는 기존 동작을 건드리지 않는다."""
    app, calls = briefing_app

    result = app.api_create_briefing({"markets": ["us", "kr"]})

    assert len(calls) == 1
    assert calls[0]["markets"] == ["us", "kr"]
    assert "reports" not in result


def test_cli_mode_submits_one_job_per_publication_date(monkeypatch: pytest.MonkeyPatch):
    import app

    submitted = []

    def fake_submit(kind, params, adapter=""):
        submitted.append({"date": params["date"], "markets": list(params["markets"])})
        return {"id": f"job-{params['date']}", "status": "queued"}

    monkeypatch.setattr(app, "read_automation_settings", lambda: {})
    monkeypatch.setattr(app, "request_generation_mode", lambda _body: "llm_cli")
    monkeypatch.setattr(app, "submit_agent_task", fake_submit)

    result = app.api_create_briefing({"date": "2026-08-07", "markets": ["us", "kr"]})

    assert submitted == [
        {"date": "2026-08-07", "markets": ["kr"]},
        {"date": "2026-08-10", "markets": ["us"]},
    ]
    # 작업이 둘이라는 사실을 숨기지 않는다. 하나만 돌려주면 화면이 그것만 기다리다
    # 나머지가 끝나기 전에 다 됐다고 말한다.
    assert [job["id"] for job in result["jobs"]] == ["job-2026-08-07", "job-2026-08-10"]


def test_a_session_that_has_not_happened_is_refused(briefing_app):
    """성립하지 않는 요청은 거부한다.

    지난 사고의 직접 원인이 이것이었다 — 08-10 08:02에 08-10 한국장을 요청하자 코드가
    금요일 종가로 메우고 그 값을 영구 캐시했다. 아주 먼 미래 날짜로 시각과 무관하게
    같은 판정이 나오는지 본다.
    """
    from fastapi import HTTPException

    app, calls = briefing_app

    with pytest.raises(HTTPException) as caught:
        app.api_create_briefing({"date": "2099-01-04", "markets": ["kr"]})

    assert caught.value.status_code == 400
    assert caught.value.detail["error"] == "no_valid_briefing_target"
    assert [row["reason"] for row in caught.value.detail["markets"]] == ["session_not_available"]
    assert calls == [], "거부된 요청은 생성을 시작하지 않는다"


def test_a_weekend_session_is_refused(briefing_app):
    """2026-08-08은 토요일이다."""
    from fastapi import HTTPException

    app, calls = briefing_app

    with pytest.raises(HTTPException) as caught:
        app.api_create_briefing({"date": "2026-08-08", "markets": ["kr", "us"]})

    assert caught.value.status_code == 400
    assert {row["reason"] for row in caught.value.detail["markets"]} == {"not_a_session"}
    assert calls == []


def test_a_market_closed_that_day_is_skipped_while_the_others_proceed(briefing_app):
    """2026-07-03은 미국 독립기념일 대체휴장이라 뉴욕만 쉰다. 서울은 연다.

    한 시장이 휴장이라고 다른 시장 브리핑까지 막을 이유가 없다. 대신 빠졌다는 사실을
    응답에 남긴다 — 조용히 빠지면 사용자는 왜 없는지 알 수 없다.

    날짜를 충분히 과거로 잡는다. 최근 날짜를 쓰면 그 시장의 오늘 장이 끝났는지에 따라
    거부 사유가 `not_a_session`과 `session_not_available` 사이를 오간다(둘 다 옳은
    거부지만 테스트가 시각에 의존하게 된다).
    """
    app, calls = briefing_app

    result = app.api_create_briefing({"date": "2026-07-03", "markets": ["kr", "us"]})

    assert [row["markets"] for row in calls] == [["kr"]]
    assert [row["market"] for row in result["skippedMarkets"]] == ["us"]
    assert result["skippedMarkets"][0]["reason"] == "not_a_session"


def test_cli_mode_with_one_group_still_returns_a_bare_job(monkeypatch: pytest.MonkeyPatch):
    import app

    monkeypatch.setattr(app, "read_automation_settings", lambda: {})
    monkeypatch.setattr(app, "request_generation_mode", lambda _body: "llm_cli")
    monkeypatch.setattr(
        app, "submit_agent_task",
        lambda kind, params, adapter="": {"id": "job-one", "status": "queued"},
    )

    result = app.api_create_briefing({"date": "2026-08-07", "markets": ["kr"]})

    assert result["id"] == "job-one"
    assert "jobs" not in result


def test_a_weekly_request_runs_once_for_every_market(briefing_app):
    """주간에는 세션이 없다. 발행일이 하나이므로 시장마다 나눌 이유가 없다.

    일간에서 발행일이 갈리는 이유는 시장마다 마감 시각이 달라 세션일→발행일 변환이
    다르기 때문이다. 주간 창은 달력 7일이라 네 시장이 같은 발행일을 쓴다.
    """
    app, calls = briefing_app

    result = app.api_create_briefing({"date": "2026-08-16", "markets": ["us", "kr"], "kind": "weekly"})

    assert calls == [{"date": "2026-08-16", "markets": ["us", "kr"]}]
    assert "reports" not in result


def test_a_weekend_weekly_request_is_not_rejected_as_a_non_session(briefing_app):
    """2026-08-16은 일요일이다. 일간 판정을 태우면 `not_a_session`으로 막힌다."""
    app, calls = briefing_app

    app.api_create_briefing({"date": "2026-08-16", "markets": ["us"], "kind": "weekly"})

    assert calls == [{"date": "2026-08-16", "markets": ["us"]}]


def test_a_future_week_is_refused(briefing_app):
    from fastapi import HTTPException

    app, calls = briefing_app

    with pytest.raises(HTTPException) as excinfo:
        app.api_create_briefing({"date": "2099-01-04", "markets": ["us"], "kind": "weekly"})

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["markets"][0]["reason"] == "week_not_available"
    assert calls == []


def test_the_weekly_kind_reaches_the_builder(briefing_app, monkeypatch: pytest.MonkeyPatch):
    app, _calls = briefing_app
    seen = {}

    def capture(date, **kwargs):
        seen.update(kwargs)
        return {"id": "r", "date": date}

    monkeypatch.setattr(app, "build_briefing", capture)
    app.api_create_briefing({"date": "2026-08-16", "markets": ["us"], "kind": "weekly"})

    assert seen["kind"] == "weekly"


def test_an_unknown_kind_falls_back_to_daily(briefing_app):
    """모르는 값은 고장이지 선택이 아니다."""
    app, calls = briefing_app

    app.api_create_briefing({"date": "2026-08-07", "markets": ["us"], "kind": "monthly"})

    # 일간 경로를 탔다 — 발행일 변환이 걸린다(08-07 세션 → 08-10 발행).
    assert calls == [{"date": "2026-08-10", "markets": ["us"]}]
