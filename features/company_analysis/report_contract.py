"""기업분석 산출물 계약 — 섹션·분량·근거 연결을 생성 뒤에 검증한다.

지금까지 기업분석은 계약을 **프롬프트에만** 두고 산출물을 확인하지 않았다.
`style.py::REQUIRED_SECTION_HEADINGS`에 9개 섹션이 정의돼 있지만 그것을 쓰는 함수는
`validate_prompt_structure(prompt)` 하나뿐이다 — 프롬프트 파일을 검사할 뿐 생성된
보고서는 아무도 보지 않는다.

실측(저장된 4건):
- SpaceX·LAM은 `어떻게 접근할까`와 `자료 한계와 참고자료`가 통째로 없다
- 섹션 길이가 2~3배로 흔들린다(실적 1,818~4,366자, 개요 806~2,582자)
- 본문의 숨김 근거 태그가 **0개**, `sourceLedger` 필드 자체가 없다
  → `source_grounding` 0.08~0.42로 네 건 모두 최하위 항목
- `repairApplied: False`, `repairCount: 0` — 보수 패스가 한 번도 돌지 않았다

딥 리서치와 다른 점:
- 9개 섹션이 **전부 고정**이다(딥은 머리·꼬리만 고정, 본문은 계획이 정한다).
- 그래서 본문 구성 차이라는 개념이 없고, 빠지면 그대로 결함이다.

경계:
- 결함은 **차단이 아니다.** 기업분석은 딥 파이프라인 같은 후보·재시도 구조가 없어,
  차단하면 사용자가 아무것도 받지 못한다. 점수 상한과 보수 대상 지정으로 쓴다.
- 유보 면제 섹션이 딥과 다르다. 여기서는 `자료 한계와 참고자료`가 그 자리다.
"""
from __future__ import annotations

from features.common.report_prose import (
    HEDGE_DENSITY_LIMIT,
    HEDGE_REPEAT_DENSITY,
    HEDGE_REPEAT_MIN,
    defect,
    hedge_stats as _hedge_stats,
    hedgiest_section as _hedgiest_section,
    sections_citing,
    split_sections,
    tagged_source_ids,
    unattributed_speech,
    visible_character_count,
    visible_markdown,
)
from features.common.research_quality.contract_ceiling import apply_contract_ceiling
from features.company_analysis.style import REQUIRED_SECTION_HEADINGS

# 데이터 한계 서술이 그 섹션의 일이다. 거기까지 유보로 세면 성실한 보고서가 벌을 받는다.
HEDGE_EXEMPT_SECTIONS = ("자료 한계와 참고자료",)
# 근거를 인용하는 자리가 아닌 섹션. 개요는 회사 소개, 접근은 판단, 자료 한계는 메모다.
_SOURCE_EXEMPT = frozenset({"어떻게 접근할까", "자료 한계와 참고자료"})
# 섹션 연결이 이 비율 아래면 보고서 전체가 근거에 매여 있지 않다.
MIN_SOURCE_LINKAGE = 0.7


def hedge_stats(markdown: str) -> dict:
    return _hedge_stats(markdown, exempt=HEDGE_EXEMPT_SECTIONS)


def hedgiest_section(markdown: str) -> str:
    return _hedgiest_section(markdown, exempt=HEDGE_EXEMPT_SECTIONS)


def source_required_sections() -> list[str]:
    return [name for name in REQUIRED_SECTION_HEADINGS if name not in _SOURCE_EXEMPT]


def missing_sections(markdown: str) -> list[str]:
    """계약이 요구하는데 본문에 없는 섹션.

    제목 문자열로 찾는다 — 과거 보고서가 `## 섹션 1 — 기업 개요와 사업 구조`처럼
    다른 이름을 써서 계약과 어긋난 전례가 있다.
    """
    written = {str(row.get("heading") or "") for row in split_sections(visible_markdown(markdown))}
    return [
        name for name in REQUIRED_SECTION_HEADINGS
        if not any(name in heading for heading in written)
    ]


