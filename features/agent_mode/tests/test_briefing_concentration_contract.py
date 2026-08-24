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
