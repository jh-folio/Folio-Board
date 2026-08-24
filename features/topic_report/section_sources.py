"""Parse hidden per-section source tags and project ledger usage."""
from __future__ import annotations

import re


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_TAG = re.compile(r"<!--\s*folio-source-ids:\s*(.*?)-->", re.IGNORECASE | re.DOTALL)
_SOURCE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,79}$")


def parse_section_source_ids(markdown: str) -> tuple[dict[str, list[str]], list[str]]:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    usage: dict[str, list[str]] = {}
    malformed: list[str] = []
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():body_end]
        ids: list[str] = []
        for tag in _TAG.findall(body):
            for raw in tag.split(","):
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
