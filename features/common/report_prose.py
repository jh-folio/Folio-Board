"""보고서 산문을 재는 공용 도구 — 섹션 나누기, 유보 표현, 발언 귀속.

딥 리서치에서 만들어 쓰던 것을 기업분석도 쓰게 되면서 `features/common/`으로 올렸다.
어느 기능도 다른 기능의 모듈을 직접 import하지 않는다(§13).

여기 있는 것은 **보고서 종류와 무관한 것**뿐이다. 어떤 섹션이 필수인지, 분량 하한이
얼마인지, 어떤 결함이 차단인지는 각 기능의 계약이 정한다.
"""
from __future__ import annotations

import re

# 태그 이름을 특정하지 않는다. 모델이 새 이름을 만들어 쓰면 분량 계산에 주석이 섞인다.
_HIDDEN_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# 접두 있는 ID(ev_/market_/macro_/web_ — 브리핑 evidence, 웹 조회 인용)와 접두 없는
# 16자 hex(로컬 문서 ID, `research_library/indexing`·RSS writer·
# source_ledger_from_items()가 기존 id를 보존할 때 전부 이 형태 — 실측: 기업분석
# 로컬 출처 태그가 전부 이 꼴이었는데 접두만 찾는 옛 정규식이 전부 놓쳐 섹션마다
# 정확히 하나씩 단 보고서도 `unlinked_section`·`low_source_linkage`로 오판되고
# 품질 점수가 69점에 묶였다) 둘 다 받는다.
SOURCE_ID_RE = re.compile(r"(?:ev|market|macro|web)_[A-Za-z0-9_.\-]+|\b[0-9a-f]{16}\b")

# 유보 표현. 제안서 §13 Rule 3의 목록에 실측에서 실제로 나온 것을 더했다.
HEDGE_PHRASES = (
    "수 있다", "수 있으", "수 있는", "가능성이 있다", "가능성을 배제",
    "단정하기 어렵", "판단하기 어렵", "확인하기 어렵",
    "함께 봐야", "함께 볼", "점검해야", "구분해야", "주의해야",
    "것으로 보인다", "보이지만",
)
# 이 밀도를 넘으면 판단이 아니라 회피다. 실측 기준: 문제로 지적된 보고서가
# 천자당 3.07~3.34회였고 그중 `수 있다` 하나가 23회였다.
HEDGE_DENSITY_LIMIT = 2.5
HEDGE_REPEAT_MIN = 10
HEDGE_REPEAT_DENSITY = 1.5
# 발언에 붙는 직함. 중앙은행 인사는 원문이 영문이고 본문은 한국어라 이름을 대조할 수
# 없어("Jerome H. Powell" vs "파월") 직함이 유일한 실마리다.
#
# `CFO`는 **넣지 않는다.** 기업분석 본문에서 그 세 글자는 대부분 영업현금흐름이다
# (실측: `CFO/영업이익 92.1%`, `장기부채/CFO 161.9%`). 직함으로 세면 재무표만 있어도
# 귀속이 통과한다. 기업 임원은 본문이 라틴 이름을 그대로 쓰는 편이라 이름으로 잡는다.
SPEAKER_ROLE_WORDS = (
    "의장", "총재", "이사", "장관", "위원", "대표", "사장", "회장", "부사장",
    "최고경영자", "최고재무책임자", "CEO",
)
# 라틴 이름에서 성(姓)만 뽑는다. 본문이 이름 전체를 옮겨 적지 않아도 성은 남는다.
# 첫 글자 **뒤에 소문자**가 와야 이름이다 — 그 조건이 없으면 `Colette Kress·CFO`의
# 성이 `CFO`가 되고, 재무표의 영업현금흐름만 있어도 귀속이 통과한다.
_LATIN_NAME = re.compile(r"[A-Z][a-z][a-zA-Z'\-]*")


def canonical_heading(value: str) -> str:
    """번호 접두를 뗀 헤딩. 실제 저장 보고서는 `## 1. Executive Summary`처럼
    번호를 붙이므로, usage 키를 원문 그대로 두면 검증의 정규화 이름 조회가 한 번도
    맞지 않아 모든 보고서의 섹션 연결이 0이 된다(리뷰 실측)."""
    return re.sub(r"^\d+\.\s*", "", str(value or "").strip())


def visible_markdown(markdown: str) -> str:
    """독자가 보는 본문. 숨김 주석(근거 태그)을 걷어낸다."""
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    return _HIDDEN_COMMENT.sub("", text).strip()


def visible_character_count(markdown: str) -> int:
    return len(visible_markdown(markdown))


def split_sections(markdown: str) -> list[dict]:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    rows = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        rows.append({
            "heading": canonical_heading(match.group(1)),
            "rawHeading": match.group(1).strip(),
            "body": text[match.end():end].strip(),
        })
    return rows


def defect(category: str, code: str, severity: int, *, section: str = "", fixable: bool = True) -> dict:
    return {"category": category, "code": code, "severity": severity, "section": section, "fixable": fixable}


