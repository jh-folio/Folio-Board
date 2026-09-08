from __future__ import annotations

from collections.abc import Callable, Iterable
import math

try:
    import polars as pl
except Exception:  # pragma: no cover - optional dependency fallback
    pl = None


def polars_enabled() -> bool:
    return pl is not None


def sort_records(records: Iterable[dict], fields: list[str], descending: bool | list[bool] = True) -> list[dict]:
    rows = list(records or [])
    if not rows:
        return []
    if pl is None:
        return sorted(rows, key=lambda row: tuple(row.get(field, 0) or 0 for field in fields), reverse=bool(descending))
    try:
        sort_rows = []
        for idx, row in enumerate(rows):
            sort_row = {"_idx": idx}
            for field in fields:
                value = row.get(field)
                if value is None:
                    value = "" if field.lower().endswith(("date", "time")) else 0
                sort_row[field] = value
            sort_rows.append(sort_row)
        frame = pl.DataFrame(sort_rows)
        if isinstance(descending, list):
            reverse_flags = descending
        else:
            reverse_flags = [bool(descending)] * len(fields)
        order = frame.sort(fields, descending=reverse_flags).get_column("_idx").to_list()
        return [rows[int(idx)] for idx in order]
    except Exception:
        return sorted(rows, key=lambda row: tuple(row.get(field, 0) or 0 for field in fields), reverse=True)


def top_records(records: Iterable[dict], fields: list[str], limit: int, descending: bool | list[bool] = True) -> list[dict]:
    return sort_records(records, fields, descending=descending)[: max(0, int(limit or 0))]


def filter_archive_records(records: Iterable[dict], start_iso: str = "", end_iso: str = "", source: str = "") -> list[dict]:
    rows = list(records or [])
    if not rows:
        return []
    if pl is None:
        out = []
        for row in rows:
            value = row.get("timestampSort") or ""
            if (start_iso or end_iso) and not value:
                continue
            if start_iso and value and value < start_iso:
                continue
            if end_iso and value and value > end_iso:
                continue
            if source and row.get("source") != source:
                continue
            out.append(row)
        return out
    try:
        frame = pl.DataFrame([
            {
                "_idx": row.get("_idx"),
                "timestampSort": row.get("timestampSort") or "",
                "source": row.get("source") or "",
            }
            for row in rows
        ])
        expr = pl.lit(True)
        if start_iso or end_iso:
            expr = expr & pl.col("timestampSort").cast(pl.Utf8).str.len_chars().gt(0)
        if start_iso:
            expr = expr & (pl.col("timestampSort") >= start_iso)
        if end_iso:
            expr = expr & (pl.col("timestampSort") <= end_iso)
        if source:
            expr = expr & (pl.col("source") == source)
        idxs = frame.filter(expr).get_column("_idx").to_list()
        by_idx = {row["_idx"]: row for row in rows}
        return [by_idx[idx] for idx in idxs if idx in by_idx]
    except Exception:
        out = []
        for row in rows:
            value = row.get("timestampSort") or ""
            if (start_iso or end_iso) and not value:
                continue
            if start_iso and value and value < start_iso:
                continue
            if end_iso and value and value > end_iso:
                continue
            if source and row.get("source") != source:
                continue
            out.append(row)
        return out


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _finite_sum(values: Iterable[object]) -> float | None:
    total = 0.0
    for value in values:
        number = _finite_number(value)
        if number is None:
            return None
        total += number
        if not math.isfinite(total):
            return None
    return total


def _finite_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    result = left - right
    return result if math.isfinite(result) else None


def _finite_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _append_calculation_reason(row: dict, reason: str) -> None:
    existing = row.get("calculationUnavailable")
    reasons = list(existing) if isinstance(existing, list) else []
    if reason not in reasons:
        reasons.append(reason)
    row["calculationUnavailable"] = reasons


def _has_calculation_reason(row: dict, reasons: set[str]) -> bool:
    value = row.get("calculationUnavailable")
    return isinstance(value, list) and any(reason in reasons for reason in value)


