"""Remove operational provider notes, not source attribution or market facts."""
from __future__ import annotations

import re


_PROVIDER_WARNING = re.compile(r"(?:provider|프로바이더|데이터\s*공급자)\s*(?:경고|warning)", re.I)
_TOSS_API = re.compile(r"(?:Toss|토스(?:증권)?)\s*(?:Open\s*API|오픈\s*API)", re.I)
_PROVIDER_STATE = re.compile(r"설정|연결|집계\s*시장\s*데이터|configured|aggregate\s*market\s*payload", re.I)


def strip_provider_operational_notes(markdown: str) -> tuple[str, int]:
    """Drop only identified operational sentences; preserve neighboring prose.

    A source note such as '원·달러 환율은 yfinance 기준 ...' is still valid.
    This is deterministic and does not call an LLM or alter stored diagnostics.
    """
    removed = 0
    lines = []
    for line in str(markdown or "").splitlines(keepends=True):
        spans = re.split(r"(?<=[.!?。！？])(?=[ \t]+[^\r\n])", line)
        kept = []
        for sentence in spans:
            operational = _PROVIDER_WARNING.search(sentence) or (
                _TOSS_API.search(sentence) and _PROVIDER_STATE.search(sentence)
                and re.search(r"yfinance|provider|공급", sentence, re.I)
            )
            if operational:
                removed += 1
            else:
                kept.append(sentence)
        if kept:
            cleaned = "".join(kept)
            if line.endswith("\n") and not cleaned.endswith("\n"):
                cleaned += "\r\n" if line.endswith("\r\n") else "\n"
            lines.append(cleaned)
        elif line.endswith("\n"):
            # Do not join two previously separate paragraphs.
            lines.append("\n")
    return "".join(lines), removed
