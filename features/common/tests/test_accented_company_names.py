"""악센트가 붙은 회사 이름도 같은 회사로 읽어야 한다.

`_key()`의 문자 필터는 허용 범위 밖을 공백으로 바꾼다. 그래서 악센트 붙은 글자가
이름을 조각냈다 — `Estée Lauder` -> `est e lauder`, `Nestlé` -> `nestl`,
`Société Générale` -> `soci t  g n rale`. SEC와 구성종목 파일은 대개 악센트 없는
표기(`ESTEE LAUDER COMPANIES INC`)라 둘이 만나지 못했다.

실측: 2026-08-19 미국장 브리핑이 주도 기업 ②로 `Estée Lauder`를 꼽았는데 `unknown`
으로 끝나 차트가 빈자리로 나갔다. 유럽 종목은 더 넓게 걸렸다.

일본어 탁점은 악센트가 아니다. `バ`는 `ハ`+탁점으로 분해되는데 그걸 떼면 다른 글자가
된다. 그래서 앞 글자가 ASCII 라틴일 때만 뗀다.
"""
from __future__ import annotations

import pytest

from features.common.tests.company_listing_fixtures import company_listing_cache

from features.common.company_resolution import _fold_latin_accents, _key, resolve_company_query


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Estée Lauder", "estee lauder"),
        ("Nestlé", "nestle"),
        ("Société Générale", "societe generale"),
        ("L'Oréal", "l oreal"),
        ("Anheuser-Busch", "anheuser busch"),
    ],
)
def test_latin_accents_fold_into_the_plain_letter(raw, expected):
    assert _key(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["삼성전자", "SK하이닉스", "トヨタ自動車", "ソフトバンクグループ", "日本製鉄", "現代自動車"],
)
def test_other_scripts_are_untouched(raw):
    """한글·가나·한자는 그대로 남는다. 지우면 그 이름으로는 아무것도 못 찾는다."""
    assert _key(raw) == raw.lower()


def test_japanese_voiced_marks_survive():
    """탁점을 떼면 다른 글자가 된다 — ソフトバンク가 ソフトハンク가 되면 안 된다."""
    assert _fold_latin_accents("ソフトバンクグループ") == "ソフトバンクグループ"
    assert _fold_latin_accents("ハ") == "ハ"


def test_the_accented_and_plain_spellings_resolve_to_one_company():
    accented = resolve_company_query("Estée Lauder")
    plain = resolve_company_query("Estee Lauder")

    assert accented.get("status") == "confident"
    assert (accented.get("match") or {}).get("ticker") == "EL"
    assert (accented.get("match") or {}).get("ticker") == (plain.get("match") or {}).get("ticker")


@pytest.mark.parametrize(
    ("query", "ticker"),
    [("Société Générale", "GLE.PA"), ("L'Oréal", "OR.PA")],
)
def test_european_accented_names_resolve_to_their_home_listing(query, ticker):
    resolution = resolve_company_query(query, prefer_home=True)

    assert (resolution.get("match") or {}).get("ticker") == ticker


def test_the_briefing_chart_path_keeps_the_accented_leader():
    """실제로 빈자리가 났던 경로(2026-08-19 미국장 주도 기업 ②)."""
    from features.daily_briefing.visuals import leading_company_subjects_from_markdown

    markdown = (
        "# US Market Briefing — 2026.08.19 마감\n"
        "## 3. 미국장을 주도한 기업 ① — Moderna\n"
        "## 4. 미국장을 주도한 기업 ② — Estée Lauder\n"
    )

    result = leading_company_subjects_from_markdown(markdown)

    assert [row["ticker"] for row in result["us"]] == ["MRNA", "EL"]
    assert result["unresolvedByMarket"]["us"] == []
