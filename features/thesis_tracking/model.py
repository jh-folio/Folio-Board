"""Thesis 데이터 모델 + company_thesis 노트 파싱 + enum.

company_thesis 노트(개선안 02 §3) 구조:
  frontmatter: type, ticker, company, status, review_cycle, conviction,
               created, last_reviewed, key_metrics[], linked_regimes[]
  body 섹션(헤딩): 핵심 Thesis / 핵심 가정 / 강화 신호 / 약화 신호 / 이탈 조건 / 다음 리뷰 체크포인트
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- enum ---------------------------------------------------------------
CONVICTION_CHOICES = {"low", "medium", "medium_high", "high"}
CONVICTION_DEFAULT = "medium"
REVIEW_CYCLE_CHOICES = {"weekly", "monthly", "quarterly", "event_driven"}
REVIEW_CYCLE_DEFAULT = "quarterly"
STATUS_CHOICES = {"active", "watch", "closed"}
STATUS_DEFAULT = "active"

# Thesis Delta 판정 enum (개선안 02 §5) — delta 엔진과 공유
VERDICT_CHOICES = {"strengthened", "maintained", "weakened", "at_risk", "broken", "insufficient_evidence"}
VERDICT_DEFAULT = "insufficient_evidence"
VERDICT_LABELS = {
    "strengthened": "강화",
    "maintained": "유지",
    "weakened": "약화",
    "at_risk": "이탈 위험",
    "broken": "이탈",
    "insufficient_evidence": "판단 보류",
}

# 리스트 필드 (저장/직렬화 공통)
LIST_FIELDS = [
    "key_assumptions",
    "supporting_signals",
    "weakening_signals",
    "falsification_triggers",
    "next_checkpoints",
    "key_metrics",
    "linked_regimes",
]


def normalize_ticker(value) -> str:
    """thesis PK용 티커 정규화 — 노트 색인(`investment_notes._clean_ticker`)과 **같은 규칙**.

    thesis.ticker와 native_note_index.ticker가 join 키인데 두 경로가 다른 정규화를
    쓰면 같은 회사가 두 행으로 갈라진다(`005930.KS` vs `005930`, `BRK.B` vs `BRK-B`) —
    카드가 영영 "연결된 Thesis가 없습니다"를 보여주고 `만들기`가 행을 계속 늘린다.
    규칙: 한국 6자리 코드는 `.KS`/`.KQ`를 떼고, 그 외 `.`은 `-`로, `[A-Z0-9-]{1,12}`만 허용.
    """
    raw = str(value or "").strip().upper().lstrip("$")
    korean = re.fullmatch(r"(\d{6})(?:\.(?:KS|KQ))?", raw)
    if korean:
        return korean.group(1)
    raw = raw.replace(".", "-")
    return raw if re.fullmatch(r"[A-Z0-9-]{1,12}", raw) else ""


@dataclass
class Thesis:
    ticker: str = ""
    company: str = ""
    core_thesis: str = ""
    key_assumptions: list = field(default_factory=list)
    supporting_signals: list = field(default_factory=list)
    weakening_signals: list = field(default_factory=list)
    falsification_triggers: list = field(default_factory=list)
    next_checkpoints: list = field(default_factory=list)
    key_metrics: list = field(default_factory=list)
    linked_regimes: list = field(default_factory=list)
    review_cycle: str = REVIEW_CYCLE_DEFAULT
    conviction: str = CONVICTION_DEFAULT
    status: str = STATUS_DEFAULT
    source: str = "obsidian"          # obsidian | manual | native_note (store.VAULT_OWNED_SOURCES가 소유권 판정)
    note_path: str = ""
    created_at: str = ""
    last_reviewed_at: str = ""

    def to_row(self) -> dict:
        return {
            "ticker": self.ticker,
            "company": self.company,
            "core_thesis": self.core_thesis,
            "key_assumptions": list(self.key_assumptions),
            "supporting_signals": list(self.supporting_signals),
            "weakening_signals": list(self.weakening_signals),
            "falsification_triggers": list(self.falsification_triggers),
            "next_checkpoints": list(self.next_checkpoints),
            "key_metrics": list(self.key_metrics),
            "linked_regimes": list(self.linked_regimes),
            "review_cycle": self.review_cycle,
            "conviction": self.conviction,
            "status": self.status,
            "source": self.source,
            "note_path": self.note_path,
            "created_at": self.created_at,
            "last_reviewed_at": self.last_reviewed_at,
        }


# --- normalize ----------------------------------------------------------

def normalize_conviction(v) -> str:
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    return s if s in CONVICTION_CHOICES else CONVICTION_DEFAULT


def normalize_review_cycle(v) -> str:
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    return s if s in REVIEW_CYCLE_CHOICES else REVIEW_CYCLE_DEFAULT


def normalize_status(v) -> str:
    s = str(v or "").strip().lower()
    return s if s in STATUS_CHOICES else STATUS_DEFAULT


def normalize_verdict(v) -> str:
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    return s if s in VERDICT_CHOICES else VERDICT_DEFAULT


# --- body 섹션 파싱 ------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")


def _split_sections(body: str) -> dict:
    """body를 헤딩 단위로 분할. {heading_text: [lines]}."""
    sections: dict = {}
    current = None
    buf: list = []
    for line in (body or "").splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                sections[current] = buf
            current = m.group(1).strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = buf
    return sections


def _find_section(sections: dict, keywords) -> list:
    # 내용이 있는 첫 매칭을 우선한다(문서 H1 제목이 키워드에 걸려 빈 섹션을 반환하는 것 방지).
    first = None
    for head, lines in sections.items():
        h = head.lower()
        if any(k in h for k in keywords):
            if first is None:
                first = lines
            if any(ln.strip() for ln in lines):
                return lines
    return first or []


def _bullets(lines) -> list:
    out = []
    for ln in lines or []:
        m = _BULLET_RE.match(ln)
        if m:
            out.append(m.group(1).strip())
    return out


def _paragraph(lines) -> str:
    parts = [ln.strip() for ln in (lines or []) if ln.strip() and not _BULLET_RE.match(ln)]
    return " ".join(parts).strip()


def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in v if str(x).strip()]


def parse_company_thesis(meta: dict, body: str, *, note_path: str = "", source: str = "obsidian") -> Thesis:
    """frontmatter(meta) + body로 Thesis를 만든다."""
    meta = meta or {}
    sections = _split_sections(body)

    core = _paragraph(_find_section(sections, ["핵심 thesis", "core thesis", "thesis", "핵심 논리", "투자 논리"]))
    assumptions = _bullets(_find_section(sections, ["가정", "assumption"]))
    supporting = _bullets(_find_section(sections, ["강화", "supporting", "strength"]))
    weakening = _bullets(_find_section(sections, ["약화", "weakening", "weak"]))
    falsification = _bullets(_find_section(sections, ["이탈", "falsif", "break", "exit"]))
    checkpoints = _bullets(_find_section(sections, ["체크포인트", "checkpoint", "리뷰", "review"]))

    return Thesis(
        ticker=str(meta.get("ticker", "") or "").strip().upper(),
        company=str(meta.get("company", "") or "").strip(),
        core_thesis=core,
        key_assumptions=assumptions,
        supporting_signals=supporting,
        weakening_signals=weakening,
        falsification_triggers=falsification,
        next_checkpoints=checkpoints,
        key_metrics=_as_list(meta.get("key_metrics")),
        linked_regimes=_as_list(meta.get("linked_regimes")),
        review_cycle=normalize_review_cycle(meta.get("review_cycle")),
        conviction=normalize_conviction(meta.get("conviction")),
        status=normalize_status(meta.get("status")),
        source=source,
        note_path=note_path,
        created_at=str(meta.get("created", "") or "").strip(),
        last_reviewed_at=str(meta.get("last_reviewed", "") or meta.get("created", "") or "").strip(),
    )


def parse_thesis_text(text: str, *, note_path: str = "", source: str = "obsidian") -> Thesis:
    """노트 전체 텍스트 → Thesis (Obsidian importer 파서 재사용)."""
    from features.obsidian.importer.parser import parse_frontmatter
    meta, body = parse_frontmatter(text)
    return parse_company_thesis(meta, body, note_path=note_path, source=source)
