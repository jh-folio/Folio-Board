from __future__ import annotations

import json
import re

from features.topic_report.report_contract import canonical_heading, split_sections


_NESTED_H2 = re.compile(r"^##\s+", re.MULTILINE)
# 보수 응답의 `replacementBody`에는 원래 본문에 있던 숨김 태그가 그대로 딸려 온다.
# 지우지 않고 새 태그를 덧붙이면 한 섹션에 태그가 둘이 되고, 렌더러가 escape하는 순간
# 사용자 화면에 두 줄이 그대로 보인다(실측: 11개 섹션 보고서에 태그 17개).
_SOURCE_TAG = re.compile(r"<!--\s*folio-source-ids:[\s\S]*?-->", re.IGNORECASE)


def parse_patch_response(value: str) -> list[dict]:
    raw = str(value or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("patch_json_invalid") from None
        try:
            payload = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("patch_json_invalid") from exc
    patches = payload.get("patches") if isinstance(payload, dict) else None
    if not isinstance(patches, list):
        raise ValueError("patches_array_required")
    return patches


def merge_section_patches(markdown: str, patches: list[dict], *, allowed_sections: set[str]) -> str:
    sections = split_sections(markdown)
    if not sections:
        raise ValueError("report_sections_missing")
    replacements = {}
    for patch in patches:
        heading = canonical_heading(str(patch.get("heading") or "").removeprefix("## "))
        body = _SOURCE_TAG.sub("", str(patch.get("replacementBody") or "")).strip()
        source_ids = [str(item).strip() for item in patch.get("sourceIds") or [] if str(item).strip()]
        if heading not in allowed_sections or heading not in {row["heading"] for row in sections} or not body:
            raise ValueError("patch_outside_allowed_sections")
        if _NESTED_H2.search(body):
            raise ValueError("patch_contains_h2")
        tag = f"<!-- folio-source-ids: {', '.join(source_ids)} -->" if source_ids else ""
        replacements[heading] = f"{body}\n\n{tag}".strip()
    first_start = re.search(r"^##\s+", markdown, re.MULTILINE)
    prefix = markdown[:first_start.start()].rstrip() if first_start else ""
    output = prefix
    for row in sections:
        output += f"\n\n## {row['rawHeading']}\n\n{replacements.get(row['heading'], row['body']).strip()}"
    return output.strip()


__all__ = ["merge_section_patches", "parse_patch_response"]
