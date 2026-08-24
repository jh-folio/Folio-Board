"""Resolve approved market/macro requirements without silently dropping gaps."""
from __future__ import annotations

from datetime import UTC, datetime

from features.topic_report.macro_data import BOK_SERIES_META, FRED_SERIES_META


_MACRO_ALIASES = {
    "미국 기준금리": "FEDFUNDS",
    "연준 기준금리": "FEDFUNDS",
    "미국 실업률": "UNRATE",
    "미국 cpi": "CPIAUCSL",
    "미국 소비자물가": "CPIAUCSL",
    "비농업고용": "PAYEMS",
    "미국 10년물": "DGS10",
    "미국 2년물": "DGS2",
    "장단기 금리차": "T10Y2Y",
    "한국 기준금리": "722Y001",
    "한국 소비자물가": "731Y003",
    "경상수지": "301Y013",
    "외환보유액": "732Y004",
}


def _macro_id(requirement: str) -> str:
    text = str(requirement or "").strip()
    upper = text.upper()
    if upper in FRED_SERIES_META or upper in BOK_SERIES_META:
        return upper
    lowered = text.casefold()
    for alias, series_id in _MACRO_ALIASES.items():
        if alias in lowered:
            return series_id
    for series_id, label in FRED_SERIES_META.items():
        if lowered in label.casefold() or label.casefold() in lowered:
            return series_id
    for series_id, meta in BOK_SERIES_META.items():
        label = str(meta.get("label") or "")
        if lowered in label.casefold() or label.casefold() in lowered:
            return series_id
    return ""


def resolve_material_requirements(
    plan: dict,
    market_data: dict,
    macro_data: dict,
    *,
    resolved_at: str | None = None,
) -> dict:
    ticker_rows = market_data.get("tickers") if isinstance(market_data.get("tickers"), dict) else {}
    label_to_symbol = {
        str(row.get("label") or "").casefold(): symbol
        for symbol, row in ticker_rows.items()
        if isinstance(row, dict) and str(row.get("label") or "")
    }
    market = []
    for requirement in plan.get("requiredMarketData") or []:
        text = str(requirement or "").strip()
        symbol = text.upper() if text.upper() in ticker_rows else label_to_symbol.get(text.casefold(), "")
        row = ticker_rows.get(symbol) if symbol else None
        if not symbol:
            status, as_of = "unsupported", ""
        elif not isinstance(row, dict) or row.get("error"):
            status, as_of = "failed", ""
        elif row.get("last") is None:
            status, as_of = "missing", ""
        else:
            status, as_of = "available", str(row.get("asOfDate") or "")[:10]
        market.append({
            "requirement": text,
            "symbol": symbol,
            "status": status,
            "asOfDate": as_of,
            "sourceId": f"market_{symbol}" if symbol else "",
        })

    fred = ((macro_data.get("fred") or {}).get("series") or {}) if isinstance(macro_data, dict) else {}
    bok = ((macro_data.get("bok") or {}).get("series") or {}) if isinstance(macro_data, dict) else {}
    macro = []
    for requirement in plan.get("requiredMacroData") or []:
        text = str(requirement or "").strip()
        series_id = _macro_id(text)
        row = fred.get(series_id) or bok.get(series_id) if series_id else None
        if not series_id:
            status, as_of = "unsupported", ""
        elif not isinstance(row, dict):
            status, as_of = "failed", ""
        elif row.get("latest") is None:
            status, as_of = "missing", ""
        else:
            status = "available"
            as_of = str(row.get("latestDate") or row.get("latestPeriod") or "")[:10]
        macro.append({
            "requirement": text,
            "seriesId": series_id,
            "status": status,
            "asOfDate": as_of,
            "sourceId": f"macro_{series_id}" if series_id else "",
        })
    return {
        "schemaVersion": 1,
        "market": market,
        "macro": macro,
        "resolvedAt": resolved_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def material_gap_messages(resolution: dict) -> list[dict]:
    rows = []
    for category in ("market", "macro"):
        for item in resolution.get(category) or []:
            status = str(item.get("status") or "")
            if status == "available":
                continue
            requirement = str(item.get("requirement") or "")
            rows.append({
                "category": f"{category}_data",
                "severity": "high" if status == "failed" else "medium",
                "message": f"필수 {category} 자료 '{requirement}' 상태: {status}",
                "sourceSection": "materialResolution",
            })
    return rows


def material_source_items(resolution: dict, market_data: dict, macro_data: dict) -> list[dict]:
    items = []
    for row in resolution.get("market") or []:
        if row.get("status") == "available":
            items.append({
                "id": row.get("sourceId"),
                "sourceId": row.get("sourceId"),
                "title": f"{row.get('symbol')} market series",
                "source": "yfinance",
                "date": row.get("asOfDate"),
                "type": "market_data",
                "evidenceRole": "data_point",
            })
    for row in resolution.get("macro") or []:
        if row.get("status") == "available":
            items.append({
                "id": row.get("sourceId"),
                "sourceId": row.get("sourceId"),
                "title": f"{row.get('seriesId')} macro series",
                "source": "FRED" if str(row.get("seriesId")) in FRED_SERIES_META else "BOK ECOS",
                "date": row.get("asOfDate"),
                "type": "macro_data",
                "evidenceRole": "data_point",
            })
    return items


__all__ = ["material_gap_messages", "material_source_items", "resolve_material_requirements"]
