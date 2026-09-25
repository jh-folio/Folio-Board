"""Shared Wikipedia table parsing for the Europe and Japan universes.

The S&P 500 and KOSPI 200 universes already take membership from Wikipedia and
join a market-cap source for box sizing. Europe and Japan follow the same shape,
so the fetching and cell-stripping live here instead of twice.

Sector labels come from the price provider rather than from each index's own
Wikipedia column. The four European tables use four different taxonomies — ICB,
Prime Standard, GICS sub-industry — and a heatmap grouped by four vocabularies
at once is not a grouping. One provider taxonomy across every market is both
consistent and free of a hand-written mapping that would rot.
"""
from __future__ import annotations

import html
import re
import urllib.request
from typing import Callable

_USER_AGENT = "Mozilla/5.0 Folio-Board/1.0"


def fetch_wikipedia_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def strip_cell(cell: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell or ""))).strip()


def wikitables(html_text: str) -> list[str]:
    return re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>.*?</table>', html_text or "", re.S)


def table_rows(table_html: str) -> list[list[str]]:
    """Data rows as stripped cell lists; header-only rows are dropped."""
    rows = []
    for row_html in re.findall(r"<tr[ >](.*?)</tr>", table_html or "", re.S):
        if "<td" not in row_html:
            continue
        rows.append([strip_cell(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)])
    return rows


def enrich_with_provider_metadata(
    rows: list[dict],
    *,
    info_fetcher: Callable[[str], dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """Attach sector, market cap, and cap currency from the price provider.

    Names the provider cannot resolve are returned separately rather than
    dropped silently — a universe quietly missing a third of its members would
    still render a plausible-looking heatmap.
    """
    fetch = info_fetcher or _yfinance_info
    enriched: list[dict] = []
    missing: list[str] = []
    for row in rows:
        symbol = str(row.get("providerSymbol") or "").strip()
        info = fetch(symbol) if symbol else {}
        cap = info.get("marketCap")
        if not symbol or not cap:
            missing.append(symbol or str(row.get("label") or ""))
            continue
        enriched.append({
            **row,
            # 위키백과 표기는 자국어다(`トヨタ自動車`). 그것만 두면 "Toyota"로
            # 찾을 때 자국 상장이 후보에 아예 없고 미국 ADR만 걸린다.
            "englishName": str(info.get("englishName") or "").strip(),
            "sector": str(info.get("sector") or "Other"),
            "industry": str(info.get("industry") or info.get("sector") or "Other"),
            "marketCap": float(cap),
            "capCurrency": str(info.get("financialCurrency") or info.get("currency") or "").upper(),
        })
    return enriched, missing


def _yfinance_info(symbol: str) -> dict:  # pragma: no cover - network
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
    except Exception:
        return {}
    # LSE 종목은 시세가 펜스(GBp)로 오지만 marketCap은 파운드다. 시가총액 통화를
    # 시세 통화로 읽으면 영국 기업이 100배 커진다.
    currency = str(info.get("currency") or "").strip()
    return {
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "marketCap": info.get("marketCap"),
        "currency": "GBP" if currency == "GBp" else currency,
        "financialCurrency": None,
        "englishName": info.get("longName") or info.get("shortName"),
    }
