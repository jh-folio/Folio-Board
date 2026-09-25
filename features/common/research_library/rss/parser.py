"""Feed parsing for Folio Board Evidence Intake.

Turns raw RSS/Atom XML into a uniform ``raw item`` dict
(``title``/``description``/``link``/``published_at_utc``) that the
normalizer later promotes into an ``IntakeEvidenceItem``. RSS and Atom share
one builder so both dialects produce identical raw items.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

KST = dt.timezone(dt.timedelta(hours=9))

_TAG_RE = re.compile(r"<[^>]+>")


def strip_markup(text: str) -> str:
    """Drop embedded HTML from feed descriptions (e.g. Google News wraps the
    description in ``<a href>``/``<font>``), leaving plain text for summaries
    and relevance scoring."""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", str(text or ""))).strip()

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
)


def find_text(item, tag: str) -> str:
    """Return the text of the first child matching ``tag`` (namespace agnostic)."""
    for child in item:
        if child.tag == tag or child.tag.endswith("}" + tag):
            return (child.text or "").strip()
    return ""


def find_atom_link(entry) -> str:
    """Pick the best Atom ``<link>`` href, preferring rel=alternate."""
    fallback = ""
    for child in entry:
        if not (child.tag == "link" or child.tag.endswith("}link")):
            continue
        href = (child.attrib or {}).get("href", "").strip()
        rel = (child.attrib or {}).get("rel", "").strip().lower()
        if href and rel in {"", "alternate"}:
            return href
        if href and not fallback:
            fallback = href
    return fallback


def parse_pub_date(text: str):
    """Parse a feed timestamp into a UTC-aware datetime, or ``None``."""
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        for fmt in _DATE_FORMATS:
            try:
                parsed = dt.datetime.strptime(str(text).strip(), fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc if "T" in fmt else KST)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        # A timezone-less feed timestamp (e.g. mk.co.kr sends RFC822 pubDate without
        # an offset) is a Korean publisher's local time, not UTC. Defaulting to UTC
        # here pushed Korean articles +9h into the future (a 15:37 KST close report
        # showed as 00:37 next-day). Treat naive timestamps as KST, consistent with
        # the non-ISO strptime branch above. Genuine UTC feeds keep their explicit tz.
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(dt.timezone.utc)


def _raw_item(title: str, description: str, link: str, pub_date, publisher: str = "") -> dict | None:
    """Build a uniform raw item, dropping entries missing required fields.

    ``publisher`` carries the feed-declared originating outlet (RSS ``<source>``).
    Aggregating feeds such as Yahoo Finance mix many outlets in one feed, so this
    is what lets a feed be filtered or re-tagged by the actual publisher.
    """
    if not (title and link and pub_date):
        return None
    return {
        "title": html.unescape(title),
        "description": strip_markup(html.unescape(description or "")),
        "link": link.strip(),
        "published_at_utc": pub_date,
        "publisher": html.unescape(str(publisher or "")).strip()[:80],
    }


def _is_tag(element, tag: str) -> bool:
    return element.tag == tag or element.tag.endswith("}" + tag)


def find_rss_items(root) -> list:
    """Collect ``<item>`` elements across RSS 0.9x/2.0 and RSS 1.0 (RDF).

    RSS 2.0 nests items inside an unnamespaced ``<channel>``. RSS 1.0 puts both
    ``channel`` and ``item`` in the ``purl.org/rss/1.0`` namespace and makes the
    items **siblings** of the channel rather than its children — so looking only
    for unnamespaced ``channel/item`` silently returns nothing. That matters
    beyond a stray feed: RSS 1.0 is still common among Japanese publishers
    (Nikkei Asia, Asahi), so the Japan expansion depends on reading it.
    """
    items = [child for child in root if _is_tag(child, "item")]
    for child in root:
        if _is_tag(child, "channel"):
            items.extend(grandchild for grandchild in child if _is_tag(grandchild, "item"))
    return items


def parse_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    entries = find_rss_items(root)
    results = []
    for item in entries:
        raw = _raw_item(
            find_text(item, "title"),
            find_text(item, "description") or find_text(item, "encoded"),
            find_text(item, "link") or find_text(item, "guid"),
            parse_pub_date(find_text(item, "pubDate") or find_text(item, "date")),
            find_text(item, "source") or find_text(item, "creator"),
        )
        if raw:
            results.append(raw)
    return results


def parse_atom(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    entries = [c for c in root if c.tag == "entry" or c.tag.endswith("}entry")]
    results = []
    for entry in entries:
        raw = _raw_item(
            find_text(entry, "title"),
            find_text(entry, "summary") or find_text(entry, "content"),
            find_atom_link(entry),
            parse_pub_date(find_text(entry, "published") or find_text(entry, "updated")),
        )
        if raw:
            results.append(raw)
    return results


def parse_feed(xml_bytes: bytes) -> list[dict]:
    """Dispatch to the Atom or RSS parser based on the document root."""
    root = ET.fromstring(xml_bytes)
    if root.tag == "feed" or root.tag.endswith("}feed"):
        return parse_atom(xml_bytes)
    return parse_rss(xml_bytes)