def validate_company_report(
    markdown: str,
    *,
    depth_policy: dict | None = None,
    source_ledger: list[dict] | None = None,
    quote_sources: list[dict] | None = None,
) -> dict:
    """결함 목록과 지표. 어느 것도 산출물을 되돌리지 않는다(§경계)."""
    text = str(markdown or "").strip()
    policy = dict(depth_policy or {})
    defects: list[dict] = []
    if not text:
        return {"defects": [defect("blocking", "empty_body", 100, fixable=False)], "metrics": {}}

    sections = split_sections(visible_markdown(text))
    by_heading = {str(row.get("heading") or ""): str(row.get("body") or "") for row in sections}

    for name in missing_sections(text):
        defects.append(defect("structure", "section_missing", 60, section=name))

    # 분량 — 섹션 예산은 하한이다. 채울 말이 없으면 줄이지 말고 무엇을 확인하지
    # 못했는지를 그 자리에 쓴다.
    budgets = policy.get("sectionBudgets") or {}
    for heading, budget in budgets.items():
        body = by_heading.get(heading)
        if body is None or not budget:
            continue
        if len(body) < int(budget) * 0.7:
            defects.append(defect("depth", "thin_section", 35, section=heading))
    total = visible_character_count(text)
    recommended_min = int(policy.get("recommendedMinChars") or 0)
    safety_max = int(policy.get("safetyMaxChars") or 0)
    if recommended_min and total < recommended_min:
        defects.append(defect("depth", "below_recommended_length", 45))
    if safety_max and total > safety_max:
        defects.append(defect("depth", "above_safety_length", 45))

    # 근거 연결 — 어느 문장이 어느 자료에서 왔는지.
    known = {str(row.get("sourceId") or "") for row in source_ledger or [] if row.get("sourceId")}
    required = [name for name in source_required_sections() if name in by_heading]
    linked = 0
    for name in required:
        tagged = tagged_source_ids(_raw_section(text, name))
        if tagged:
            linked += 1
            unknown = sorted(tagged - known) if known else []
            if unknown:
                defects.append(defect("evidence", "unknown_source_tag", 40, section=name))
        else:
            defects.append(defect("evidence", "unlinked_section", 35, section=name))
    # 잴 섹션이 하나도 없으면 **재지 못한 것**이다. 1.0으로 두면 계약이 자기 섹션을
    # 못 찾은 보고서가 근거 연결 만점으로 보고된다(실측: 옛 제목을 쓴 3건이 그랬다).
    linkage = round(linked / len(required), 2) if required else None
    if linkage is not None and linkage < MIN_SOURCE_LINKAGE:
        defects.append(defect("evidence", "low_source_linkage", 70))

    # 품질 평가가 찾는 것을 계약도 본다. 네 건 모두 같은 자리에서 점수를 잃었는데
    # 재료가 없어서가 아니라 쓰라고 한 적이 없어서였다.
    visible = visible_markdown(text)
    if not any(marker in visible for marker in _SCOPE_MARKERS):
        defects.append(defect("structure", "scope_undefined", 40, section=REQUIRED_SECTION_HEADINGS[0]))
    scenario_body = next(
        (body for heading, body in by_heading.items() if _SCENARIO_SECTION in heading), "",
    )
    if scenario_body and not any(word in scenario_body for word in _CONDITION_WORDS):
        defects.append(defect("depth", "scenario_not_conditional", 35, section=_SCENARIO_SECTION))

    # 내부 용어 노출 — 상태 관리에 쓰는 말이 독자에게 가면 안 된다.
    leaked = sorted({term for term in INTERNAL_TERMS if term in visible})
    if leaked:
        defects.append(defect(
            "style", "internal_term_leak", 35,
            section=next((h for h in by_heading if any(t in by_heading[h] for t in leaked)), ""),
        ))

    # 문체 — 재는 것은 둘뿐이다.
    hedges = hedge_stats(text)
    if hedges["per1000"] > HEDGE_DENSITY_LIMIT:
        defects.append(defect("style", "hedge_overuse", 40, section=hedgiest_section(text)))
    if hedges["topCount"] >= HEDGE_REPEAT_MIN and hedges["topPer1000"] > HEDGE_REPEAT_DENSITY:
        defects.append(defect("style", "hedge_repetition", 35, section=hedgiest_section(text)))
    unattributed = unattributed_speech(text, quote_sources)
    citing = sections_citing(text, unattributed)
    for source_id in unattributed[:3]:
        defects.append(defect("evidence", "speech_unattributed", 40, section=citing.get(source_id, "")))

    return {
        "defects": defects,
        "metrics": {
            "chars": total,
            "sectionCount": len(sections),
            "sourceLinkage": linkage,
            "hedgePer1000": hedges["per1000"],
            "majorDefectCount": sum(1 for row in defects if int(row.get("severity") or 0) >= 40),
        },
    }


