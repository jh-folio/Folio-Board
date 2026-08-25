"""Read-only longitudinal history for KR daily leader selection."""
from __future__ import annotations

import json
import re
from pathlib import Path

from features.common.workspace import data_dir
_KNOWN = {
    "삼성전자": "kr:005930", "samsungelectronics": "kr:005930", "005930": "kr:005930",
    "sk하이닉스": "kr:000660", "skhynix": "kr:000660", "000660": "kr:000660",
}
_KR_DAILY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.kr\.json$")


def canonical_company_id(subject: str, ticker: str = "") -> str:
    ticker_key = re.sub(r"[^0-9A-Za-z]", "", str(ticker or "")).casefold()
    subject_key = re.sub(r"[^0-9A-Za-z가-힣]", "", str(subject or "")).casefold()
    if ticker_key in _KNOWN:
        return _KNOWN[ticker_key]
    if subject_key in _KNOWN:
        return _KNOWN[subject_key]
    if re.fullmatch(r"\d{6}", ticker_key):
        return f"kr:{ticker_key}"
    if re.match(r"^\d{6}", ticker_key):
        return f"kr:{ticker_key[:6]}"
    return f"kr:name:{subject_key}" if subject_key else ""


def _control(report: dict) -> dict:
    value = report.get("concentrationControl") or {}
    return (value.get("byMarket") or {}).get("kr") or value


def history_rows_from_report(report: dict) -> list[dict]:
    control = _control(report)
    decision = control.get("leaderDecision") or {}
    chosen = set(decision.get("finalPair") or [])
    session_date = str(report.get("sessionDate") or report.get("date") or "")
    rows = []
    for signature in control.get("signatures") or []:
        if not isinstance(signature, dict) or (chosen and signature.get("candidateId") not in chosen):
            continue
        row = dict(signature)
        row["sessionDate"] = session_date
        row["canonicalId"] = str(row.get("canonicalId") or canonical_company_id(row.get("subject"), row.get("ticker")))
        if row["canonicalId"]:
            rows.append(row)
    if not rows:
        # Older reports predate structured concentration signatures.  Preserve
        # appearance history from headings; causal comparison starts accruing
        # only after the structured format exists.
        for subject in re.findall(
            r"^##\s+[34]\.\s+한국장을\s+주도한\s+기업\s+[①②]\s*[—-]\s*(.+?)\s*$",
            str(report.get("markdown") or ""),
            re.MULTILINE,
        ):
            canonical = canonical_company_id(subject)
            if canonical:
                rows.append({
                    "sessionDate": session_date,
                    "subject": subject.strip(),
                    "canonicalId": canonical,
                    "catalysts": [], "mechanisms": [], "outcomes": [], "evidenceIds": [],
                })
    return rows


def load_recent_history(
    *,
    before_date: str,
    reports_dir: Path | None = None,
    session_limit: int = 10,
) -> list[dict]:
    root = Path(reports_dir) if reports_dir is not None else data_dir() / "briefings"
    if not root.exists():
        return []
    dated = []
    for path in root.iterdir():
        match = _KR_DAILY_FILE.fullmatch(path.name)
        if match and match.group(1) < str(before_date or "9999-99-99"):
            dated.append((match.group(1), path))
    rows = []
    for _date, path in sorted(dated, reverse=True)[: max(0, int(session_limit))]:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(report, dict):
            rows.extend(history_rows_from_report(report))
    return rows


def history_metrics(signature: dict, history: list[dict]) -> dict:
    canonical = str(signature.get("canonicalId") or canonical_company_id(signature.get("subject"), signature.get("ticker")))
    matches = [row for row in history or [] if str(row.get("canonicalId") or "") == canonical]
    def causal_similarity(other: dict) -> float:
        ratios = []
        for key in ("catalysts", "mechanisms", "outcomes"):
            left, right = set(signature.get(key) or []), set(other.get(key) or [])
            ratios.append(len(left & right) / max(1, len(left | right)))
        return sum(ratios) / 3

    similarities = [causal_similarity(row) for row in matches]
    max_similarity = max(similarities, default=0.0)
    repeated = sum(value >= 0.67 for value in similarities)
    return {
        "canonicalId": canonical,
        "recentAppearanceCount": len(matches),
        "sameCausalPathCount": repeated,
        "maxCausalSimilarity": round(max_similarity, 3),
        "novelCausalPath": bool(matches) and max_similarity < 0.34,
    }


__all__ = ["canonical_company_id", "history_metrics", "history_rows_from_report", "load_recent_history"]
