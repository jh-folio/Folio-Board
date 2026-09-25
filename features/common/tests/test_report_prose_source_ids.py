"""SOURCE_ID_RE가 로컬 문서 ID(접두 없는 16자 hex)와 evidence ID(ev_/web_ 등 접두)를
둘 다 잡는지 못박는다. 실측: 기업분석 로컬 출처 태그가 전부 16자 hex라 접두만 찾던
옛 정규식이 태그가 섹션마다 정확히 하나씩 있어도 매번 놓쳤다(unlinked_section 오판,
품질 점수 69점 고정)."""
from __future__ import annotations

from features.common.report_prose import SOURCE_ID_RE, tagged_source_ids


def test_bare_hex_local_document_id_matches():
    # research_library/indexing·RSS writer·source_ledger_from_items()가 기존 id를
    # 보존할 때 쓰는 실제 형태(hashlib.sha256(...).hexdigest()[:16]).
    assert SOURCE_ID_RE.findall("<!-- folio-source-ids: 008e6b3760b24375 -->") == ["008e6b3760b24375"]


def test_prefixed_evidence_id_still_matches():
    assert SOURCE_ID_RE.findall("<!-- folio-source-ids: ev_001, web_003 -->") == ["ev_001", "web_003"]


def test_mixed_ids_in_one_tag_all_match():
    tag = "<!-- folio-source-ids: 4160ec8e94b535bd, a00b7bcf537f80b0, web_002 -->"
    assert set(SOURCE_ID_RE.findall(tag)) == {"4160ec8e94b535bd", "a00b7bcf537f80b0", "web_002"}


def test_short_or_uppercase_hex_does_not_false_positive():
    # 16자보다 짧거나 대문자면 실제 ID 형식이 아니다 — 우연한 hex 단어를 근거로 오인하지 않는다.
    assert SOURCE_ID_RE.findall("<!-- note: abc123 -->") == []
    assert SOURCE_ID_RE.findall("<!-- note: 008E6B3760B24375 -->") == []


def test_tagged_source_ids_reads_bare_hex_from_a_real_shaped_section():
    section = (
        "본문 문장입니다. 다른 문장도 있습니다.\n\n"
        "<!-- folio-source-ids: 15163eaceb7cb9d8 -->"
    )
    assert tagged_source_ids(section) == {"15163eaceb7cb9d8"}