# 품질 평가가 찾는 것들. 네 건 모두 같은 자리에서 점수를 잃었는데, 재료가 없어서가
# 아니라 **쓰라고 한 적이 없어서**다(실측: 범위 선언 0/4건, 시나리오 조건어 0회).
_SCOPE_MARKERS = ("분석 범위", "질문 정의", "포함 범위", "제외 범위")
# 품질 평가기(`research_quality/evaluator.py`)가 세는 낱말 그대로다. 여기서 넓히면
# 계약은 통과시키고 점수는 안 오르는 표현이 생기고, 아래 예시가 그런 말을 가르치면
# 모델은 시킨 대로 쓰고도 벌을 받는다(실제로 `밑돌면`으로 쓸 뻔했다).
_CONDITION_WORDS = ("넘으면", "아래로", "위로", "이상", "이하", "돌파", "하회", "상회", "되면", "라면", "초과", "미만")
_SCENARIO_SECTION = "성장 전망과 체크포인트"
# 내부 상태 관리에 쓰는 말. 최종 본문은 독자의 말로 쓴다.
# `evidence`·`thesis`는 한국어 문장 안에서도 그대로 쓰이므로 함께 잡는다.
INTERNAL_TERMS = (
    "data gap", "data_gap", "dataGap",
    "resolved", "partial", "unresolved",
    "comparable_context", "official_financials",
    "Business implication", "Valuation implication",
    "thesis", "Thesis", "trigger", "Trigger",
)


def render_quality_requirements() -> str:
    """생성 컨텍스트에 실을 서술 요구. 원칙이 아니라 **어디에 무엇을** 쓸지 지시한다."""
    return "\n".join([
        "## 이 보고서가 반드시 담아야 할 것",
        "",
        f"1. **분석 범위** — `{REQUIRED_SECTION_HEADINGS[0]}` 안에 이 보고서가 다루는 것과",
        "   **다루지 않는 것**을 한 문단으로 밝히고, 그 문단을 `분석 범위:`로 시작합니다.",
        "   예: \"분석 범위: 이 분석은 본업 수익성과 밸류에이션을 다루며, 소송·규제 리스크의",
        "   법률적 판단과 단기 수급은 다루지 않습니다.\"",
        f"2. **조건형 시나리오** — `{_SCENARIO_SECTION}`에는 근거 있는 수치 조건 또는 확인 가능한 사건 조건을 씁니다.",
        "   관찰할 변화, 확인 자료나 시점, 판단에 미치는 의미를 연결합니다. 수치 기준은 출처를 밝히고 임의로 만들지 않습니다.",
        "   예: \"다음 실적 공시에서 신규 공장 가동이 연기된 것으로 확인되면 매출 확대 시점의 가정을 재검토합니다.\"",
        "   \"업황이 좋아지면\"처럼 확인 기준이 모호한 조건은 피합니다.",
        "   체크포인트 표의 칸도 방향만 적지 말고 조건으로 씁니다: \"전년 수준으로 복귀\"가 아니라",
        "   \"원가율이 전년 수준(66.5%) 위로 올라가면\", \"한 자릿수로 둔화\"가 아니라 \"한 자릿수가 되면\".",
        "3. **섹션은 자기 몫만** — 같은 쟁점을 여러 섹션에서 연결하되 각 섹션의 새 근거·의미·반대 설명을 더합니다.",
        "   이미 설명한 결론은 짧게 참조하고 같은 설명을 반복하지 않습니다.",
        "4. **내부 용어를 본문에 쓰지 마세요.** 아래는 상태 관리용 말이지 독자의 말이 아닙니다:",
        "   " + ", ".join(f"`{term}`" for term in INTERNAL_TERMS[:10]),
        "   \"자료 한계\"·\"확인되지 않음\"·\"판단이 바뀌는 조건\"처럼 한국어로 풀어 쓰고,",
        "   표의 상태 칸도 `partial`이 아니라 \"일부 확인\"처럼 적습니다.",
    ])


