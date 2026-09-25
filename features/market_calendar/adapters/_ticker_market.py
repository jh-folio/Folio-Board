"""Infer the listing market for an estimated-calendar ticker.

yfinance suffixes carry the exchange, so a KRX symbol must not be stored with US
metadata: `GET /api/market-calendar?market=KR` filters on the stored column and
would otherwise miss the event while the US segment shows it wrongly.

0.5에서 시장이 넷으로 늘었는데 이 표는 한국 접미사만 알고 있었다. 그래서
`AZN.L`(런던)·`8306.T`(도쿄)·`SAP.DE`(프랑크푸르트)의 실적·배당이 전부 미국
일정으로 저장됐다. 유럽 구성종목 파일이 실제로 쓰는 접미사는 `.L/.PA/.DE/.AS`
넷이고, 일본은 `.T`다.
"""
from __future__ import annotations

KR_SUFFIXES = (".KS", ".KQ")
JP_SUFFIXES = (".T", ".JP")
# 유럽은 국가별 거래소가 갈리지만 Folio Board의 시장 단위는 EUROPE 하나다.
# 타임존은 거래소를 따라간다 — 런던만 GMT/BST로 나머지와 한 시간 어긋난다.
EUROPE_LONDON_SUFFIXES = (".L",)
EUROPE_CONTINENT_SUFFIXES = (".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".LS", ".VI", ".SW", ".F", ".DU")


def market_for_ticker(ticker: str) -> tuple[str, str]:
    """Return (market, timezone) for a yfinance symbol."""
    symbol = str(ticker or "").strip().upper()
    if symbol.endswith(KR_SUFFIXES):
        return "KR", "Asia/Seoul"
    if symbol.endswith(JP_SUFFIXES):
        return "JP", "Asia/Tokyo"
    if symbol.endswith(EUROPE_LONDON_SUFFIXES):
        return "EUROPE", "Europe/London"
    if symbol.endswith(EUROPE_CONTINENT_SUFFIXES):
        return "EUROPE", "Europe/Paris"
    return "US", "America/New_York"
