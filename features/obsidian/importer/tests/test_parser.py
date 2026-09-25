"""Obsidian Import 파서·분류·인덱스 단위 테스트.

의존성: 프로젝트 모듈 + 표준 라이브러리만. pytest 없이 스크립트로 바로 실행 가능.

    py -3 -m features.obsidian.importer.tests.test_parser
    py -3 features/obsidian/importer/tests/test_parser.py
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.obsidian.importer import parser as P
from features.obsidian.importer import note_index as idx


# ---------------------------------------------------------------------------
# 샘플 노트
# ---------------------------------------------------------------------------

COMPANY_THESIS = """---
type: company_thesis
ticker: lrcx
company: Lam Research
status: active
review_cycle: quarterly
source_layer: user_synthesis
reuse_as_hypothesis: true
key_metrics:
  - WFE outlook
  - gross margin
  - China revenue exposure
---

# LRCX 투자 Thesis

HBM과 메모리 capex 회복이 중기 성장 동력이다.
"""

MARKET_MEMO = """---
type: market_memo
topic: "AI 데이터센터 전력 병목"
status: active
source_layer: user_synthesis
reuse_as_hypothesis: true
---

전력 병목이 핵심 변수다.
"""

SOURCE_NOTE = """---
type: source_note
generated_by: Folio OS
source_layer: primary_processed
reuse_as_evidence: false
---

자동 생성 자료 본문.
"""

# 2026-09 리네이밍 이후 새로 내보내는 노트는 신규 표시명을 쓴다. 신·구 값 모두
# self_generated로 인식돼야 한다(dual-read, plan §4.3) — classify()는 값을
# 비교하지 않고 bool(generated_by)로만 판정하므로 이름이 바뀌어도 안전하다.
SOURCE_NOTE_NEW_MARKER = """---
type: source_note
generated_by: Folio Board
source_layer: primary_processed
reuse_as_evidence: false
---

자동 생성 자료 본문.
"""

# 현재 Obsidian export가 만드는 브리핑 노트(명시 마커 없음, type만 briefing)
EXPORTED_BRIEFING = """---
date: 2026-06-09
type: briefing
tags:
  - AI
  - Semiconductors
generated_at: 2026-06-09T08:30:00
---

# 2026-06-09 브리핑
"""

# 사용자가 reuse를 명시적으로 끈 thesis
THESIS_HYP_OFF = """---
type: company_thesis
ticker: NVDA
reuse_as_hypothesis: false
---
본문
"""

PLAIN_NOTE = """# 그냥 메모

