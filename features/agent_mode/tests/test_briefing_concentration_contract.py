from __future__ import annotations

from features.agent_mode.briefing_contract import briefing_contract_violations, briefing_output_contract


def _markdown(second: str) -> str:
    return f"""# Korea Market Briefing — 2026.08.24 마감
## 0. 오늘의 한국장 성격
## 1. 한국장 시장 흐름
## 2. 한국장을 움직인 핵심 변수
## 3. 한국장을 주도한 기업 ① — 삼성전자
## 4. 한국장을 주도한 기업 ② — {second}
## 5. 일반 투자자 관점
## 6. 다음 한국장 체크포인트
## 오늘의 결론
## Source & Data Notes
""" + ("본문입니다. " * 800) + ("\n**한 줄 결론:** 결론\n" * 7) + ("· 요약\n" * 18)


def test_expected_leading_companies_are_exact_and_ordered() -> None:
    contract = briefing_output_contract(
        "kr",
        expected_titles={"kr": "Korea Market Briefing — 2026.08.24 마감"},
        expected_leading_companies={"kr": ["삼성전자", "SK하이닉스"]},
    )
    assert not briefing_contract_violations(_markdown("SK하이닉스"), contract)
    assert any("주도 기업 불일치" in row for row in briefing_contract_violations(_markdown("NAVER"), contract))


def test_multi_market_contract_requires_notes_per_market():
    """합본에 Notes 하나만 요구하면 모델이 공통 꼬리를 쓰고, 분리가 그 꼬리를 마지막
    시장 파일에 준다(2026-08-24 kr+jp 실측: 일본장 Notes에 한국장 문장)."""
    from features.agent_mode.briefing_contract import briefing_output_contract

    contract = briefing_output_contract("multi", "default", markets=["kr", "jp"])
    notes = [s for s in contract["requiredSections"] if s == "Source & Data Notes"]
    assert len(notes) == 2


def test_leading_company_match_is_normalized():
    """띄어쓰기·부기 하나로 45분짜리 CLI 두 번을 버리게 하지 않는다 — active 강제 시
    공백 제거·포함 일치면 같은 회사다."""
    from features.agent_mode.briefing_contract import briefing_contract_violations

    contract = {
        "requiredSections": [], "kind": "daily", "marketScope": "kr",
        "requireLeadingCompanyNames": True,
        "expectedLeadingCompanies": {"kr": ["SK하이닉스"]},
        "expectedTitles": {}, "requireImmediateSectionZeroAfterTitle": False,
    }
    markdown = (
        "# Korea Market Briefing — 2026.08.24 마감\n"
        "## 3. 한국장을 주도한 기업 ① — SK 하이닉스 (000660)\n본문\n"
        "## 4. 한국장을 주도한 기업 ② — 삼성전자\n본문\n"
    )
    violations = briefing_contract_violations(markdown, contract)
    assert not any("주도 기업 불일치" in v for v in violations), violations


def test_shadow_mode_stays_out_of_the_contract_and_prompt(monkeypatch):
    """shadow는 관측 전용이다(README 계약) — 프롬프트 권위 주입·판정 CLI 호출이 없어야 한다."""
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