def render_section_retry(missing: list[str]) -> str:
    """골격이 어긋난 초안을 다시 쓰게 하는 지시.

    실패한 초안을 되돌려 주지 않는다 — 앵커가 되어 같은 실수를 되풀이한다. 무엇이
    빠졌는지와 써야 할 제목만 짚는다.
    """
    if not missing:
        return ""
    return "\n".join([
        "## 다시 작성 요청",
        "직전 산출물이 아래 섹션을 빠뜨렸거나 다른 제목으로 썼습니다. 같은 자료로 처음부터",
        "다시 쓰되, **아래 아홉 개 제목을 이 순서대로 H2(`## `)로 하나씩 모두** 쓰세요.",
        "제목을 바꾸거나 번호를 붙이거나 합치지 마세요.",
        "",
        *[f"- {name}" for name in REQUIRED_SECTION_HEADINGS],
        "",
        "이번에 빠진 것: " + ", ".join(missing),
    ])


def render_source_contract(source_ledger: list[dict] | None) -> str:
    """생성 컨텍스트에 실을 근거 목록과 태그 규칙.

    태그가 없으면 어느 문장이 어느 자료에서 왔는지 아무도 모른다(실측: 저장된 보고서
    4건 모두 숨김 태그 0개, `source_grounding` 0.08~0.42). 인용할 ID를 먼저 보여 주고,
    그 자리에서 형식을 지시한다 — 규칙만 주면 무엇을 인용할지 알 수 없다.
    """
    rows = [row for row in source_ledger or [] if row.get("sourceId")]
    if not rows:
        return ""
    lines = [
        "## 근거 인용 (필수)",
        "아래가 이 보고서가 인용할 수 있는 자료 전부입니다. 각 섹션 **끝**에 그 섹션이",
        "실제로 쓴 근거 ID를 숨김 주석으로 답니다:",
        "",
        "    <!-- folio-source-ids: ev_001, ev_004 -->",
        "",
        "- 목록에 없는 ID를 만들지 마세요. 본문에 ID를 눈에 보이게 적지도 마세요.",
        f"- 아래 섹션에는 반드시 답니다: {', '.join(source_required_sections())}",
        "- 그 섹션에서 어떤 자료도 쓰지 않았다면, 쓰지 않았다는 사실이 문제입니다.",
        "",
    ]
    for row in rows[:60]:
        title = str(row.get("title") or "")[:110]
        source = str(row.get("source") or "")
        date = str(row.get("date") or "")[:10]
        lines.append(f"- [{row['sourceId']}] {title} — {source} {date}".rstrip())
    return "\n".join(lines)


def _raw_section(markdown: str, heading: str) -> str:
    """숨김 태그를 포함한 원문 섹션. 태그를 세려면 주석이 살아 있어야 한다."""
    for row in split_sections(str(markdown or "")):
        if heading in str(row.get("heading") or ""):
            return str(row.get("body") or "")
    return ""


def apply_report_ceiling(report: dict) -> dict:
    """계약 결함의 무게를 이 보고서의 품질 점수에 반영한다.

    지금까지는 섹션이 통째로 빠져도 66점이 나왔다. 계약이 잡은 것을 점수가 읽지 않으면
    사용자는 무엇이 비었는지 모른 채 등급만 본다.
    """
    quality = (report or {}).get("quality")
    validation = (report or {}).get("contractValidation")
    if not isinstance(quality, dict) or not isinstance(validation, dict):
        return report
    report["quality"] = apply_contract_ceiling(quality, validation)
    return report


__all__ = [
    "HEDGE_EXEMPT_SECTIONS",
    "INTERNAL_TERMS",
    "MIN_SOURCE_LINKAGE",
    "hedge_stats",
    "hedgiest_section",
    "apply_report_ceiling",
    "missing_sections",
    "render_quality_requirements",
    "render_section_retry",
    "render_source_contract",
    "source_required_sections",
    "validate_company_report",
]
