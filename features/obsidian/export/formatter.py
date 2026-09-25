"""Obsidian note formatting: YAML frontmatter, wikilink injection, user-notes preservation."""
import re


# ---------------------------------------------------------------------------
# Obsidian Charts YAML block generation
# ---------------------------------------------------------------------------

def _fv(v, scale: float = 1.0, dec: int = 1) -> str:
    if v is None:
        return "null"
    return str(round(v / scale, dec))


def _inline_labels(labels: list) -> str:
    return "[" + ", ".join(f'"{l}"' for l in labels) + "]"


def _inline_data(values: list, scale: float = 1.0, dec: int = 1) -> str:
    return "[" + ", ".join(_fv(v, scale, dec) for v in values) + "]"


def _auto_scale(values: list) -> tuple[float, str]:
    """Return (divisor, unit_label) based on max magnitude."""
    max_val = max((abs(v) for v in values if v is not None), default=0)
    if max_val >= 1e12:
        return 1e12, "T"
    if max_val >= 1e9:
        return 1e9, "B"
    if max_val >= 1e6:
        return 1e6, "M"
    return 1.0, ""


def _bar_block(labels: list, series: list[tuple]) -> str:
    """Render Obsidian Charts bar block. series = [(title, data, scale, dec), ...]"""
    lines = ["```chart", "type: bar", f"labels: {_inline_labels(labels)}", "series:"]
    for title, data, scale, dec in series:
        lines.append(f'  - title: "{title}"')
        lines.append(f"    data: {_inline_data(data, scale, dec)}")
    lines += ["fill: false", "beginAtZero: false", "```"]
    return "\n".join(lines)


def _line_block(labels: list, series: list[tuple]) -> str:
    """Render Obsidian Charts line block. series = [(title, data, scale, dec), ...]"""
    lines = ["```chart", "type: line", f"labels: {_inline_labels(labels)}", "series:"]
    for title, data, scale, dec in series:
        lines.append(f'  - title: "{title}"')
        lines.append(f"    data: {_inline_data(data, scale, dec)}")
    lines += ["fill: false", "beginAtZero: false", "tension: 0.4", "```"]
    return "\n".join(lines)


def _pct(arr: list) -> list:
    return [v * 100 if v is not None else None for v in (arr or [])]


def charts_to_markdown(charts_data: dict) -> str:
    """Convert analysisCharts payload to Obsidian Charts YAML markdown blocks."""
    if not charts_data or not charts_data.get("available"):
        return ""
    charts = charts_data.get("charts") or []
    if not charts:
        return ""

    parts: list[str] = ["## 재무 차트"]

    for chart in charts:
        kind = chart.get("kind", "")
        title = chart.get("title", kind)

        if kind == "performance":
            years = chart.get("years", [])
            revenue = chart.get("revenue") or []
            scale, unit = _auto_scale(revenue)
            parts.append(f"### {title}" + (f" (단위: {unit} USD)" if unit else ""))
            parts.append(_bar_block(years, [
                ("Revenue", revenue, scale, 1),
                ("Operating Income", chart.get("operatingIncome") or [], scale, 1),
                ("Net Income", chart.get("netIncome") or [], scale, 1),
            ]))
            net_margin = _pct(chart.get("netMargin"))
            if any(v is not None for v in net_margin):
                parts.append("**Net Margin %**")
                parts.append(_line_block(years, [("Net Margin %", net_margin, 1.0, 1)]))

        elif kind == "cashflow":
            years = chart.get("years", [])
            cfo = chart.get("operatingCashFlow") or []
            scale, unit = _auto_scale(cfo)
            parts.append(f"### {title}" + (f" (단위: {unit} USD)" if unit else ""))
            parts.append(_bar_block(years, [
                ("Operating CF", cfo, scale, 1),
                ("CapEx", chart.get("capitalExpenditure") or [], scale, 1),
                ("Free CF", chart.get("freeCashFlow") or [], scale, 1),
            ]))
            fcf_margin = _pct(chart.get("fcfMargin"))
            if any(v is not None for v in fcf_margin):
                parts.append("**FCF Margin %**")
                parts.append(_line_block(years, [("FCF Margin %", fcf_margin, 1.0, 1)]))

        elif kind == "margins":
            years = chart.get("years", [])
            parts.append(f"### {title}")
            parts.append(_line_block(years, [
                ("Gross Margin %", _pct(chart.get("grossMargin")), 1.0, 1),
                ("Operating Margin %", _pct(chart.get("operatingMargin")), 1.0, 1),
                ("Net Margin %", _pct(chart.get("netMargin")), 1.0, 1),
            ]))

        elif kind == "dcf":
            scenarios = chart.get("scenarios") or []
            if scenarios:
                labels = [s.get("name", "") for s in scenarios]
                values = [s.get("perShare") for s in scenarios]
                parts.append(f"### {title}")
                parts.append(_bar_block(labels, [("Intrinsic Value / Share", values, 1.0, 2)]))
                if chart.get("currentPrice") is not None:
                    parts.append(f"> Current Price: ${chart['currentPrice']:.2f}")

        elif kind == "scenario_price":
            scenarios = chart.get("scenarios") or []
            if scenarios:
                labels = [s.get("label", "") for s in scenarios]
                values = [s.get("price") for s in scenarios]
                parts.append(f"### {title}")
                parts.append(_bar_block(labels, [("적정가", values, 1.0, 0)]))
                if chart.get("currentPrice") is not None:
                    parts.append(f"> 현재가: ${chart['currentPrice']:.2f}")

        elif kind == "price_return":
            labels = chart.get("labels") or []
            series_map = chart.get("series") or {}
            if labels and series_map:
                parts.append(f"### {title}")
                series = [(sym, vals, 1.0, 1) for sym, vals in series_map.items()]
                parts.append(_bar_block(labels, series))

    return "\n\n".join(parts)

