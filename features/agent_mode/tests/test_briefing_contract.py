from features.agent_mode.briefing_contract import (
    briefing_contract_violations,
    briefing_output_contract,
)


def _valid_markdown(scope="both"):
    contract = briefing_output_contract(scope)
    replacements = {
        "US Market Briefing": "# US Market Briefing — 2099.12.31",
        "Korea Market Briefing": "# Korea Market Briefing — 2099.12.31",
        "3. 미국장을 주도한 기업 ①": "## 3. 미국장을 주도한 기업 ① — NVIDIA",
        "4. 미국장을 주도한 기업 ②": "## 4. 미국장을 주도한 기업 ② — Alphabet",
        "3. 한국장을 주도한 기업 ①": "## 3. 한국장을 주도한 기업 ① — Samsung Electronics",
        "4. 한국장을 주도한 기업 ②": "## 4. 한국장을 주도한 기업 ② — SK hynix",
    }
    headings = "\n\n".join(replacements.get(heading, f"## {heading}") for heading in contract["requiredSections"])
    conclusions = "\n".join(
        "**한 줄 결론:** 시장의 가격 반응과 내부 구조를 함께 해석합니다."
        for _ in range(contract["minimumOneLineConclusions"])
    )
    bullets = "\n".join(
        "· 핵심 수치와 시장 내부 구조를 확인합니다."
        for _ in range(contract["minimumMiddleDotBullets"])
    )
    body = "시장 흐름과 근거, 반대 신호, 다음 체크포인트를 자연스러운 줄글로 설명합니다. "
    padding = body * 300
    return f"{headings}\n\n{conclusions}\n{bullets}\n\n{padding}"


def test_briefing_output_contract_matches_api_prompt_for_each_scope():
    both = briefing_output_contract("both")
    assert "0. 오늘의 미국장 성격" in both["requiredSections"]
    assert "6. 다음 미국장 체크포인트" in both["requiredSections"]
    assert "0. 오늘의 한국장 성격" in both["requiredSections"]
    assert "6. 다음 한국장 체크포인트" in both["requiredSections"]
    assert both["minimumCharacters"] == 10000
    assert both["minimumOneLineConclusions"] == 14
    assert both["minimumMiddleDotBullets"] == 36
    assert both["retryOnViolation"] == 0

    us = briefing_output_contract("us")
    assert any("미국장 시장 흐름" in row for row in us["requiredSections"])
    assert not any("한국장" in row for row in us["requiredSections"])
    assert us["minimumCharacters"] == 5000
    assert us["minimumOneLineConclusions"] == 7
    assert us["minimumMiddleDotBullets"] == 18


def test_concise_contract_keeps_sections_but_reduces_length_target():
    concise = briefing_output_contract("both", "concise")

    assert concise["briefingType"] == "concise"
    assert concise["requiredSections"] == briefing_output_contract("both")["requiredSections"]
    assert concise["minimumCharacters"] == 5000
    assert concise["minimumOneLineConclusions"] == 14
    assert concise["minimumMiddleDotBullets"] == 36


def test_market_focused_contract_keeps_full_length_target():
    contract = briefing_output_contract("us", "market_focused")

    assert contract["briefingType"] == "market_focused"
    assert contract["minimumCharacters"] == 5000


def test_abbreviated_cli_briefing_violates_structure_and_length_contract():
    markdown = """# Daily Market Briefing

## US Market Briefing
짧은 미국장 요약

## Korea Market Briefing
짧은 한국장 요약

## Source & Data Notes
자료 메모
"""
    violations = briefing_contract_violations(markdown, briefing_output_contract("both"))
    assert any("필수 제목 누락" in row and "미국장 시장 흐름" in row for row in violations)
    assert any("최소 분량" in row for row in violations)
    assert any("한 줄 결론" in row for row in violations)
    assert any("가운뎃점" in row for row in violations)


def test_complete_cli_briefing_satisfies_contract():
    contract = briefing_output_contract("both")
    assert briefing_contract_violations(_valid_markdown("both"), contract) == []


def test_both_scope_requires_repeated_shared_headings_for_each_market():
    contract = briefing_output_contract("both")
    markdown = _valid_markdown("both")
    markdown = markdown.replace("## 5. 일반 투자자 관점", "", 1)
    markdown = markdown.replace("## 오늘의 결론", "", 1)
    violations = briefing_contract_violations(markdown, contract)
    assert any("5. 일반 투자자 관점" in row and "2회" in row for row in violations)
    assert any("오늘의 결론" in row and "2회" in row for row in violations)
