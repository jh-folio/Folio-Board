"""축별 분석 패스 — 하위 질문을 검색용으로만 쓰지 않고 실제로 답하게 한다.

예전 딥 리서치는 하위 질문 12개를 만들어 **검색에만** 쓰고 버렸다. 생성 컨텍스트는
질문 목록을 넣으면서 "커버리지와 남은 갭을 Source & Data Notes에 반영하라"고만 지시했고,
각 질문에 답하라는 말은 없었다. 그래서 12개 질문이 근거를 모아 오면 보고서는 그것을
가중치 15%짜리 섹션 하나에 밀어 넣어 축당 400자로 답했다(실측).

여기서는 축마다 한 번씩 모델을 불러 그 축의 질문에 답하는 짧은 브리프를 만들고,
본문 생성이 그 브리프를 뼈대로 쓴다. 축이 곧 본문 섹션이므로 브리프 하나가 섹션 하나가
된다.

경계:
- 브리프는 **근거 안에서만** 쓴다. 새 수치·새 출처를 만들지 않는다(§5 원칙 4).
- 한 축이 실패해도 보고서를 죽이지 않는다. 그 축은 `status: unavailable`로 남고
  본문 생성은 기존 근거로 진행한다 — 축 하나 때문에 수 분짜리 실행을 버리지 않는다.
- 호출 수는 축 수로 묶이고 예산이 소진되면 남은 축은 건너뛴다.
"""
from __future__ import annotations

from features.topic_report.execution import propagate_interruption

import json
import re
from collections.abc import Callable, Iterable

from features.topic_report.evidence_text import read_evidence_body

AxisCall = Callable[[str, str], str]

MAX_AXIS_CALLS = 8
_EVIDENCE_PER_AXIS = 8
_BODY_CHARS_PER_ITEM = 1200
_LIST_LIMIT = 6
# 이 개수 미만이면 그 축은 로컬 근거로 답할 수 없다고 보고 웹 보완을 의무화한다.
THIN_EVIDENCE = 3


def _clean_list(values, limit: int = _LIST_LIMIT) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        text = " ".join(str(raw or "").split()).strip()
        if text and text not in out:
            out.append(text[:400])
        if len(out) >= limit:
            break
    return out


def _extract_json(text: str) -> dict:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("axis_brief_json_invalid") from None
        return json.loads(raw[start:end + 1])


def axis_evidence(axis_key: str, question_ids: set[str], evidence_items: list[dict]) -> list[dict]:
    """그 축에 붙은 근거. 축 검색으로 들어온 것과 그 축의 질문이 데려온 것 둘 다."""
    rows = [
        item for item in evidence_items or []
        if isinstance(item, dict)
        and (
            str(item.get("axisKey") or item.get("axis") or "") == axis_key
            or str(item.get("researchQuestionId") or "") in question_ids
        )
    ]
    rows.sort(key=lambda item: (-float(item.get("relevance") or 0), str(item.get("id") or "")))
    return rows[:_EVIDENCE_PER_AXIS]


def _render_evidence(rows: list[dict]) -> str:
    lines = []
    for row in rows:
        body = read_evidence_body(str(row.get("path") or ""), limit=_BODY_CHARS_PER_ITEM)
        lines.append(
            f"[{row.get('id', '')}] {row.get('source', '')} | {str(row.get('date', ''))[:10]}\n"
            f"제목: {str(row.get('title', ''))[:200]}\n"
            f"내용: {body or str(row.get('summary') or '')[:400] or '(본문 없음 — 제목만)'}"
        )
    return "\n\n".join(lines) if lines else "(이 축에 연결된 로컬 근거가 없습니다)"


