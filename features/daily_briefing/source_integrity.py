"""Source-use contract for generated briefings.

The model may see more documents than it finally cites and Agent CLIs may add
public web sources.  This module keeps those states separate, removes the
machine manifest from reader Markdown, and builds the final source ledger from
declared or deterministically observed use.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from urllib.parse import urlsplit, urlunsplit


MANIFEST_START = "<!-- FOLIO_BRIEFING_MANIFEST_V1"
MANIFEST_END = "FOLIO_BRIEFING_MANIFEST_V1 -->"
_MANIFEST_RE = re.compile(
    rf"{re.escape(MANIFEST_START)}\s*(.*?)\s*{re.escape(MANIFEST_END)}",
    re.DOTALL,
)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)


def normalize_source_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        # URL-shaped values from a model manifest must never become clickable
        # sources. Local documents are represented by ``path`` and do not pass
        # through this branch. Keep the normalizer intentionally small: Q3 owns
        # claim semantics, while Q2 only needs basic http(s) safety.
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def stable_source_id(source: dict, index: int = 0) -> str:
    existing = str(source.get("sourceId") or source.get("source_id") or "").strip()
    if existing:
        return existing
    key = "|".join(
        str(source.get(field) or "").strip()
        for field in ("url", "path", "title", "date", "source")
    ) or str(index)
    return "src_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def attach_source_ids(sources, *, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for index, source in enumerate(sources or [], 1):
        if not isinstance(source, dict):
            continue
        row = deepcopy(source)
        row["sourceId"] = stable_source_id(row, index)
        normalized_url = normalize_source_url(row.get("url"))
        if row.get("url") and not normalized_url:
            # Do not let a malformed/model-supplied scheme reach markdown
            # rendering. Local sources remain addressable through ``path``.
            row["url"] = ""
        key = normalized_url or str(row.get("path") or row.get("title") or row["sourceId"])
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def source_manifest_prompt(sources) -> str:
    rows = attach_source_ids(sources)
    catalog = [
        {
            "sourceId": row["sourceId"],
            "title": str(row.get("title") or "")[:180],
            "url": str(row.get("url") or ""),
        }
        for row in rows
    ]
    return "\n".join(
        [
            "## Folio source-use manifest (machine contract)",
            "Do not write a reader-facing 참고자료/Sources section. The application owns it.",
            "After the complete report, append exactly one HTML comment using the delimiters below.",
            "Declare only source IDs that materially support the final report. If web search adds a source, declare URL, title, publisher, publishedAt, and supported claim IDs.",
            "Every core number, sector-breadth statement, capital-flow statement, and causal statement must appear in claims with its supporting sourceIds.",
            "Candidate source catalog:",
            json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
            MANIFEST_START,
            '{"usedSourceIds":[],"externalSources":[],"claims":[]}',
            MANIFEST_END,
        ]
    )


def extract_source_manifest(markdown: str) -> tuple[str, dict, list[str]]:
    text = str(markdown or "")
    matches = list(_MANIFEST_RE.finditer(text))
    if not matches:
        return text.strip(), {}, ["manifest_missing"]
    if len(matches) != 1:
        cleaned = _MANIFEST_RE.sub("", text).strip()
        return cleaned, {}, ["manifest_count_invalid"]
    match = matches[0]
    cleaned = (text[: match.start()] + text[match.end() :]).strip()
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return cleaned, {}, ["manifest_json_invalid"]
    if not isinstance(payload, dict):
        return cleaned, {}, ["manifest_shape_invalid"]
    errors: list[str] = []
    for field in ("usedSourceIds", "externalSources", "claims"):
        if not isinstance(payload.get(field, []), list):
            errors.append(f"manifest_{field}_invalid")
    return cleaned, payload if not errors else {}, errors


def markdown_external_links(markdown: str) -> list[dict]:
    rows = []
    seen = set()
    for title, url in _MARKDOWN_LINK_RE.findall(str(markdown or "")):
        normalized = normalize_source_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append({"title": re.sub(r"\s+", " ", title).strip(), "url": url.strip()})
    return rows


def _external_source(row: dict, index: int) -> dict | None:
    url = normalize_source_url(row.get("url"))
    title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip()
    if not url or not title:
        return None
    publisher = re.sub(r"\s+", " ", str(row.get("publisher") or row.get("source") or "")).strip()
    if not publisher:
        publisher = urlsplit(url).netloc.removeprefix("www.")
    out = {
        "title": title[:240],
        "url": url,
        "source": publisher[:120],
        "date": str(row.get("publishedAt") or row.get("date") or "")[:32],
        "type": "web",
        "external": True,
    }
    out["sourceId"] = stable_source_id(out, index)
    supports = row.get("supports")
    if isinstance(supports, list):
        out["supports"] = [str(value)[:80] for value in supports if str(value).strip()][:24]
    return out


def reconcile_source_ledger(markdown: str, candidates, *, limit: int) -> tuple[str, list[dict], dict, dict]:
    cleaned, manifest, errors = extract_source_manifest(markdown)
    candidate_rows = attach_source_ids(candidates, limit=limit)
    by_id = {row["sourceId"]: row for row in candidate_rows}
    by_url = {normalize_source_url(row.get("url")): row for row in candidate_rows if normalize_source_url(row.get("url"))}

    declared_ids = [str(value).strip() for value in manifest.get("usedSourceIds", []) if str(value).strip()]
    invalid_ids = [value for value in declared_ids if value not in by_id]
    if invalid_ids:
        errors.append("manifest_source_outside_whitelist")
    declared_rows = [deepcopy(by_id[value]) for value in declared_ids if value in by_id]

    external_rows: list[dict] = []
    for index, value in enumerate(manifest.get("externalSources", []) if manifest else [], 1):
        if isinstance(value, dict):
            normalized = _external_source(value, index)
            if normalized:
                external_rows.append(normalized)
            else:
                errors.append("manifest_external_source_invalid")

    observed_links = markdown_external_links(cleaned)
    observed_used = []
    for index, link in enumerate(observed_links, len(external_rows) + 1):
        normalized_url = normalize_source_url(link.get("url"))
        if normalized_url in by_url:
            observed_used.append(deepcopy(by_url[normalized_url]))
            continue
        if any(normalize_source_url(row.get("url")) == normalized_url for row in external_rows):
            continue
        normalized = _external_source(link, index)
        if normalized:
            external_rows.append(normalized)

    manifest_valid = bool(manifest) and not errors
    # The existing reference list remains an accessible view of every writer
    # input, even when a valid manifest declares only a subset. Declaration and
    # later claim verification are tracked separately in evidence metadata.
    selected = [deepcopy(row) for row in candidate_rows]
    final_rows = attach_source_ids([*selected, *external_rows], limit=limit)
    final_urls = {normalize_source_url(row.get("url")) for row in final_rows if normalize_source_url(row.get("url"))}
    missing_visible = [
        normalize_source_url(row.get("url"))
        for row in observed_links
        if normalize_source_url(row.get("url")) not in final_urls
    ]
    if missing_visible:
        errors.append("visible_link_missing_from_ledger")

    claims = manifest.get("claims", []) if manifest_valid else []
    claim_rows = [row for row in claims if isinstance(row, dict)]
    evidence = {
        "version": 1,
        "status": "declared" if manifest_valid else "inferred_candidate_fallback",
        "candidateSourceCount": len(candidate_rows),
        # The fallback ledger keeps writer-input rows accessible for legacy
        # readers, but it must not be mistaken for model use or verified claim
        # evidence when the manifest is missing/invalid.
        "writerInputSourceCount": len(candidate_rows),
        "declaredUsedSourceCount": len(declared_rows) if manifest_valid else 0,
        "actualUsedSourceCount": len(declared_rows) if manifest_valid else 0,
        "verifiedSourceCount": 0,
        "accessibleSourceCount": len(final_rows),
        "actualUsedStatus": "declared" if manifest_valid else "unknown",
        "usedSourceCountSemantics": "accessible_writer_ledger",
        "usedSourceCount": len(final_rows),
        "externalSourceCount": sum(bool(row.get("external")) for row in final_rows),
        "errors": sorted(set(errors)),
    }
    claim_ledger = {
        "version": 1,
        "claims": claim_rows,
        "validation": {
            "status": "pass" if not errors else "review",
            "reasonCodes": sorted(set(errors)),
        },
    }
    return cleaned, final_rows, evidence, claim_ledger


__all__ = [
    "MANIFEST_END",
    "MANIFEST_START",
    "attach_source_ids",
    "extract_source_manifest",
    "markdown_external_links",
    "normalize_source_url",
    "reconcile_source_ledger",
    "source_manifest_prompt",
    "stable_source_id",
]
