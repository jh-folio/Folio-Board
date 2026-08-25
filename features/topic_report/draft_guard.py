"""초안이 못 쓸 물건이면 **쓰기만** 한 번 더 시킨다.

딥 실행에서 값비싼 것은 쓰기가 아니라 그 앞이다 — 근거 팩, 웹 조회(최대 4회),
축 브리프(최대 8회), 논지 선정(1회). 그런데 초안 생성은 한 번뿐이고 재시도 경로가
없어서, 마지막 쓰기 한 번이 어긋나면 앞의 모든 것이 함께 버려진다.

실측(같은 질문 4회):
- 1회차 14,912자, 계약 OK
- 2회차 **필수 섹션 누락으로 잡 실패** — 9분을 쓰고 아무것도 남기지 못했다
- 3회차 13,541자, 계약 OK
- 4회차 **5,569자 스텁** — 하한 12,000의 46%

같은 질문·같은 코드인데 절반이 못 쓸 초안이었다. 모델 편차는 없앨 수 없지만, 이미
만들어 둔 컨텍스트로 쓰기만 한 번 더 시키는 비용은 앞 작업 전체에 비하면 작다.

경계:
- **재시도는 한 번이다.** 반복 재작성 루프를 만들지 않는다(§Quality Generation 계약).
- 판정은 **차단 사유와 명백한 스텁**만 본다. 문체·근거 연결처럼 보수 패스가 다룰 것은
  여기서 보지 않는다 — 여기서 걸러 버리면 보수가 할 일을 재생성이 대신하게 된다.
- 재시도가 더 나쁘면 처음 것을 쓴다. 나쁜 초안이라도 없는 것보다 낫다.
- 실패한 초안을 되돌려 주지 않는다. 앵커가 되어 같은 실수를 되풀이한다.
"""
from __future__ import annotations

from features.topic_report.depth_policy import visible_character_count, visible_markdown
from features.topic_report.report_contract import (
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
    split_sections,
)

# 하한의 이 비율 아래면 짧은 보고서가 아니라 스텁이다. 보수 패스는 섹션 3개를 두 번
# 손볼 뿐이라 절반짜리 초안을 되살리지 못한다.
MIN_DRAFT_RATIO = 0.6


def draft_problems(markdown: str, *, min_chars: int = 0) -> list[str]:
    """다시 쓰게 할 만한 사유. 보수 패스가 다룰 것은 여기 넣지 않는다."""
    text = str(markdown or "").strip()
    if not text:
        return ["draft_empty"]
    problems: list[str] = []
    headings = [str(row.get("heading") or "") for row in split_sections(visible_markdown(text))]
    head, tail = list(REPORT_HEAD_SECTIONS), list(REPORT_TAIL_SECTIONS)
    if len(headings) < len(head) + len(tail) or headings[: len(head)] != head or headings[-len(tail):] != tail:
        problems.append("draft_sections_missing")
    if min_chars and visible_character_count(text) < min_chars * MIN_DRAFT_RATIO:
        problems.append("draft_stub")
    return problems


def retry_directive(problems: list[str], *, min_chars: int, sections: list[str]) -> str:
    """무엇이 잘못됐는지 짚어 다시 쓰게 한다. 실패한 초안은 주지 않는다."""
    lines = ["## 다시 작성 요청", "직전 산출물이 아래를 어겨 폐기했습니다. 같은 자료로 처음부터 다시 쓰세요."]
    if "draft_empty" in problems:
        lines.append("- 본문이 비어 있었습니다.")
    if "draft_sections_missing" in problems:
        lines.append(
            "- **고정 섹션이 빠졌습니다.** 아래 제목을 이 순서대로 H2(`## `)로 하나씩 모두 쓰세요. "
            "제목을 바꾸거나 합치지 마세요: " + " | ".join(sections)
        )
        lines.append("- 마지막 `## Source & Data Notes`까지 반드시 쓰고 끝내세요. 중간에 멈추지 마세요.")
    if "draft_stub" in problems:
        lines.append(
            f"- **분량이 하한에 크게 못 미쳤습니다**(보이는 본문 {min_chars:,}자가 하한). "
            "섹션 예산은 채워야 할 하한이며, 쓸 말이 없으면 분량을 줄이지 말고 "
            "무엇을 확인하지 못했는지와 그것이 판단에 남기는 한계를 그 자리에 쓰세요."
        )
    return "\n".join(lines)


def better_draft(first: str, second: str, *, min_chars: int) -> tuple[str, str]:
    """두 초안 중 쓸 것을 고른다. 돌려주는 두 번째 값은 선택 사유다."""
    first_problems = draft_problems(first, min_chars=min_chars)
    second_problems = draft_problems(second, min_chars=min_chars)
    if len(second_problems) < len(first_problems):
        return second, "retry_better"
    if len(second_problems) > len(first_problems):
        return first, "retry_worse"
    # 사유 수가 같으면 더 채운 쪽. 재시도가 같은 결함을 안고 더 짧으면 얻은 것이 없다.
    if visible_character_count(second) > visible_character_count(first):
        return second, "retry_longer"
    return first, "retry_no_gain"


__all__ = ["MIN_DRAFT_RATIO", "better_draft", "draft_problems", "retry_directive"]
