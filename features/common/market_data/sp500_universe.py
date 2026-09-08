"""Embedded S&P 500 universe with GICS sector / sub-industry classification.

The US briefing heatmap is built from this committed snapshot rather than a
live "top market caps" screener so that:

* membership matches the actual S&P 500 index, and
* sector / sub-industry labels use the familiar GICS taxonomy (the same
  grouping finviz-style maps use) instead of the Nasdaq screener's own buckets.

The file is refreshed periodically with ``build_sp500_constituents_file`` which
joins the Wikipedia constituents table (ticker + GICS) with a market-cap source
for box sizing.  At runtime only daily prices are fetched, so the heatmap no
longer depends on a live screener call.
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
import re
from typing import Any, Callable
import urllib.request

from features.common.config_bootstrap import resolve_config

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def provider_symbol(ticker: Any) -> str:
    """Return the yfinance-style symbol (``BRK.B`` / ``BF/B`` -> ``BRK-B``)."""
    return re.sub(r"[./]", "-", str(ticker or "").strip().upper())


def _join_key(symbol: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())


def _number(value: Any) -> float:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _strip_tags(cell: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell))).strip()


def parse_wikipedia_constituents(html_text: str) -> list[dict]:
    """Parse the ``#constituents`` table into ticker/label/sector/industry rows."""
    table = re.search(r'<table[^>]*id="constituents".*?</table>', html_text or "", re.S)
    if not table:
        return []
    rows: list[dict] = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)
        if len(cells) < 4:
            continue
        ticker = _strip_tags(cells[0])
        if not ticker or ticker.lower() == "symbol":
            continue
        rows.append({
            "ticker": ticker,
            "providerSymbol": provider_symbol(ticker),
            "label": _strip_tags(cells[1]) or ticker,
            "sector": _strip_tags(cells[2]) or "Other",
            "industry": _strip_tags(cells[3]) or "Other",
        })
    return rows


def join_market_caps(constituents: list[dict], caps: dict) -> tuple[list[dict], list[str]]:
    """Attach market caps (keyed by a separator-insensitive symbol) to rows.

    Returns the rows that found a positive cap plus the tickers that did not.
    """
    cap_by_key = {_join_key(symbol): _number(value) for symbol, value in (caps or {}).items()}
    joined, missing = [], []
    for row in constituents:
        cap = cap_by_key.get(_join_key(row.get("ticker")))
        if not cap or cap <= 0:
            missing.append(str(row.get("ticker") or ""))
            continue
        joined.append({**row, "marketCap": cap})
    return joined, missing


def fetch_wikipedia_html(url: str = WIKIPEDIA_URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Folio-Board/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def build_sp500_constituents_file(
    path: Path | str | None = None,
    *,
    html_fetcher: Callable[[], str] | None = None,
    cap_fetcher: Callable[[], dict] | None = None,
) -> dict:
    """Refresh the embedded S&P 500 universe file (membership + GICS + caps)."""
    from features.common.market_data.market_universe import fetch_nasdaq_screener

    html_text = (html_fetcher or fetch_wikipedia_html)()
    constituents = parse_wikipedia_constituents(html_text)
    if not constituents:
        raise ValueError("Wikipedia constituents table returned no rows")

    def _default_caps() -> dict:
        return {
            str(row.get("symbol") or "").upper(): row.get("marketCap")
            for row in fetch_nasdaq_screener()
        }

    caps = (cap_fetcher or _default_caps)()
    companies, missing = join_market_caps(constituents, caps)
    payload = {
        "asOf": dt.date.today().isoformat(),
        "source": "wikipedia:List_of_S&P_500_companies + nasdaq screener caps",
        "count": len(companies),
        "missingCap": missing,
        "companies": sorted(companies, key=lambda row: row.get("marketCap") or 0, reverse=True),
    }
    target = Path(path) if path is not None else resolve_config("sp500_constituents.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_sp500_constituents(path: Path | str | None = None) -> list[dict]:
    target = Path(path) if path is not None else resolve_config("sp500_constituents.json")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    companies = payload.get("companies") if isinstance(payload, dict) else None
    return companies if isinstance(companies, list) else []


if __name__ == "__main__":  # pragma: no cover - manual refresh entry point
    result = build_sp500_constituents_file()
    print(f"wrote {result['count']} companies, missing caps: {len(result['missingCap'])}")
