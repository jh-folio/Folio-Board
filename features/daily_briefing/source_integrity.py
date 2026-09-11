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


def attach_source_ids_preserving_aliases(sources) -> list[dict]:
    """Attach IDs while retaining duplicate-URL IDs for later canonicalization."""
    rows: list[dict] = []
    seen: dict[str, dict] = {}
    for index, source in enumerate(sources or [], 1):
        if not isinstance(source, dict):
            continue
        row = deepcopy(source)
        row["sourceId"] = stable_source_id(row, index)
        normalized_url = normalize_source_url(row.get("url"))
        if row.get("url") and not normalized_url:
            row["url"] = ""
        key = normalized_url or str(row.get("path") or row.get("title") or row["sourceId"])
        if key in seen:
            existing = seen[key]
            alias = str(row.get("sourceId") or "").strip()
            if alias and alias != str(existing.get("sourceId") or ""):
                existing.setdefault("_sourceAliases", []).append(alias)
            continue
        seen[key] = row
        rows.append(row)
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
    # Keep an ID supplied by the writer.  Replacing it with a hash here makes
    # the manifest internally inconsistent: claims can still refer to the
    # supplied ID while the final ledger only contains the generated hash.
    supplied_id = str(row.get("sourceId") or row.get("source_id") or "").strip()
    out["sourceId"] = supplied_id or stable_source_id(out, index)
    supports = row.get("supports")
    if isinstance(supports, list):
        out["supports"] = [str(value)[:80] for value in supports if str(value).strip()][:24]
    return out


_CLAIM_SOURCE_ID_FIELDS = (
    "supportingSourceIds", "sourceIds", "sources",
)
def _normalize_claim_rows(
    claims, *, aliases: dict[str, str], available_ids: set[str], ambiguous_ids: set[str],
) -> tuple[list[dict], list[str]]:
    """Keep claim metadata intact and make only known IDs attributable.

    A claim is writer metadata, not independent verification.  A dangling
    supplemental reference therefore becomes an explicit unresolved ID rather
    than a source row fabricated from that reference.  This lets a complete
    authored report survive harmless bookkeeping drift while keeping the
    production source whitelist strict for any ID that remains attached.
    """
    normalized: list[dict] = []
    unresolved_all: list[str] = []
    for raw_claim in list(claims or []):
        if not isinstance(raw_claim, dict):
            continue
        claim = deepcopy(raw_claim)
        unresolved: list[str] = []
        for field in _CLAIM_SOURCE_ID_FIELDS:
            if field not in claim:
                continue
            value = claim.get(field)
            is_sequence = isinstance(value, (list, tuple, set))
            raw_values = (
                [str(item).strip() for item in value if str(item).strip()]
                if is_sequence else
                ([value.strip()] if isinstance(value, str) and value.strip() else [])
            )
            kept: list[str] = []
            for source_id in raw_values:
                canonical = aliases.get(source_id, source_id)
                if source_id in ambiguous_ids or canonical in ambiguous_ids:
                    if source_id not in unresolved:
                        unresolved.append(source_id[:120])
                elif canonical in available_ids:
                    if canonical not in kept:
                        kept.append(canonical)
                elif source_id not in unresolved:
                    unresolved.append(source_id[:120])
            if is_sequence:
                claim[field] = kept
            elif kept:
                claim[field] = kept[0]
            else:
                # An empty scalar is ignored by the finalizer's source-field
                # precedence and is safer than retaining a dangling ID.
                claim[field] = ""
        if unresolved:
            claim["unresolvedSourceIds"] = unresolved[:24]
            claim["sourceResolution"] = "unresolved"
            for source_id in unresolved:
                if source_id not in unresolved_all:
                    unresolved_all.append(source_id)
        normalized.append(claim)
    return normalized, unresolved_all[:24]