_PROMPT = """당신은 투자 리서치 분석가다. 아래 한 분석축에 대해서만 답하라.
독자는 이 분야를 처음 보는 개인 투자자다.

규칙:
- 제공된 근거와 수치 안에서만 쓴다. 없는 숫자·출처를 만들지 마라.
  단, 컨텍스트에 `## 웹 검색 사용`이 있으면 허용 목록 안에서 검색해 보완하라 —
  특히 과거 사례와 정책 당국자 발언은 로컬 자료에 거의 없다. 찾은 사실에는 URL을 남긴다.
- concept: 이 축을 이해하는 데 꼭 필요한 개념을, 배경지식 없는 사람이 읽어도 알 수 있게 설명한다.
  용어를 나열하지 말고 무엇을 뜻하는지 풀어 쓴다.
- mechanism: 그 개념이 시장에서 **어떤 순서로** 작동하는지 인과 단계로 쓴다.
  예: "A가 오르면 → B의 조달비용이 오르고 → C의 현재가치가 낮아진다".
- findings: 제공된 자료로 지금 이 축에 대해 말할 수 있는 판단.
  이 축이 **보고서 전체 질문에 어떤 답을 보태는지**가 드러나야 한다.
- 근거가 부족하면 findings에 적지 말고 uncertainties에 무엇이 없는지 적어라.
- counterEvidence는 반드시 채운다. 이 축의 판단이 틀릴 수 있는 근거다.
- competingExplanations: 같은 자료를 **다르게 설명하는** 해석. 반대 근거와 다르다 —
  반대 근거가 "어긋나는 자료"라면 이쪽은 "같은 자료의 다른 이야기"다. 최대 2개.
- whatWouldChangeThis: 지금 판단이 틀렸다면 **어떤 데이터가 보여야 하는가**.
  "더 지켜봐야 한다"가 아니라 관측 가능한 것으로 적는다(지표 이름·방향·대략의 크기).
- sourceIds는 제공된 근거 ID(ev_xxx)와 자료 ID만 쓴다.
- webSources: 웹에서 찾은 사실의 출처 URL. 검색하지 않았으면 빈 배열.

JSON 객체 하나만 출력하라:
{{"concept": ["개념 설명 문장", ...], "mechanism": ["작동 단계", ...], "findings": ["판단 문장", ...], "numbers": ["지표 = 값 (기간)", ...], "counterEvidence": ["반대 근거", ...], "competingExplanations": ["같은 자료의 다른 해석", ...], "whatWouldChangeThis": ["이 판단이 틀렸다면 보여야 할 관측", ...], "uncertainties": ["확인 못 한 것", ...], "sourceIds": ["ev_001", ...], "webSources": ["https://…"]}}"""


def _other_axes_notice(axis: dict, all_axes: list[dict]) -> str:
    """다른 섹션이 맡은 주제. 여기서 그 전개를 되풀이하지 않게 한다.

    축 브리프는 축마다 독립 호출이라 서로의 몫을 모른다. 그래서 전이 경로 축이
    가장 생생한 예시로 사례 축의 사건을 집어 오고, 사례 섹션이 같은 이야기를 다시
    한다(실측: 경로 섹션에 2021이 4회·2024가 3회, 두 사례는 각자 2,000자 넘는
    섹션을 따로 갖고 있었다).
    """
    others = [
        str(row.get("label") or "")
        for row in all_axes or []
        if str(row.get("key") or "") != str(axis.get("key") or "") and str(row.get("label") or "")
    ]
    if not others:
        return ""
    return "\n".join([
        "이 보고서의 **다른 섹션이 맡은 주제**입니다(각각 독립된 섹션으로 따로 씁니다):",
        *[f"- {label}" for label in others],
        "**그 주제를 여기서 전개하지 마세요.** 당신의 축을 설명하는 데 그 사례가 필요하면",
        "결론 한 줄만 빌려 쓰고 넘어가세요 — 전개·수치·경위는 그 섹션의 몫입니다.",
    ])


def _axis_context(
    axis: dict,
    questions: list[str],
    rows: list[dict],
    material: str,
    asked: str = "",
    web_directive: str = "",
    all_axes: list[dict] | None = None,
) -> str:
    blocks = [
        # 축만 주면 그 축을 독립 주제로 답한다. 이 축이 무엇에 봉사하는지 함께 준다.
        f"보고서 전체가 답해야 할 질문(사용자 원문):\n{asked}" if asked else "",
        f"분석축: {axis.get('label', '')}",
        "이 축이 답해야 할 질문:\n" + "\n".join(f"- {q}" for q in questions) if questions else "",
        _other_axes_notice(axis, list(all_axes or [])),
        "시장·거시 자료:\n" + material if material else "",
        web_directive or "",
        _thin_evidence_notice(axis, rows) if web_directive else "",
        "이 축의 근거:\n" + _render_evidence(rows),
    ]
    return "\n\n".join(block for block in blocks if block)


