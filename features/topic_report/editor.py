"""리서치 에디터 — 분석가가 사실을 정하고, 에디터는 전달 방식을 정한다.

지금 최종 생성 호출은 **분석가이면서 동시에 작가**다. 근거를 지키는 일과 읽히게 쓰는
일을 한 호출에 얹으면 모델은 안전한 쪽으로 기운다 — 실측으로 문단마다 `~일 수 있다`,
`단정하기 어렵다`가 붙고, 꼬리 섹션 넷이 같은 말을 되풀이하고, 웹에서 찾아온 파월·월러
발언이 전부 "연준은 ~라고 설명했다"로 익명화됐다.

같은 원리를 이미 확인했다. 웹 검색을 브리프 호출에 "필요하면 검색하라"로 얹는 방식은
네 번 모두 실패했고(신규 URL 0~1건), **찾기 전용 호출로 분리하자 즉시 성공했다**
(사실 12건·발언 6건). 찾기와 쓰기가 그랬듯 분석과 서술도 나눈다.

에디터는 새 사실을 만들 수 없다. 그리고 **그 금지를 프롬프트가 아니라 코드가 집행한다** —
이 프로젝트에서 반복 확인한 것은 프롬프트가 부탁이지 제한이 아니라는 사실이다. 편집본은
원문과 대조해 새 수치·새 근거 ID·반론 축소·섹션 누락·분량 급감을 검사하고, 하나라도
걸리면 편집본을 버리고 초안을 그대로 쓴다(보고서를 죽이지 않는다).
"""
from __future__ import annotations

import re
from collections.abc import Callable

from features.topic_report.depth_policy import visible_character_count, visible_markdown
from features.topic_report.report_contract import hedge_stats, split_sections
from features.topic_report.section_sources import SOURCE_TAG_NAMES

EditorCall = Callable[[str, str], str]

# 편집이 이보다 더 줄이면 압축이 아니라 삭제다.
MIN_LENGTH_RATIO = 0.85
# 이보다 더 늘리면 편집이 아니라 집필이다. 실측으로 초안 5,569자가 편집본 13,415자로
# 나왔고(+141%), 새 수치·새 ID가 없어 검사를 통과했지만 근거 없는 산문이 채워져
# `unlinked_section` 7건이 남았다. 초안이 짧은 것은 보수 패스가 다룰 일이다.
MAX_LENGTH_RATIO = 1.25
# 계약 한계(2.5)보다 낮게 겨눈다. 한계에 딱 맞추라고 하면 넘긴 채로 끝난다.
_HEDGE_GOAL_PER_1000 = 2.0
_COUNTER_SECTION = "반론과 리스크"
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SOURCE_ID = re.compile(r"\b((?:ev|market|macro|web)_[A-Za-z0-9_.\-]+)\b")
_TAG = re.compile(
    r"<!--\s*(?:" + "|".join(re.escape(name) for name in SOURCE_TAG_NAMES) + r")\s*:(.*?)-->",
    re.IGNORECASE | re.DOTALL,
)


PROMPT = """당신은 리서치 에디터다. 아래 초안을 **다시 쓰지 말고 다듬어라.**
분석은 이미 끝났다. 당신이 정하는 것은 사실이 아니라 전달 방식이다.

절대 금지(코드가 검사한다. 어기면 편집본은 통째로 버려진다):
- 새 숫자를 넣지 마라. 초안에 없는 수치는 하나도 추가할 수 없다.
- 새 근거 ID를 넣지 마라. 각 섹션 끝의 `<!-- folio-source-ids: ... -->` 주석은
  **그대로 두어라**. 지우거나 옮기거나 ID를 바꾸지 마라.
- 반대 근거와 반론을 지우지 마라. 확신을 높이는 방향으로 고치지 마라.
- 섹션 제목을 바꾸거나, 합치거나, 빼지 마라. 순서도 그대로다.
- 전체 분량을 줄이지 마라. 이것은 압축 작업이지 요약 작업이 아니다.
- **분량을 크게 늘리지도 마라.** 없는 분석을 채워 넣는 것은 편집이 아니다.
  초안이 짧으면 짧은 대로 두어라 — 그것은 당신이 고칠 문제가 아니다.

할 일:
- **결론을 먼저 쓴다.** "여러 요인을 고려할 때 A일 가능성이 있으나 B도 배제할 수 없다"를
  "현재로서는 A가 더 설득력 있다. 다만 B를 배제하기에는 데이터가 부족하다"로 바꾼다.
- **caveat를 압축한다.** 같은 불확실성이 여러 번 나오면 가장 중요한 한 곳에만 남긴다.
  한 문단에 유보 표현은 원칙적으로 한 번이다. 불확실성을 **없애지 말고 모아라.**
- **반복을 통합한다.** 같은 판단이 여러 섹션에서 되풀이되면 한 곳에서 제대로 말하고
  나머지는 짧게 참조한다.
- **발언은 실명과 시점을 살린다.** "연준은 ~라고 설명했다"처럼 뭉개지 말고,
  근거에 이름과 날짜가 있으면 "파월 의장은 2022년 3월 기자회견에서 ~라고 말했다"로 쓴다.
- **문장 길이에 변화를 준다.** 짧은 단언 → 설명 문단 → 짧은 마무리. 모든 문장이
  같은 길이면 읽는 사람은 어디가 중요한지 알 수 없다.
- **메타 문장을 지운다.** "이 섹션에서는 ~을 살펴본다", "앞서 언급했듯이" 같은
  글에 대한 글은 뺀다. 그 자리에 내용을 쓴다.
- 문장 사이의 논리를 이어라. 조각이 나열되지 않게 연결어와 이행 문장을 쓴다.

편집한 Markdown 전문만 출력하라. 설명·머리말·코드펜스를 붙이지 마라."""


