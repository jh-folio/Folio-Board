# -*- coding: utf-8 -*-
"""변화 크기의 바닥 회귀 테스트.

`change_event_index` 61건 중 `no_material_change`가 **0건**이던 상태에서 나왔다.
피드가 매일 "달라졌다"고 말하면 실제로 달라진 날을 가려낼 수 없다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.change_intelligence.adapters.briefing import build_briefing_basis
from features.common.change_intelligence.adapters.topic import build_topic_basis
from features.common.change_intelligence.comparator import compare_basis

REF = {"storageKind": "json_report", "id": "prev"}


def _briefing(date, drivers, issues, tape):
    return {
        "id": date, "date": date, "generatedAt": f"{date}T22:00:00+00:00", "marketScope": "us",
        "marketDrivers": [
            {"driver": name, "score": score, "docCount": 5,
             "topDocs": [{"title": f"{name} 기사", "url": f"https://ex.com/{name}"}]}
            for name, score in drivers
        ],
        "issueCoverage": [
            {"issueId": issue_id, "market": "US", "title": f"이슈 {issue_id}", "marketImpactStatus": "measured",
             "topDocs": [{"title": f"이슈 {issue_id} 기사", "url": f"https://ex.com/{issue_id}"}]}
            for issue_id in issues
        ],
        "marketTape": {"items": [{"id": symbol, "value": value} for symbol, value in tape]},
        "sources": [
            {"id": f"s{index}", "title": f"기사 {index}", "url": f"https://news{index}.com/a",
             "source": f"매체{index}", "reliabilityTier": 2, "publisherGroup": f"g{index}"}
            for index in range(1, 5)
        ],
    }


def _compare(current, previous):
    return compare_basis(
        build_briefing_basis(current), build_briefing_basis(previous),
        current_ref=REF, baseline_ref=REF,
    )


def test_a_quiet_day_is_a_quiet_day():
    """이슈 목록이 통째로 갈리고 종가가 조금씩 움직인 평범한 하루.

    예전에는 이 조합만으로 materiality 0.60이 나왔다 — 이슈 상수 0.35에 건수 가산
    상한 0.25가 매일 붙었다. 그래서 어떤 브리핑도 `no_material_change`가 못 됐다.
    """
    tape = [("SPY", 100.0), ("QQQ", 200.0), ("CL=F", 80.0), ("^VIX", 16.0)]
    moved = [("SPY", 100.2), ("QQQ", 200.6), ("CL=F", 81.2), ("^VIX", 16.3)]
    previous = _briefing("2026-08-24", [("반도체/AI", 30), ("금리", 20)], ["a1", "a2", "a3"], tape)
    current = _briefing("2026-08-25", [("반도체/AI", 30), ("금리", 20)], ["b1", "b2", "b3"], moved)

    summary = _compare(current, previous)
    assert summary["status"] == "no_material_change"
    assert summary["materiality"] == 0.0
    # 사라지지는 않는다. 무엇을 다뤘는지는 그대로 남고 크기만 0이다.
    assert [row["change"] for row in summary["changedItems"] if row["kind"] == "issue_coverage"]


def test_a_large_metric_move_still_registers():
    tape = [("SPY", 100.0), ("CL=F", 80.0)]
    previous = _briefing("2026-08-24", [("금리", 20)], ["a1"], tape)
    current = _briefing("2026-08-25", [("금리", 20)], ["a1"], [("SPY", 96.0), ("CL=F", 86.0)])

    summary = _compare(current, previous)
    assert summary["status"] == "major_change"
    assert summary["materiality"] >= 0.7


def test_driver_weight_is_measured_by_how_far_it_moved():
    """동인의 크기는 그날의 비중이 아니라 직전 대비 이동량이다."""
    tape = [("SPY", 100.0)]
    previous = _briefing("2026-08-24", [("반도체/AI", 20), ("금리", 80)], ["a1"], tape)
    same = _briefing("2026-08-25", [("반도체/AI", 20), ("금리", 80)], ["a1"], tape)
    # 비중 20%p 이동은 신호, 60%p 이동은 그날의 이야기가 뒤집힌 것이다.
    nudged = _briefing("2026-08-25", [("반도체/AI", 45), ("금리", 55)], ["a1"], tape)
    reversed_day = _briefing("2026-08-25", [("반도체/AI", 80), ("금리", 20)], ["a1"], tape)


    assert _compare(same, previous)["materiality"] == 0.0
    assert _compare(nudged, previous)["status"] == "developing_signal"
    # 그날의 이야기가 통째로 뒤집힌 경우까지 같은 눈금으로 잰다.
    assert _compare(reversed_day, previous)["status"] == "major_change"


def test_evidence_grade_alone_does_not_make_a_signal():
    """브리핑은 발행처가 늘 여럿이라 reliability가 언제나 0.85였다.

    그 값을 materiality의 대안 조건으로 두면 "단위 하나라도 바뀌면 신호"가 된다.
    """
    tape = [("SPY", 100.0)]
    previous = _briefing("2026-08-24", [("금리", 20)], ["a1"], tape)
    current = _briefing("2026-08-25", [("금리", 20)], ["a1"], [("SPY", 100.05)])

    summary = _compare(current, previous)
    assert summary["reliability"] >= 0.55
    assert summary["status"] == "no_material_change"


def test_custom_deep_research_reports_are_not_one_lineage():
    """`topicKey`가 `custom`인 것은 주제가 아니라 종류다.

    계보로 쓰면 아무 관계 없는 질문끼리 비교되어(실측 21건이 한 계보) 매번
    변화로 잡힌다. 정체성을 못 찾으면 자기 자신이 계보이고, 그러면 기준선이 없다.
    """
    first = {"id": "r1", "topicKey": "custom", "topicLabel": "장기금리와 기간 프리미엄"}
    second = {"id": "r2", "topicKey": "custom", "topicLabel": "엔캐리 청산과 한국 시장"}
    rerun = {"id": "r3", "topicKey": "custom", "topicLabel": "장기금리와 기간 프리미엄"}

    lineages = [build_topic_basis(report)["lineageId"] for report in (first, second, rerun)]
    assert lineages[0] != lineages[1]
    # 같은 질문의 재실행은 계속 이어 붙는다 — 비교가 성립하는 유일한 경우다.
    assert lineages[0] == lineages[2]