def _canonicalize_sources(candidate_rows: list[dict], external_rows: list[dict]):
    """Merge URL aliases while preserving every explicit source ID safely."""
    rows: list[dict] = []
    by_url: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    used_ids: set[str] = set()
    ambiguous_ids: set[str] = set()

    def add_aliases(row: dict, canonical_id: str) -> None:
        for field in ("sourceId", "source_id"):
            value = str(row.get(field) or "").strip()
            if value:
                existing = aliases.get(value)
                if existing and existing != canonical_id:
                    # An ID reused for two different canonical URLs is
                    # ambiguous. Keep the first mapping and make claims using
                    # this ID unresolved rather than retargeting them.
                    ambiguous_ids.add(value)
                    continue
                aliases[value] = canonical_id
        for value in row.get("_sourceAliases") or []:
            value = str(value or "").strip()
            if value:
                existing = aliases.get(value)
                if existing and existing != canonical_id:
                    ambiguous_ids.add(value)
                    continue
                aliases[value] = canonical_id
                # Duplicate-URL aliases reserve the ID just as a canonical
                # ID does.  Otherwise a different-URL external row can
                # silently take over the alias and rewrite its attribution.
                used_ids.add(value)

    # Canonicalization enriches rows when URL aliases merge.  Work on copies
    # so a second market reconciliation can never lose the caller's aliases.
    for row in [*(deepcopy(candidate_rows)), *(deepcopy(external_rows))]:
        source_id = str(row.get("sourceId") or "").strip()
        url = normalize_source_url(row.get("url"))
        existing = by_url.get(url) if url else None
        if existing is not None:
            canonical_id = str(existing["sourceId"])
            # Preserve useful external metadata when a local candidate and a
            # declared web row point at the same URL, but retain the first
            # canonical ID so claims do not split across aliases.
            for key, value in row.items():
                if value not in (None, "", [], {}) and existing.get(key) in (None, "", [], {}):
                    existing[key] = deepcopy(value)
            add_aliases(row, canonical_id)
            continue
        if not source_id or source_id in used_ids:
            # An explicit collision across different URLs is ambiguous.  Do
            # not alias it to an unrelated source; derive a deterministic ID
            # from the safe row instead and leave the original claim dangling.
            if source_id in used_ids:
                ambiguous_ids.add(source_id)
                row = deepcopy(row)
                row.pop("sourceId", None)
                row.pop("source_id", None)
            source_id = stable_source_id(row, len(rows) + 1)
            row["sourceId"] = source_id
        else:
            row["sourceId"] = source_id
        used_ids.add(source_id)
        rows.append(row)
        if url:
            by_url[url] = row
        add_aliases(row, source_id)
    for row in rows:
        row.pop("_sourceAliases", None)
    return rows, aliases, ambiguous_ids


