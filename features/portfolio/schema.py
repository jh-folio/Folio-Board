"""Additive Portfolio document contract for revision-safe writes."""
from __future__ import annotations


def revision(value: object, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def expected_revision(value: dict | None) -> int | None:
    if not isinstance(value, dict) or "expectedRevision" not in value:
        return None
    return revision(value.get("expectedRevision"))


def portfolio_document(value: dict | None) -> dict:
    value = value if isinstance(value, dict) else {}
    raw_schema = value.get("schemaVersion")
    try:
        source_schema = int(raw_schema)
    except (TypeError, ValueError):
        source_schema = 1
    source_schema = max(1, source_schema)
    return {
        # Reads are projected to v3 but callers never write this projection
        # back merely by opening an older file.
        "schemaVersion": 3,
        "sourceSchemaVersion": source_schema,
        "revision": revision(value.get("revision")),
        "positions": value.get("positions") if isinstance(value.get("positions"), list) else [],
        "cash": value.get("cash") if isinstance(value.get("cash"), list) else [],
        "updatedAt": str(value.get("updatedAt") or ""),
    }
