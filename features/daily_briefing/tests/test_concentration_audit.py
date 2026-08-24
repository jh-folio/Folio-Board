from __future__ import annotations

from features.daily_briefing.concentration.audit import audit_concentration


def test_entity_mentions_alone_do_not_trigger_repair() -> None:
    markdown = """# 한국 시장
## 0. 시장 성격
삼성전자는 지수 비중이 큽니다.
## 1. 시장 흐름
삼성전자의 거래대금이 컸습니다.
## 2. 핵심 변수
삼성전자 실적 발표 일정이 있습니다.
## 3. 한국장을 주도한 기업 ① — 삼성전자
파운드리 수주로 가동률이 개선될 수 있습니다.
## 4. 한국장을 주도한 기업 ② — SK하이닉스
HBM 공급계약으로 제품 믹스가 개선될 수 있습니다.
"""
    audit = audit_concentration(markdown, leader_subjects=["삼성전자", "SK하이닉스"])
    assert audit["status"] != "repair_candidate"


def test_reworded_same_causal_claim_across_sections_is_detected() -> None:
    markdown = """# 한국 시장
## 1. 시장 흐름
HBM 공급 확대가 판매 단가와 영업이익을 끌어올려 주가 상승으로 이어집니다.
## 2. 핵심 변수
고대역폭 메모리 공급 증가는 단가 개선과 영업이익 증가를 통해 주가에 영향을 줍니다.
## 3. 한국장을 주도한 기업 ① — SK하이닉스
HBM 공급 확대가 판매 단가와 영업이익을 끌어올려 주가 상승으로 이어집니다.
## 5. 일반 투자자 관점
고대역폭 메모리 공급 증가는 단가 개선과 영업이익 증가를 통해 주가에 영향을 줍니다.
"""
    audit = audit_concentration(markdown, leader_subjects=["SK하이닉스"])
    assert audit["status"] == "repair_candidate"
    assert "claim_overlap" in audit["signals"]
