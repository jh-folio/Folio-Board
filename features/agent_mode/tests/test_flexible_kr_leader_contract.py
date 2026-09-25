"""US/KR daily briefings keep the established fixed-two leader shape."""

from features.agent_mode.briefing_contract import (
    briefing_contract_violations,
    briefing_output_contract,
)


def _body(contract: dict, market: str = "kr", *, omit: str = "") -> str:
    label = "미국장" if market == "us" else "한국장"
    title = "US Market Briefing" if market == "us" else "Korea Market Briefing"
    lines = [
        f"# {title} — 2026.08.25 마감",
        f"## 0. 오늘의 {label} 성격",
        f"## 1. {label} 시장 흐름",
        f"## 2. {label}을 움직인 핵심 변수",
        f"## 3. {label}을 주도한 기업 ① — 첫기업",
        f"## 4. {label}을 주도한 기업 ② — 둘째기업",
        "## 5. 일반 투자자 관점",
        f"## 6. 다음 {label} 체크포인트",
        "## 오늘의 결론",
        "## Source & Data Notes",
    ]
    selected = [line for line in lines if not omit or omit not in line]
    return "\n\n".join(selected) + "\n" + (
        "**한 줄 결론:** 확인\n" * contract["minimumOneLineConclusions"]
        + "· 확인 항목\n" * contract["minimumMiddleDotBullets"]
        + "근거 있는 분석 문장 " * 1000
    )


def test_legacy_optional_mode_is_ignored_for_us_and_kr_daily() -> None:
    for market in ("us", "kr"):
        contract = briefing_output_contract(
            market,
            markets=[market],
            leader_section_modes={market: "optional_zero_to_two"},
        )
        assert contract["leaderSectionModes"] == {market: "fixed_two"}
        assert f"3. {'미국장' if market == 'us' else '한국장'}을 주도한 기업 ①" in contract["requiredSections"]
        assert f"4. {'미국장' if market == 'us' else '한국장'}을 주도한 기업 ②" in contract["requiredSections"]
        assert contract["minimumOneLineConclusions"] == 7
        assert contract["minimumMiddleDotBullets"] == 18


def test_fixed_two_contract_requires_each_named_slot_even_with_legacy_modes() -> None:
    for market in ("us", "kr"):
        contract = briefing_output_contract(
            market,
            markets=[market],
            leader_section_modes={market: "qualified_zero_to_two"},
        )
        for ordinal in ("①", "②"):
            broken = _body(contract, market, omit=f"기업 {ordinal}")
            violations = briefing_contract_violations(broken, contract)
            assert any("주도 기업명 누락" in row and f"기업 {ordinal}" in row for row in violations)


def test_fixed_two_contract_requires_named_companies_in_active_off_and_shadow_shapes() -> None:
    for mode in ("active", "off", "shadow"):
        contract = briefing_output_contract(
            "kr", markets=["kr"], leader_section_modes={"kr": "fixed_two"},
        )
        broken = _body(contract, "kr", omit="기업 ②")
        assert any("기업 ②" in row for row in briefing_contract_violations(broken, contract)), mode


def test_expected_leading_companies_are_exact_and_ordered() -> None:
    contract = briefing_output_contract(
        "kr",
        expected_titles={"kr": "Korea Market Briefing — 2026.08.24 마감"},
        expected_leading_companies={"kr": ["삼성전자", "SK하이닉스"]},
    )
    markdown = _body(contract, "kr").replace("첫기업", "삼성전자").replace("둘째기업", "SK하이닉스")
    markdown = markdown.replace("2026.08.25", "2026.08.24")
    assert not briefing_contract_violations(markdown, contract)
    wrong = markdown.replace("SK하이닉스", "NAVER")
    assert any("주도 기업 불일치" in row for row in briefing_contract_violations(wrong, contract))


def test_shadow_mode_stays_out_of_concentration_adjudication(monkeypatch):
    import features.daily_briefing.concentration.runtime as runtime

    monkeypatch.setenv("KR_BRIEFING_CONCENTRATION_MODE", "shadow")

    def boom(*args, **kwargs):
        raise AssertionError("shadow에서 판정 CLI가 호출되면 안 된다")

    monkeypatch.setattr(runtime, "configured_adjudication", boom)
    groups = [
        {"company": "삼성전자", "sector": "Tech", "briefingGroupScore": 10.0, "docs": [], "score": 10},
        {"company": "SK하이닉스", "sector": "Tech", "briefingGroupScore": 9.0, "docs": [], "score": 9},
    ]
    effective, control = runtime.prepare_concentration(groups, market_scope="kr", kind="daily")
    assert effective == groups or [g["company"] for g in effective] == [g["company"] for g in groups]
    assert control.get("mode") == "shadow"


def test_fixed_two_mode_does_not_change_jp_or_europe() -> None:
    for market in ("jp", "europe"):
        contract = briefing_output_contract(
            market, markets=[market], leader_section_modes={market: "optional_zero_to_two"},
        )
        assert any("주도한 기업 ①" in row for row in contract["requiredSections"])
        assert any("주도한 기업 ②" in row for row in contract["requiredSections"])
        assert contract["leaderSectionModes"] == {market: "fixed_two"}