USER_NOTES_MARKER = "\n\n---\n## 사용자 메모\n"


def build_frontmatter(meta: dict) -> str:
    """Build YAML frontmatter block from a dict. None values are skipped."""
    lines = ["---"]
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            s = str(value)
            # Quote strings that contain YAML-special characters
            needs_quote = any(c in s for c in (':', '#', '[', ']', '{', '}', '&', '*', '?', '|', '<', '>', '!', '"', "'"))
            if needs_quote:
                escaped = s.replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
            else:
                lines.append(f"{key}: {s}")
    lines.append("---")
    return "\n".join(lines)


def inject_wikilinks(text: str, names: list[str]) -> str:
    """Wrap first occurrence of each company name in [[wikilinks]].

    Processes longest names first to prevent partial-name replacement.
    Skips names shorter than 3 characters and avoids double-wrapping.
    """
    sorted_names = sorted((n for n in names if n and len(n) >= 3), key=len, reverse=True)
    already_linked: set[str] = set()
    for name in sorted_names:
        if name in already_linked:
            continue
        # Don't re-wrap already-wikilinked text
        if f"[[{name}]]" in text:
            already_linked.add(name)
            continue
        escaped = re.escape(name)
        # Word-boundary aware: avoid matching inside longer words or existing [[...]]
        pattern = r"(?<!\[\[)(?<![A-Za-z0-9가-힣])(" + escaped + r")(?![A-Za-z0-9가-힣])(?!\]\])"
        # Keep citation labels/URLs and code intact. Only prose gets wikilinks.
        protected = [(m.start(), m.end()) for m in re.finditer(
            r"(?ms)```.*?```|~~~.*?~~~|`[^`\n]*`|!?\[[^\]\n]*\]\([^\n]*?\)|https?://[^\s<>]+",
            text,
        )]
        match = next((m for m in re.finditer(pattern, text)
                      if not any(a <= m.start() < b for a, b in protected)), None)
        new_text = text[:match.start()] + "[[" + match.group(1) + "]]" + text[match.end():] if match else text
        if new_text != text:
            text = new_text
            already_linked.add(name)
    return text


def preserve_user_notes(existing_content: str, new_body: str) -> str:
    """Merge new auto-generated content with preserved user notes section.

    Everything after USER_NOTES_MARKER in the existing file is kept intact.
    If no marker exists in the existing file, a blank user-notes section is appended.
    """
    if existing_content and USER_NOTES_MARKER in existing_content:
        _, user_part = existing_content.split(USER_NOTES_MARKER, 1)
        return new_body + USER_NOTES_MARKER + user_part
    return new_body + USER_NOTES_MARKER + "\n"


def strip_duplicate_h1(text: str, title: str) -> str:
    """Remove the first H1 when it duplicates the surrounding note title."""
    body = str(text or "").lstrip()
    expected = str(title or "").strip()
    if not expected:
        return str(text or "")
    match = re.match(r"^#\s+(.+?)\s*(?:\n|$)", body)
    if not match:
        return str(text or "")
    if match.group(1).strip() != expected:
        return str(text or "")
    return body[match.end():].lstrip()
