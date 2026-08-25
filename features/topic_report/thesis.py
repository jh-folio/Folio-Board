"""핵심 논지 선정 — 축별 발견을 하나의 판단으로 모은다.

축별 브리프가 다섯 개 모이면 축마다 좋은 발견이 있지만, 본문 생성은 그것을 **병렬로**
늘어놓는다. 실측으로 마지막 보고서는 인플레이션 → 장기금리 → 엔캐리 → 정책 신뢰 →
한국 시장을 차례로 다루고 끝났고, 독자는 "그래서 지금 가장 타당한 판단이 무엇인가"를
알 수 없었다. 꼬리 섹션 넷이 같은 메시지를 되풀이한 것도 중심이 없기 때문이다.

그래서 본문을 쓰기 **전에** 한 번 멈춰, 지금 근거가 가장 강하게 지지하는 결론 하나를
고른다. 이 단계의 핵심은 나열을 금지하는 것이다 — 가능성을 모두 적는 것은 판단이
아니라 판단의 회피다.

경계:
- 새 사실을 만들지 않는다. 논지는 축 브리프가 이미 말한 것에서만 나온다(§5 원칙 4).
- sourceId는 축이 실제로 본 근거와 대조해 걸러낸다. 브리프에서 쓰는 방식과 같다.
- confidence는 enum이다. 자유 텍스트로 확신의 세기를 정하지 않는다.
- 실패해도 보고서를 죽이지 않는다. 논지가 없으면 본문은 예전처럼 축 브리프로 쓴다.
- **반대 근거를 지우지 않는다.** 논지를 세우는 일이 확증편향의 입구가 될 수 있어,
  버린 해석과 반증 조건을 함께 남기도록 계약에 박는다(§5 원칙 3).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable

ThesisCall = Callable[[str, str], str]

CONFIDENCE_LEVELS = ("high", "medium", "low")
_MAX_SUPPORTING = 3
_MAX_REASONS = 5


def _clean_list(values, limit: int = _MAX_REASONS) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        text = " ".join(str(raw or "").split()).strip()
        if text and text not in out:
            out.append(text[:400])
        if len(out) >= limit:
            break
    return out


def _text(value, limit: int = 400) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _extract_json(text: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("thesis_json_invalid") from None
        return json.loads(raw[start:end + 1])


def known_source_ids(briefs: Iterable[dict]) -> set[str]:
    """축들이 실제로 본 근거 ID. 논지가 인용할 수 있는 범위다."""
    return {
        str(source_id)
        for brief in briefs or []
        if isinstance(brief, dict)
        for source_id in brief.get("sourceIds") or []
        if str(source_id)
    }


_PROMPT = """당신은 리서치 책임자다. 아래 축별 분석을 모두 읽고, **지금 근거가 가장 강하게
지지하는 결론 하나**를 고르라. 보고서를 쓰지 말고 판단만 돌려준다.

가장 중요한 규칙:
- **가능성을 나열하지 마라.** 여러 해석을 모두 적는 것은 판단이 아니다.
  하나를 고르고, 왜 그것이 다른 해석보다 설명력이 높은지 말하라.
- 고르지 못할 만큼 근거가 약하면 confidence를 "low"로 두되, 그래도 **하나는 고른다**.

- primaryThesis.claim: 이 보고서 전체를 관통하는 판단 한 문장. 주제 요약이 아니라
  **주장**이어야 한다. "A는 중요하다"가 아니라 "A가 아니라 B가 지금의 핵심이다" 꼴.
- because: 그 판단을 지지하는 근거를 축을 가로질러 3~5개. 각각 어느 축에서 왔는지 드러나게.
- supportingTheses: 본문이 함께 다룰 보조 판단 최대 3개. 주 논지와 겹치지 않게.
- rejectedExplanation: **버린 해석 중 가장 강했던 것**과 왜 그것이 더 약한지.
  버릴 해석이 없으면 claim을 빈 문자열로 둔다.
- whatWouldChangeThis: 이 판단이 틀렸다면 **무엇이 관측되어야 하는가**.
  "더 지켜봐야 한다"가 아니라 지표 이름·방향으로 적는다.
