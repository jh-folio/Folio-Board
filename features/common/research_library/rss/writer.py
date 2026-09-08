"""Markdown archive IO for Folio Board Evidence Intake items.

Owns the on-disk archive format: rendering an ``IntakeEvidenceItem`` to a
YAML front matter Markdown file, resolving collision-free filenames, indexing
existing files for dedupe/enrichment, upgrading legacy line-oriented Markdown,
and writing the ``.state.json`` run report.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path

from features.common.atomic_replace import replace_with_retry
from features.common.market_calendar import infer_doc_markets
from features.common.research_library.rss.article import normalize_text
from features.common.research_library.rss.feed_config import feed_market_for_media
from features.common.research_library.rss.normalizer import markets_with_feed_fallback
from features.common.research_library.rss.policy import normalize_url, should_retry_existing_item


KST = dt.timezone(dt.timedelta(hours=9))
TS_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S"
TS_FORMAT = "%Y-%m-%d %H-%M-%S"
INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]'
URL_LINE_PREFIX = "- URL:"


def _yaml_value(value):
    if value is None:
        return "null"
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return json.dumps(text, ensure_ascii=False)


def _frontmatter(mapping: dict) -> str:
    rows = ["---"]
    for key, value in mapping.items():
        rows.append(f"{key}: {_yaml_value(value)}")
    rows.append("---")
    return "\n".join(rows)


def evidence_markdown(evidence: dict, *, store_full_text: bool = False) -> str:
    published_at = evidence.get("published_at_utc")
    collected_at = evidence.get("collected_at_utc")
    if isinstance(published_at, dt.datetime):
        published_kst = published_at.astimezone(KST).strftime(TS_DISPLAY_FORMAT)
        date = published_at.astimezone(KST).strftime("%Y-%m-%d")
    else:
        published_kst = ""
        date = ""
    if isinstance(collected_at, dt.datetime):
        collected_kst = collected_at.astimezone(KST).strftime(TS_DISPLAY_FORMAT)
    else:
        collected_kst = ""

    full_text = evidence.get("full_text") if store_full_text else ""
    full_text_note = full_text or "Full text is not saved by default. Use --save-full-text for local/private archive only."
    front = _frontmatter(
        {
            "id": evidence.get("id", ""),
            "title": evidence.get("title", ""),
            "source": evidence.get("source", ""),
            "collector": evidence.get("collector", "rss"),
            "source_type": evidence.get("source_type", "news"),
            "date": date,
            "published_at_kst": published_kst,
            "collected_at_kst": collected_kst,
            "url": evidence.get("url", ""),
            "normalized_url": evidence.get("normalized_url", ""),
            "query": evidence.get("query", ""),
            "query_source": evidence.get("query_source", "rss_feed"),
            "language": evidence.get("language", ""),
            "collection_status": evidence.get("collection_status", ""),
            "relevance_score": evidence.get("relevance_score", 0),
            "search_score": evidence.get("search_score"),
            "reliability_tier": evidence.get("reliability_tier", 2),
            "related_tickers": evidence.get("related_tickers") or [],
            "related_themes": evidence.get("related_themes") or [],
            "markets": evidence.get("markets") or markets_with_feed_fallback(
                infer_doc_markets({
                    "title": evidence.get("title", ""),
                    "summary": evidence.get("summary") or evidence.get("description") or "",
                    "content": evidence.get("full_text") or "",
                    "url": evidence.get("url", ""),
                    "source": evidence.get("source", ""),
                }),
                feed_market_for_media(evidence.get("source", "")),
            ),
            "event_id": evidence.get("event_id"),
            "narrative_ids": evidence.get("narrative_ids") or [],
        }
    )
    return (
        f"{front}\n\n"
        f"# {evidence.get('title', '')}\n\n"
        "## Summary\n\n"
        f"{evidence.get('summary') or evidence.get('description') or ''}\n\n"
        "## Full Text\n\n"
        f"{full_text_note}\n\n"
        "## Collection Notes\n\n"
        f"- Status: {evidence.get('collection_status', '')}\n"
        f"- Error: {evidence.get('error', '')}\n"
    )


def _rss_evidence(media, title, description, published_at_utc, link, status, summary, full_text, error, normalized_url=""):
    """Build a default RSS ``IntakeEvidenceItem`` for the legacy write path."""
    return {
        "id": hashlib.sha256(f"rss|{normalize_url(link) or link}|{title}".encode("utf-8")).hexdigest()[:16],
        "collector": "rss",
        "source_type": "news",
        "source": media,
        "title": title,
        "url": link,
        "normalized_url": normalized_url or normalize_url(link),
        "published_at_utc": published_at_utc,
        "collected_at_utc": dt.datetime.now(dt.timezone.utc),
        "query": "",
        "query_source": "rss_feed",
        "language": "",
        "description": description,
        "summary": summary,
        "full_text": full_text,
        "collection_status": status,
        "error": error,
        "relevance_score": 0,
        "search_score": None,
        "related_tickers": [],
        "related_themes": [],
        # 수집 경로는 항상 `evidence`를 넘기므로 여기는 방어용이다. 그래도 같은 규칙을
        # 쓴다 — 세 경로가 다른 답을 내면 어느 것이 옳은지 나중에 알 수 없다.
        "markets": markets_with_feed_fallback(
            infer_doc_markets({
                "title": title,
                "summary": summary or description,
                "content": full_text,
                "url": link,
                "source": media,
            }),
            feed_market_for_media(media),
        ),
        "event_id": None,
        "narrative_ids": [],
        "reliability_tier": 2,
    }


def _atomic_write(path: Path, content: str) -> None:
    """기사 파일을 원자적으로 쓴다.

    교체는 `replace_with_retry()`가 한다 — Windows에서 백신·검색 색인기가 대상 핸들을
    잡으면 제자리 교체가 `WinError 5/32`로 거부되고, 그때 한 번에 실패로 끝내면 수집한
    기사를 잃는다. 자료 폴더를 두 프로세스가 함께 보는 구성에서는 더 자주 걸린다.
    """
    tmp = path.with_name(f".tmp-{path.name}")
    try:
        tmp.write_text(content, encoding="utf-8")
        replace_with_retry(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def sanitize_filename(text: str) -> str:
    cleaned = html.unescape(text or "")
    cleaned = cleaned.replace("\n", " ").replace("\r", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(INVALID_FILENAME_CHARS, "", cleaned).strip(" .")
    return (cleaned or "untitled")[:160]


def resolve_unique_path(archive_dir: Path, base_name: str, existing_filenames: set):
    filename = f"{base_name}.md"
    if filename not in existing_filenames:
        return archive_dir / filename, filename
    for idx in range(2, 1000):
        candidate = f"{base_name} ({idx}).md"
        if candidate not in existing_filenames:
            return archive_dir / candidate, candidate
    return None, None


def format_list_item(label: str, value: str) -> str:
    text = (value or "").strip()
    if not text:
        return f"- {label}: \n"
    lines = text.splitlines()
    if len(lines) == 1:
        return f"- {label}: {lines[0]}\n"
    first, rest = lines[0], lines[1:]
    return f"- {label}: {first}\n" + "\n".join(f"  {line}" for line in rest) + "\n"


def write_markdown(archive_dir, media, title, description, published_at_utc, link, status,
                   summary, full_text, error, existing_filenames, normalized_url="",
                   store_full_text=False, evidence=None):
    """Write a new archive Markdown file with a collision-free timestamped name."""
    if published_at_utc is None:
        published_at_utc = dt.datetime.now(dt.timezone.utc)
    ts_slug = published_at_utc.astimezone(KST).strftime(TS_FORMAT)
    base_name = f"{ts_slug} - {media} - {sanitize_filename(title)}"
    path, filename = resolve_unique_path(archive_dir, base_name, existing_filenames)
    if path is None:
        return None
    item = evidence or _rss_evidence(media, title, description, published_at_utc, link, status, summary, full_text, error, normalized_url)
    _atomic_write(path, evidence_markdown(item, store_full_text=store_full_text))
    existing_filenames.add(filename)
    return path


def write_markdown_to_path(path, media, title, description, published_at_utc, link, status,
                           summary, full_text, error, store_full_text=False, evidence=None):
    """Rewrite an existing archive file in place (enrichment of legacy items)."""
    item = evidence or _rss_evidence(media, title, description, published_at_utc, link, status, summary, full_text, error)
    _atomic_write(path, evidence_markdown(item, store_full_text=store_full_text))
    return path


def parse_existing_file(path: Path):
    """Read an archived Markdown file into a normalized metadata dict.

    Returns ``None`` for files already in the new status-aware format
    (front matter + Full Text), which need no legacy upgrade.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    if "Collection Status" in raw and "Full Text" in raw:
        return None
    # 새 front matter 포맷은 snake_case 키(collection_status)와 `## Full Text` 섹션을 쓴다.
    # 이 검사를 빠뜨리면 새 포맷 파일이 legacy로 오인돼 body 전체가
    # Description/Summary 필드로 평탄화되는 오염이 발생한다.
    if re.search(r"^collection_status\s*:", raw, re.M) and "Full Text" in raw:
        return None
    meta = {}
    body = raw
    front = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$", raw)
    if front:
        body = front.group(2)
        for line in front.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                raw_value = value.strip()
                try:
                    parsed_value = json.loads(raw_value)
                    if isinstance(parsed_value, (str, int, float)):
                        raw_value = str(parsed_value)
                except Exception:
                    raw_value = raw_value.strip("\"'")
                meta[key.strip().lower()] = raw_value
    else:
        current = None
        for line in raw.splitlines():
            m = re.match(r"^-\s+([^:]+):\s*(.*)$", line)
            if m:
                current = m.group(1).strip().lower()
                meta[current] = m.group(2).strip()
            elif current and line.startswith("  "):
                meta[current] += "\n" + line.strip()
    title = meta.get("title") or ""
    if not title:
        for line in body.splitlines():
            if line.strip().startswith("#"):
                title = line.strip().lstrip("#").strip()
                break
    if not title:
        title = path.stem
    url = meta.get("url", "")
    normalized = meta.get("normalized_url") or meta.get("normalized url") or normalize_url(url)
    if not url:
        match = re.search(r"Original link:\s*(https?://\S+)", raw)
        if match:
            url = match.group(1).strip()
            normalized = normalize_url(url)
    timestamp = meta.get("timestamp (utc+9)") or meta.get("date") or ""
    if len(timestamp) == 10:
        timestamp = f"{timestamp} 00:00:00"
    description = meta.get("description") or normalize_text(body.replace(f"# {title}", "", 1))
    description = re.sub(r"Original link:\s*https?://\S+", "", description).strip()
    return {
        "title": title,
        "source": meta.get("source") or meta.get("feed") or "",
        "timestamp": timestamp,
        "url": url,
        "normalized_url": normalized,
        "collection_status": meta.get("collection_status") or meta.get("collection status") or "",
        "description": description,
    }


