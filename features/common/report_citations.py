"""Render source-ledger-backed citations as portable Markdown links.

Only ledger IDs/URLs are public. Provider IDs, quoted source text and source
document offsets never leave the private execution object. These links record
attribution, not a new factual-quality verdict.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

_START = "<!-- folio-citation-links -->"
_END = "<!-- /folio-citation-links -->"
_GENERATED = re.compile(r"\n\n" + re.escape(_START) + r"\n인용 출처: [^\n]*\n" + re.escape(_END) + r"(?:\n\n|\n?\Z)")
_TAG = re.compile(r"<!--\s*(?:folio-source-ids|folio-sources|source-ids|sources)\s*:\s*(.*?)-->", re.I)
_INLINE = re.compile(r"\[((?:ev|web|market|macro)_[\w.-]+(?:\s*,\s*(?:ev|web|market|macro)_[\w.-]+)*)\](?!\()")


def strip_citation_links(markdown: str) -> str:
    protected = _protected(markdown)
    return _GENERATED.sub(lambda m: m.group() if any(a <= m.start() + 2 < b for a, b in protected) else "", markdown)


def visible_citation_markdown(markdown: str) -> str:
    """Notion has no HTML-comment syntax; omit only our citation bookkeeping."""
    protected = _protected(markdown)
    pattern = re.compile(r"<!--\s*(?:(?:folio-source-ids|folio-sources|source-ids|sources)\s*:[\s\S]*?|/?folio-citation-links\s*)-->", re.I)
    return pattern.sub(lambda m: m.group() if any(a <= m.start() < b for a, b in protected) else "", markdown)


def _url(value) -> str:
    value = str(value or "")
    if any(ord(c) < 33 for c in value) or "\\" in value:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
        _ = parsed.port
    except ValueError:
        return ""
    return value


def _protected(text: str) -> list[tuple[int, int]]:
    # Never interpret source IDs inside examples, links or code as citations.
    pattern = r"(?ms)^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]{0,3}\1[ \t]*(?:\n|$)|\Z)|`+[^`\n]*`+|!?\[[^\]\n]*\]\([^\n]*?\)"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def render_citation_links(markdown: str, source_ledger, *, execution=None) -> str:
    """Keep original tags/text; insert links after their paragraph/block.

    Re-rendering removes only our generated paragraphs. Native offsets must
    still map uniquely to unchanged text; no document-index to ledger inference.
    Unknown, duplicate or unsafe sources remain unlinked.
    """
    text = strip_citation_links(str(markdown or ""))
    rows = [r for r in (source_ledger or []) if isinstance(r, dict)]
    by_id, by_url = {}, {}
    for row in rows:
        sid, url = str(row.get("sourceId") or ""), _url(row.get("url"))
        if sid:
            by_id.setdefault(sid, []).append(row)
        if url:
            by_url.setdefault(url, []).append(row)
    protected = _protected(text)
    placements: dict[int, dict[str, str]] = {}

    def add(start: int, end: int, row: dict):
        if not 0 <= start < end <= len(text) or any(a <= start < b or a < end <= b for a, b in protected):
            return
        url = _url(row.get("url"))
        if not url:
            return
        # End of the containing paragraph avoids splitting links, lists and tables.
        boundary = re.search(r"\n\s*\n|\n(?=#{1,6}\s)", text[end:])
        position = end + boundary.start() if boundary else len(text)
        label = re.sub(r"[\[\]<>`*_\\\r\n]", " ", str(row.get("title") or row.get("source") or row.get("sourceId") or "출처"))
        label = " ".join(label.split())[:120] or "출처"
        link_url = quote(url, safe=":/?#@!$&'+,;=%~._-")
        placements.setdefault(position, {})[url] = f"[{label}]({link_url})"

    for pattern in (_TAG, _INLINE):
        for match in pattern.finditer(text):
            for sid in re.split(r"[,\s]+", match.group(1).strip()):
                matches = by_id.get(sid, [])
                if len(matches) == 1:
                    add(match.start(), match.end(), matches[0])
    if execution is not None:
        mapped = execution.with_text(text)
        for citation in mapped.provider.citations if mapped.provider is not None else ():
            matches = by_url.get(_url(citation.url), []) if citation.url else by_id.get(citation.source_id, [])
            if len(matches) == 1 and citation.start is not None and citation.end is not None:
                add(citation.start, citation.end, matches[0])
    for position, links in sorted(placements.items(), reverse=True):
        block = "\n\n" + _START + "\n인용 출처: " + " · ".join(links.values()) + "\n" + _END + "\n\n"
        text = text[:position] + block + text[position:]
    return text
