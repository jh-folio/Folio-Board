"""Obsidian vault export: settings management and note writing for briefings, analyses, narratives."""
import base64
import binascii
import os
import re
from pathlib import Path

from features.common.canonical_report_io import safe_child_path
from features.common.config_bootstrap import resolve_config
from features.common.utils import read_json, write_json
from features.common.taxonomy import normalize_tag
from features.daily_briefing.schema import MARKET_TAGS, briefing_export_units
from features.obsidian.export.formatter import build_frontmatter, inject_wikilinks, preserve_user_notes, charts_to_markdown, strip_duplicate_h1
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = data_dir()
SETTINGS_PATH = DATA_DIR / "obsidian-settings.json"
MARKET_MEMORY_DB = DATA_DIR / "market-memory.sqlite3"
BRIEFINGS_DIR = DATA_DIR / "briefings"
COMPANY_ANALYSIS_DIR = DATA_DIR / "company-analysis"


# ---------------------------------------------------------------------------
# Vault settings
# ---------------------------------------------------------------------------

def get_vault_settings() -> dict:
    return read_json(SETTINGS_PATH, {"vaultPath": ""})


def save_vault_settings(vault_path: str) -> dict:
    settings = {"vaultPath": vault_path.strip()}
    write_json(SETTINGS_PATH, settings)
    return settings


def _require_vault() -> Path:
    settings = get_vault_settings()
    vault_path = settings.get("vaultPath", "").strip()
    if not vault_path:
        raise ValueError("Obsidian vault 경로가 설정되지 않았습니다.")
    try:
        p = Path(vault_path).resolve(strict=True)
    except OSError:
        raise ValueError(f"Vault 경로가 존재하지 않습니다: {vault_path}")
    if not p.is_dir():
        raise ValueError(f"Vault 경로가 폴더가 아닙니다: {vault_path}")
    return p


# ---------------------------------------------------------------------------
# Company name list for wikilink injection
# ---------------------------------------------------------------------------

def _all_company_names() -> list[str]:
    """Return all known company names and aliases, deduped."""
    from features.common.company_lookup import COMPANIES
    seen: set[str] = set()
    names: list[str] = []

    def _add(n: str) -> None:
        if n and n not in seen:
            seen.add(n)
            names.append(n)

    for c in COMPANIES:
        _add(c.get("name", ""))
        for alias in c.get("aliases", []):
            _add(alias)

    master_data = read_json(resolve_config("company_master.json"), {})
    master_list = master_data.get("companies", []) if isinstance(master_data, dict) else master_data
    for c in master_list:
        if not isinstance(c, dict):
            continue
        _add(c.get("name", ""))
        for alias in c.get("aliases", []):
            _add(alias)

    return names


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

def _obsidian_tag(tag: str) -> str:
    """Convert a tag to Obsidian-safe format: spaces replaced with underscores."""
    return tag.replace(" ", "_") if tag else tag


def _safe_filename(name: str) -> str:
    """Strip characters that Obsidian / Windows disallow in filenames."""
    cleaned = "".join(char for char in str(name) if char not in '\\/:*?"<>|#^[]').strip()
    cleaned = os.path.basename(cleaned)
    return cleaned if cleaned not in {"", ".", ".."} else "Untitled"


# ---------------------------------------------------------------------------
# Briefing export
# ---------------------------------------------------------------------------

def _write_briefing_chart_images(
    folder: Path, date: str, chart_images: list[str] | None, market_scope: str = "",
) -> list[str]:
    """Write browser-rendered PNG/SVG fallbacks inside the vault, with strict bounds."""
    if not chart_images:
        return []
    assets = safe_child_path(folder, "assets")
    links = []
    for index, image in enumerate(chart_images[:12], start=1):
        assets.mkdir(parents=True, exist_ok=True)
        market_part = f"-{market_scope}" if market_scope else ""
        stem = _safe_filename(f"briefing-{date}{market_part}-visual-{index}")
        if isinstance(image, dict) and image.get("mimeType") == "image/svg+xml":
            svg_text = str(image.get("svgText") or "")
            lowered = svg_text.lower()
            if (
                not svg_text.lstrip().startswith("<svg")
                or "<script" in lowered
                or re.search(r"\son[a-z]+\s*=", lowered)
                or len(svg_text.encode("utf-8")) > 2 * 1024 * 1024
            ):
                continue
            filename = stem + ".svg"
            # Filename is a validated child of the selected vault.
            # codeql[py/path-injection]
            safe_child_path(assets, filename).write_text(svg_text, encoding="utf-8")
            links.append(f"![[assets/{filename}]]")
            continue
        prefix = "data:image/png;base64,"
        data_url = image if isinstance(image, str) else image.get("dataUrl") if isinstance(image, dict) else ""
        if not isinstance(data_url, str) or not data_url.startswith(prefix):
            continue
        try:
            raw = base64.b64decode(data_url[len(prefix):], validate=True)
        except (ValueError, binascii.Error):
            continue
        if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 8 * 1024 * 1024:
            continue
        filename = stem + ".png"
        # Filename is a validated child of the selected vault.
        # codeql[py/path-injection]
        safe_child_path(assets, filename).write_bytes(raw)
        links.append(f"![[assets/{filename}]]")
    return links