def _body_outside(markdown: str, exempt) -> str:
    names = tuple(exempt or ())
    return "".join(
        str(row.get("body") or "")
        for row in split_sections(visible_markdown(markdown))
        if not any(name in str(row.get("heading") or "") for name in names)
    )


def hedge_stats(markdown: str, *, exempt=()) -> dict:
    """유보 표현의 밀도와 한 표현의 쏠림. 둘 다 봐야 한다 —
    총량이 적어도 한 표현만 스무 번 나오면 글이 같은 자리에서 계속 멈춘다.

    `exempt`는 유보가 있어야 마땅한 섹션이다(데이터 한계 서술). 거기까지 세면
    성실한 보고서가 벌을 받는다.
    """
    body = _body_outside(markdown, exempt)
    length = len(body)
    counts = {phrase: body.count(phrase) for phrase in HEDGE_PHRASES}
    counts = {phrase: count for phrase, count in counts.items() if count}
    total = sum(counts.values())
    top = max(counts.items(), key=lambda row: row[1], default=("", 0))
    return {
        "chars": length,
        "total": total,
        "per1000": round((total / length * 1000) if length else 0.0, 2),
        "topPhrase": top[0],
        "topCount": top[1],
        "topPer1000": round(top[1] / length * 1000, 2) if length else 0.0,
    }


def hedgiest_section(markdown: str, *, exempt=()) -> str:
    """유보 표현이 가장 몰린 섹션. 보수가 손댈 자리를 가리킨다."""
    names = tuple(exempt or ())
    best, best_count = "", 0
    for row in split_sections(visible_markdown(markdown)):
        heading = str(row.get("heading") or "")
        if any(name in heading for name in names):
            continue
        body = str(row.get("body") or "")
        count = sum(body.count(phrase) for phrase in HEDGE_PHRASES)
        if count > best_count:
            best, best_count = heading, count
    return best


def tagged_source_ids(markdown: str) -> set[str]:
    """숨김 주석 안에 적힌 근거 ID."""
    return {
        source_id
        for match in re.finditer(r"<!--(.*?)-->", str(markdown or ""), re.DOTALL)
        for source_id in SOURCE_ID_RE.findall(match.group(1))
    }


def sections_citing(markdown: str, source_ids) -> dict:
    """근거 ID별로 그것을 인용한 첫 섹션."""
    wanted = {str(source_id) for source_id in source_ids or []}
    out: dict = {}
    for row in split_sections(str(markdown or "")):
        found = set(SOURCE_ID_RE.findall(str(row.get("body") or "")))
        for source_id in wanted & found:
            out.setdefault(source_id, str(row.get("heading") or ""))
    return out


def speaker_identity(who: str) -> dict:
    """화자 문자열에서 본문과 대조할 실마리를 뽑는다.

    두 갈래를 함께 본다 — 직함은 한국어로 옮겨 적어도 남고(파월 **의장**), 라틴 이름은
    기업 임원 인용에서 본문이 그대로 옮겨 적는 편이다(실측: `Tim Archer와 CFO Doug
    Bettinger`). 어느 하나라도 본문에 있으면 화자를 밝힌 것으로 본다.
    """
    text = str(who or "")
    role = next((word for word in SPEAKER_ROLE_WORDS if word in text), "")
    names = _LATIN_NAME.findall(text)
    # 성이 이름보다 뒤에 온다. 중간 이름·이니셜은 버린다.
    name = names[-1] if names else ""
    return {"role": role, "name": name}


def unattributed_speech(markdown: str, quote_sources) -> list[str]:
    """인용한 발언 근거 중 본문이 화자를 밝히지 않은 것.

    실측: 파월·월러 발언 4건을 찾아 원장에 올렸고 본문이 그 태그를 달았는데,
    문장은 전부 "연준은 ~라고 설명했다"였고 이름은 0회였다. 누가 말했는지가 사라지면
    그것은 발언이 아니라 기관 입장이다.
    """
    rows = [row for row in quote_sources or [] if isinstance(row, dict) and row.get("sourceId")]
    if not rows:
        return []
    visible = visible_markdown(markdown)
    tagged = tagged_source_ids(markdown)
    missing = []
    for row in rows:
        source_id = str(row.get("sourceId") or "")
        clues = [str(row.get(key) or "") for key in ("role", "name")]
        clues = [clue for clue in clues if clue]
        if source_id not in tagged or not clues:
            continue
        if not any(clue in visible for clue in clues):
            missing.append(source_id)
    return missing


__all__ = [
    "HEDGE_DENSITY_LIMIT",
    "HEDGE_PHRASES",
    "HEDGE_REPEAT_DENSITY",
    "HEDGE_REPEAT_MIN",
    "SOURCE_ID_RE",
    "SPEAKER_ROLE_WORDS",
    "canonical_heading",
    "defect",
    "hedge_stats",
    "hedgiest_section",
    "sections_citing",
    "speaker_identity",
    "split_sections",
    "tagged_source_ids",
    "unattributed_speech",
    "visible_character_count",
    "visible_markdown",
]
