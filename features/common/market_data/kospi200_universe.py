"""Embedded KOSPI 200 universe for the Korean briefing heatmap.

pykrx's KOSPI/KOSPI200 endpoints now require KRX login credentials
(``KRX_ID`` / ``KRX_PW``), so they are unavailable in most local setups and the
heatmap fell back to a tiny 25-name list.  To always show a full KOSPI 200-sized
universe we embed the constituents (membership + sector + a market-cap snapshot)
in ``config/kospi200_constituents.json`` and fetch only live prices at runtime,
mirroring the S&P 500 approach.

Refresh with ``py -3 -m features.common.market_data.kospi200_universe`` which
reads the Wikipedia "KOSPI 200" constituents table (Company / Symbol / GICS
Sector) and joins a yfinance market-cap snapshot for box sizing.  Sectors are
mapped to familiar Korean GICS-sector names.
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

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/KOSPI_200"

# GICS sector (English) -> familiar Korean label used elsewhere in the app.
GICS_SECTOR_KO = {
    "Information Technology": "정보기술",
    "Financials": "금융",
    "Health Care": "헬스케어",
    "Consumer Discretionary": "경기소비재",
    "Communication Services": "커뮤니케이션서비스",
    "Industrials": "산업재",
    "Consumer Staples": "필수소비재",
    "Materials": "소재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    # The Wikipedia KOSPI 200 table also uses KRX-style group names; map those too.
    "IT": "정보기술",
    "Constructions": "건설",
    "Heavy Industries": "중공업",
    "Energy & Chemicals": "에너지화학",
    "Steels & Materials": "철강소재",
    "Consumer Staples": "필수소비재",
}


def _strip_tags(cell: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell))).strip()


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_wikipedia_kospi200(html_text: str) -> list[dict]:
    """Parse the KOSPI 200 constituents table (Company / Symbol / GICS Sector)."""
    rows: list[dict] = []
    seen = set()
    for table in re.findall(r"<table.*?</table>", html_text or "", re.S):
        if len(re.findall(r"\b\d{6}\b", table)) < 50:
            continue
        for row_html in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)
            if len(cells) < 3:
                continue
            name = _strip_tags(cells[0])
            symbol_match = re.search(r"\d{6}", _strip_tags(cells[1]))
            if not symbol_match:
                continue
            ticker = symbol_match.group(0)
            if ticker in seen:
                continue
            seen.add(ticker)
            gics = _strip_tags(cells[2]) or "기타"
            sector = GICS_SECTOR_KO.get(gics, gics)
            rows.append({
                "ticker": ticker,
                "label": name or ticker,
                "sector": sector,
                "industry": sector,
            })
        if rows:
            break
    return rows


def fetch_wikipedia_html(url: str = WIKIPEDIA_URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Folio-Board/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def _yfinance_market_caps(tickers: list[str]) -> dict:
    import yfinance as yf

    caps = {}
    handles = yf.Tickers(" ".join(f"{ticker}.KS" for ticker in tickers))
    for ticker in tickers:
        try:
            info = handles.tickers[f"{ticker}.KS"].fast_info
            cap = getattr(info, "market_cap", None)
            if cap is None and hasattr(info, "get"):
                cap = info.get("market_cap")
            if cap:
                caps[ticker] = float(cap)
        except Exception:
            continue
    return caps


def build_kospi200_constituents_file(
    path: Path | str | None = None,
    *,
    html_fetcher: Callable[[], str] | None = None,
    cap_fetcher: Callable[[list[str]], dict] | None = None,
) -> dict:
    constituents = parse_wikipedia_kospi200((html_fetcher or fetch_wikipedia_html)())
    if not constituents:
        raise ValueError("Wikipedia KOSPI 200 table returned no rows")
    caps = (cap_fetcher or _yfinance_market_caps)([row["ticker"] for row in constituents])
    companies, missing = [], []
    for row in constituents:
        cap = caps.get(row["ticker"])
        if not cap or cap <= 0:
            missing.append(row["ticker"])
            # keep the name/sector but use a small placeholder cap so it still tiles
            cap = 1.0
        companies.append({**row, "marketCap": float(cap)})
    payload = {
        "asOf": dt.date.today().isoformat(),
        "source": "wikipedia:KOSPI_200 + yfinance market caps",
        "count": len(companies),
        "missingCap": missing,
        "companies": sorted(companies, key=lambda row: row.get("marketCap") or 0, reverse=True),
    }
    target = Path(path) if path is not None else resolve_config("kospi200_constituents.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_kospi200_constituents(path: Path | str | None = None) -> list[dict]:
    target = Path(path) if path is not None else resolve_config("kospi200_constituents.json")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    companies = payload.get("companies") if isinstance(payload, dict) else None
    return companies if isinstance(companies, list) else []


if __name__ == "__main__":  # pragma: no cover - manual refresh entry point
    result = build_kospi200_constituents_file()
    print(f"wrote {result['count']} KOSPI200 constituents, missing caps: {len(result['missingCap'])}")
