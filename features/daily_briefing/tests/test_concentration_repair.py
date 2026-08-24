from __future__ import annotations

import pytest

from features.daily_briefing.concentration.audit import audit_concentration
from features.daily_briefing.concentration.repair import apply_section_patches, repair_concentration


MARKDOWN = """# 한국 시장

## 3. 한국장을 주도한 기업 ① — 삼성전자

기존 삼성전자 본문

## 4. 한국장을 주도한 기업 ② — SK하이닉스

기존 SK하이닉스 본문

## 5. 일반 투자자 관점

기존 관점
"""


def test_repair_changes_only_allowed_section() -> None:
    updated = apply_section_patches(
        MARKDOWN,
        [{"heading": "5. 일반 투자자 관점", "replacementBody": "중복을 제거한 관점"}],
        allowed_headings={"5. 일반 투자자 관점"},
    )
    assert "중복을 제거한 관점" in updated
    assert "기존 삼성전자 본문" in updated
    assert "기존 SK하이닉스 본문" in updated


def test_repair_cannot_change_leader_heading_or_add_nested_heading() -> None:
    with pytest.raises(ValueError):
        apply_section_patches(
            MARKDOWN,
            [{"heading": "5. 일반 투자자 관점", "replacementBody": "## 4. 한국장을 주도한 기업 ② — NAVER\n본문"}],
            allowed_headings={"5. 일반 투자자 관점"},
        )


def test_semantic_repair_is_applied_only_when_audit_improves() -> None:
    markdown = """# 한국 시장
## 1. 시장 흐름
HBM 공급 확대가 판매 단가와 영업이익을 끌어올려 주가 상승으로 이어집니다.
## 2. 핵심 변수
고대역폭 메모리 공급 증가는 단가 개선과 영업이익 증가를 통해 주가에 영향을 줍니다.
## 3. 한국장을 주도한 기업 ① — SK하이닉스
HBM 공급 확대가 판매 단가와 영업이익을 끌어올려 주가 상승으로 이어집니다.
## 4. 한국장을 주도한 기업 ② — 삼성전자
파운드리 신규 수주가 가동률 회복으로 연결될지 확인해야 합니다.
"""
    before = audit_concentration(markdown, leader_subjects=["SK하이닉스", "삼성전자"])
    heading = before["affectedSections"][-1].removeprefix("## ")
    response = '{"patches":[{"heading":"' + heading + '","replacementBody":"외국인 수급과 업종 확산 여부를 별도로 확인해야 합니다."}]}'

    repaired, after = repair_concentration(
        markdown,
        before,
        leader_subjects=["SK하이닉스", "삼성전자"],
        other_major_subjects=[],
        invoke=lambda _prompt: response,
    )

    assert repaired != markdown
    assert after["repair"]["applied"] is True
    assert after["status"] != "repair_candidate"
