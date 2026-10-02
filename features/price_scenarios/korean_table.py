"""spec-3 reading of a DART `stockTotqySttus` common-stock row (spec §2.4).

Pure. Row identification, cell reading and the two table equations. A row that
satisfies both equations exactly lets its empty cumulative cells be read as 0
and its numeric cells as period-end units; anything else stays unproven and the
caller falls back to the general (spec-2) rules. Nothing here guesses units.
"""
from __future__ import annotations

import re

from .decimal_ops import number, source_number

IDENTITY_UNCONFIRMED = "share_count_identity_unconfirmed"
VOTING_NOTICE = "common_row_label_voting_shares"
EMPTY = {"-", "–", "—"}
_PLAIN = re.compile(r"^[0-9]+$")
_COMMAS = re.compile(r"^[0-9]{1,3}(,[0-9]{3})+$")
_FOOTNOTE = re.compile(r"(\*|\(주[0-9]+\))$")
COMMON_LABELS = {"보통주", "보통주식"}
CELLS = ("now_to_isu_stock_totqy", "now_to_dcrs_stock_totqy", "istc_totqy", "redc", "profit_incnr", "rdmstk_repy", "etc")


def normalize_label(label) -> str:
    text = "".join(str(label or "").split())
    while _FOOTNOTE.search(text):
        text = _FOOTNOTE.sub("", text)
    return text


def read_cell(text):
    """('empty' | int | None): None means the cell cannot be read."""
    compact = "".join(str(text if text is not None else "").split())
    if compact in EMPTY:
        return "empty"
    if _PLAIN.match(compact) or _COMMAS.match(compact):
        return int(compact.replace(",", ""))
    return None


def select_common_row(rows: list[dict]):
    """(row, notice) or (None, error code) by the three-way label rule."""
    labelled = [(normalize_label(row.get("se")), row) for row in rows]
    common = [row for label, row in labelled if label in COMMON_LABELS]
    voting = [row for label, row in labelled if label == "의결권있는주식"]
    non_voting = [row for label, row in labelled if label == "의결권없는주식"]
    if len(common) == 1 and not voting and not non_voting:
        return common[0], None
    if not common and len(voting) == 1 and len(non_voting) == 1:
        return voting[0], VOTING_NOTICE
    return None, IDENTITY_UNCONFIRMED


def table_reading(row: dict) -> dict | None:
    """Per-cell reading when both equations hold exactly, else None.

    Returns {"cells": {name: int}, "zeroCells": [names read from an empty cell]}.
    """
    values = {}
    for name in CELLS:
        value = read_cell(row.get(name))
        if value is None:
            return None
        values[name] = value
    if values["now_to_isu_stock_totqy"] == "empty" or values["istc_totqy"] == "empty":
        return None
    numeric = {name: (0 if value == "empty" else value) for name, value in values.items()}
    zero_cells = [name for name, value in values.items() if value == "empty"]
    if numeric["now_to_isu_stock_totqy"] - numeric["now_to_dcrs_stock_totqy"] != numeric["istc_totqy"]:
        return None
    if numeric["redc"] + numeric["profit_incnr"] + numeric["rdmstk_repy"] + numeric["etc"] != numeric["now_to_dcrs_stock_totqy"]:
        return None
    return {"cells": numeric, "zeroCells": zero_cells}


def observation(packet: dict, *, corp_code: str, as_of: str) -> dict:
    """spec-3 year-end observation, or {"state": "unknown", "reason"}.

    Cumulative cells carry `row_arithmetic_zero` (an empty cell proven 0, unit
    free) or `row_arithmetic_period_end_unit` / `explicit_zero` (numeric cells in
    the report's period-end unit) with the seven source cells kept as `rowCells`.
    """
    if not isinstance(packet, dict) or packet.get("status") != "000" or not isinstance(packet.get("list"), list):
        return {"state": "unknown", "reason": "share_count_source_unavailable"}
    rows = [row for row in packet["list"] if isinstance(row, dict) and row.get("corp_code") == corp_code
            and normalize_label(row.get("se")) not in {"합계", "비고"}]
    row, notice = select_common_row(rows)
    if row is None:
        return {"state": "unknown", "reason": notice}
    end, accession = row.get("stlm_dt"), str(row.get("rcept_no") or "")
    filed = f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}"
    if not end or not re.fullmatch(r"\d{14}", accession) or end > as_of or filed > as_of:
        return {"state": "unknown", "reason": "future_share_count_source"}
    reading = table_reading(row)
    cells = {name: row.get(name) for name in CELLS}
    shares = source_number(row.get("istc_totqy"))
    if shares is None or number(shares) <= 0:
        return {"state": "unknown", "reason": "invalid_ending_shares"}
    decreases = {}
    for key, field in (("profitCancellation", "profit_incnr"), ("redemption", "rdmstk_repy")):
        raw = row.get(field)
        entry = {"value": None, "rawCell": raw, "unitDate": None, "unitProof": None}
        if reading is not None:
            was_empty = field in reading["zeroCells"]
            value = reading["cells"][field]
            statement = ("row_arithmetic_zero" if was_empty else "explicit_zero" if value == 0 else "row_arithmetic_period_end_unit")
        elif read_cell(raw) == 0:  # a cell written as numeric 0 stays an explicit zero even when the row arithmetic fails (§2.4)
            value, statement = 0, "explicit_zero"
        else:
            decreases[key] = entry
            continue
        entry.update(value=str(value), unitDate=end, unitProof={
            "source": "dart_report", "accession": accession, "filed": filed, "locator": f"stockTotqySttus.{field}",
            "statement": statement, "sameDayBasis": "post_event",
            "rowCells": {"label": row.get("se"), "accession": accession, "stlm_dt": end, **cells}})
        decreases[key] = entry
    out = {"state": "received", "observation": {"periodEnd": end, "shares": shares, "decreases": decreases,
          "source": {"provider": "dart_stockTotqySttus", "accession": accession, "filed": filed, "corpCode": corp_code,
                     "locator": f"row={normalize_label(row.get('se'))}; istc_totqy"}}}
    if notice:
        out["notice"] = notice
    return out