def _briefing_images_for_market(chart_images, market_scope, *, allow_legacy=False):
    selected = []
    target = str(market_scope or "").upper()
    for image in chart_images or []:
        if isinstance(image, str):
            if allow_legacy:
                selected.append(image)
            continue
        if not isinstance(image, dict):
            continue
        image_market = str(image.get("market") or "").upper()
        # 통합 범위(BOTH/ALL)는 모든 시장 이미지를 받는다. 시장 하나면 그 시장과
        # 시장 공통 이미지만 받는다.
        if target in {"BOTH", "ALL"} or image_market in {target, "BOTH", "ALL"}:
            selected.append(image)
    return selected


def _write_briefing_note(folder, date, unit, chart_images):
    market_scope = unit.get("marketScope", "both")

    tag_seen: set[str] = set()
    tags: list[str] = []
    for raw in unit.get("tags") or []:
        nt = _obsidian_tag(normalize_tag(raw))
        if nt and nt not in tag_seen:
            tag_seen.add(nt)
            tags.append(nt)
    for h in (unit.get("headlines") or []):
        for t in (h.get("tags") or []):
            nt = _obsidian_tag(normalize_tag(t))
            if nt and nt not in tag_seen:
                tag_seen.add(nt)
                tags.append(nt)

    generated_at = (unit.get("generatedAt") or "")[:19]
    meta: dict = {
        "date": date,
        "type": "briefing",
        "market": market_scope,
        "briefing_type": unit.get("briefingType", "default"),
        "generated_by": "Folio OS",
        "source_layer": "primary_processed",
        "reuse_as_evidence": False,
        "tags": tags,
    }
    if generated_at:
        meta["generated_at"] = generated_at

    frontmatter = build_frontmatter(meta)
    title = unit.get("title", f"브리핑 {date}")
    title_line = f"# {title}"

    from features.daily_briefing.service import export_markdown_with_sources

    # 주간 본문에는 참고자료 섹션이 없다(sources 필드가 소유). 내보내기는 markdown만
    # 렌더링하므로 여기서 되붙인다 — 일간은 본문에 이미 있어 그대로 통과한다.
    markdown = export_markdown_with_sources(unit)
    if not markdown:
        parts: list[str] = []
        for h in (unit.get("headlines") or []):
            parts.append(f"## {h.get('title', '')}")
            body = h.get("body", "")
            if body:
                parts.append(body)
        markdown = "\n\n".join(parts)

    body_with_links = inject_wikilinks(strip_duplicate_h1(markdown, title), _all_company_names())
    image_links = _write_briefing_chart_images(folder, date, chart_images, market_scope)
    if image_links:
        body_with_links += "\n\n## 시장 시각자료\n\n" + "\n\n".join(image_links)
    new_body = f"{frontmatter}\n\n{title_line}\n\n{body_with_links}"

    market_label = MARKET_TAGS.get(market_scope, "종합")
    filename = _safe_filename(f"브리핑 {date} {market_label}") + ".md"
    note_path = safe_child_path(folder, filename)

    # note_path is a validated child of the selected vault.
    # codeql[py/path-injection]
    existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    # note_path is a validated child of the selected vault.
    # codeql[py/path-injection]
    note_path.write_text(preserve_user_notes(existing, new_body), encoding="utf-8")

    return {"ok": True, "path": str(note_path), "filename": filename, "chartImageCount": len(image_links)}