def _numbers(text: str) -> list[str]:
    return [match.group(0).replace(",", "") for match in _NUMBER.finditer(text or "")]


def _normalized(text: str) -> str:
    return (text or "").replace(",", "")


def _numeric_value(number: str) -> float | None:
    try:
        return float(number)
    except (TypeError, ValueError):
        return None


def new_numbers(original: str, edited: str) -> list[str]:
    """편집본에만 있는 수치. 초안 어디에도 없는 숫자는 지어낸 것이다.

    **부분 문자열로 찾으면 안 된다.** 예전에는 초안 전체를 한 문자열로 두고
    `number in haystack`으로 물었는데, 그러면 더 긴 숫자 안에 우연히 들어 있는 숫자가
    전부 통과한다 — 실측으로 초안에 `31,458.42`가 있으면 지어낸 `8.4%`가 위반으로 잡히지
    않았다(`8.4` ⊂ `31458.42`). 12,000자 보고서에서는 짧은 수치 대부분이 그렇게 통과하고,
    편집본은 그대로 Canonical 본문이 된다. 이 모듈의 docstring은 그 금지를 프롬프트가
    아니라 **코드가 집행한다**고 말한다.

    표기 변형(7.0% → 7%)까지 위반으로 잡으면 정당한 편집이 막히므로, 문자열이 다르면
    수치로 한 번 더 견준다.
    """
    original_numbers = set(_numbers(visible_markdown(original)))
    original_values = {value for value in (_numeric_value(row) for row in original_numbers) if value is not None}
    seen = set()
    out: list[str] = []
    for number in _numbers(visible_markdown(edited)):
        if number in seen:
            continue
        if number in original_numbers:
            continue
        value = _numeric_value(number)
        if value is not None and value in original_values:
            continue
        seen.add(number)
        out.append(number)
    return out


def _tagged_ids(text: str) -> set[str]:
    return {
        source_id
        for match in _TAG.finditer(text or "")
        for source_id in _SOURCE_ID.findall(match.group(1))
    }


def _counter_evidence_size(markdown: str) -> tuple[int, int]:
    """반론 섹션의 (글자 수, 근거 태그 수). 확증편향 방지 장치가 줄었는지 본다.

    **원문에서 센다.** visible_markdown은 주석을 지우므로 그 위에서 태그를 세면 언제나
    0이고, 근거가 통째로 빠져도 검사가 걸리지 않는다. 글자 수만 주석을 뺀 값으로 센다.
    """
    for row in split_sections(str(markdown or "")):
        if _COUNTER_SECTION in str(row.get("heading") or ""):
            body = str(row.get("body") or "")
            return len(visible_markdown(body)), len(_SOURCE_ID.findall(body))
    return 0, 0


def _headings(markdown: str) -> list[str]:
    return [str(row.get("heading") or "") for row in split_sections(visible_markdown(markdown))]


def check_edit(original: str, edited: str) -> list[str]:
    """편집본이 지켜야 할 계약. 위반 목록을 돌려주며 비어 있으면 채택 가능하다."""
    violations: list[str] = []
    if not str(edited or "").strip():
        return ["editor_empty_output"]
    if _headings(edited) != _headings(original):
        violations.append("editor_changed_sections")
    added = new_numbers(original, edited)
    if added:
        violations.append("editor_added_numbers:" + ",".join(added[:5]))
    lost_ids = _tagged_ids(original) - _tagged_ids(edited)
    if lost_ids:
        violations.append("editor_dropped_source_ids:" + ",".join(sorted(lost_ids)[:5]))
    if _tagged_ids(edited) - _tagged_ids(original):
        violations.append("editor_added_source_ids")
    before_chars, before_tags = _counter_evidence_size(original)
    after_chars, after_tags = _counter_evidence_size(edited)
    # 반론은 확증편향 방지의 집행 장치다. 에디터가 다듬다 줄이면 그 장치가 약해진다.
    if before_chars and (after_chars < before_chars * MIN_LENGTH_RATIO or after_tags < before_tags):
        violations.append("editor_weakened_counterevidence")
    before_len = visible_character_count(original)
    after_len = visible_character_count(edited)
    if before_len and after_len < before_len * MIN_LENGTH_RATIO:
        violations.append("editor_shortened_report")
    if before_len and after_len > before_len * MAX_LENGTH_RATIO:
        violations.append(f"editor_expanded_report:{after_len}/{before_len}")
    return violations