def _thin_evidence_notice(axis: dict, rows: list[dict]) -> str:
    """근거가 얇은 축에는 검색을 **의무**로 준다.

    "필요하면 보완하라"는 허가로는 모델이 움직이지 않는다 — 팩에 근거가 많으면 스스로
    충분하다고 판단한다. 몇 건뿐인지 숫자로 알려 주고 무엇을 찾을지 지정한다.
    """
    if len(rows) >= THIN_EVIDENCE:
        return ""
    return "\n".join([
        f"**이 축의 로컬 근거는 {len(rows)}건뿐입니다. 웹 검색으로 반드시 보완하세요.**",
        f"- '{axis.get('label', '')}'에 해당하는 당시의 실제 전개·수치·정책 당국자 발언을 찾으세요.",
        "- 찾은 사실은 webSources에 URL을 남기세요. URL 없는 사실은 쓰지 마세요.",
        "- 검색해도 확인되지 않으면 uncertainties에 그렇게 적으세요.",
    ])


def build_axis_briefs(
    plan: dict,
    evidence_items: list[dict],
    *,
    run_call: AxisCall,
    material_context: str = "",
    web_directive: str = "",
    max_calls: int = MAX_AXIS_CALLS,
    existing: list[dict] | None = None,
    on_brief: Callable[[dict], None] | None = None,
) -> list[dict]:
    """축마다 브리프 하나.

    `existing`은 앞선 실행이 이미 만든 브리프다(재개). 그 축은 호출을 쓰지 않고 그대로
    쓴다 — 사용량 한도로 끊긴 실행이 다시 돌 때 성공한 축을 다시 태우지 않기 위해서다.
    `on_brief`는 성공한 브리프 하나가 나올 때마다 불린다(체크포인트 저장).
    """
    axes = list((plan or {}).get("analysisAxes") or [])
    done = {
        str(row.get("axisKey") or ""): dict(row)
        for row in existing or []
        if isinstance(row, dict) and str(row.get("status") or "") == "ok"
    }
    asked = str((plan or {}).get("topic") or "").strip()
    subquestions = list(((plan or {}).get("deepResearch") or {}).get("subQuestions") or [])
    briefs: list[dict] = []
    calls = 0
    for axis in axes:
        axis_key = str(axis.get("key") or "")
        questions = [
            str(row.get("question") or "")
            for row in subquestions
            if str(row.get("axisKey") or "") == axis_key
        ] or _clean_list(axis.get("questions"), limit=3)
        question_ids = {
            str(row.get("id") or "")
            for row in subquestions
            if str(row.get("axisKey") or "") == axis_key
        }
        if axis_key in done:
            briefs.append(done[axis_key])
            continue
        rows = axis_evidence(axis_key, question_ids, evidence_items)
        brief = {
            "axisKey": axis_key,
            "label": str(axis.get("label") or ""),
            "evidenceCount": len(rows),
            "status": "unavailable",
            "concept": [],
            "mechanism": [],
            "findings": [],
            "numbers": [],
            "counterEvidence": [],
            "competingExplanations": [],
            "whatWouldChangeThis": [],
            "uncertainties": [],
            "sourceIds": [],
            "webSources": [],
        }
        if calls >= max_calls:
            brief["status"] = "skipped_budget"
            briefs.append(brief)
            continue
        calls += 1
        try:
            payload = _extract_json(
                run_call(
                    _PROMPT,
                    _axis_context(axis, questions, rows, material_context, asked, web_directive, axes),
                )
            )
        except Exception as error:
            propagate_interruption(error)
            briefs.append(brief)
            continue
        known = {str(row.get("id") or "") for row in rows}
        brief.update({
            "status": "ok",
            "concept": _clean_list(payload.get("concept"), limit=3),
            "mechanism": _clean_list(payload.get("mechanism"), limit=5),
            "findings": _clean_list(payload.get("findings")),
            "numbers": _clean_list(payload.get("numbers")),
            "counterEvidence": _clean_list(payload.get("counterEvidence")),
            "competingExplanations": _clean_list(payload.get("competingExplanations"), limit=2),
            "whatWouldChangeThis": _clean_list(payload.get("whatWouldChangeThis"), limit=4),
            "uncertainties": _clean_list(payload.get("uncertainties")),
            # 이 축이 실제로 본 근거만 남긴다. 모델이 지어낸 ID는 원장과 맞지 않는다.
            "sourceIds": [row for row in _clean_list(payload.get("sourceIds"), limit=12) if row in known or row.startswith(("market_", "macro_", "web_"))],
            "webSources": [row for row in _clean_list(payload.get("webSources"), limit=8) if row.startswith("http")],
        })
        if not brief["findings"]:
            brief["status"] = "empty"
        briefs.append(brief)
        if on_brief is not None and brief["status"] == "ok":
            on_brief(brief)
    return briefs