def existing_file_needs_enrichment(path: Path, *, retry_failed=False, retry_summary_only=False) -> bool:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # New-format files carry the status in YAML front matter. parse_existing_file
    # returns None for them (legacy-upgrade parser), so without this check every
    # new-format file fell through to `return True` and was refetched each run.
    front_match = re.search(r'^collection_status:\s*"?([a-z_]+)"?\s*$', raw, re.M)
    if front_match:
        return should_retry_existing_item(front_match.group(1), retry_failed=retry_failed, retry_summary_only=retry_summary_only)
    parsed = parse_existing_file(path)
    if parsed and parsed.get("collection_status"):
        return should_retry_existing_item(parsed["collection_status"], retry_failed=retry_failed, retry_summary_only=retry_summary_only)
    status_match = re.search(r"^-\s+Collection Status:\s*(.+?)\s*$", raw, re.M)
    if status_match:
        return should_retry_existing_item(status_match.group(1), retry_failed=retry_failed, retry_summary_only=retry_summary_only)
    return True


def upgrade_existing_files(archive_dir: Path, limit=0) -> int:
    """Rewrite up to ``limit`` legacy files into the status-aware format."""
    if limit <= 0 or not archive_dir.exists():
        return 0
    upgraded = 0
    files = sorted(
        [p for p in archive_dir.iterdir() if p.is_file() and p.suffix.lower() == ".md"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        parsed = parse_existing_file(path)
        if not parsed:
            continue
        content = (
            format_list_item("Title", parsed["title"])
            + format_list_item("Source", parsed["source"])
            + format_list_item("Timestamp (UTC+9)", parsed["timestamp"])
            + format_list_item("URL", parsed["url"])
            + format_list_item("Collection Status", "legacy_rss")
            + format_list_item("Description", parsed["description"])
            + format_list_item("Summary", parsed["description"])
            + format_list_item("Full Text", "")
            + format_list_item("Error", "legacy file upgraded without refetching article body")
        )
        _atomic_write(path, content)
        upgraded += 1
        if upgraded >= limit:
            break
    return upgraded


def load_archive_index(archive_dir: Path):
    """Index existing archive files by normalized URL for dedupe/enrichment.

    Returns ``(existing_links, existing_filenames, link_paths)``.
    """
    existing_links: set = set()
    existing_filenames: set = set()
    link_paths: dict = {}
    if not archive_dir.exists():
        return existing_links, existing_filenames, link_paths
    for entry in archive_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".md":
            continue
        existing_filenames.add(entry.name)
        try:
            raw = entry.read_text(encoding="utf-8", errors="replace")
            urls = []
            # New-format files: parse_existing_file intentionally returns None
            # for them (it is the legacy-upgrade parser), so read url /
            # normalized_url straight from the YAML front matter. Missing this
            # made every new-format file invisible to dedupe and re-created
            # the same article with " (2)", " (3)" filename suffixes each run.
            for field in ("normalized_url", "url"):
                match = re.search(rf'^{field}:\s*"?([^"\r\n]+?)"?\s*$', raw, re.M)
                if match:
                    urls.append(match.group(1).strip())
            if not urls:
                parsed = parse_existing_file(entry)
                if parsed:
                    urls.extend([parsed.get("url", ""), parsed.get("normalized_url", "")])
            if not urls:
                for line in raw.splitlines():
                    if line.startswith(URL_LINE_PREFIX):
                        urls.append(line.split(":", 1)[1].strip())
                        break
            for url in urls:
                key = normalize_url(url) or str(url or "").strip()
                if key:
                    existing_links.add(key)
                    link_paths[key] = entry
        except OSError:
            continue
    return existing_links, existing_filenames, link_paths


def validate_manifest(entries: list) -> dict:
    """Mark each manifest entry accepted/rejected and flag in-run duplicates."""
    report = {"ok": True, "issues": [], "accepted": 0, "rejected": 0}
    seen_links = set()
    for entry in entries:
        link = entry.get("link", "")
        link_key = entry.get("normalized_url") or normalize_url(link) or link
        if not entry.get("title") or not link:
            report["issues"].append("title/link missing")
            entry["accepted"] = False
        elif link_key in seen_links:
            report["issues"].append(f"duplicate in manifest: {link}")
            entry["accepted"] = False
        else:
            entry["accepted"] = True
            seen_links.add(link_key)
        report["accepted" if entry.get("accepted") else "rejected"] += 1
    report["ok"] = not report["issues"]
    return report


def write_state(archive_dir: Path, state: dict) -> None:
    state_path = archive_dir / ".state.json"
    digest = hashlib.sha256(json.dumps(state, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    tmp = archive_dir / f".tmp-rss-state-{digest}.json"
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        replace_with_retry(tmp, state_path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
