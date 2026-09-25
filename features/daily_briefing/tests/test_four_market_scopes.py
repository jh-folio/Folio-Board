"""Task 3.1 — the read/write/list/delete matrix across four markets plus `all`.

The gate is that a reader never infers coverage from a scope label, and that
legacy `both` records keep meaning exactly the two markets they were generated
with.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from features.daily_briefing.archive import BriefingArchiveIndex
from features.daily_briefing.schema import (
    AGGREGATE_SCOPES,
    SINGLE_MARKET_SCOPES,
    briefing_export_units,
    briefing_file_name,
    briefing_scope_view,
    market_keys_for_briefing_scope,
    normalize_market_scope,
    split_market_markdown,
    visual_sidecar_file_name,
    visual_sidecar_gzip_file_name,
)

DATE = "2026-08-05"
TITLES = {
    "us": "US Market Briefing", "kr": "Korea Market Briefing",
    "europe": "Europe Market Briefing", "jp": "Japan Market Briefing",
}


def _write(root: Path, scope: str, *, generation_scope: str = "", text: str = "") -> Path:
    path = root / briefing_file_name(DATE, scope)
    path.write_text(json.dumps({
        "date": DATE,
        "marketScope": scope,
        "briefingType": "default",
        "generatedAt": f"{DATE}T08:00:00+09:00",
        **({"generationScope": generation_scope} if generation_scope else {}),
        "markdown": f"# {TITLES[scope]}\n\n{text or scope}-body",
    }, ensure_ascii=False), encoding="utf-8")
    return path


# --- scope contract -----------------------------------------------------


def test_all_covers_four_markets_and_both_stays_two():
    assert market_keys_for_briefing_scope("all") == ("us", "kr", "europe", "jp")
    # 저장된 `both` 보고서는 유럽·일본을 담은 적이 없다. 소급해서 넓히면
    # 생성된 적 없는 커버리지를 주장하게 된다.
    assert market_keys_for_briefing_scope("both") == ("us", "kr")
    # `multi`는 이름 없는 조합의 레이블이다. 읽기 검색 범위는 네 시장이지만
    # 실제 커버리지는 저장된 시장 목록이 말한다.
    assert AGGREGATE_SCOPES == {"all", "both", "multi"}


def test_an_unknown_scope_does_not_widen_to_four_markets():
    assert normalize_market_scope("garbage") == "both"


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_each_market_gets_its_own_file_and_sidecar(scope):
    assert briefing_file_name(DATE, scope) == f"{DATE}.{scope}.json"
    assert visual_sidecar_gzip_file_name(DATE, scope) == f"{DATE}.{scope}.visuals.json.gz"


@pytest.mark.parametrize("scope", ["all", "both"])
def test_aggregate_scopes_share_the_dated_base_file(scope):
    assert briefing_file_name(DATE, scope) == f"{DATE}.json"


# --- read ---------------------------------------------------------------


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_read_returns_the_requested_market(scope):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written, generation_scope="all")
        with patch("features.daily_briefing.service.BRIEFINGS_DIR", root):
            from features.daily_briefing.service import resolve_briefing

            report = resolve_briefing(DATE, scope)
        assert report["marketScope"] == scope
        assert f"{scope}-body" in report["markdown"]


def test_an_aggregate_read_records_what_generated_and_what_was_asked_for():
    """An `all` run that lost Europe still says `all` — the lists show the gap."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in ("us", "kr", "jp"):
            _write(root, written, generation_scope="all")
        with patch("features.daily_briefing.service.BRIEFINGS_DIR", root):
            from features.daily_briefing.service import resolve_briefing

            report = resolve_briefing(DATE, "all")
        assert report["marketScope"] == "all"
        assert report["includedMarkets"] == ["US", "KR", "JP"]
        assert report["expectedMarkets"] == ["US", "KR", "EUROPE", "JP"]
        assert any("EUROPE" in text for text in report["coverageWarnings"])
        assert set(report["briefings"]) == {"us", "kr", "jp"}


