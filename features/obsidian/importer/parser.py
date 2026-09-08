"""Obsidian 노트 frontmatter 파싱 + 계층(hypothesis / self_generated) 분류.

PyYAML 의존 없이 Folio Board가 다루는 frontmatter 부분집합만 파싱한다:
- `key: value` 스칼라 (따옴표 가능)
- `key: [a, b]` 인라인 리스트
- 블록 리스트:
      key:
        - item
- bool (true/false), null

분류 규칙(CLAUDE.md §5, IMPLEMENTATION_PLAN Step 1):
- `company_thesis` / `market_memo` (또는 source_layer: user_synthesis) → hypothesis (import 대상)
- Folio Board(구 Folio OS)가 생성·내보낸 노트(generated_by 있음 / source_layer: primary_processed /
  reuse_as_evidence: false / 생성 타입) → self_generated (import 제외, 자기참조 금지).
  `classify()`는 `generated_by` 값을 비교하지 않고 `bool()`로만 판정하므로, 신·구 표시명
  중 어느 쪽이 적혀 있어도(과거 export가 쓴 `Folio OS`, 새 export가 쓰는 `Folio Board`)
  똑같이 self_generated로 걸린다 — 값 비교가 필요한 곳은 이 파일이 아니라
  web/src/app/deepResearchPayload.ts::parseLedger 하나뿐이다.
- 그 외 → unknown (import 제외)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 사용자 2차 사고(hypothesis)로 취급하는 노트 타입
HYPOTHESIS_TYPES = {"company_thesis", "market_memo", "topic_review", "investment_journal"}
# Folio Board(구 Folio OS)가 생성·내보낸 노트 타입 (self-reference 방지 — import 제외)
GENERATED_TYPES = {"source_note", "briefing", "company_analysis", "narrative", "thesis_delta", "topic_report"}

LAYER_HYPOTHESIS = "hypothesis"
LAYER_SELF_GENERATED = "self_generated"
LAYER_UNKNOWN = "unknown"

_FENCE = "---"


@dataclass
class ParsedNote:
    note_type: str = "unknown"
    layer: str = LAYER_UNKNOWN          # hypothesis | self_generated | unknown
    importable: bool = False            # hypothesis로 import 가능한가
    ticker: str = ""
    company: str = ""
    status: str = ""
    title: str = ""
    source_layer: str = ""
    reuse_as_hypothesis: bool = False
    reuse_as_evidence: bool = False
    tags: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    body: str = ""

    @property
    def is_hypothesis(self) -> bool:
        return self.layer == LAYER_HYPOTHESIS

    @property
    def is_self_generated(self) -> bool:
        return self.layer == LAYER_SELF_GENERATED

    @property
    def is_evidence(self) -> bool:
        # Obsidian 노트는 어떤 경우에도 evidence가 아니다(3계층 위계, 원칙 2).
        return False


# ---------------------------------------------------------------------------
# Frontmatter 파싱 (PyYAML 의존 없음)
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter_text, body) 반환. frontmatter 없으면 ('', 원문)."""
    if not text:
        return "", ""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    # 닫는 fence 없음 → frontmatter 아님
    return "", text


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        inner = s[1:-1]
        if s[0] == '"':
            inner = inner.replace('\\"', '"')
        return inner
    return s


def _split_inline(inner: str) -> list:
    """따옴표를 고려한 콤마 분리."""
    parts, buf, quote = [], [], ""
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p != ""]


def _coerce(s: str):
    """스칼라 문자열을 bool/null/inline-list/str로 변환."""
    raw = s.strip()
    if raw == "":
        return ""
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_unquote(x) for x in _split_inline(inner)] if inner else []
    return _unquote(raw)


_KEY_RE = re.compile(r"^([A-Za-z0-9_\-]+):\s?(.*)$")
_ITEM_RE = re.compile(r"^\s+-\s+(.*)$")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """frontmatter dict와 body를 반환한다."""
    fm_text, body = split_frontmatter(text)
    meta: dict = {}
    if not fm_text:
        return meta, body
    lines = fm_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        m = _KEY_RE.match(line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        if rest.strip() == "":
            # 블록 리스트 가능성 — 이어지는 들여쓰기 `- ` 라인 수집
            items, j = [], i + 1
            while j < len(lines):
                im = _ITEM_RE.match(lines[j])
                if im:
                    items.append(_coerce(im.group(1)))
                    j += 1
                elif lines[j].strip() == "":
                    break
                else:
                    break
            if items:
                meta[key] = items
                i = j
            else:
                meta[key] = ""
                i += 1
        else:
            meta[key] = _coerce(rest)
            i += 1
    return meta, body


# ---------------------------------------------------------------------------
# 분류
# ---------------------------------------------------------------------------

def _is_false(v) -> bool:
    return v is False or (isinstance(v, str) and v.strip().lower() == "false")


def _is_true(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() == "true")


def _first_heading(body: str) -> str:
    for line in (body or "").splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


def classify(meta: dict, body: str = "") -> ParsedNote:
    note_type = str(meta.get("type", "") or "").strip().lower()
    source_layer = str(meta.get("source_layer", "") or "").strip().lower()
    generated_by = str(meta.get("generated_by", "") or "").strip()
    reuse_ev = meta.get("reuse_as_evidence", None)
    reuse_hyp = meta.get("reuse_as_hypothesis", None)

    # self-generated 판정 — 하나라도 걸리면 import 제외(자기참조 금지)
    self_generated = (
        bool(generated_by)
        or source_layer == "primary_processed"
        or _is_false(reuse_ev)
        or note_type in GENERATED_TYPES
    )

    if self_generated:
        layer = LAYER_SELF_GENERATED
        importable = False
        reuse_as_hypothesis = False
        reuse_as_evidence = _is_true(reuse_ev)  # 보통 False
    elif note_type in HYPOTHESIS_TYPES or source_layer == "user_synthesis":
        layer = LAYER_HYPOTHESIS
        reuse_as_hypothesis = not _is_false(reuse_hyp)  # 기본 True, 명시 false면 제외
        importable = reuse_as_hypothesis
        reuse_as_evidence = False
    else:
        layer = LAYER_UNKNOWN
        importable = False
        reuse_as_hypothesis = False
        reuse_as_evidence = False

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    return ParsedNote(
        note_type=note_type or "unknown",
        layer=layer,
        importable=importable,
        ticker=str(meta.get("ticker", "") or "").strip().upper(),
        company=str(meta.get("company", "") or "").strip(),
        status=str(meta.get("status", "") or "").strip().lower(),
        title=str(meta.get("title", "") or "").strip() or _first_heading(body),
        source_layer=source_layer,
        reuse_as_hypothesis=reuse_as_hypothesis,
        reuse_as_evidence=reuse_as_evidence,
        tags=[str(t) for t in tags],
        meta=meta,
        body=body,
    )


def parse_note(text: str) -> ParsedNote:
    """노트 전체 텍스트 → ParsedNote."""
    meta, body = parse_frontmatter(text)
    return classify(meta, body)
