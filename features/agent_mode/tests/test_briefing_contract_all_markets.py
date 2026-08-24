"""네 시장 어느 조합이든 계약이 자기 자신과 모순되지 않는다."""
import itertools

import pytest

from features.agent_mode.briefing_contract import (
    MARKET_LABELS,
    TITLE_REQUIREMENTS,
    briefing_contract_violations,
    briefing_output_contract,
)

DATE = "2026.08.12"


def _market_block(key: str) -> str:
    """그 시장의 필수 섹션을 계약이 요구하는 그대로 쓴 본문."""
    label = MARKET_LABELS[key]
    lines = [f"# {TITLE_REQUIREMENTS[key]} — {DATE} 마감", "", f"## 0. 오늘의 {label} 성격", "**한 줄 결론:** 요약."]
    for index, name in ((1, f"{label} 시장 흐름"), (2, f"{label}을 움직인 핵심 변수")):
        lines += ["", f"## {index}. {name}", "**한 줄 결론:** 요약."]
        lines += [f"· 항목 {n}" for n in range(9)]
    lines += ["", f"## 3. {label}을 주도한 기업 ① — 대표기업", "**한 줄 결론:** 요약."]
    lines += ["", f"## 4. {label}을 주도한 기업 ② — 다른기업", "**한 줄 결론:** 요약."]
    lines += ["", "## 5. 일반 투자자 관점", "**한 줄 결론:** 요약."]
    lines += ["", f"## 6. 다음 {label} 체크포인트", "**한 줄 결론:** 요약."]
    lines += ["", "## 오늘의 결론", "**한 줄 결론:** 요약.", "본문 " + "가" * 6000]
    return "\n".join(lines)


def _report(keys) -> str:
    # Notes는 시장마다 하나다(2026-08-24 계약) — 합본 꼬리 하나만 쓰면 분리가
    # 그 꼬리를 마지막 시장 파일에 몰아준다.
    return "\n\n".join(
        _market_block(key) + "\n\n## Source & Data Notes\n자료 메모." for key in keys
    ) + "\n"


def _contract(keys):
    return briefing_output_contract(
        "multi",
        "default",
        markets=tuple(keys),
        expected_titles={key: f"{TITLE_REQUIREMENTS[key]} — {DATE} 마감" for key in keys},
    )


@pytest.mark.parametrize("key", sorted(TITLE_REQUIREMENTS))
def test_a_single_market_report_passes_its_own_contract(key):
    """**계약이 요구하는 그대로 쓴 보고서는 통과해야 한다.**

    예전에는 `us가 아니면 한국장`이라 일본장·유럽장 제목 뒤에 `0. 오늘의 한국장 성격`을
    요구했다. 같은 계약의 필수 섹션 목록은 `0. 오늘의 일본장 성격`을 요구하므로 계약이
    자기 자신과 모순됐고, 그 조합은 무엇을 써도 통과할 수 없었다.
    """
    assert briefing_contract_violations(_report([key]), _contract([key])) == []


@pytest.mark.parametrize("keys", [
    pair for pair in itertools.combinations(sorted(TITLE_REQUIREMENTS), 2)
])
def test_every_two_market_combination_passes_its_own_contract(keys):
    """18:00 예약이 쓰는 `kr+jp`를 포함해 어느 짝이든 성립해야 한다."""
    assert briefing_contract_violations(_report(keys), _contract(keys)) == []


def test_all_four_markets_pass_together():
    keys = sorted(TITLE_REQUIREMENTS)
    assert briefing_contract_violations(_report(keys), _contract(keys)) == []


def test_a_wrong_section_zero_is_still_caught():
    """느슨해진 것이 아니라 시장별로 정확해진 것이다."""
    broken = _report(["jp"]).replace("## 0. 오늘의 일본장 성격", "## 0. 오늘의 한국장 성격")

    violations = briefing_contract_violations(broken, _contract(["jp"]))

    assert any("0. 오늘의 일본장 성격" in item for item in violations)


def test_a_missing_leading_company_is_caught_per_market():
    """예전에는 문서 전체를 훑어 다른 시장의 헤딩이 대신 걸리면 통과했다."""
    keys = ("kr", "jp")
    broken = _report(keys).replace("## 3. 일본장을 주도한 기업 ① — 대표기업", "## 3. 일본장을 주도한 기업 ① — [기업명]")

    violations = briefing_contract_violations(broken, _contract(keys))

    assert any("일본장을 주도한 기업 ①" in item for item in violations)