def test_the_generation_response_carries_the_same_coverage_contract_as_the_read():
    """A client rendering right after generation must see which markets are missing."""
    report = briefing_scope_view({
        "date": DATE, "marketScope": "all",
        "includedMarkets": ["US", "KR", "JP"],
        "expectedMarkets": ["US", "KR", "EUROPE", "JP"],
        "coverageWarnings": ["EUROPE 브리핑이 생성되지 않았습니다."],
        "briefings": {"us": {"markdown": "# US Market Briefing"}},
    }, "all")
    assert report["includedMarkets"] == ["US", "KR", "JP"]
    assert report["expectedMarkets"] == ["US", "KR", "EUROPE", "JP"]
    assert report["coverageWarnings"]


def test_a_legacy_both_read_never_reaches_for_europe_or_japan():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written, generation_scope="both")
        with patch("features.daily_briefing.service.BRIEFINGS_DIR", root):
            from features.daily_briefing.service import resolve_briefing

            report = resolve_briefing(DATE, "both")
        assert report["includedMarkets"] == ["US", "KR"]
        assert set(report["briefings"]) == {"us", "kr"}
        assert "coverageWarnings" not in report


# --- list ---------------------------------------------------------------


def test_an_all_run_still_shows_four_cards():
    """다중 시장 생성이라도 카드는 시장별로 남는다.

    예전에는 한 번의 생성에서 나온 파일들을 카드 하나로 접었다. 그 카드는 모든 시장을
    이어 붙인 합본으로 열려, 각 시장 보고서를 화면에서 읽을 수 없었다
    (2026-08-10 사용자 결정).
    """
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written, generation_scope="all")

        payload = BriefingArchiveIndex(root, ttl_seconds=0).query()

        assert payload["total"] == 4
        assert [item["marketScope"] for item in payload["items"]] == list(SINGLE_MARKET_SCOPES)


def test_a_partial_run_shows_only_the_markets_it_wrote():
    """넷을 요청했다가 셋만 나왔으면 카드도 셋이다. 없는 시장의 카드를 만들지 않는다."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in ("us", "kr", "jp"):
            _write(root, written, generation_scope="all")

        payload = BriefingArchiveIndex(root, ttl_seconds=0).query()

        assert [item["marketScope"] for item in payload["items"]] == ["us", "kr", "jp"]


def test_two_runs_on_one_date_do_not_multiply_the_cards():
    """같은 날 `both` 생성과 `all` 생성이 있어도 시장당 한 장이다."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "us", generation_scope="both")
        _write(root, "kr", generation_scope="both")
        _write(root, "europe", generation_scope="all")
        _write(root, "jp", generation_scope="all")

        payload = BriefingArchiveIndex(root, ttl_seconds=0).query()

        assert sorted(item["marketScope"] for item in payload["items"]) == ["europe", "jp", "kr", "us"]


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_the_archive_filters_by_each_market(scope):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written)
        payload = BriefingArchiveIndex(root, ttl_seconds=0).query(market_scope=scope)
        assert [item["marketScope"] for item in payload["items"]] == [scope]


