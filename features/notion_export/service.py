"""Notion export service — push briefings, company analysis, topic reports to Notion."""
import os
from pathlib import Path

from features.llm_settings.client import load_dotenv, mask_secret
from features.daily_briefing.schema import MARKET_TAGS, briefing_export_units
from features.notion_export.client import create_page, markdown_to_blocks, upload_image_to_imgbb

ROOT = Path(__file__).resolve().parent.parent.parent


def notion_config():
    load_dotenv()
    return {
        "token": os.environ.get("NOTION_TOKEN", "").strip(),
        "dbId": os.environ.get("NOTION_DB_ID", "").strip(),
    }


def public_notion_settings():
    cfg = notion_config()
    token = cfg["token"]
    db_id = cfg["dbId"]
    return {
        "hasToken": bool(token),
        "tokenMasked": mask_secret(token),
        "dbId": db_id,
        "dbIdMasked": (db_id[:8] + "...") if db_id else "",
        "hasDb": bool(db_id),
    }


def _require_config():
    cfg = notion_config()
    if not cfg["token"]:
        raise ValueError("Notion 통합 토큰이 설정되지 않았습니다.")
    if not cfg["dbId"]:
        raise ValueError("Notion 데이터베이스 ID가 설정되지 않았습니다.")
    return cfg


def _imgbb_key() -> str:
    load_dotenv()
    return os.environ.get("IMGBB_API_KEY", "").strip()


def _chart_image_blocks(chart_images: list[str] | None) -> list[dict]:
    """Upload chart images to imgbb and return Notion image blocks."""
    if not chart_images:
        return []
    key = _imgbb_key()
    if not key:
        return []
    blocks = [{"type": "divider", "divider": {}}]
    for img in chart_images:
        url = upload_image_to_imgbb(img, key)
        if url:
            blocks.append({"type": "image", "image": {"type": "external", "external": {"url": url}}})
    return blocks if len(blocks) > 1 else []


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
        if target in {"BOTH", "ALL"} or image_market in {target, "BOTH", "ALL"}:
            selected.append(image.get("dataUrl"))
    return [image for image in selected if isinstance(image, str) and image]


def export_briefing(date, briefing, chart_images=None):
    """Export a briefing dict to Notion."""
    cfg = _require_config()
    units = briefing_export_units(briefing)
    exports = []
    for unit in units:
        from features.daily_briefing.service import export_markdown_with_sources

        # 주간 본문에는 참고자료 섹션이 없다(sources 필드가 소유). 내보내기는 markdown만
        # 렌더링하므로 여기서 되붙인다 — 일간은 본문에 이미 있어 그대로 통과한다.
        markdown = export_markdown_with_sources(unit)
        if not markdown:
            parts = []
            for h in (unit.get("headlines") or []):
                parts.append(f"## {h.get('title', '')}")
                body = h.get("body", "")
                if body:
                    parts.append(body)
            markdown = "\n\n".join(parts)

        scope = unit.get("marketScope", "both")
        market_label = MARKET_TAGS.get(scope, "종합")
        type_label = (unit.get("tags") or ["", "기본"])[-1]
        title = f"브리핑 {date} {market_label}"
        images = _briefing_images_for_market(chart_images, scope, allow_legacy=len(units) == 1)
        blocks = markdown_to_blocks(markdown) + _chart_image_blocks(images)
        result = create_page(
            cfg["token"], cfg["dbId"],
            title=title, date_str=date, page_type=f"{market_label} · {type_label}",
            blocks=blocks,
        )
        exports.append({
            "ok": True, "notionUrl": result.get("url", ""),
            "pageId": result.get("id", ""), "title": title,
        })
    first = exports[0] if exports else {"ok": True, "notionUrl": "", "pageId": "", "title": ""}
    return {**first, "exports": exports}


def export_analysis(report, chart_images=None):
    """Export a company analysis report dict to Notion."""
    cfg = _require_config()
    company_raw = report.get("company") or report.get("ticker") or "Unknown"
    if isinstance(company_raw, dict):
        company = (company_raw.get("name") or company_raw.get("ticker") or "Unknown").strip()
    else:
        company = str(company_raw).strip()
    saved_at = report.get("savedAt") or report.get("generatedAt") or ""
    date_str = saved_at[:10] if saved_at else ""
    title = f"{company} 기업분석" + (f" {date_str}" if date_str else "")

    blocks = markdown_to_blocks(report.get("markdown", "")) + _chart_image_blocks(chart_images)
    result = create_page(
        cfg["token"], cfg["dbId"],
        title=title, date_str=date_str, page_type="기업분석",
        subject=company, blocks=blocks,
    )
    return {"ok": True, "notionUrl": result.get("url", ""), "pageId": result.get("id", ""), "title": title}


def export_topic_report(report, chart_images=None):
    """Export a topic report dict to Notion."""
    cfg = _require_config()
    topic_label = (report.get("topicLabel") or report.get("title") or "테마분석").strip()
    date_str = (report.get("date") or report.get("savedAt") or "")[:10]
    title = report.get("title") or (f"{topic_label} 분석" + (f" {date_str}" if date_str else ""))

    blocks = markdown_to_blocks(report.get("markdown", "")) + _chart_image_blocks(chart_images)
    result = create_page(
        cfg["token"], cfg["dbId"],
        title=title, date_str=date_str, page_type="테마분석",
        subject=topic_label, blocks=blocks,
    )
    return {"ok": True, "notionUrl": result.get("url", ""), "pageId": result.get("id", ""), "title": title}
