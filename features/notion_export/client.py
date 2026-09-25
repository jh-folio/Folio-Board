"""Notion API HTTP client — no external dependencies, uses urllib."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"
# Notion API 상한: rich_text 한 조각 2,000자, 한 요청의 자식 블록 100개.
RICH_TEXT_LIMIT = 2000
MAX_CHILDREN_PER_REQUEST = 100


def _notion_request(token, method, path, body=None):
    url = f"{NOTION_API_BASE}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API HTTP {e.code}: {body_text[:500]}") from e


def upload_image_to_imgbb(base64_img: str, api_key: str) -> str | None:
    """Upload a base64 PNG to imgbb and return the hosted URL, or None on failure."""
    img_data = base64_img.split(",", 1)[1] if "," in base64_img else base64_img
    data = urllib.parse.urlencode({"key": api_key, "image": img_data}).encode()
    req = urllib.request.Request("https://api.imgbb.com/1/upload", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("data", {}).get("url")
    except Exception:
        return None


def create_page(token, database_id, title, date_str, page_type, subject=None, blocks=None):
    """Create a new page in a Notion database and append content blocks."""
    properties = {
        "이름": {"title": [{"text": {"content": title}}]},
        "날짜": {"date": {"start": date_str} if date_str else None},
        "유형": {"select": {"name": page_type}},
    }
    if not date_str:
        del properties["날짜"]
    if subject:
        properties["주제"] = {"rich_text": [{"text": {"content": subject}}]}

    payload = {"parent": {"database_id": database_id}, "properties": properties}
    if blocks:
        payload["children"] = blocks[:100]

    result = _notion_request(token, "POST", "/pages", payload)
    page_id = result.get("id")

    if blocks and len(blocks) > 100 and page_id:
        remaining = blocks[100:]
        while remaining:
            batch = remaining[:100]
            remaining = remaining[100:]
            _notion_request(token, "PATCH", f"/blocks/{page_id}/children", {"children": batch})

    return result


# ── Inline Markdown → Notion rich_text ────────────────────────────────────────

_INLINE_RE = re.compile(
    r"\*\*(.+?)\*\*"              # **bold**
    r"|\*([^*\n]+?)\*"            # *italic*
    r"|_([^_\n]+?)_"              # _italic_
    r"|`([^`\n]+?)`"              # `code`
    r"|\[([^\]]+)\]\(([^)]+)\)"  # [text](url)
)


def _text_piece(content, bold=False, italic=False, code=False):
    return {
        "type": "text",
        # Notion rich_text 한 조각은 2,000자를 넘으면 400이다.
        "text": {"content": str(content or "")[:RICH_TEXT_LIMIT], "link": None},
        "annotations": {
            "bold": bold, "italic": italic,
            "strikethrough": False, "underline": False,
            "code": code, "color": "default",
        },
    }


def _link_piece(content, url):
    return {
        "type": "text",
        "text": {"content": str(content or "")[:RICH_TEXT_LIMIT], "link": {"url": url}},
        "annotations": {
            "bold": False, "italic": False,
            "strikethrough": False, "underline": False,
            "code": False, "color": "default",
        },
    }


def parse_inline(text):
    """Parse inline Markdown into a Notion rich_text list."""
    pieces = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            pieces.append(_text_piece(text[pos:m.start()]))
        if m.group(1) is not None:       # **bold**
            pieces.append(_text_piece(m.group(1), bold=True))
        elif m.group(2) is not None:     # *italic*
            pieces.append(_text_piece(m.group(2), italic=True))
        elif m.group(3) is not None:     # _italic_
            pieces.append(_text_piece(m.group(3), italic=True))
        elif m.group(4) is not None:     # `code`
            pieces.append(_text_piece(m.group(4), code=True))
        else:                            # [text](url)
            pieces.append(_link_piece(m.group(5), m.group(6)))
        pos = m.end()
    if pos < len(text):
        pieces.append(_text_piece(text[pos:]))
    return pieces or [_text_piece("")]


def _block(block_type, rich_text):
    return {"type": block_type, block_type: {"rich_text": rich_text}}


# ── Markdown table → Notion table block ───────────────────────────────────────

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{1,}:?$")


def _table_cells(line):
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _is_separator_row(cells):
    return bool(cells) and all(_TABLE_SEPARATOR_CELL_RE.fullmatch(cell.replace(" ", "")) for cell in cells)


def _table_block(table_lines):
    """Convert consecutive Markdown table lines into one Notion table block."""
    rows = []
    has_header = False
    for line in table_lines:
        cells = _table_cells(line)
        if _is_separator_row(cells):
            has_header = len(rows) == 1
            continue
        rows.append(cells)
    if not rows:
        return None
    width = max(len(cells) for cells in rows)
    children = []
    # Notion은 모든 행의 셀 수가 table_width와 같아야 하고, 한 요청의 자식은 100개까지다.
    for cells in rows[:MAX_CHILDREN_PER_REQUEST]:
        padded = list(cells[:width]) + [""] * (width - len(cells))
        children.append({"type": "table_row", "table_row": {"cells": [parse_inline(cell) for cell in padded]}})
    return {
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": has_header,
            "has_row_header": False,
            "children": children,
        },
    }


def markdown_to_blocks(markdown):
    """Convert a Markdown string to a list of Notion block dicts."""
    from features.common.report_citations import visible_citation_markdown
    blocks = []
    lines = visible_citation_markdown(markdown or "").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.rstrip()

        # Image: ![alt](url)
        img_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", s)
        if img_match:
            url = img_match.group(2).strip()
            if url:
                blocks.append({"type": "image", "image": {"type": "external", "external": {"url": url}}})
            i += 1
            continue

        # Horizontal rule
        if re.fullmatch(r"[-*_]{3,}", s):
            blocks.append({"type": "divider", "divider": {}})
            i += 1
            continue

        # Headings
        h_match = re.match(r"^(#{1,6})\s+(.*)", s)
        if h_match:
            level = min(len(h_match.group(1)), 3)
            btype = f"heading_{level}"
            blocks.append(_block(btype, parse_inline(h_match.group(2).strip())))
            i += 1
            continue

        # Table — 연속한 `| ... |` 행을 하나의 table 블록으로 묶는다.
        # (묶지 않으면 문단 수집 루프가 표 전체를 한 줄로 이어 붙인다)
        if _TABLE_ROW_RE.match(s):
            table_lines = []
            while i < len(lines):
                candidate = lines[i].rstrip()
                if not _TABLE_ROW_RE.match(candidate):
                    break
                table_lines.append(candidate)
                i += 1
            table = _table_block(table_lines)
            if table:
                blocks.append(table)
            continue

        # Bulleted list
        if re.match(r"^[-*]\s", s):
            blocks.append(_block("bulleted_list_item", parse_inline(s[2:])))
            i += 1
            continue

        # Numbered list
        nl_match = re.match(r"^\d+\.\s+(.*)", s)
        if nl_match:
            blocks.append(_block("numbered_list_item", parse_inline(nl_match.group(1))))
            i += 1
            continue

        # Empty line
        if not s:
            i += 1
            continue

        # Paragraph — collect consecutive non-structural lines
        para_lines = []
        while i < len(lines):
            l = lines[i].rstrip()
            if not l:
                break
            if re.match(r"^#{1,6}\s|^[-*]\s|\d+\.\s|^[-*_]{3,}$", l) or _TABLE_ROW_RE.match(l):
                break
            para_lines.append(l)
            i += 1
        text = " ".join(para_lines)
        if text:
            blocks.append(_block("paragraph", parse_inline(text)))

    return blocks