- confidence: high(1차 자료 또는 직접 데이터로 확인, 독립 근거 2개 이상, 반증 약함) /
  medium(근거는 있으나 대안 설명도 가능) / low(간접 근거, 데이터 부족).
- sourceIds: 제공된 축 분석에 실제로 등장한 ID만 쓴다. 없으면 빈 배열.

JSON 객체 하나만 출력하라:
{{"primaryThesis": {{"claim": "…", "because": ["…"], "sourceIds": ["ev_001"], "confidence": "medium"}}, "supportingTheses": [{{"claim": "…", "sourceIds": ["ev_002"]}}], "rejectedExplanation": {{"claim": "…", "whyWeaker": "…"}}, "whatWouldChangeThis": ["…"]}}"""


def _context(plan: dict, briefs: list[dict], material_context: str = "") -> str:
    asked = _text((plan or {}).get("topic"), limit=1200)
    blocks = [
        f"보고서가 답해야 할 질문(사용자 원문):\n{asked}" if asked else "",
        "시장·거시 자료:\n" + material_context if material_context else "",
        "## 축별 분석 결과",
    ]
    for brief in briefs:
        if not isinstance(brief, dict):
            continue
        lines = [f"### {brief.get('label', '')} (상태={brief.get('status', '')}, 근거 {brief.get('evidenceCount', 0)}건)"]
        for key, title in (
            ("findings", "발견"),
            ("numbers", "수치"),
            ("counterEvidence", "반대 근거"),
            ("competingExplanations", "다른 해석"),
            ("whatWouldChangeThis", "이 판단이 틀렸다면"),
            ("uncertainties", "확인 못 한 것"),
        ):
            values = brief.get(key) or []
            if values:
                lines.append(f"- {title}: " + " / ".join(str(v) for v in values))
        if brief.get("sourceIds"):
            lines.append("- 근거 ID: " + ", ".join(str(v) for v in brief["sourceIds"]))
        blocks.append("\n".join(lines))
    return "\n\n".join(block for block in blocks if block)


def select_thesis(
    plan: dict,
    briefs: list[dict],
    *,
    run_call: ThesisCall,
    material_context: str = "",
) -> dict:
    """축별 브리프에서 핵심 논지를 고른다. 실패하면 빈 dict를 돌려준다."""
    usable = [b for b in briefs or [] if isinstance(b, dict) and (b.get("findings") or b.get("numbers"))]
    if not usable:
        return {}
    try:
        payload = _extract_json(run_call(_PROMPT, _context(plan, usable, material_context)))
    except Exception:  # noqa: BLE001 - 논지 선정 실패가 보고서를 죽이지 않는다
        return {}
    known = known_source_ids(usable)

    def _ids(values) -> list[str]:
        # 축이 실제로 본 것만 남긴다. 모델이 지어낸 ID는 원장과 맞지 않는다.
        return [
            row for row in _clean_list(values, limit=8)
            if row in known or row.startswith(("market_", "macro_", "web_"))
        ]

    primary = payload.get("primaryThesis") if isinstance(payload.get("primaryThesis"), dict) else {}
    claim = _text(primary.get("claim"))
    if not claim:
        return {}
    confidence = str(primary.get("confidence") or "").strip().lower()
    supporting = [
        {"claim": _text(row.get("claim")), "sourceIds": _ids(row.get("sourceIds"))}
        for row in (payload.get("supportingTheses") or [])[:_MAX_SUPPORTING]
        if isinstance(row, dict) and _text(row.get("claim"))
    ]
    rejected = payload.get("rejectedExplanation") if isinstance(payload.get("rejectedExplanation"), dict) else {}
    return {
        "primaryThesis": {
            "claim": claim,
            "because": _clean_list(primary.get("because")),
            "sourceIds": _ids(primary.get("sourceIds")),
            # 결론의 세기는 enum이 소유한다. 모르는 값은 medium으로 내린다(§5 원칙 4).
            "confidence": confidence if confidence in CONFIDENCE_LEVELS else "medium",
        },
        "supportingTheses": supporting,
        "rejectedExplanation": {
            "claim": _text(rejected.get("claim")),
            "whyWeaker": _text(rejected.get("whyWeaker")),
        } if _text(rejected.get("claim")) else {},
        "whatWouldChangeThis": _clean_list(payload.get("whatWouldChangeThis")),
    }


# 확신의 세기를 문장 강도로 옮긴다. 같은 근거를 두고 어떤 보고서는 단언하고 어떤
# 보고서는 얼버무리는 것을 막는다.
_STRENGTH = {
    "high": "현재 데이터는 이것을 보여준다 — 단정형으로 쓰되 반증 조건을 함께 남긴다.",
    "medium": "현재 데이터는 이쪽에 무게를 싣는다 — 우세하다고 쓰되 대안을 배제하지 않는다.",
    "low": "경계가 필요한 수준이다 — 가능성으로 쓰고 무엇이 부족한지 밝힌다.",
}


def render_thesis(thesis: dict) -> str:
    """생성 컨텍스트에 실을 블록. 본문 전체가 이 판단을 향하게 한다."""
    primary = (thesis or {}).get("primaryThesis") or {}
    claim = str(primary.get("claim") or "")
    if not claim:
        return ""
    confidence = str(primary.get("confidence") or "medium")
    lines = [
        "=" * 60,
        "## 이 보고서의 핵심 논지",
        "아래는 축별 분석을 모아 이미 내린 판단입니다. 본문은 이 판단을 **검증하고 확장**하는",
        "글이어야 합니다. 가능성을 다시 나열하지 말고, 각 섹션이 이 논지와 어떤 관계인지가",
        "글 안에서 드러나게 쓰세요 — 다만 이 문장들을 소제목으로 만들거나 그대로 옮겨 적지 마세요.",
        "",
        f"**핵심 판단**: {claim}",
        f"**확신 수준**: {confidence} — {_STRENGTH.get(confidence, _STRENGTH['medium'])}",
    ]
    if primary.get("because"):
        lines.append("**근거**: " + " / ".join(str(v) for v in primary["because"]))
    if primary.get("sourceIds"):
        lines.append("**근거 ID**: " + ", ".join(str(v) for v in primary["sourceIds"]))
    if thesis.get("supportingTheses"):
        lines.append("")
        lines.append("**함께 다룰 보조 판단**:")
        lines.extend(f"- {row['claim']}" for row in thesis["supportingTheses"])
    rejected = thesis.get("rejectedExplanation") or {}
    if rejected.get("claim"):
        lines.append("")
        lines.append(
            f"**검토했으나 채택하지 않은 해석**: {rejected['claim']}"
            + (f" — 더 약한 이유: {rejected['whyWeaker']}" if rejected.get("whyWeaker") else "")
        )
        lines.append("이 해석은 본문에서 **지우지 말고** 반론 자리에서 다루세요.")
    if thesis.get("whatWouldChangeThis"):
        lines.append("")
        lines.append("**이 판단이 틀렸다면 관측되어야 할 것**:")
        lines.extend(f"- {v}" for v in thesis["whatWouldChangeThis"])
        lines.append("이 항목들은 체크포인트 섹션의 뼈대입니다.")
    lines.append("")
    return "\n".join(lines)


def thesis_summary(thesis: dict) -> dict:
    primary = (thesis or {}).get("primaryThesis") or {}
    if not primary.get("claim"):
        return {"status": "unavailable"}
    return {
        "status": "ok",
        "claim": str(primary.get("claim") or ""),
        "confidence": str(primary.get("confidence") or ""),
        "reasonCount": len(primary.get("because") or []),
        "supportingCount": len((thesis or {}).get("supportingTheses") or []),
        "hasRejectedExplanation": bool(((thesis or {}).get("rejectedExplanation") or {}).get("claim")),
        "falsifierCount": len((thesis or {}).get("whatWouldChangeThis") or []),
        "sourceIds": list(primary.get("sourceIds") or []),
    }


__all__ = [
    "CONFIDENCE_LEVELS",
    "known_source_ids",
    "render_thesis",
    "select_thesis",
    "thesis_summary",
]
