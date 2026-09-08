"""주간 브리핑은 일간 옆에 나란히 산다.

가장 큰 위험은 **저장 키 충돌**이었다. 일요일에 주간을 만들면 `_scope_session_date()`가
그 시장의 직전 세션(대개 금요일)을 돌려주므로, 종류 접미사가 없으면 주간 보고서가
`{금요일}.{시장}.json`으로 떨어져 그 주 금요일 일간 브리핑을 통째로 덮어쓴다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from features.daily_briefing.archive import (
    REPORT_FILE_RE,
    SCOPED_REPORT_FILE_RE,
    BriefingArchiveIndex,
)
from features.daily_briefing.schema import (
    BRIEFING_KINDS,
    briefing_file_name,
    briefing_market_metadata,
    briefing_scope_view,
    enrich_briefing_sections,
    normalize_briefing_kind,
    visual_sidecar_gzip_file_name,
)
from features.daily_briefing.weekly import weekly_title, weekly_window


# ---------------------------------------------------------------- 창 계산


@pytest.mark.parametrize(
    ("published", "week_start", "preview_start"),
    [
        # 일요일 발행이면 지난주 창이 정확히 월~일이고 다음주는 바로 다음날부터다.
        ("2026-08-23", "2026-08-17", "2026-08-24"),
        # 금요일 발행도 "지난 7일"이라는 뜻은 그대로다. 다음주는 그 다음 월요일.
        ("2026-08-21", "2026-08-15", "2026-08-24"),
        # 월요일 발행은 **그 다음** 월요일이 다음주다. 오늘이 낀 주를 다음주라고
        # 부르면 이미 지나간 이틀이 프리뷰에 들어간다.
        ("2026-08-17", "2026-08-11", "2026-08-24"),
    ],
)
def test_the_window_is_the_last_seven_days_and_the_week_ahead(published, week_start, preview_start):
    window = weekly_window(published)

    assert window.week_start == week_start
    assert window.week_end == published
    assert window.preview_start == preview_start
    assert window.preview_end == (
        dt.date.fromisoformat(preview_start) + dt.timedelta(days=6)
    ).isoformat()


def test_the_source_window_is_seven_calendar_days():
    """세션 창이 아니라 달력 7일이다. 시장마다 창을 다르게 잡을 이유가 없다."""
    dates = weekly_window("2026-08-23").source_dates

    assert dates == [
        "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20",
        "2026-08-21", "2026-08-22", "2026-08-23",
    ]


def test_the_title_carries_the_span_not_a_session_state():
    """`마감`/`장중`은 하루짜리 라벨이라 한 주를 덮는 글에 성립하지 않는다."""
    title = weekly_title("us", weekly_window("2026-08-23"))

    assert title == "US Market Briefing 주간 — 08.17~08.23"
    assert "마감" not in title and "장중" not in title


# ---------------------------------------------------------------- 저장 키


def test_the_weekly_file_never_overwrites_the_daily_one():
    """**이번 릴리즈에서 가장 위험했던 충돌.**

    일요일 실행의 세션일은 금요일이다. 접미사가 없으면 그 주 금요일 일간 브리핑이
    주간 보고서로 덮여 사라진다.
    """
    friday_daily = briefing_file_name("2026-08-21", "us")
    sunday_weekly = briefing_file_name("2026-08-23", "us", "weekly")

    assert friday_daily == "2026-08-21.us.json"
    assert sunday_weekly == "2026-08-23.us.weekly.json"
    # 같은 날짜여도 종류가 다르면 파일이 다르다.
    assert briefing_file_name("2026-08-21", "us", "weekly") != friday_daily


def test_the_daily_file_name_is_unchanged():
    """기존 일간 저장 키가 바뀌면 이미 저장된 보고서가 화면에서 사라진다."""
    assert briefing_file_name("2026-08-21", "kr") == "2026-08-21.kr.json"
    assert visual_sidecar_gzip_file_name("2026-08-21", "kr") == "2026-08-21.kr.visuals.json.gz"


def test_the_archive_scanner_sees_weekly_files():
    """정규식에 없는 종류는 저장은 되는데 화면에는 없는 상태가 된다."""
    assert REPORT_FILE_RE.fullmatch("2026-08-23.us.weekly.json")
    assert SCOPED_REPORT_FILE_RE.fullmatch("2026-08-23.us.weekly.json")
    # 사이드카는 계속 보고서로 읽히지 않는다.
    assert not REPORT_FILE_RE.fullmatch("2026-08-23.us.weekly.visuals.json")


def test_the_canonical_identity_knows_every_kind():
    """`canonical_identity`가 모르는 종류는 커밋이 정체성 검증에서만 조용히 막힌다."""
    from features.common.canonical_identity import BRIEFING_KIND_SUFFIXES

    assert set(BRIEFING_KIND_SUFFIXES) == BRIEFING_KINDS - {"daily"}


def test_the_canonical_path_check_pairs_the_suffix_with_the_kind():
    """파일 이름이 주간이라고 말하는데 본문이 일간이면 보고서가 자기 종류를 잘못 말한다."""
    from pathlib import Path

    from features.common.canonical_identity import (
        CanonicalIdentityError,
        ReportKind,
        validate_report_identity,
    )

    weekly_path = Path("data/briefings/2026-08-23.us.weekly.json")
    validate_report_identity(
        ReportKind.BRIEFING, weekly_path,
        {"date": "2026-08-23", "marketScope": "us", "kind": "weekly"},
    )
    with pytest.raises(CanonicalIdentityError):
        validate_report_identity(
            ReportKind.BRIEFING, weekly_path,
            {"date": "2026-08-23", "marketScope": "us", "kind": "daily"},
        )
    # 접미사 없는 일간 경로는 `kind`를 적지 않은 옛 보고서도 그대로 통과한다.
    validate_report_identity(
        ReportKind.BRIEFING, Path("data/briefings/2026-08-21.us.json"),
        {"date": "2026-08-21", "marketScope": "us"},
    )


# ---------------------------------------------------------------- 메타·카드


def _weekly_report(markdown="# US Market Briefing 주간 — 08.17~08.23\n\n본문"):
    return {
        "date": "2026-08-23",
        "kind": "weekly",
        "marketScope": "us",
        "weekStart": "2026-08-17",
        "weekEnd": "2026-08-23",
        "previewStart": "2026-08-24",
        "previewEnd": "2026-08-30",
        "markdown": markdown,
        "generatedAt": "2026-08-23T09:00:00+09:00",
    }


def test_weekly_metadata_does_not_resolve_a_session():
    """세션 판정을 태우면 일요일 주간 보고서가 금요일 마감이라고 말하게 된다."""
    metadata = briefing_market_metadata(_weekly_report(), "us", _weekly_report())

    assert metadata["kind"] == "weekly"
    assert metadata["title"] == "US Market Briefing 주간 — 08.17~08.23"
    assert metadata["sessionMode"] == ""
    # 날짜 필터가 걸리도록 구간 끝을 세션일 자리에 둔다.
    assert metadata["sessionDate"] == "2026-08-23"
    assert metadata["publicationDate"] == "2026-08-23"
    assert "주간" in metadata["tags"]


def test_the_weekly_view_does_not_rewrite_the_title_into_a_session_title():
    """제목 정규화는 H1을 `{라벨} — {세션일} {마감}`으로 다시 쓰는 일이다."""
    view = briefing_scope_view(_weekly_report(), "us")

    assert view["markdown"].splitlines()[0] == "# US Market Briefing 주간 — 08.17~08.23"
    assert view["title"] == "US Market Briefing 주간 — 08.17~08.23"
    assert view["weekStart"] == "2026-08-17"


def test_sections_carry_the_window_so_the_card_can_read_it():
    sections = enrich_briefing_sections(
        {"us": {"markdown": "# US Market Briefing 주간 — 08.17~08.23"}},
        report_date="2026-08-23",
        report_scope="us",
        briefing_type="default",
        generated_at="2026-08-23T09:00:00+09:00",
        kind="weekly",
        weekly_window={
            "weekStart": "2026-08-17", "weekEnd": "2026-08-23",
            "previewStart": "2026-08-24", "previewEnd": "2026-08-30",
        },
    )

    assert sections["us"]["kind"] == "weekly"
    assert sections["us"]["weekStart"] == "2026-08-17"
    assert sections["us"]["title"] == "US Market Briefing 주간 — 08.17~08.23"
    # 세션 모드는 주간 섹션에 붙지 않는다.
    assert "sessionMode" not in sections["us"]


def test_a_saved_report_without_a_kind_reads_as_daily():
    """판올림 호환. 이미 저장된 보고서에는 이 필드가 없다."""
    assert normalize_briefing_kind(None) == "daily"
    assert normalize_briefing_kind("") == "daily"
    assert normalize_briefing_kind("bogus") == "daily"
    assert briefing_market_metadata({"date": "2026-08-21", "marketScope": "us"}, "us")["kind"] == "daily"


def test_the_archive_filters_by_kind():
    index = BriefingArchiveIndex("data/briefings")
    daily = {"item": {
        "marketScope": "us", "reportScope": "us", "briefingType": "default", "kind": "daily",
        "reportDate": "2026-08-21", "sessionDate": "2026-08-20",
    }, "searchText": ""}
    weekly = {"item": {
        "marketScope": "us", "reportScope": "us", "briefingType": "default", "kind": "weekly",
        "reportDate": "2026-08-23", "sessionDate": "2026-08-23",
    }, "searchText": ""}
    from pathlib import Path

    index._entries = {
        Path("2026-08-21.us.json"): {"signature": (1, 1), "rows": [daily], "warning": ""},
        Path("2026-08-23.us.weekly.json"): {"signature": (1, 1), "rows": [weekly], "warning": ""},
    }
    index._last_scan = float("inf")

    every = index.query(kind="all")
    only_weekly = index.query(kind="weekly")
    only_daily = index.query(kind="daily")

    assert every["total"] == 2
    assert [row["kind"] for row in only_weekly["items"]] == ["weekly"]
    assert [row["kind"] for row in only_daily["items"]] == ["daily"]
    with pytest.raises(ValueError):
        index.query(kind="monthly")


# ---------------------------------------------------------------- target


def test_a_weekend_publication_is_not_rejected_as_a_non_session():
    """일간 판정을 태우면 주말 발행이 `not_a_session`으로 막혀 주간을 만들 길이 없다."""
    from features.daily_briefing.target import resolve_weekly_targets

    now = dt.datetime(2026, 8, 23, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
    targets, errors = resolve_weekly_targets(["us", "kr"], publication_date="2026-08-23", now=now)

    assert errors == []
    assert [target.market for target in targets] == ["us", "kr"]
    assert targets[0].artifact_id == "2026-08-23.us.weekly"
    assert targets[0].week_start == "2026-08-17"


def test_a_future_week_cannot_be_summarized():
    from features.daily_briefing.target import resolve_weekly_targets

    now = dt.datetime(2026, 8, 23, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
    targets, errors = resolve_weekly_targets(["us"], publication_date="2026-08-30", now=now)

    assert targets == []
    assert [error.reason for error in errors] == ["week_not_available"]


# ---------------------------------------------------------------- 계약


def test_the_weekly_output_contract_does_not_demand_session_titles():
    from features.agent_mode.briefing_contract import briefing_output_contract

    contract = briefing_output_contract(
        "us", "default", markets=["us"], kind="weekly",
        expected_titles={"us": "US Market Briefing 주간 — 08.17~08.23"},
    )

    assert contract["kind"] == "weekly"
    assert contract["titleDatePattern"] == "주간 — MM.DD~MM.DD"
    # 주간에는 `주도한 기업 ①/②`가 없다. 켜 두면 무엇을 써도 통과할 수 없다.
    assert contract["requireLeadingCompanyNames"] is False
    assert "0. 지난주 미국장 한 줄 요약" in contract["requiredSections"]
    assert "0. 오늘의 미국장 성격" not in contract["requiredSections"]


def test_the_daily_output_contract_is_unchanged():
    from features.agent_mode.briefing_contract import briefing_output_contract

    contract = briefing_output_contract("both", "default")

    assert contract["kind"] == "daily"
    assert contract["titleDatePattern"] == "YYYY.MM.DD 마감|장중"
    assert contract["requireLeadingCompanyNames"] is True
    assert "0. 오늘의 미국장 성격" in contract["requiredSections"]


def test_the_weekly_contract_checks_the_span_title_and_section_zero():
    from features.agent_mode.briefing_contract import (
        briefing_contract_violations,
        briefing_output_contract,
    )

    contract = briefing_output_contract("us", "default", markets=["us"], kind="weekly")
    daily_title = "# US Market Briefing — 2026.08.21 마감\n\n## 0. 오늘의 미국장 성격\n"

    violations = briefing_contract_violations(daily_title, contract)

    assert any("주간" in violation for violation in violations)


def test_every_weekly_prompt_satisfies_its_own_contract():
    """주간 프롬프트에 일간 검사를 태우면 성립하지 않는 규칙을 요구하게 된다."""
    from features.daily_briefing.contracts import prompt_contract_errors
    from features.daily_briefing.service import BRIEFING_PROMPT_WEEKLY_PATHS

    for market, path in BRIEFING_PROMPT_WEEKLY_PATHS.items():
        text = path.read_text(encoding="utf-8")
        assert prompt_contract_errors(text) == [], market


def test_weekly_prompts_are_a_separate_file_set():
    from features.daily_briefing.service import briefing_prompt_paths

    daily = briefing_prompt_paths(["us"], "daily")
    weekly = briefing_prompt_paths(["us"], "weekly")

    assert daily != weekly
    assert weekly[0].name == "prompt_weekly_us.md"


# ---------------------------------------------------------------- 경계


def test_the_weekly_briefing_does_not_write_back_to_market_memory():
    """일간이 이미 그 주에 같은 이슈를 넣었다. 다시 넣으면 근거 카운트가 부푼다."""
    import inspect

    from features.agent_mode import service as agent_service
    from features.daily_briefing import builder

    assert 'if kind != "weekly" and market_scope in AGGREGATE_SCOPES and len(saved_reports) == len(requested_scopes):' in inspect.getsource(
        builder.build_briefing
    )
    assert 'if persist and kind != "weekly" and market_scope == "both" and len(saved_reports) == len(requested_scopes):' in inspect.getsource(
        agent_service.write_briefing_from_markdown
    )


def test_the_scheduler_can_run_a_daily_and_a_weekly_schedule_on_the_same_day():
    """일요일 아침이 정확히 그 경우다. 종류가 억제 키에 없으면 뒤가 조용히 스킵된다."""
    import inspect

    from features.automation import service

    source = inspect.getsource(service.run_due_automations)

    assert 'key = (str(schedule.get("kind") or "daily"), *markets)' in source


def test_a_saved_schedule_without_a_kind_stays_daily():
    from features.automation.schema import normalize_schedule

    assert normalize_schedule({"id": "a", "enabled": True})["kind"] == "daily"
    assert normalize_schedule({"id": "a", "kind": "weekly"})["kind"] == "weekly"
    # 모르는 값은 고장이므로 기본값으로 되돌린다.
    assert normalize_schedule({"id": "a", "kind": "monthly"})["kind"] == "daily"


# ---------------------------------------------------------------- 정체성


def test_the_change_event_id_does_not_collide_with_the_daily_report():
    """`change_event_index`의 PK는 `(artifact_kind, artifact_id)`다.

    주간의 `date`는 발행일이라 그날이 세션일인 일간과 값이 같다. 종류가 없으면 평일에
    낸 주간이 그날 일간의 변화 이벤트를 덮어써서, Change Feed가 일간 자리에 주간
    내용을 보여주고 잘못된 보고서를 연다.
    """
    from features.common.change_intelligence.adapters.briefing import _briefing_artifact_id

    daily = {"date": "2026-08-20", "marketScope": "us"}
    weekly = {"date": "2026-08-20", "marketScope": "us", "kind": "weekly"}

    assert _briefing_artifact_id(daily, "us") == "2026-08-20.us"
    assert _briefing_artifact_id(weekly, "us") == "2026-08-20.us.weekly"
    # 이미 접미사가 붙은 id를 두 번 붙이지 않는다.
    assert _briefing_artifact_id({**weekly, "id": "2026-08-20.us.weekly"}, "us") == "2026-08-20.us.weekly"


def test_the_baseline_lineage_keeps_weekly_and_daily_apart():
    """계보가 같으면 주간이 직전 일간을 기준선으로 잡고, 그다음 일간이 그 주간을 잡는다.

    한 주의 동인 집합과 하루의 동인 집합을 비교한 결과가 Change Feed에 실린다 —
    새 기능이 이미 있던 일간 Change Feed를 조용히 망가뜨리는 경로다.
    """
    from features.common.change_intelligence.adapters.briefing import build_briefing_basis

    daily = build_briefing_basis({"date": "2026-08-20", "marketScope": "us", "generatedAt": "2026-08-20T09:00:00+09:00"})
    weekly = build_briefing_basis({
        "date": "2026-08-20", "marketScope": "us", "kind": "weekly",
        "generatedAt": "2026-08-20T10:00:00+09:00",
    })

    assert daily["lineageId"] != weekly["lineageId"]
    assert daily["artifactId"] != weekly["artifactId"]


def test_the_baseline_selector_will_not_match_across_kinds():
    from features.common.change_intelligence.baseline import _matches
    from features.common.change_intelligence.adapters.briefing import build_briefing_basis

    daily = build_briefing_basis({"date": "2026-08-19", "marketScope": "us", "generatedAt": "2026-08-19T09:00:00+09:00"})
    weekly = build_briefing_basis({
        "date": "2026-08-20", "marketScope": "us", "kind": "weekly",
        "generatedAt": "2026-08-20T09:00:00+09:00",
    })

    assert _matches(weekly, daily) is False
    # 같은 종류끼리는 계속 이어진다.
    older_weekly = build_briefing_basis({
        "date": "2026-08-13", "marketScope": "us", "kind": "weekly",
        "generatedAt": "2026-08-13T09:00:00+09:00",
    })
    assert _matches(weekly, older_weekly) is True


def test_the_overlay_lands_on_the_report_that_is_open(monkeypatch, tmp_path):
    """주간을 열어 두고 누른 `개인 해석 생성`이 그날 일간 보고서를 고치면 안 된다."""
    import features.personal_overlay.service as overlay_service

    (tmp_path / "2026-08-20.us.json").write_text("{}", encoding="utf-8")
    (tmp_path / "2026-08-20.us.weekly.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(overlay_service, "BRIEFINGS_DIR", tmp_path)

    daily = overlay_service._briefing_overlay_path("2026-08-20", "us", "daily")
    weekly = overlay_service._briefing_overlay_path("2026-08-20", "us", "weekly")

    assert daily.name == "2026-08-20.us.json"
    assert weekly.name == "2026-08-20.us.weekly.json"


def test_the_cli_overlay_id_round_trips_through_canonical_identity():
    """CLI 경로는 report id로 파일을 되짚는다. 접미사가 없으면 일간을 연다."""
    from features.common.canonical_identity import _briefing_identity

    assert _briefing_identity("2026-08-20.weekly", "us") == ("2026-08-20", "us", "weekly")
    assert _briefing_identity("2026-08-20", "us") == ("2026-08-20", "us", None)


def test_reads_and_deletes_do_not_fall_back_across_kinds():
    """주간을 물었는데 일간을 돌려주면 화면이 다른 보고서를 열어 놓고 주간이라 말한다."""
    import inspect

    from features.daily_briefing import service

    source = inspect.getsource(service.resolve_briefing)

    assert "if kind == WEEKLY:" in source
    # 주간 분기는 legacy `{date}.json` fallback을 타지 않는다.
    weekly_branch = source.split("if kind == WEEKLY:")[1].split("if scope in SINGLE_MARKET_SCOPES:")[0]
    assert "briefing_file_name(date_text)" not in weekly_branch


def test_an_empty_week_stops_before_the_cli_runs():
    """주간은 창이 비어도 넓히지 않는다. 그대로 pack을 만들면 CLI를 두 번 돌리고 실패한다."""
    import inspect

    from features.agent_mode import service as agent_service

    source = inspect.getsource(agent_service.prepare_briefing_pack)

    assert "raise WeeklyWindowEmptyError(" in source
    assert issubclass(agent_service.WeeklyWindowEmptyError, ValueError)


def test_the_cli_overlay_opens_the_weekly_file_that_exists(monkeypatch, tmp_path):
    """CLI 주간 개인 해석이 저장된 적 없는 이름을 열어 언제나 실패하던 것을 막는다.

    주간 id는 `{발행일}.weekly`라 시장이 빠져 있는데, 주간 보고서는 시장별로만
    저장된다(`{발행일}.{시장}.weekly.json`). 예전에는 로더가 id에 `.json`만 붙여
    `{발행일}.weekly.json`을 열었고 그 파일은 만들어지는 경로가 없다.
    """
    import features.agent_mode.service as agent_service
    import features.personal_overlay.service as overlay_service

    (tmp_path / "2026-08-23.us.json").write_text('{"kind": "daily"}', encoding="utf-8")
    (tmp_path / "2026-08-23.us.weekly.json").write_text('{"kind": "weekly"}', encoding="utf-8")
    monkeypatch.setattr(overlay_service, "BRIEFINGS_DIR", tmp_path)

    canonical, path, kind = agent_service._load_canonical_for_overlay("briefing", "2026-08-23.weekly", "us")

    assert kind == "briefing"
    assert path.name == "2026-08-23.us.weekly.json"
    assert canonical == {"kind": "weekly"}

    # 종류를 싣지 않은 요청은 그대로 일간을 연다.
    daily, daily_path, _ = agent_service._load_canonical_for_overlay("briefing", "2026-08-23", "us")
    assert daily_path.name == "2026-08-23.us.json"
    assert daily == {"kind": "daily"}


def test_the_aggregate_overlay_finds_the_only_market_that_generated(monkeypatch, tmp_path):
    """합본 범위로 물어도 그 날짜에 시장 파일이 하나뿐이면 가리키는 대상이 하나다.

    합본 이름(`{발행일}.weekly.json`)은 저장되는 경로가 없다. 예전에는 그 이름을
    그대로 돌려줘 시장 파일이 멀쩡히 있는데도 404가 됐다.
    """
    import features.personal_overlay.service as overlay_service

    (tmp_path / "2026-08-23.us.weekly.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(overlay_service, "BRIEFINGS_DIR", tmp_path)

    assert overlay_service._briefing_overlay_path("2026-08-23", "multi", "weekly").name == "2026-08-23.us.weekly.json"

    # 여러 시장이 함께 있으면 어느 쪽에 얹을지 정할 수 없다 — 예전 동작을 유지한다.
    (tmp_path / "2026-08-23.kr.weekly.json").write_text("{}", encoding="utf-8")
    assert overlay_service._briefing_overlay_path("2026-08-23", "multi", "weekly").name == "2026-08-23.weekly.json"


def test_an_empty_week_never_reaches_the_model():
    """자료 0건이면 LLM을 부르지 않는다 — 근거 없이 한 주의 흐름을 쓰게 된다.

    CLI 경로는 `WeeklyWindowEmptyError`로 호출 전에 막고 규칙 경로는 "자료 0건"을
    본문에 적는데, API 키 경로만 그 계약 밖에서 빈 컨텍스트로 프롬프트를 보냈다.
    """
    import inspect

    from features.daily_briefing import builder

    source = inspect.getsource(builder._scope_result)
    gate = source.split("generate_llm_briefing(")[0]

    assert 'if kind == "weekly" and not scoped_docs:' in gate
    assert '"weekly_window_empty"' in gate


def test_the_weekly_data_gap_reads_its_own_window():
    """주간 자료가 0건인데 일간 세션 풀이 차 있으면 갭이 안 붙던 것을 막는다."""
    import inspect

    from features.daily_briefing import builder

    source = inspect.getsource(builder.build_briefing)

    assert "if not (weekly_pool if weekly_pool is not None else docs):" in source
    # 주간 창은 시장과 무관하므로 한 번만 고른다.
    assert source.count("weekly_documents(all_documents, week)") == 1


def test_the_report_listing_sees_weekly_but_the_prev_checklist_does_not():
    """주간이 목록 정규식에서 빠지면 저장은 되는데 화면에는 없다.

    아카이브는 자기 정규식에 종류를 넣어 뒀지만 `GET /api/briefings`와 대시보드
    payload(명령 팔레트·Agent 홈 최근 보고서)를 먹이는 이 정규식은 그대로였다.
    반대로 전일 체크포인트 조회는 계속 일간만 봐야 한다 — 한 주를 덮는 보고서를
    물어오면 오늘의 세션 체크리스트가 지난주 확인 항목으로 바뀐다.
    """
    from features.daily_briefing.service import (
        BRIEFING_DAILY_REPORT_FILE_RE,
        BRIEFING_REPORT_FILE_RE,
    )

    assert BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-23.us.weekly.json")
    assert BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-23.us.json")
    assert not BRIEFING_REPORT_FILE_RE.fullmatch("2026-08-23.us.visuals.json")

    assert not BRIEFING_DAILY_REPORT_FILE_RE.fullmatch("2026-08-23.us.weekly.json")
    assert BRIEFING_DAILY_REPORT_FILE_RE.fullmatch("2026-08-23.us.json")

    import inspect

    from features.daily_briefing import service

    assert "BRIEFING_DAILY_REPORT_FILE_RE" in inspect.getsource(service.load_prev_briefing)


def test_one_predicate_decides_what_is_weekly():
    """종류 판정이 흩어져 있으면 정규화 규칙이 바뀔 때 절반만 따라온다.

    같은 비교가 계약 검사·프롬프트 선택·상한 계산·예약·라우트에 일곱 벌 있었다.
    주간을 일간 프롬프트로 만든 뒤 주간 계약으로 검사하는 식의 어긋남이 이 중복에서 나온다.
    """
    import inspect
    from pathlib import Path

    from features.daily_briefing.limits import BRIEFING_KINDS, is_weekly, normalize_briefing_kind
    from features.daily_briefing.schema import BRIEFING_KINDS as SCHEMA_KINDS

    assert is_weekly("weekly") is True
    assert is_weekly(" WEEKLY ") is True
    assert is_weekly("daily") is False
    assert is_weekly(None) is False
    # enum 정의는 schema 하나이며 limits는 그것을 다시 내보낼 뿐이다.
    assert BRIEFING_KINDS is SCHEMA_KINDS
    assert normalize_briefing_kind("weekly") == "weekly"
    assert normalize_briefing_kind("nonsense") == "daily"

    # 손으로 적은 비교가 런타임 코드에 남아 있지 않아야 한다.
    root = Path(inspect.getfile(is_weekly)).parents[2]
    offenders = []
    for path in list(root.glob("features/**/*.py")) + [root / "app.py"]:
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if 'in {"daily", "weekly"}' in text or 'str(kind or "daily").strip().lower()' in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_weekly_body_never_carries_a_sources_section():
    """주간 본문에는 참고자료 섹션이 없다 — 출처는 `sources` 필드와 리더 패널이 단일 소유자다.

    모델이 `## 7. 참고자료`처럼 변형 헤딩으로 목록을 쓰면 정확 일치 검사가 놓쳐 코드가
    두 번째 `## 참고자료`를 덧붙였고, 리더는 정확 일치하는 쪽만 떼어내 첫 목록이 본문에
    남아 두 번 보였다(2026-08-22 사용자 보고).
    """
    from features.daily_briefing.service import append_briefing_sources, strip_markdown_sources_section

    body = (
        "## 이번 주 결론\n\n**한 주의 시장 성격:** 강세\n\n"
        "## 7. 참고자료 (24건)\n\n- [A](https://a)\n- [B](https://b)\n\n"
        "## Source & Data Notes\n\n- 로컬 자료 24건"
    )
    sources = [{"title": "A", "url": "https://a", "source": "x", "date": "2026-08-20"}]

    weekly = append_briefing_sources(body, sources, limit=24, kind="weekly")
    assert "참고자료" not in weekly
    # 뒤따르는 Source & Data Notes는 살아남는다 — 끝까지 자르면 노트까지 사라진다.
    assert "## Source & Data Notes" in weekly and "로컬 자료 24건" in weekly
    assert weekly.startswith("## 이번 주 결론")

    # 일간 계약은 그대로다 — 본문에 참고자료가 없으면 코드가 붙인다.
    daily = append_briefing_sources("## 0. 오늘\n\n본문", sources, limit=24, kind="daily")
    assert "## 참고자료" in daily

    # 변형 헤딩 세 가지를 모두 잡는다.
    for heading in ("## 참고자료", "### 참고 자료", "## Sources Used"):
        assert "참고" not in strip_markdown_sources_section(f"## 본문\n\n글\n\n{heading}\n\n- x") or "Sources" not in strip_markdown_sources_section(f"## 본문\n\n글\n\n{heading}\n\n- x")


def test_sources_heading_variants_are_loose_but_safe():
    """변형 헤딩은 잡고, 진짜 분석 섹션은 참고자료로 오인하지 않는다."""
    from features.daily_briefing.service import markdown_has_sources, strip_markdown_sources_section

    assert markdown_has_sources("## 7. 참고자료\n- a")
    assert markdown_has_sources("### 참고 자료 (24건)\n- a")
    assert markdown_has_sources("## Sources Used:\n- a")
    # "Sources of Uncertainty"는 분석 섹션이다 — 오인하면 Canonical 본문이 잘린다.
    assert not markdown_has_sources("## Sources of Uncertainty\n본문")

    text = "## 분석\n글\n\n## Sources of Uncertainty\n불확실성\n\n## 참고자료\n- x"
    out = strip_markdown_sources_section(text)
    assert "Uncertainty" in out and "- x" not in out


def test_strip_sources_keeps_following_h3_section():
    """h3 참고자료 뒤의 h3 섹션이 함께 지워지면 안 된다(꼬리 탐색이 h3까지 봐야 한다)."""
    from features.daily_briefing.service import strip_markdown_sources_section

    text = "## 본문\n글\n\n### 참고 자료\n- [a](http://x) — s, d\n\n### Source & Data Notes\n노트"
    out = strip_markdown_sources_section(text)
    assert "Source & Data Notes" in out and "참고 자료" not in out


def test_daily_append_skips_variant_heading():
    """모델이 `## 7. 참고자료`로 쓴 날 코드가 두 번째 목록을 덧붙이면 안 된다(일간)."""
    from features.daily_briefing.service import append_briefing_sources

    markdown = "## 본문\n글\n\n## 7. 참고자료\n- 모델이 쓴 목록"
    out = append_briefing_sources(markdown, [{"title": "T", "source": "S", "date": "D", "url": "http://u"}])
    assert out.count("참고자료") == 1


def test_export_markdown_reattaches_weekly_sources():
    """주간 본문에는 참고자료가 없다 — 내보내기 경계에서 sources 필드로 되붙인다."""
    from features.daily_briefing.service import export_markdown_with_sources

    unit = {
        "markdown": "## 지난주 미국장 흐름\n글",
        "sources": [{"title": "기사", "source": "매체", "date": "2026-08-21", "url": "http://a"}],
    }
    out = export_markdown_with_sources(unit)
    assert "## 참고자료" in out and "http://a" in out
    # 일간처럼 본문에 이미 있으면 그대로 통과한다 — 두 번 붙이지 않는다.
    daily = {"markdown": "## 본문\n\n## 참고자료\n- 이미", "sources": unit["sources"]}
    assert export_markdown_with_sources(daily).count("참고자료") == 1
