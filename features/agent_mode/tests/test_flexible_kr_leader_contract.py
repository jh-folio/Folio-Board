from features.agent_mode.briefing_contract import briefing_contract_violations, briefing_output_contract


def _body(contract: dict) -> str:
    headings = []
    for item in contract["requiredSections"]:
        if item == "Korea Market Briefing":
            headings.append("# Korea Market Briefing — 2026.08.25 마감")
        elif "주도한 기업 ①" in item:
            headings.append(f"## {item} — NAVER")
        else:
            headings.append(f"## {item}")
    return "\n\n".join(headings) + "\n" + ("**한 줄 결론:** 확인\n" * 7) + ("· 확인 항목\n" * 18) + ("근거 있는 분석 문장 " * 1000)


def test_flexible_kr_contract_accepts_zero_leader_fallback() -> None:
    contract = briefing_output_contract(
        "kr", markets=["kr"], expected_leading_companies={"kr": []},
        leader_section_modes={"kr": "qualified_zero_to_two"},
    )
    assert "3. 오늘의 기업 신호" in contract["requiredSections"]
    assert not any("주도한 기업" in row for row in contract["requiredSections"])
    assert briefing_contract_violations(_body(contract), contract) == []


def test_flexible_kr_contract_accepts_one_and_rejects_extra_slot() -> None:
    contract = briefing_output_contract(
        "kr", markets=["kr"], expected_leading_companies={"kr": ["NAVER"]},
        leader_section_modes={"kr": "qualified_zero_to_two"},
    )
    markdown = _body(contract)
    assert briefing_contract_violations(markdown, contract) == []
    extra = markdown + "\n## 4. 한국장을 주도한 기업 ② — 삼성전자\n추가"
    assert any("슬롯 수 불일치" in row for row in briefing_contract_violations(extra, contract))
