"""문체 계약 — 유보 표현 과잉과 발언 익명화만 잰다.

측정할 수 없는 것("자연스러움")은 계약에 넣지 않는다. 규칙으로 강제한 서술 형식이
오히려 품질을 해친 실패를 두 번 겪었다(11개 섹션 고정 골격, 4단계 초심자 소제목).
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report.report_contract import (
    HEDGE_DENSITY_LIMIT,
    hedge_stats,
    unattributed_speech,
)
from features.topic_report.web_lookup import speaker_sources


def _doc(body: str, notes: str = "") -> str:
    return "## 장기금리\n\n" + body + ("\n\n## Source & Data Notes\n\n" + notes if notes else "")


# ------------------------------------------------------------------ 유보 표현

def test_hedge_density_is_measured_outside_the_notes_section():
    # 데이터 한계 서술은 Source & Data Notes의 일이다. 거기까지 세면 성실한 보고서가
    # 벌을 받는다.
    body = "장기금리는 4.35%까지 올랐다. " * 20
    notes = "이 수치는 단정하기 어렵다. 함께 봐야 한다. 점검해야 한다. " * 5
    stats = hedge_stats(_doc(body, notes))
    assert stats["total"] == 0
    assert stats["per1000"] == 0.0


def test_hedge_overuse_is_detected():
    # 문제로 지적된 보고서가 천자당 3.07~3.34회였다.
    stats = hedge_stats(_doc("금리가 더 오를 수 있다. 다만 내릴 가능성이 있다. " * 12))
    assert stats["per1000"] > HEDGE_DENSITY_LIMIT


def test_a_decisive_report_passes():
    stats = hedge_stats(_doc(
        "현재로서는 기대 재평가가 우세하다. 10년물은 4.35%까지 올랐고 단기물은 제자리였다. "
        "성장 기대만으로는 이 격차가 설명되지 않는다. " * 8
        + "다만 기간 프리미엄을 직접 분해할 자료는 없을 수 있다."
    ))
    assert stats["per1000"] <= HEDGE_DENSITY_LIMIT


def test_one_phrase_carrying_the_whole_report_is_flagged_separately():
    # 총량이 적어도 한 표현만 스무 번 나오면 글이 같은 자리에서 계속 멈춘다.
    # 실측: 한 보고서에서 유보 31회 중 23회가 `수 있다`였다.
    stats = hedge_stats(_doc("이것은 그렇게 될 수 있다. " + "금리는 4.35% 수준에서 움직였다. " * 30) )
    assert stats["topPhrase"] == "수 있다"
    assert stats["topCount"] == 1


# ------------------------------------------------------------------ 발언 귀속

_QUOTES = [{"sourceId": "web_007", "role": "의장"}, {"sourceId": "web_008", "role": "이사"}]


def test_institutional_voice_loses_the_speaker():
    # 실측: 파월·월러 발언 4건을 원장에 올리고 본문이 태그까지 달았는데, 문장은 전부
    # "연준은 ~라고 설명했다"였고 이름은 0회였다.
    doc = "연준은 기대가 고착되면 위험하다고 설명했다.\n<!-- folio-source-ids: web_007, web_008 -->"
    assert unattributed_speech(doc, _QUOTES) == ["web_007", "web_008"]


def test_naming_the_speaker_satisfies_the_contract():
    doc = ("파월 의장은 2022년 3월 기자회견에서 기대 고착의 위험을 말했고, "
           "월러 이사도 같은 취지로 발언했다.\n<!-- folio-source-ids: web_007, web_008 -->")
    assert unattributed_speech(doc, _QUOTES) == []


def test_quotes_the_report_never_cited_are_not_flagged():
    # 안 쓴 발언까지 귀속을 요구하면 쓰지 않은 자료로 벌을 준다.
    assert unattributed_speech("본문에 태그가 없다.", _QUOTES) == []


def test_role_words_survive_transliteration_but_names_do_not():
    # 이름으로 대조할 수 없어서 직함을 쓴다 — 원문은 "Jerome H. Powell", 본문은 "파월".
    rows = [{"quotes": [
        {"who": "Jerome H. Powell·연준 의장", "what": "…", "url": "https://a", "sourceId": "web_007"},
        {"who": "우에다 가즈오 일본은행 총재", "what": "…", "url": "https://b", "sourceId": "web_009"},
        {"who": "시장 참가자", "what": "…", "url": "https://c", "sourceId": "web_010"},
    ]}]
    assert speaker_sources(rows) == [
        {"sourceId": "web_007", "role": "의장"},
        {"sourceId": "web_009", "role": "총재"},
    ]


def test_no_quote_sources_means_no_check():
    assert unattributed_speech("아무 글", []) == []
    assert unattributed_speech("아무 글", None) == []


# ------------------------------------------------- 결함이 고칠 자리를 가리킨다

def test_style_defects_point_at_a_repairable_section():
    # repairable_sections는 section이 빈 결함을 건너뛴다. 자리를 안 주면 그 결함은
    # 점수만 깎고 보수가 손댈 수 없다 — 잡아 놓고 고칠 길을 막는 셈이다.
    from features.topic_report.report_contract import hedgiest_section, sections_citing

    doc = ("## 얕은 섹션\n\n금리는 4.35%다.\n\n"
           "## 유보가 몰린 섹션\n\n" + "그럴 수 있다. 가능성이 있다. " * 8
           + "\n<!-- folio-source-ids: web_007 -->\n\n"
           "## Source & Data Notes\n\n" + "단정하기 어렵다. " * 20)
    assert hedgiest_section(doc) == "유보가 몰린 섹션"
    assert sections_citing(doc, ["web_007", "web_404"]) == {"web_007": "유보가 몰린 섹션"}


def test_repairable_sections_can_use_those_defects():
    from features.topic_report.candidate_pipeline import repairable_sections

    validation = {"defects": [
        {"code": "hedge_overuse", "severity": 40, "fixable": True, "section": "장기금리"},
        {"code": "speech_unattributed", "severity": 40, "fixable": True, "section": "결론"},
    ]}
    assert repairable_sections(validation, limit=3) == ["장기금리", "결론"]
