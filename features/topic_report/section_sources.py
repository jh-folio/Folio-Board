"""Parse hidden per-section source tags and project ledger usage."""
from __future__ import annotations

import re


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# 태그 이름도 모델이 바꿔 쓴다. 실측으로 한 보고서가 `<!-- sources: ev_015 -->`를 22개
# 썼고, 정확한 이름만 읽던 파서가 하나도 못 읽어 근거 연결이 1.00에서 0.38로 떨어졌다.
# 뜻이 같은 표기를 형식 하나로 버리지 않는다 — 정본 이름은 `folio-source-ids`다.
SOURCE_TAG_NAMES = ("folio-source-ids", "folio-sources", "source-ids", "sources")
_TAG = re.compile(
    r"<!--\s*(?:" + "|".join(SOURCE_TAG_NAMES) + r")\s*:\s*(.*?)-->",
    re.IGNORECASE | re.DOTALL,
)
# 근거 ID만으로 이뤄진 대괄호 묶음. 일반 대괄호(각주, 강조)를 삼키지 않도록
# 항목 전부가 알려진 접두사를 가질 때만 인용으로 본다.
#
# **접두사 목록은 한 곳에서 나온다.** `web`이 빠져 있던 시절, 같은 릴리즈가 만든
# `web_NNN`을 `render_lookup`이 대괄호 형식으로 가르치는데 이 정규식만 그것을 몰랐다.
# 항목 **전부**가 맞아야 하므로 `[ev_003, web_001]` 한 묶음이 통째로 버려졌다 —
# 같이 있던 `ev_003`까지 잃고, 그 섹션은 근거 없음(`unlinked_section`)이 되며
# `webSearchAudit.citedSourceIds`는 실제로 인용한 보고서를 0건으로 보고했다.
SOURCE_ID_PREFIXES = ("ev", "market", "macro", "web")
_PREFIX_GROUP = "(?:" + "|".join(SOURCE_ID_PREFIXES) + r")_[A-Za-z0-9_.\-]+"
_INLINE_CITATION = re.compile(r"\[(" + _PREFIX_GROUP + r"(?:\s*,\s*" + _PREFIX_GROUP + r")*)\]")
_SOURCE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,79}$")


def canonical_heading(value: str) -> str:
    """번호 접두를 뗀 헤딩. 실제 저장 보고서는 `## 1. Executive Summary`처럼
    번호를 붙이므로, usage 키를 원문 그대로 두면 검증의 정규화 이름 조회가 한 번도
    맞지 않아 모든 보고서의 섹션 연결이 0이 된다(리뷰 실측)."""
    return re.sub(r"^\d+\.\s*", "", str(value or "").strip())


def parse_section_source_ids(markdown: str) -> tuple[dict[str, list[str]], list[str]]:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    usage: dict[str, list[str]] = {}
    malformed: list[str] = []
    for index, match in enumerate(matches):
        heading = canonical_heading(match.group(1))
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():body_end]
        ids: list[str] = []
        # 모델은 숨김 주석 대신 본문에 `[macro_DGS10, ev_019]`처럼 쓰기도 한다.
        # 형식이 달라도 인용은 인용이다 — 세지 않으면 연결이 실제보다 낮게 나온다.
        for tag in _TAG.findall(body) + _INLINE_CITATION.findall(body):
            # 구분자는 쉼표만이 아니다. 모델이 `ev_020 ev_021`처럼 공백으로 쓰면 예전에는
            # 통째로 한 토큰이 되어 malformed로 떨어졌고, 그 섹션은 근거 연결이 0이 됐다
            # (실측: 한 보고서에서 11개 섹션 중 4개가 "연결 없음", linkage 0.56). 뜻은
            # 분명한데 형식 하나로 근거를 잃을 이유가 없다.
            for raw in re.split(r"[,\s]+", tag):
                source_id = raw.strip()
                if not source_id:
                    continue
                if _SOURCE_ID.fullmatch(source_id) is None:
                    malformed.append(source_id)
                    continue
                if source_id not in ids:
                    ids.append(source_id)
        usage[heading] = ids
    return usage, malformed


def apply_section_usage(
    markdown: str,
    source_ledger: list[dict],
    *,
    forbidden_source_ids: set[str] | None = None,
) -> tuple[list[dict], dict]:
    usage, malformed = parse_section_source_ids(markdown)
    known = {str(row.get("sourceId") or "") for row in source_ledger if str(row.get("sourceId") or "")}
    forbidden = forbidden_source_ids or set()
    unknown = sorted({source_id for ids in usage.values() for source_id in ids if source_id not in known})
    forbidden_used = sorted({source_id for ids in usage.values() for source_id in ids if source_id in forbidden})
    reverse: dict[str, list[str]] = {}
    for heading, ids in usage.items():
        for source_id in ids:
            if source_id in known and source_id not in forbidden:
                reverse.setdefault(source_id, []).append(heading)
    projected: list[dict] = []
    for source in source_ledger:
        row = dict(source)
        row["usedInSections"] = reverse.get(str(row.get("sourceId") or ""), [])
        projected.append(row)
    return projected, {
        "sectionUsage": usage,
        "malformedSourceIds": sorted(set(malformed)),
        "unknownSourceIds": unknown,
        "forbiddenSourceIds": forbidden_used,
    }


__all__ = ["apply_section_usage", "parse_section_source_ids"]