def hedge_target(markdown: str) -> str:
    """유보 표현을 **몇 회로** 줄일지 숫자로 준다.

    원칙만 준 세 번의 편집에서 유보가 한 번도 줄지 않았다(실측 천자당 1.83 → 그대로,
    2.58, 3.42). 이 프로젝트에서 두 번 확인한 것과 같은 패턴이다 — 웹 검색도 "필요하면
    하라"는 허가로는 움직이지 않았고 "이것을 찾아라"는 과제를 주자 곧바로 했다.
    원칙은 지침이고 숫자는 과제다.
    """
    stats = hedge_stats(markdown)
    if not stats["total"] or stats["per1000"] <= _HEDGE_GOAL_PER_1000:
        return ""
    goal = max(1, int(stats["chars"] / 1000 * _HEDGE_GOAL_PER_1000))
    lines = [
        "## 유보 표현 줄이기 (이번 편집의 핵심 과제)",
        f"지금 본문의 유보 표현은 **{stats['total']}회**입니다(천자당 {stats['per1000']}).",
    ]
    if stats["topCount"] >= 5:
        lines.append(f"그중 `{stats['topPhrase']}` 하나가 **{stats['topCount']}회**입니다.")
    lines += [
        f"**{goal}회 이하로 줄이세요.** 방법은 셋입니다:",
        "1. 같은 불확실성이 여러 번 나오면 가장 중요한 한 곳에만 남기고 나머지는 지운다.",
        "2. 근거가 뒷받침하는 문장은 단언으로 바꾼다 — "
        "`A일 수 있다` → `현재 자료는 A를 가리킨다`.",
        "3. 지울 수 없는 유보는 문장 끝의 습관이 아니라 **판단의 조건**으로 쓴다 — "
        "`~할 수 있다`가 아니라 `X가 Y를 넘으면 이 판단은 약해진다`.",
        "지운 자리를 비워 두지 마세요. 그 자리에 판단이나 확인하지 못한 것을 써서 분량을 유지합니다.",
        "불확실성을 **없애는 것이 아니라 모으는 것**입니다.",
    ]
    return "\n".join(lines)


def _context(markdown: str, thesis: dict | None, budgets: dict | None) -> str:
    claim = str(((thesis or {}).get("primaryThesis") or {}).get("claim") or "")
    blocks = [
        f"이 보고서의 핵심 판단(이미 정해졌다. 바꾸지 마라):\n{claim}" if claim else "",
        # 예산을 주면 그 하한까지 채우려 하고, 그러면 확장 상한에 걸려 통째로 버려진다.
        # 분량은 보수 패스의 일이다. 여기서는 줄이지 말라는 것만 말한다.
        "분량은 지금 수준을 유지하세요. 채우거나 덧붙이는 것은 당신의 일이 아닙니다." if budgets else "",
        hedge_target(markdown),
        "## 편집할 초안\n" + str(markdown or ""),
    ]
    return "\n\n".join(block for block in blocks if block)


def edit_report(
    markdown: str,
    *,
    run_call: EditorCall,
    thesis: dict | None = None,
    section_budgets: dict | None = None,
) -> dict:
    """초안을 다듬는다. 계약을 어기면 초안을 그대로 돌려준다."""
    original = str(markdown or "")
    if not original.strip():
        return {"markdown": original, "status": "skipped", "violations": []}
    try:
        raw = run_call(PROMPT, _context(original, thesis, section_budgets))
    except Exception:  # noqa: BLE001 - 편집 실패가 보고서를 죽이지 않는다
        return {"markdown": original, "status": "unavailable", "violations": []}
    edited = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", str(raw or "").strip(), flags=re.IGNORECASE | re.DOTALL)
    violations = check_edit(original, edited)
    measured = {
        "charsBefore": visible_character_count(original),
        "charsAfter": visible_character_count(edited),
        # 에디터가 유보를 줄였는지는 이 둘을 나란히 두어야 안다. 남기지 않으면
        # 초안이 원래 낮았던 것과 구분되지 않는다.
        "hedgeBefore": hedge_stats(original)["per1000"],
        "hedgeAfter": hedge_stats(edited)["per1000"],
    }
    if violations:
        # 거부해도 길이는 남긴다. 0/0으로 두면 무엇이 거부됐는지 기록이 말하지 못한다.
        return {"markdown": original, "status": "rejected", "violations": violations, **measured}
    return {"markdown": edited, "status": "applied", "violations": [], **measured}


def editor_summary(result: dict) -> dict:
    row = result or {}
    return {
        "status": str(row.get("status") or "skipped"),
        "violations": list(row.get("violations") or []),
        "charsBefore": int(row.get("charsBefore") or 0),
        "charsAfter": int(row.get("charsAfter") or 0),
        "hedgeBefore": float(row.get("hedgeBefore") or 0.0),
        "hedgeAfter": float(row.get("hedgeAfter") or 0.0),
    }


__all__ = [
    "MAX_LENGTH_RATIO",
    "MIN_LENGTH_RATIO",
    "PROMPT",
    "check_edit",
    "hedge_target",
    "edit_report",
    "editor_summary",
    "new_numbers",
]