def export_briefing_to_obsidian(date: str, briefing: dict, chart_images: list[str] | None = None) -> dict:
    vault = _require_vault()
    folder = safe_child_path(vault, "Briefings")
    folder.mkdir(parents=True, exist_ok=True)
    units = briefing_export_units(briefing)
    exports = []
    for unit in units:
        scoped_images = _briefing_images_for_market(
            chart_images, unit.get("marketScope"), allow_legacy=len(units) == 1,
        )
        exports.append(_write_briefing_note(folder, date, unit, scoped_images))
    first = exports[0] if exports else {"ok": True, "path": "", "filename": "", "chartImageCount": 0}
    return {**first, "exports": exports}


# ---------------------------------------------------------------------------
# Company analysis export
# ---------------------------------------------------------------------------

def export_analysis_to_obsidian(report: dict) -> dict:
    vault = _require_vault()
    folder = safe_child_path(vault, "Companies")
    folder.mkdir(parents=True, exist_ok=True)

    company = report.get("company") or {}
    if isinstance(company, str):
        company_name = company
        ticker = ""
        sector = ""
        market = ""
    else:
        company_name = company.get("name") or report.get("query", "Unknown")
        ticker = company.get("ticker", "")
        sector = company.get("sector", "")
        market = company.get("market", "")

    saved_at = (report.get("savedAt") or report.get("saved") or report.get("generatedAt") or "")[:10]

    tag_seen: set[str] = set()
    tags: list[str] = []

    def _add_tag(raw: str) -> None:
        nt = _obsidian_tag(normalize_tag(raw))
        if nt and nt not in {"Unclassified", ""} and nt not in tag_seen:
            tag_seen.add(nt)
            tags.append(nt)

    # 1. Sector from company data
    if sector and sector != "Unclassified":
        _add_tag(sector)

    # 2. Ticker and market — useful for Obsidian graph/search
    if ticker:
        ticker_safe = ticker.replace(".", "_")
        if ticker_safe not in tag_seen:
            tag_seen.add(ticker_safe)
            tags.append(ticker_safe)
    if market:
        _add_tag(market)

    # 3. Content-derived sector and impact tags from markdown
    markdown_text = report.get("markdown", "")
    if markdown_text:
        try:
            from features.common.research_library.indexing.service import find_terms, SECTOR_TERMS, IMPACT_TERMS
            for t in find_terms(markdown_text, SECTOR_TERMS) + find_terms(markdown_text, IMPACT_TERMS):
                _add_tag(t)
        except Exception:
            pass

    meta: dict = {
        "type": "company_analysis",
        "ticker": ticker or None,
        "sector": sector or None,
        "market": market or None,
        "date": saved_at or None,
        "generated_by": "Folio OS",
        "source_layer": "primary_processed",
        "reuse_as_evidence": False,
        "tags": tags,
    }

    frontmatter = build_frontmatter(meta)
    subtitle = f"기업분석" + (f" — {saved_at}" if saved_at else "")
    body_md = inject_wikilinks(report.get("markdown", ""), _all_company_names())
    charts_md = charts_to_markdown(report.get("analysisCharts") or {})
    if charts_md:
        body_md = body_md + "\n\n" + charts_md
    new_body = (
        f"{frontmatter}\n\n"
        f"# {company_name}\n"
        f"_{subtitle}_\n\n"
        f"{body_md}"
    )

    filename = _safe_filename(company_name) + ".md"
    note_path = safe_child_path(folder, filename)

    # note_path is a validated child of the selected vault.
    # codeql[py/path-injection]
    existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    # note_path is a validated child of the selected vault.
    # codeql[py/path-injection]
    note_path.write_text(preserve_user_notes(existing, new_body), encoding="utf-8")

    return {"ok": True, "path": str(note_path), "filename": filename, "company": company_name}


# ---------------------------------------------------------------------------
# Topic report export
# ---------------------------------------------------------------------------

