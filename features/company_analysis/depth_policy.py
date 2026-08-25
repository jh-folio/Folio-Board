"""기업분석 분량 계약 — 섹션 예산은 채워야 할 **하한**이다.

지금까지 기업분석에는 분량 기준이 코드에도 프롬프트에도 없었다(grep 0건). 그래서
같은 9섹션인데 길이가 2~3배로 흔들렸다 — 실적과 재무 품질 1,818~4,366자,
기업 개요 806~2,582자, 전체 본문 9,720~17,113자(실측 4건).

**목표 분량은 확보한 자료를 따라간다.** 고정 하한을 두면 자료가 0건인 회사에서
모델이 없는 이야기로 칸을 채운다 — 딥 리서치에서 에디터가 초안 5,569자를 13,415자로
늘려 근거 없는 산문이 채워진 것과 같은 실패다. 자료가 얇으면 하한도 낮아지고,
비어 있다는 사실은 데이터 갭이 말한다.

가중치는 실측 중앙값과 분석 비중을 함께 본 것이다. 숫자를 다루는 섹션(실적·재무)이
가장 크고, 판단을 적는 섹션(어떻게 접근할까)과 메모(자료 한계)가 가장 작다.
"""
from __future__ import annotations

from features.company_analysis.style import REQUIRED_SECTION_HEADINGS

# 자료가 하나도 없어도 회사의 공식 숫자만으로 이만큼은 쓸 수 있다.
_BASE_CHARS = 11_000
# 보조 자료 한 건당. 상한을 두어 뉴스가 많은 대형주만 길어지지 않게 한다.
_PER_DOCUMENT = 250
_MAX_DOCUMENTS = 12
# 공식 숫자와 공시 서술이 있으면 쓸 것이 그만큼 는다.
_SEC_FACTS_BONUS = 1_000
_FILING_BONUS = 1_000
_TARGET_CAP = 17_000
# 이보다 길면 읽는 사람이 감당하지 못한다. 딥 리서치와 달리 한 회사 이야기다.
SAFETY_MAX_CHARS = 24_000

_SECTION_WEIGHTS = {
    "핵심 판단": 12,
    "기업 개요와 돈 버는 방식": 12,
    "실적과 재무 품질": 16,
    "밸류에이션": 10,
    "경쟁우위": 12,
    "리스크와 반증조건": 12,
    "성장 전망과 체크포인트": 12,
    "어떻게 접근할까": 8,
    "자료 한계와 참고자료": 6,
}


def build_depth_policy(
    *,
    document_count: int = 0,
    sec_facts_ok: bool = False,
    ranked_filing_ok: bool = False,
) -> dict:
    """확보한 자료로 이 보고서가 겨눌 분량을 정한다."""
    target = _BASE_CHARS
    target += min(max(int(document_count or 0), 0), _MAX_DOCUMENTS) * _PER_DOCUMENT
    if sec_facts_ok:
        target += _SEC_FACTS_BONUS
    if ranked_filing_ok:
        target += _FILING_BONUS
    target = min(_TARGET_CAP, target)

    total_weight = sum(_SECTION_WEIGHTS.values())
    budgets = {
        heading: max(400, round(target * _SECTION_WEIGHTS[heading] / total_weight))
        for heading in REQUIRED_SECTION_HEADINGS
        if heading in _SECTION_WEIGHTS
    }
    return {
        "schemaVersion": 1,
        "targetChars": target,
        "recommendedMinChars": target,
        "recommendedMaxChars": round(target * 1.3),
        "safetyMaxChars": SAFETY_MAX_CHARS,
        "sectionBudgets": budgets,
        "sections": list(REQUIRED_SECTION_HEADINGS),
    }


def render_length_contract(policy: dict) -> str:
    """생성 컨텍스트에 실을 블록.

    "충실히 쓰세요"는 지침이고 숫자는 과제다 — 이 세션에서 세 번 확인했다
    (웹 검색 허가 4회 실패 → 찾기 과제 1회 성공, 유보 압축 원칙 3회 실패 →
    "21회 이하로" 1회 성공).
    """
    budgets = (policy or {}).get("sectionBudgets") or {}
    if not budgets:
        return ""
    lines = [
        "## 분량 (섹션별 하한)",
        f"보이는 본문 전체는 {int(policy.get('recommendedMinChars') or 0):,}자 이상, "
        f"{int(policy.get('safetyMaxChars') or 0):,}자를 넘지 않게 씁니다.",
        "아래 숫자는 **채워야 할 하한**이지 상한이 아닙니다.",
        "",
    ]
    lines += [f"- {heading}: {chars:,}자 이상" for heading, chars in budgets.items()]
    lines += [
        "",
        "쓸 말이 없으면 분량을 줄이지 말고, **무엇을 확인하지 못했는지와 그것이 판단에",
        "남기는 한계**를 그 자리에 쓰세요. 없는 내용으로 칸을 채우지는 마세요.",
    ]
    return "\n".join(lines)


__all__ = ["SAFETY_MAX_CHARS", "build_depth_policy", "render_length_contract"]
