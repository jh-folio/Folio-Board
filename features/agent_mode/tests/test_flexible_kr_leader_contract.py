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


def _optional_body(
    contract: dict,
    market: str,
    leader_headings: list[str],
    *,
    conclusions: int = 7,
    bullets: int = 18,
) -> str:
    title = "US Market Briefing" if market == "us" else "Korea Market Briefing"
    heading_map = {
        "US Market Briefing": f"# {title} — 2026.08.25 마감",
        "Korea Market Briefing": f"# {title} — 2026.08.25 마감",
    }
    lines = []
    for item in contract["requiredSections"]:
        if item in heading_map:
            lines.append(heading_map[item])
        else:
            lines.append(f"## {item}")
        if item == f"2. {'미국장' if market == 'us' else '한국장'}을 움직인 핵심 변수":
            lines.extend(leader_headings)
    return "\n\n".join(lines) + "\n" + ("**한 줄 결론:** 확인\n" * conclusions) + ("· 확인 항목\n" * bullets) + ("근거 있는 분석 문장 " * 1000)


def test_us_daily_optional_slots_allow_zero_one_or_two_without_inferred_empty() -> None:
    contract = briefing_output_contract(
        "us", markets=["us"], leader_section_modes={"us": "optional_zero_to_two"},
    )
    assert "us" not in contract["expectedLeadingCompanies"]
    for headings in (
        ["## 3. 오늘의 기업 신호"],
        ["## 3. 미국장을 주도한 기업 ① — NVIDIA"],
        [
            "## 3. 미국장을 주도한 기업 ① — NVIDIA",
            "## 4. 미국장을 주도한 기업 ② — Microsoft",
        ],
    ):
        assert briefing_contract_violations(_optional_body(contract, "us", headings), contract) == []


def test_optional_zero_company_shape_has_matching_quantitative_minimums() -> None:
    contract = briefing_output_contract(
        "us", briefing_type="concise", markets=["us"],
        leader_section_modes={"us": "optional_zero_to_two"},
    )

    # With no company section, the stable shape has five numbered sections
    # plus the conclusion: 6 conclusion markers and 15 middle-dot lines.
    assert contract["minimumOneLineConclusions"] == 6
    assert contract["minimumMiddleDotBullets"] == 15
    markdown = _optional_body(
        contract, "us", [], conclusions=6, bullets=15,
    )
    assert briefing_contract_violations(markdown, contract) == []


def test_optional_slots_require_sequential_concrete_company_names() -> None:
    contract = briefing_output_contract(
        "kr", markets=["kr"], leader_section_modes={"kr": "qualified_zero_to_two"},
    )
    markdown = _optional_body(contract, "kr", ["## 4. 한국장을 주도한 기업 ② — 삼성전자"])
    violations = briefing_contract_violations(markdown, contract)
    assert any("슬롯 순서 불일치" in row for row in violations)


def test_flexible_leader_mode_does_not_change_jp_or_europe() -> None:
    for market in ("jp", "europe"):
        contract = briefing_output_contract(
            market, markets=[market], leader_section_modes={market: "optional_zero_to_two"},
        )
        assert any("주도한 기업 ①" in row for row in contract["requiredSections"])
        assert any("주도한 기업 ②" in row for row in contract["requiredSections"])
        assert contract["leaderSectionModes"] == {market: "fixed_two"}


def test_optional_zero_company_fallback_is_scoped_per_market() -> None:
    contract = briefing_output_contract(
        "both", markets=["us", "kr"],
        leader_section_modes={"us": "optional_zero_to_two", "kr": "optional_zero_to_two"},
    )
    markdown = "\n\n".join([
        "# US Market Briefing — 2026.08.25 마감",
        "## 0. 오늘의 미국장 성격",
        "## 1. 미국장 시장 흐름",
        "## 2. 미국장을 움직인 핵심 변수",
        "## 3. 오늘의 기업 신호",
        "## 5. 일반 투자자 관점",
        "## 6. 다음 미국장 체크포인트",
        "## 오늘의 결론",
        "## Source & Data Notes",
        "# Korea Market Briefing — 2026.08.25 마감",
        "## 0. 오늘의 한국장 성격",
        "## 1. 한국장 시장 흐름",
        "## 2. 한국장을 움직인 핵심 변수",
        "## 3. 오늘의 기업 신호",
        "## 5. 일반 투자자 관점",
        "## 6. 다음 한국장 체크포인트",
        "## 오늘의 결론",
        "## Source & Data Notes",
    ]) + "\n" + ("**한 줄 결론:** 확인\n" * 14) + ("· 확인 항목\n" * 36) + ("근거 있는 분석 문장 " * 1000)
    assert briefing_contract_violations(markdown, contract) == []