def export_topic_report_to_obsidian(report: dict) -> dict:
    """테마 보고서를 Vault의 Topic Reports/ 폴더로 내보낸다 (설계 04 §15).

    자기참조 방지(Folio OS 원칙 5): generated_by / source_layer: primary_processed /
    reuse_as_evidence: false 를 frontmatter에 붙여, Obsidian importer가 이 노트를
    evidence로 재사용하지 않게 한다.
    """
    vault = _require_vault()
    folder = safe_child_path(vault, "Topic Reports")
    folder.mkdir(parents=True, exist_ok=True)

    label = report.get("topicLabel") or report.get("topicKey") or "테마 분석"
    date = (report.get("date") or report.get("generatedAt") or "")[:10]
    plan = report.get("topicPlan") or {}
    quality = report.get("quality") or {}

    tag_seen: set[str] = set()
    tags: list[str] = []
    for raw in (plan.get("regions") or []) + (plan.get("assetClasses") or []):
        nt = _obsidian_tag(normalize_tag(str(raw)))
        if nt and nt not in {"Unclassified", ""} and nt not in tag_seen:
            tag_seen.add(nt)
            tags.append(nt)

    meta: dict = {
        "type": "topic_report",
        "topic": label,
        "report_type": plan.get("reportType") or report.get("topicKey") or None,
        "date": date or None,
        "generated_by": "Folio OS",
        "source_layer": "primary_processed",
        "reuse_as_evidence": False,
        "quality_score": quality.get("score") if quality else None,
        "tags": tags,
    }

    frontmatter = build_frontmatter(meta)
    body_md = inject_wikilinks(report.get("markdown", ""), _all_company_names())
    new_body = (
        f"{frontmatter}\n\n"
        f"# {label}\n"
        f"_테마 분석" + (f" — {date}" if date else "") + "_\n\n"
        f"{body_md}"
    )

    filename = _safe_filename(f"{label} {date}".strip()) + ".md"
    note_path = safe_child_path(folder, filename)
    # note_path is a validated child of the selected vault.
    # codeql[py/path-injection]
    existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    # note_path is a validated child of the selected vault.
    # codeql[py/path-injection]
    note_path.write_text(preserve_user_notes(existing, new_body), encoding="utf-8")
    return {"ok": True, "path": str(note_path), "filename": filename, "topic": label}


# ---------------------------------------------------------------------------
# Market narrative export
# ---------------------------------------------------------------------------

def export_narratives_to_obsidian() -> dict:
    """Export all active/watch market narrative states, grouped by story family."""
    from features.market_memory.memory import list_states
    from collections import defaultdict

    vault = _require_vault()
    folder = safe_child_path(vault, "Narratives")
    folder.mkdir(parents=True, exist_ok=True)

    states = list_states(MARKET_MEMORY_DB, limit=100, status="current")
    if not states:
        return {"ok": True, "count": 0, "files": []}

    # Group by storyFamily, preserving insertion order
    families: dict[str, list[dict]] = defaultdict(list)
    for s in states:
        family = s.get("storyFamily") or s.get("story") or "기타"
        families[family].append(s)

    company_names = _all_company_names()
    files: list[str] = []

    _bias_label = {"bullish": "강세", "bearish": "약세", "neutral": "중립", "mixed": "혼조"}
    _status_label = {"active": "활성", "watch": "관찰"}

    for family_label, members in families.items():
        top = members[0]
        statuses = list(dict.fromkeys(m["status"] for m in members))
        meta: dict = {
            "type": "narrative",
            "status": statuses[0] if len(statuses) == 1 else statuses,
            "importance": top.get("importance", "medium"),
            "region": top.get("region", "GLOBAL"),
            "updated": (top.get("updatedAt") or "")[:10] or None,
            "generated_by": "Folio OS",
            "source_layer": "primary_processed",
            "reuse_as_evidence": False,
        }

        frontmatter = build_frontmatter(meta)
        sections: list[str] = []
        for member in members:
            bl = _bias_label.get(member.get("bias", ""), "")
            sl = _status_label.get(member.get("status", ""), "")
            label = member.get("stateLabel") or member.get("story", "")
            qualifier = ", ".join(filter(None, [sl, bl]))
            heading = f"## {label}" + (f" ({qualifier})" if qualifier else "")
            summary = member.get("summary") or ""
            rationale = member.get("rationale") or ""
            parts = [heading]
            if summary:
                parts.append(summary)
            if rationale and rationale != summary:
                parts.append(rationale)
            sections.append("\n\n".join(parts))

        body = (
            f"{frontmatter}\n\n"
            f"# {family_label}\n\n"
            + "\n\n---\n\n".join(sections)
        )
        body_with_links = inject_wikilinks(body, company_names)

        filename = _safe_filename(family_label) + ".md"
        note_path = safe_child_path(folder, filename)
        # note_path is a validated child of the selected vault.
        # codeql[py/path-injection]
        existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
        # note_path is a validated child of the selected vault.
        # codeql[py/path-injection]
        note_path.write_text(preserve_user_notes(existing, body_with_links), encoding="utf-8")
        files.append(filename)

    return {"ok": True, "count": len(files), "files": files}
