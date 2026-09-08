"""Conservative briefing repair guard: edits may omit/reorder known text.

This is not an entailment model. A new paraphrase is rejected rather than
treated as proof; optional editing failure keeps the original report.
"""
import re


def preserves_briefing_input(original: str, candidate: str, sources=()) -> bool:
    def normalize(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()
    allowed = [normalize(original)]
    allowed.extend(normalize(row.get("writerExcerpt")) for row in sources if isinstance(row, dict))
    for raw in re.split(r"\n+|(?<=[.!?。])\s+", str(candidate or "")):
        text = normalize(re.sub(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+)", "", raw))
        if text and not any(text in source for source in allowed):
            return False
    return True
