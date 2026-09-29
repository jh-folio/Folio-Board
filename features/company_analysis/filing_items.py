#!/usr/bin/env python3
from __future__ import annotations

import re

from features.common.utils import strip_html_text

DEFAULT_ITEM_LIMITS = {
    "1": 4200,
    "1A": 3200,
    "7": 5200,
    "7A": 2200,
    "8": 1800,
}

ITEM_LABELS = {
    "1": "Item 1. Business",
    "1A": "Item 1A. Risk Factors",
    "7": "Item 7. Management's Discussion and Analysis",
    "7A": "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Item 8. Financial Statements and Supplementary Data",
}

ITEM_ORDER = ["1", "1A", "1B", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B"]


def normalize_text(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def readable_filing_text(text: str) -> str:
    """Return a compact text view from local SEC/DART/IR HTML or text filings."""
    value = strip_html_text(text)
    value = re.sub(r"\s+", " ", value)
    return normalize_text(value)


def _item_heading_regex() -> re.Pattern:
    item_tokens = "|".join(re.escape(item) for item in sorted(ITEM_ORDER, key=len, reverse=True))
    return re.compile(
        rf"(?i)\b(?:PART\s+[IVX]+\s*)?ITEM\s+({item_tokens})\s*[\.\-:]?\s+(.{{0,140}})"
    )


def extract_items(text: str) -> dict[str, str]:
    body = normalize_text(text)
    if not body:
        return {}
    matches = list(_item_heading_regex().finditer(body))
    if len(matches) < 2:
        return {}

    candidates: dict[str, list[str]] = {}
    for idx, match in enumerate(matches):
        item = match.group(1).upper()
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        chunk = normalize_text(body[start:end])
        word_count = len(re.findall(r"[A-Za-z0-9가-힣]+", chunk))
        if word_count < 80:
            continue
        candidates.setdefault(item, []).append(chunk)

    # SEC filings often include a table of contents before the real section.
    # Keep the longest chunk for each item, which is usually the body section.
    return {item: max(chunks, key=len) for item, chunks in candidates.items()}


def select_analysis_items(text: str, wanted: list[str] | None = None, limits: dict[str, int] | None = None) -> list[dict]:
    wanted = wanted or ["1", "1A", "7", "7A", "8"]
    limits = {**DEFAULT_ITEM_LIMITS, **(limits or {})}
    items = extract_items(text)
    selected = []
    for item in wanted:
        content = items.get(item)
        if not content:
            continue
        limit = limits.get(item, 2500)
        selected.append(
            {
                "item": item,
                "label": ITEM_LABELS.get(item, f"Item {item}"),
                "text": content[:limit],
                "availableChars": len(content),
            }
        )
    return selected


FILING_EXCERPT_THEMES = [
    {
        "label": "Business / company overview",
        "item": "business",
        "keywords": ["business", "overview", "customers", "services", "products", "segment", "revenue"],
        "limit": 2400,
    },
    {
        "label": "Risk factors",
        "item": "risk",
        "keywords": ["risk factors", "material risks", "regulatory", "competition", "liquidity", "launch", "license"],
        "limit": 2600,
    },
    {
        "label": "Growth strategy",
        "item": "growth",
        "keywords": ["growth strategy", "strategy", "investment", "capacity", "expansion", "starship", "starlink", "ai"],
        "limit": 2200,
    },
    {
        "label": "Financial / operating discussion",
        "item": "financial",
        "keywords": ["revenue", "cash flow", "capital expenditures", "margin", "profitability", "liquidity"],
        "limit": 2200,
    },
    {
        "label": "Regulatory / legal matters",
        "item": "regulation",
        "keywords": ["regulatory", "faa", "license", "approval", "legal", "government", "compliance"],
        "limit": 1800,
    },
]


def _excerpt_around(text: str, index: int, limit: int) -> str:
    start = max(0, index - limit // 4)
    end = min(len(text), start + limit)
    start = max(0, end - limit)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."
    return excerpt


def _keyword_score(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


def select_filing_keyword_excerpts(text: str, max_excerpts: int = 5, *, themes=None) -> list[dict]:
    """Select useful excerpts from local filings that do not expose 10-K/10-Q Item headings.

    S-1/F-1/prospectus/proxy HTML often arrives as saved SEC HTML where Item
    headings are unavailable or table-layout noise hides them. These excerpts
    keep local official material usable without treating it as structured 10-K
    evidence.
    """
    body = readable_filing_text(text)
    if not body:
        return []
    selected = []
    used_spans: list[tuple[int, int]] = []
    lower = body.lower()
    for theme in FILING_EXCERPT_THEMES if themes is None else themes:
        best_idx = -1
        best_kw = ""
        for keyword in theme["keywords"]:
            idx = lower.find(keyword.lower())
            if idx >= 0 and (best_idx < 0 or idx < best_idx):
                best_idx = idx
                best_kw = keyword
                if theme.get("preferKeywordOrder"):
                    break
        if best_idx < 0:
            continue
        limit = int(theme.get("limit", 2000))
        start = max(0, best_idx - limit // 4)
        end = min(len(body), start + limit)
        if any(not (end < a or start > b) for a, b in used_spans):
            continue
        excerpt = _excerpt_around(body, best_idx, limit)
        if len(re.findall(r"[A-Za-z0-9가-힣]+", excerpt)) < 60:
            continue
        used_spans.append((start, end))
        selected.append(
            {
                "item": theme["item"],
                "label": theme["label"],
                "text": excerpt,
                "availableChars": len(body),
                "keywords": [kw for kw in theme["keywords"] if kw.lower() in excerpt.lower()] or [best_kw],
                "score": 45 + _keyword_score(excerpt, theme["keywords"]) * 5,
            }
        )
        if len(selected) >= max_excerpts:
            break
    return selected