def render_axis_briefs(briefs: Iterable[dict]) -> str:
    """생성 컨텍스트에 실을 블록. 본문 섹션의 뼈대다."""
    rows = [row for row in briefs or [] if isinstance(row, dict)]
    if not rows:
        return ""
    lines = [
        "=" * 60,
        "## 축별 분석 (본문 섹션의 뼈대)",
        "각 항목은 같은 이름의 본문 섹션에 쓸 **재료**입니다. 목차도 아니고 문장도 아닙니다 —",
        "라벨을 소제목으로 옮기지 말고, 항목을 한 줄씩 옮겨 적지도 마세요. 필요한 것을 골라",
        "하나의 논지로 엮고, 조각 사이를 잇는 말은 직접 쓰세요. 여기 없는 수치는 새로 만들지 말고,",
        "근거가 없다고 적힌 축은 본문에서도 한계로 밝히세요.",
        "",
    ]
    for row in rows:
        lines.append(f"### {row.get('label', '')} (근거 {row.get('evidenceCount', 0)}건, 상태={row.get('status', '')})")
        for key, title in (
            ("concept", "개념"),
            ("mechanism", "작동 원리"),
            ("findings", "발견"),
            ("numbers", "수치"),
            ("counterEvidence", "반대 근거"),
            ("competingExplanations", "다른 해석"),
            ("whatWouldChangeThis", "이 판단이 틀렸다면"),
            ("uncertainties", "확인 못 한 것"),
        ):
            values = row.get(key) or []
            if values:
                lines.append(f"- {title}: " + " / ".join(str(v) for v in values))
        if row.get("webSources"):
            lines.append("- 웹 출처(본문에 URL로 인용할 것): " + ", ".join(str(v) for v in row["webSources"]))
        if row.get("sourceIds"):
            lines.append("- 근거 ID: " + ", ".join(str(v) for v in row["sourceIds"]))
        lines.append("")
    return "\n".join(lines)


def axis_brief_summary(briefs: Iterable[dict]) -> dict:
    rows = [row for row in briefs or [] if isinstance(row, dict)]
    return {
        "axisCount": len(rows),
        "okCount": sum(1 for row in rows if row.get("status") == "ok"),
        "findingCount": sum(len(row.get("findings") or []) for row in rows),
        "counterEvidenceCount": sum(len(row.get("counterEvidence") or []) for row in rows),
        "competingExplanationCount": sum(len(row.get("competingExplanations") or []) for row in rows),
        "falsifierCount": sum(len(row.get("whatWouldChangeThis") or []) for row in rows),
        "statuses": {str(row.get("axisKey") or ""): str(row.get("status") or "") for row in rows},
    }


__all__ = [
    "MAX_AXIS_CALLS",
    "axis_brief_summary",
    "axis_evidence",
    "build_axis_briefs",
    "render_axis_briefs",
]