def aggregate_portfolio(rows: Iterable[dict]) -> dict:
    """Aggregate display floats without ever returning ``NaN`` or infinity.

    Portfolio authority strings remain untouched in ``items``.  The derived
    values have already been projected to floats; when an aggregate or ratio
    exceeds that display domain it is explicitly unavailable rather than a
    JSON-unsafe pseudo-number.
    """
    items = list(rows or [])
    if not items:
        return {"rows": [], "summary": []}

    groups: dict[str, dict] = {}
    for row in items:
        currency = str(row.get("quoteCurrency") or row.get("currency") or "USD")
        group = groups.setdefault(currency, {"market": [], "cost": [], "positions": 0, "rows": []})
        group["rows"].append(row)
        market_value = row.get("marketValue")
        if market_value is not None:
            if _finite_number(market_value) is None:
                _append_calculation_reason(row, "market_value_unavailable")
            else:
                group["market"].append(market_value)
                group["positions"] += 1
        cost = row.get("cost")
        if cost is not None:
            if _finite_number(cost) is None:
                _append_calculation_reason(row, "cost_unavailable")
            else:
                group["cost"].append(cost)

    summary = []
    for currency, group in groups.items():
        # A missing quote has long been a partial-display condition.  In
        # contrast, a U.1 arithmetic failure proves that this currency total
        # would be incomplete, so never present the remaining rows as a total.
        market_incomplete = any(_has_calculation_reason(row, {"market_value_unavailable"}) for row in group["rows"])
        cost_incomplete = any(_has_calculation_reason(row, {"cost_unavailable"}) for row in group["rows"])
        pnl_incomplete = market_incomplete or cost_incomplete or any(_has_calculation_reason(row, {"pnl_unavailable"}) for row in group["rows"])
        total = None if market_incomplete else _finite_sum(group["market"])
        cost = None if cost_incomplete else _finite_sum(group["cost"])
        reasons: list[str] = []
        if total is None:
            reasons.append("market_value_total_unavailable")
            for row in group["rows"]:
                if row.get("marketValue") is not None:
                    _append_calculation_reason(row, "market_value_total_unavailable")
        if cost is None:
            reasons.append("cost_total_unavailable")
        pnl = None if pnl_incomplete else (_finite_difference(total, cost) if cost not in (None, 0.0) else None)
        if cost not in (None, 0.0) and pnl is None:
            reasons.append("pnl_unavailable")
        pnl_pct = _finite_ratio(pnl, cost)
        if pnl is not None and cost not in (None, 0.0) and pnl_pct is None:
            reasons.append("pnl_pct_unavailable")
        for row in group["rows"]:
            market_value = _finite_number(row.get("marketValue"))
            weight = _finite_ratio(market_value, total)
            row["weight"] = weight
            if market_value is not None and total is None:
                _append_calculation_reason(row, "weight_unavailable")
            elif market_value is not None and total not in (None, 0.0) and weight is None:
                _append_calculation_reason(row, "weight_unavailable")
        summary.append({
            "currency": currency,
            "marketValue": total,
            "cost": cost,
            "pnl": pnl,
            "pnlPct": pnl_pct,
            "positions": group["positions"],
            "calculationUnavailable": reasons,
        })
    return {"rows": items, "summary": summary}


def aggregate_counts(records: Iterable[dict], key_fn: Callable[[dict], str], latest_field: str = "date") -> list[dict]:
    rows = []
    for idx, record in enumerate(records or []):
        key = key_fn(record)
        if not key:
            continue
        rows.append({"_idx": idx, "key": key, "latest": record.get(latest_field, "")})
    if not rows:
        return []
    if pl is None:
        counts = {}
        for row in rows:
            entry = counts.setdefault(row["key"], {"key": row["key"], "count": 0, "latest": ""})
            entry["count"] += 1
            entry["latest"] = max(entry["latest"], row["latest"])
        return sorted(counts.values(), key=lambda item: (item["count"], item["latest"]), reverse=True)
    try:
        return (
            pl.DataFrame(rows)
            .group_by("key")
            .agg([pl.len().alias("count"), pl.col("latest").max().alias("latest")])
            .sort(["count", "latest"], descending=True)
            .to_dicts()
        )
    except Exception:
        saved = pl
        try:
            globals()["pl"] = None
            return aggregate_counts(records, key_fn, latest_field=latest_field)
        finally:
            globals()["pl"] = saved