def test_archive_all_means_no_filter_not_the_four_market_scope():
    """`all` names a briefing scope and an archive filter; they mean different things."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written)
        assert BriefingArchiveIndex(root, ttl_seconds=0).query(market_scope="all")["total"] == 4
        assert BriefingArchiveIndex(root, ttl_seconds=0).query(market_scope="aggregate")["total"] == 0


# --- delete -------------------------------------------------------------


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_deleting_one_market_leaves_the_others(scope):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written, generation_scope="all")
        with patch("features.daily_briefing.service.BRIEFINGS_DIR", root):
            from features.daily_briefing.service import delete_briefing

            result = delete_briefing(DATE, market=scope)
        assert result["deleted"] is True
        survivors = {path.name for path in root.glob("*.json") if not path.name.startswith(".")}
        assert briefing_file_name(DATE, scope) not in survivors
        for other in SINGLE_MARKET_SCOPES:
            if other != scope:
                assert briefing_file_name(DATE, other) in survivors


def test_deleting_weekly_market_removes_weekly_report_and_sidecars():
    from features.daily_briefing import service

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        kr_files = (
            briefing_file_name(DATE, "kr", "weekly"),
            visual_sidecar_file_name(DATE, "kr", "weekly"),
            visual_sidecar_gzip_file_name(DATE, "kr", "weekly"),
        )
        us_file = briefing_file_name(DATE, "us", "weekly")
        for name in (*kr_files, us_file):
            (root / name).write_bytes(b"test")

        with (
            patch.object(service, "BRIEFINGS_DIR", root),
            patch("features.daily_briefing.archive.refresh_briefing_archive"),
        ):
            result = service.delete_briefing(DATE, market="kr", kind="weekly")

        assert result["deleted"] is True
        assert result["market"] == "kr"
        assert set(result["removedFiles"]) == set(kr_files)
        assert all(not (root / name).exists() for name in kr_files)
        assert (root / us_file).exists()


def test_a_date_wide_delete_removes_every_market():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for written in SINGLE_MARKET_SCOPES:
            _write(root, written, generation_scope="all")
        with patch("features.daily_briefing.service.BRIEFINGS_DIR", root):
            from features.daily_briefing.service import delete_briefing

            result = delete_briefing(DATE)
        assert result["deleted"] is True
        assert not [p for p in root.glob("*.json") if not p.name.startswith(".")]


def test_delete_rejects_a_market_outside_the_contract():
    with TemporaryDirectory() as tmp:
        with patch("features.daily_briefing.service.BRIEFINGS_DIR", Path(tmp)):
            from features.daily_briefing.service import delete_briefing

            with pytest.raises(ValueError):
                delete_briefing(DATE, market="cn")


# --- export / overlay ---------------------------------------------------


def test_export_produces_one_unit_per_generated_market():
    report = {
        "date": DATE, "marketScope": "all", "briefingType": "default",
        "briefings": {
            key: {"markdown": f"# {TITLES[key]}\n\n{key}-body"}
            for key in SINGLE_MARKET_SCOPES
        },
    }
    units = briefing_export_units(report)
    assert [unit["marketScope"] for unit in units] == list(SINGLE_MARKET_SCOPES)


def test_export_labels_use_the_shared_market_tags():
    from features.daily_briefing.schema import MARKET_TAGS

    assert MARKET_TAGS["europe"] == "유럽장"
    assert MARKET_TAGS["jp"] == "일본장"
    assert MARKET_TAGS["all"] == MARKET_TAGS["both"] == "종합"


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_overlay_targets_the_per_market_file_when_one_exists(scope):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, scope, generation_scope="all")
        with patch("features.personal_overlay.service.BRIEFINGS_DIR", root):
            from features.personal_overlay.service import _briefing_overlay_path

            assert _briefing_overlay_path(DATE, scope).name == f"{DATE}.{scope}.json"


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_overlay_falls_back_to_the_legacy_dated_file(scope):
    """Reports saved before per-market files still take an overlay."""
    with TemporaryDirectory() as tmp:
        with patch("features.personal_overlay.service.BRIEFINGS_DIR", Path(tmp)):
            from features.personal_overlay.service import _briefing_overlay_path

            assert _briefing_overlay_path(DATE, scope).name == f"{DATE}.json"


# --- markdown splitting -------------------------------------------------


def test_a_four_market_response_splits_into_four_sections_plus_the_link():
    text = "\n".join(
        f"# {TITLES[key]} — 2026.08.05 마감\n{key}-body" for key in SINGLE_MARKET_SCOPES
    ) + "\n## 시장 간 연결 요약\nlink-body"
    parts = split_market_markdown(text, "all")
    assert set(parts) == {*SINGLE_MARKET_SCOPES, "link"}
    for key in SINGLE_MARKET_SCOPES:
        assert f"{key}-body" in parts[key]["markdown"]
        # 각 시장 구획이 다음 시장 본문을 삼키면 안 된다.
        assert sum(f"{other}-body" in parts[key]["markdown"] for other in SINGLE_MARKET_SCOPES) == 1


def test_the_legacy_two_market_link_heading_still_parses():
    text = "# US Market Briefing\nus\n# Korea Market Briefing\nkr\n## 한미 시장 연결 요약\nlink"
    assert set(split_market_markdown(text, "both")) == {"us", "kr", "link"}


# --- titles -------------------------------------------------------------


def test_each_market_titles_its_own_session_not_the_publication_date():
    from features.common.market_calendar import briefing_market_windows

    windows = briefing_market_windows(DATE, as_of=f"{DATE}T18:00:00+09:00")
    view = briefing_scope_view(
        {"date": DATE, "marketScope": "europe", "marketWindows": windows,
         "markdown": "# Europe Market Briefing\n\nbody"},
        "europe",
    )
    # 유럽은 한국시간 자정 이후 마감하므로 발행일이 아니라 전일 세션이다.
    assert "2026.08.04" in view["title"]
    assert "Europe Market Briefing" in view["title"]


# --- multi-select -------------------------------------------------------


@pytest.mark.parametrize("value,expected", [
    (["us", "jp"], ("us", "jp")),
    (["jp", "us"], ("us", "jp")),          # 순서는 계약을 따른다
    (["us", "kr"], ("us", "kr")),
    ("us,jp", ("us", "jp")),               # 쿼리스트링은 문자열로 도착한다
    ("all", ("us", "kr", "europe", "jp")),
    ("both", ("us", "kr")),
    ("europe", ("europe",)),
    ([], ("us", "kr")),
    (["nonsense"], ("us", "kr")),
])
def test_a_market_selection_resolves_from_a_list_or_a_legacy_scope(value, expected):
    from features.daily_briefing.schema import normalize_market_selection

    assert normalize_market_selection(value) == expected


@pytest.mark.parametrize("markets,label", [
    (("us",), "us"),
    (("us", "kr"), "both"),
    (("us", "kr", "europe", "jp"), "all"),
    (("us", "jp"), "multi"),
    (("europe", "jp"), "multi"),
])
def test_a_selection_label_reuses_all_and_both_only_for_their_own_sets(markets, label):
    from features.daily_briefing.schema import market_selection_scope

    assert market_selection_scope(markets) == label


def test_an_unnamed_combination_keeps_its_own_market_cards():
    """`multi`는 레이블일 뿐이다. 읽는 사람이 믿는 것은 시장별 카드다."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for key in ("us", "jp"):
            path = root / briefing_file_name(DATE, key)
            path.write_text(json.dumps({
                "date": DATE, "marketScope": key, "briefingType": "default",
                "generatedAt": f"{DATE}T08:00:00+09:00",
                "generationScope": "multi", "generationMarkets": ["us", "jp"],
                "markdown": f"# {TITLES[key]}\n\n{key}-body",
            }, ensure_ascii=False), encoding="utf-8")
        items = BriefingArchiveIndex(root, ttl_seconds=0).query()["items"]

        # 조합에 이름이 없어도(`multi`) 읽는 사람이 보는 것은 시장별 카드다.
        assert [item["marketScope"] for item in items] == ["us", "jp"]


def test_two_different_combinations_on_one_date_give_four_market_cards():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for key, markets in (("us", ["us", "jp"]), ("jp", ["us", "jp"]),
                             ("kr", ["kr", "europe"]), ("europe", ["kr", "europe"])):
            (root / briefing_file_name(DATE, key)).write_text(json.dumps({
                "date": DATE, "marketScope": key, "briefingType": "default",
                "generatedAt": f"{DATE}T08:00:00+09:00",
                "generationScope": "multi", "generationMarkets": markets,
                "markdown": f"# {TITLES[key]}\n\n{key}-body",
            }, ensure_ascii=False), encoding="utf-8")
        items = BriefingArchiveIndex(root, ttl_seconds=0).query()["items"]

        assert sorted(row["marketScope"] for row in items) == ["europe", "jp", "kr", "us"]
