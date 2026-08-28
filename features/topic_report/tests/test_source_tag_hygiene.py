"""섹션 근거 태그는 숨은 metadata다 — 사용자 화면에 글자로 남으면 안 되고,
구분자 하나로 근거 연결을 잃어도 안 된다."""
from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report.section_repair import merge_section_patches
from features.topic_report.section_sources import parse_section_source_ids

_TAG = re.compile(r"folio-source-ids")


def test_whitespace_separated_ids_are_accepted():
    # 모델이 쉼표 대신 공백을 쓰면 예전에는 통째로 한 토큰이 되어 malformed로 떨어졌고,
    # 그 섹션의 근거 연결이 0이 됐다(실측 11개 섹션 중 4개가 "연결 없음").
    usage, malformed = parse_section_source_ids(
        "## 1. Executive Summary\n\n본문\n\n<!-- folio-source-ids: ev_020 ev_021 market__TNX -->\n"
    )
    assert usage["Executive Summary"] == ["ev_020", "ev_021", "market__TNX"]
    assert malformed == []


def test_comma_separated_ids_still_work():
    usage, malformed = parse_section_source_ids(
        "## 1. 결론\n\n본문\n\n<!-- folio-source-ids: ev_009, ev_014 -->\n"
    )
    assert usage["결론"] == ["ev_009", "ev_014"]
    assert malformed == []


def test_genuinely_broken_ids_are_still_reported():
    _usage, malformed = parse_section_source_ids(
        "## 1. 결론\n\n본문\n\n<!-- folio-source-ids: ev_009, 한글아이디 -->\n"
    )
    assert malformed == ["한글아이디"]


def test_repair_does_not_leave_a_second_tag():
    """보수 응답은 원래 본문의 태그를 그대로 물고 온다.

    지우지 않고 새 태그를 덧붙이면 한 섹션에 태그가 둘이 되고, 렌더러가 모든 텍스트를
    escape하므로 사용자 화면에 두 줄이 글자 그대로 보인다(실측: 태그 17개/11섹션).
    """
    markdown = "## 1. Executive Summary\n\n옛 본문\n\n<!-- folio-source-ids: ev_001 -->\n\n## 2. 결론\n\n옛 결론\n"
    patched = merge_section_patches(
        markdown,
        [{
            "heading": "Executive Summary",
            "replacementBody": "새 본문\n\n<!-- folio-source-ids: ev_001 -->",
            "sourceIds": ["ev_001", "ev_002"],
        }],
        allowed_sections={"Executive Summary"},
    )
    assert len(_TAG.findall(patched)) == 1
    assert "ev_002" in patched
    assert "새 본문" in patched


def test_inline_citations_keep_every_id_including_web():
    """항목 전부가 맞아야 하는 정규식이라 `web` 하나가 묶음을 통째로 버렸다.

    같은 릴리즈가 `web_NNN`을 만들고 `render_lookup`이 대괄호 형식을 가르치는데
    이 패턴만 그것을 몰랐다 — `[ev_003, web_001]`이 통째로 사라져 `ev_003`까지 잃고,
    그 섹션은 근거 없음이 되며 `citedSourceIds`는 0건으로 보고됐다.
    """
    from features.topic_report.section_sources import parse_section_source_ids

    body = "## Executive Summary\n\n금리는 올랐다 [ev_003, web_001].\n"
    usage, _unknown = parse_section_source_ids(body)
    ids = usage.get("Executive Summary") or []
    assert "ev_003" in ids and "web_001" in ids, ids

    usage, _unknown = parse_section_source_ids("## Executive Summary\n\n올랐다 [web_002].\n")
    assert usage.get("Executive Summary") == ["web_002"]


def test_repair_strips_alias_tags_so_a_section_never_carries_two():
    """파서가 받아들이는 별칭을 strip이 모르면 새 태그와 함께 둘이 남는다."""
    from features.topic_report.section_repair import _SOURCE_TAG

    for name in ("folio-source-ids", "folio-sources", "source-ids", "sources"):
        assert _SOURCE_TAG.sub("", f"본문 <!-- {name}: ev_015 -->").strip() == "본문", name