def reconcile_source_ledger(markdown: str, candidates, *, limit: int) -> tuple[str, list[dict], dict, dict]:
    cleaned, manifest, errors = extract_source_manifest(markdown)
    # Do not cap the input before resolving manifest IDs.  The old order made
    # an external source append after a full candidate page and then silently
    # evict it when the combined ledger was capped.
    all_candidate_rows = attach_source_ids_preserving_aliases(candidates)

    declared_ids = [str(value).strip() for value in manifest.get("usedSourceIds", []) if str(value).strip()]

    external_rows: list[dict] = []
    for index, value in enumerate(manifest.get("externalSources", []) if manifest else [], 1):
        if isinstance(value, dict):
            normalized = _external_source(value, index)
            if normalized:
                external_rows.append(normalized)
            else:
                errors.append("manifest_external_source_invalid")

    # Collect all visible links before canonicalization.  Rebuilding based on
    # an external-row count is incorrect when one existing external and one
    # newly observed external happen to have the same count.
    observed_links = markdown_external_links(cleaned)
    known_urls = {
        normalize_source_url(row.get("url"))
        for row in [*all_candidate_rows, *external_rows]
        if normalize_source_url(row.get("url"))
    }
    for index, link in enumerate(observed_links, len(external_rows) + 1):
        normalized_url = normalize_source_url(link.get("url"))
        if normalized_url in known_urls:
            continue
        normalized = _external_source(link, index)
        if normalized:
            external_rows.append(normalized)
            known_urls.add(normalized_url)

    all_rows, aliases, ambiguous_ids = _canonicalize_sources(all_candidate_rows, external_rows)
    all_by_id = {str(row["sourceId"]): row for row in all_rows}
    canonical_declared_ids = [aliases.get(value, value) for value in declared_ids]
    invalid_ids = [value for value in canonical_declared_ids if value not in all_by_id]
    if invalid_ids:
        errors.append("manifest_source_outside_whitelist")

    # Resolve these before the presentation cap.  The JSON source ledger is a
    # complete safe ledger for the supplied writer inputs; only the reader
    # reference list is capped later by ``append_briefing_sources``.
    raw_claims = manifest.get("claims", []) if isinstance(manifest, dict) else []
    observed_links = markdown_external_links(cleaned)
    # Keep every safe row in the ledger.  In particular, an external row must
    # not be evicted merely because the candidate catalog already filled the
    # reader-list budget. Claim metadata is normalized separately, not
    # truncated to the source-list presentation limit.
    final_rows = [deepcopy(row) for row in all_rows]
    by_id = {row["sourceId"]: row for row in final_rows}
    aliases_for_final = {key: value for key, value in aliases.items() if value in by_id}
    ambiguous_declared = {
        value for raw, value in zip(declared_ids, canonical_declared_ids)
        if raw in ambiguous_ids or value in ambiguous_ids
    }
    declared_rows = [
        deepcopy(by_id[value])
        for value in canonical_declared_ids
        if value in by_id and value not in ambiguous_declared
    ]
    manifest_valid = bool(manifest) and not errors
    # The existing reference list remains an accessible view of every writer
    # input, even when a valid manifest declares only a subset. Declaration and
    # later claim verification are tracked separately in evidence metadata.
    final_urls = {normalize_source_url(row.get("url")) for row in final_rows if normalize_source_url(row.get("url"))}
    missing_visible = [
        normalize_source_url(row.get("url"))
        for row in observed_links
        if normalize_source_url(row.get("url")) not in final_urls
    ]
    if missing_visible:
        errors.append("visible_link_missing_from_ledger")

    claims = manifest.get("claims", []) if manifest_valid else []
    claim_rows, unresolved_claim_ids = _normalize_claim_rows(
        claims,
        aliases=aliases_for_final,
        available_ids=set(by_id),
        ambiguous_ids=ambiguous_ids,
    )
    evidence = {
        "version": 1,
        "status": "declared" if manifest_valid else "inferred_candidate_fallback",
        "candidateSourceCount": len(all_candidate_rows),
        # The fallback ledger keeps writer-input rows accessible for legacy
        # readers, but it must not be mistaken for model use or verified claim
        # evidence when the manifest is missing/invalid.
        "writerInputSourceCount": len(all_candidate_rows),
        "declaredUsedSourceCount": len(declared_rows) if manifest_valid else 0,
        "actualUsedSourceCount": (
            None if ambiguous_declared else (len(declared_rows) if manifest_valid else 0)
        ),
        "verifiedSourceCount": 0,
        "accessibleSourceCount": len(final_rows),
        "sourceLedgerSemantics": "complete_safe_writer_ledger",
        "readerSourceLimit": max(1, int(limit or 1)),
        "actualUsedStatus": "unknown" if ambiguous_declared or not manifest_valid else "declared",
        "usedSourceCountSemantics": "accessible_writer_ledger",
        "usedSourceCount": len(final_rows),
        "externalSourceCount": sum(bool(row.get("external")) for row in final_rows),
        "errors": sorted(set(errors)),
    }
    if unresolved_claim_ids:
        evidence["unresolvedClaimSourceIds"] = unresolved_claim_ids
    if ambiguous_ids:
        evidence["ambiguousSourceIds"] = sorted(ambiguous_ids)[:24]
    claim_reason_codes = set(errors)
    if unresolved_claim_ids:
        claim_reason_codes.add("claim_source_unresolved")
    if ambiguous_declared or any(source_id in ambiguous_ids for source_id in unresolved_claim_ids):
        claim_reason_codes.add("source_id_ambiguous")
    claim_ledger = {
        "version": 1,
        "claims": claim_rows,
        "validation": {
            "status": "pass" if not claim_reason_codes else "review",
            "reasonCodes": sorted(claim_reason_codes),
        },
    }
    return cleaned, final_rows, evidence, claim_ledger


__all__ = [
    "MANIFEST_END",
    "MANIFEST_START",
    "attach_source_ids",
    "attach_source_ids_preserving_aliases",
    "extract_source_manifest",
    "markdown_external_links",
    "normalize_source_url",
    "reconcile_source_ledger",
    "source_manifest_prompt",
    "stable_source_id",
]
