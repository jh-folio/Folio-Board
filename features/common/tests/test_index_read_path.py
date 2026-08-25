"""색인을 DB에서 읽는 빠른 경로가 실제로 쓰이는지."""
from __future__ import annotations

import inspect

from features.common.research_library.indexing import service


def test_db_read_does_not_require_the_content_column():
    """`content`가 비어 있다고 전체 재빌드로 떨어지면 안 된다.

    그 컬럼은 나중에 ALTER로 추가돼 기존 행이 전부 빈 문자열이 됐고, 증분 색인이 그
    상태를 계속 물려줬다(실측 21,127건 전부 공백). 판정이 늘 거짓이 되면서 매 캐시
    미스가 `build_index()` 전체 실행(5.6초)이 됐다 — DB 읽기는 0.6초다.
    """
    source = inspect.getsource(service._read_index_from_store)
    assert 'any(d.get("content")' not in source, "content 유무로 DB 사용을 판정하지 않는다"
    assert "if docs:" in source


def test_documents_carry_a_summary_even_without_content():
    """본문은 chunks에 있고, 화면·프롬프트가 쓰는 것은 summary다."""
    from features.common.research_library.indexing.research_index import load_documents_from_db

    if not service.RESEARCH_DB_PATH.exists():
        return
    docs = load_documents_from_db(service.RESEARCH_DB_PATH)
    if not docs:
        return
    sampled = docs[:50]
    assert sum(1 for doc in sampled if doc.get("summary")) >= len(sampled) * 0.8