frontmatter 없는 일반 노트.
"""


# ---------------------------------------------------------------------------
# frontmatter 파싱
# ---------------------------------------------------------------------------

def test_split_frontmatter_basic():
    fm, body = P.split_frontmatter(COMPANY_THESIS)
    assert "type: company_thesis" in fm
    assert body.lstrip().startswith("# LRCX 투자 Thesis")


def test_split_frontmatter_none_when_absent():
    fm, body = P.split_frontmatter(PLAIN_NOTE)
    assert fm == ""
    assert body == PLAIN_NOTE


def test_parse_scalars():
    meta, _ = P.parse_frontmatter(COMPANY_THESIS)
    assert meta["type"] == "company_thesis"
    assert meta["ticker"] == "lrcx"
    assert meta["company"] == "Lam Research"


def test_parse_bool():
    meta, _ = P.parse_frontmatter(COMPANY_THESIS)
    assert meta["reuse_as_hypothesis"] is True


def test_parse_block_list():
    meta, _ = P.parse_frontmatter(COMPANY_THESIS)
    assert meta["key_metrics"] == ["WFE outlook", "gross margin", "China revenue exposure"]


def test_parse_quoted_scalar():
    meta, _ = P.parse_frontmatter(MARKET_MEMO)
    assert meta["topic"] == "AI 데이터센터 전력 병목"  # 따옴표 제거됨


def test_parse_inline_list():
    meta, _ = P.parse_frontmatter('---\ntags: [AI, "Power Grid"]\n---\nx')
    assert meta["tags"] == ["AI", "Power Grid"]


# ---------------------------------------------------------------------------
# 분류 — hypothesis 인식
# ---------------------------------------------------------------------------

def test_company_thesis_is_hypothesis():
    note = P.parse_note(COMPANY_THESIS)
    assert note.layer == P.LAYER_HYPOTHESIS
    assert note.is_hypothesis is True
    assert note.importable is True
    assert note.ticker == "LRCX"           # 대문자 정규화
    assert "WFE outlook" in note.meta["key_metrics"]


def test_market_memo_is_hypothesis():
    note = P.parse_note(MARKET_MEMO)
    assert note.layer == P.LAYER_HYPOTHESIS
    assert note.importable is True


# ---------------------------------------------------------------------------
# 분류 — self_generated 제외 (자기참조 방지, 핵심)
# ---------------------------------------------------------------------------

def test_source_note_is_self_generated():
    note = P.parse_note(SOURCE_NOTE)
    assert note.layer == P.LAYER_SELF_GENERATED
    assert note.importable is False


def test_source_note_with_new_display_name_is_also_self_generated():
    """`generated_by: Folio Board`(신규 export)도 `Folio OS`(과거 export)와 동일하게
    걸러진다 — 이름이 바뀌었다고 자기참조 방지가 뚫리면 안 된다(plan §4.3)."""
    note = P.parse_note(SOURCE_NOTE_NEW_MARKER)
    assert note.layer == P.LAYER_SELF_GENERATED
    assert note.importable is False


def test_generated_by_excluded_from_evidence():
    note = P.parse_note(SOURCE_NOTE)
    # generated_by 노트는 evidence로도, hypothesis로도 재사용되지 않는다
    assert note.is_evidence is False
    assert note.importable is False
    assert note.is_self_generated is True


def test_reuse_as_evidence_false_excluded():
    note = P.parse_note(
        "---\ntype: market_memo\nsource_layer: user_synthesis\nreuse_as_evidence: false\n---\nx"
    )
    # reuse_as_evidence:false 마커가 있으면 user 타입이어도 self_generated로 본다
    assert note.layer == P.LAYER_SELF_GENERATED
    assert note.importable is False


def test_exported_briefing_is_self_generated():
    note = P.parse_note(EXPORTED_BRIEFING)
    # 명시 마커가 없어도 생성 타입(briefing)으로 self_generated 판정
    assert note.layer == P.LAYER_SELF_GENERATED
    assert note.importable is False


def test_reuse_as_hypothesis_false_not_importable():
    note = P.parse_note(THESIS_HYP_OFF)
    assert note.layer == P.LAYER_HYPOTHESIS
    assert note.reuse_as_hypothesis is False
    assert note.importable is False


def test_obsidian_note_is_never_evidence():
    for sample in (COMPANY_THESIS, MARKET_MEMO, SOURCE_NOTE, SOURCE_NOTE_NEW_MARKER, EXPORTED_BRIEFING, PLAIN_NOTE):
        assert P.parse_note(sample).is_evidence is False


def test_plain_note_is_unknown():
    note = P.parse_note(PLAIN_NOTE)
    assert note.layer == P.LAYER_UNKNOWN
    assert note.importable is False
    assert note.title == "그냥 메모"   # 본문 첫 헤딩에서 추출


# ---------------------------------------------------------------------------
# note_index upsert / list (in-memory DB)
# ---------------------------------------------------------------------------

def test_index_upsert_and_list():
    conn = idx.connect(":memory:")
    try:
        idx.upsert_note(conn, rel_path="Theses/LRCX.md", path="/v/Theses/LRCX.md",
                        note=P.parse_note(COMPANY_THESIS))
        idx.upsert_note(conn, rel_path="Briefings/2026-06-09.md", path="/v/Briefings/x.md",
                        note=P.parse_note(EXPORTED_BRIEFING))
        all_notes = idx.list_notes(conn)
        assert len(all_notes) == 2
        importable = idx.list_notes(conn, importable=True)
        assert len(importable) == 1
        assert importable[0]["ticker"] == "LRCX"
        assert isinstance(importable[0]["tags"], list)  # tags_json → list 복원
    finally:
        conn.close()


def test_index_upsert_is_idempotent():
    conn = idx.connect(":memory:")
    try:
        note = P.parse_note(COMPANY_THESIS)
        id1 = idx.upsert_note(conn, rel_path="Theses/LRCX.md", path="/v/a.md", note=note)
        id2 = idx.upsert_note(conn, rel_path="Theses/LRCX.md", path="/v/a.md", note=note)
        assert id1 == id2
        assert len(idx.list_notes(conn)) == 1  # 같은 rel_path → upsert, 중복 없음
    finally:
        conn.close()


def test_index_filter_by_ticker():
    conn = idx.connect(":memory:")
    try:
        idx.upsert_note(conn, rel_path="Theses/LRCX.md", path="/v/a.md", note=P.parse_note(COMPANY_THESIS))
        assert len(idx.list_notes(conn, ticker="lrcx")) == 1  # 대소문자 무관
        assert len(idx.list_notes(conn, ticker="AAPL")) == 0
    finally:
        conn.close()


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
