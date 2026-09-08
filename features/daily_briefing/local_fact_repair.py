"""One deterministic, source-bound correction pass; never calls a model."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from features.daily_briefing.finalize import _Fact


CORRECTABLE_KINDS = frozenset({
    "value_mismatch", "unit_mismatch", "direction_mismatch",
    "relative_strength_mismatch", "date_mismatch",
})
_UNITS = {"points": "포인트", "krw": "원", "usd": "달러", "percent": "%", "days": "거래일"}
_CELL_NUMBER = re.compile(r"([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(%|포인트|points?|pt|원|krw|달러|usd)?", re.I)


def _known_fact(rows: list[_Fact]) -> _Fact | None:
    """Do not choose arbitrarily between conflicting input observations."""
    if not rows:
        return None
    for attribute in ("value", "change_pct"):
        values = [getattr(row, attribute) for row in rows if getattr(row, attribute) is not None]
        if values and max(values) - min(values) > 1e-6:
            return None
    for attribute in ("date", "unit"):
        values = {getattr(row, attribute) for row in rows if getattr(row, attribute)}
        if len(values) > 1:
            return None
    return max(rows, key=lambda row: (row.value is not None) + (row.change_pct is not None))


def _statement(fact: _Fact) -> str:
    """State observations without inventing a replacement causal explanation."""
    bits = []
    if fact.value is not None:
        unit = _UNITS.get(fact.unit, "")
        number = f"{fact.value:,.2f}" if not float(fact.value).is_integer() else f"{fact.value:,.0f}"
        bits.append(f"{number}{unit}")
    if fact.change_pct is not None:
        bits.append(f"등락률 {fact.change_pct:+.2f}%")
    if not bits:
        return ""
    date = f" ({fact.date})" if fact.date else ""
    return f"{fact.label or fact.key}: {', '.join(bits)}{date}"


def _correct_table_row(old: str, group: list[dict], known: list[_Fact]) -> str:
    """Keep table columns intact; ambiguous prose cells remain for revalidation."""
    if len(known) != 1:
        return old
    fact = known[0]
    fix_value = any(row["kind"] == "unit_mismatch" or (
        row["kind"] == "value_mismatch" and row.get("unit") != "percent") for row in group)
    fix_percent = any(row["kind"] == "value_mismatch" and row.get("unit") == "percent" for row in group)
    kinds = {row["kind"] for row in group}
    cells = re.split(r"(?<!\\)\|", old)
    for index, cell in enumerate(cells):
        value = cell.strip()
        bold = value.startswith("**") and value.endswith("**")
        bare = value[2:-2] if bold else value
        replacement = None
        match = _CELL_NUMBER.fullmatch(bare)
        if match:
            raw, unit = match.groups()
            unit = unit or ""
            actual = float(raw.replace(",", ""))
            tolerance = 0.5 * 10 ** (-len(raw.split(".")[1]) if "." in raw else 0)
            if unit == "%" and fix_percent and fact.change_pct is not None:
                agrees = abs(actual - fact.change_pct) <= tolerance if raw.startswith(("+", "-")) else abs(abs(actual) - abs(fact.change_pct)) <= tolerance
                if not agrees:
                    replacement = f"{fact.change_pct:+.2f}%"
            elif unit != "%" and fix_value and fact.value is not None:
                if abs(actual - fact.value) > tolerance or "unit_mismatch" in kinds:
                    replacement = f"{fact.value:,.2f}{_UNITS.get(fact.unit, '')}"
        elif ("direction_mismatch" in kinds or fix_percent) and fact.change_pct is not None and bare in {"상승", "하락", "강세", "약세", "보합"}:
            replacement = "상승" if fact.change_pct > 0 else "하락" if fact.change_pct < 0 else "보합"
        elif "date_mismatch" in kinds and re.fullmatch(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}", bare):
            replacement = fact.date or None
        if replacement is not None:
            if bold:
                replacement = "**" + replacement + "**"
            start = len(cell) - len(cell.lstrip())
            cells[index] = cell[:start] + replacement + cell[len(cell.rstrip()):]
    return "|".join(cells)


def correct_verified_passages(markdown: str, findings: list[dict], facts: list[_Fact]) -> tuple[str, dict]:
    """Replace only identified faulty sentences with their known observations.

    Adjacent sentences, headings, source lists and all other report data remain
    untouched. Missing locations or conflicting input values are not guessed.
    """
    by_key: dict[str, list[_Fact]] = defaultdict(list)
    for fact in facts:
        by_key[fact.key].append(fact)
    grouped: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for finding in findings:
        begin, end = finding.get("bodyStart"), finding.get("bodyEnd")
        if (finding.get("kind") in CORRECTABLE_KINDS and isinstance(begin, int)
                and isinstance(end, int) and 0 <= begin < end <= len(markdown)):
            grouped[(begin, end)].append(finding)
    edits = []
    codes: set[str] = set()
    for (begin, end), group in sorted(grouped.items()):
        keys = list(dict.fromkeys(key for row in group for key in (row.get("factKey"), row.get("benchmark")) if key))
        known = [_known_fact(by_key.get(key, [])) for key in keys]
        if not known or any(fact is None or not _statement(fact) for fact in known):
            continue
        old = markdown[begin:end]
        if old.strip().startswith("|") and old.strip().endswith("|"):
            new = _correct_table_row(old, group, known)
        else:
            # Retain the list/summary role rather than breaking the output contract.
            prefix = re.match(r"\s*(?:(?:[-*·]|\d+[.)])\s+)?(?:\*\*한 줄 결론\s*:\*\*\s*)?", old).group(0)
            new = prefix + "; ".join(_statement(fact) for fact in known if fact is not None) + "."
        if old == new:
            continue
        edits.append((begin, end, new))
        codes.update(row["kind"] for row in group)
    for begin, end, new in reversed(edits):
        markdown = markdown[:begin] + new + markdown[end:]
    return markdown, {
        "localCorrectionPassCount": int(bool(edits)),
        "localCorrectedPassageCount": len(edits),
        "localCorrectionReasonCodes": sorted(codes),
    }
