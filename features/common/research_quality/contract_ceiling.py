"""계약이 잡은 결함을 품질 점수에 반영한다.

결함은 이미 셌는데 점수가 그것을 읽지 않으면, 사용자는 무엇이 비었는지 모른 채 A를
본다(실측: 딥 리서치에서 결함 14건짜리 보고서가 93점/A/pass — 근거 없는 섹션 7개,
분량 미달, 본문 구성 불일치를 전부 안고서).

딥 리서치와 기업분석이 같은 눈금을 쓴다. 어떤 결함을 몇 점으로 볼지는 각 계약이
`severity`로 정하고, 여기서는 그 무게를 점수로 옮기기만 한다.
"""
from __future__ import annotations

from features.common.research_quality.schema import grade_from_score, status_from_score


# 계약 결함의 무게를 점수 상한으로 옮긴다. 잘 쓴 문장은 없는 근거를 대신하지 못한다.
_CONTRACT_CEILINGS = ((70, 69), (40, 89))
_CONTRACT_MANY_MAJOR = (3, 79)


def apply_contract_ceiling(quality: dict, validation: dict) -> dict:
    """계약이 잡은 결함을 품질 점수에 반영한다.

    결함은 이미 셌는데 점수가 그것을 읽지 않으면, 사용자는 무엇이 비었는지 모른 채
    A를 본다(실측: 결함 14건에 93점/A/pass — 근거 없는 섹션 7개, 분량 미달,
    본문 구성 불일치를 전부 안고서).
    """
    row = dict(quality or {})
    defects = [d for d in (validation or {}).get("defects") or [] if isinstance(d, dict)]
    if not defects or not row:
        return row
    severities = [int(d.get("severity") or 0) for d in defects]
    ceiling = 100
    reasons: list[str] = []
    for threshold, cap in _CONTRACT_CEILINGS:
        hits = [d for d, sev in zip(defects, severities, strict=False) if sev >= threshold]
        if hits:
            ceiling = min(ceiling, cap)
            codes = sorted({str(d.get("code") or "") for d in hits})[:4]
            reasons.append(f"심각도 {threshold} 이상 결함 {len(hits)}건(" + ", ".join(codes) + ")")
    major_count = sum(1 for sev in severities if sev >= 40)
    if major_count >= _CONTRACT_MANY_MAJOR[0]:
        ceiling = min(ceiling, _CONTRACT_MANY_MAJOR[1])
        reasons.append(f"주요 결함 {major_count}건")
    score = int(row.get("score") or 0)
    row["contractCeiling"] = {"applied": score > ceiling, "ceiling": ceiling, "reasons": reasons}
    if score > ceiling:
        row["score"] = ceiling
        row["grade"] = grade_from_score(ceiling)
        row["status"] = status_from_score(ceiling)
        row["warnings"] = [
            *list(row.get("warnings") or []),
            f"생성 계약 결함으로 점수를 {ceiling}점으로 제한했습니다: " + "; ".join(reasons),
        ][:12]
    return row


__all__ = ["apply_contract_ceiling"]
