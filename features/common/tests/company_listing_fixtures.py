"""Opt-in, file-backed company listings for resolver/briefing regressions."""
import json

import pytest


@pytest.fixture(autouse=True, params=["basic", "exchange"])
def company_listing_cache(tmp_path, monkeypatch, request):
    """Use real parsers and ranking, without user caches or test-order state."""
    from features.common import company_resolution as resolution, config_bootstrap

    listings = [
        (50863, "INTEL CORP", "INTC", "Nasdaq"),
        (106040, "WESTERN DIGITAL CORP", "WDC", "Nasdaq"),
        (37996, "FORD MOTOR CO", "F", "NYSE"),
        (1403161, "VISA INC.", "V", "NYSE"),
        (320187, "NIKE, INC.", "NKE", "NYSE"),
        (1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"),
        (1094517, "TOYOTA MOTOR CORP", "TM", "NYSE"),
        (1001250, "ESTEE LAUDER COMPANIES INC", "EL", "NYSE"),
        (1682852, "MODERNA, INC.", "MRNA", "Nasdaq"),
        (723125, "MICRON TECHNOLOGY INC", "MU", "Nasdaq"),
        # Synthetic CIK and unknown venue retain the original name-score case.
        (1, "SK hynix", "SKHY", ""),
    ]
    basic = tmp_path / "company_tickers.json"
    exchange = tmp_path / "company_tickers_exchange.json"
    if request.param == "basic":
        basic.write_text(json.dumps({str(i): {"cik_str": cik, "title": name, "ticker": ticker}
                                    for i, (cik, name, ticker, _) in enumerate(listings)}), encoding="utf-8")
    else:
        exchange.write_text(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                                        "data": listings}), encoding="utf-8")
    dart = tmp_path / "corp_codes.json"
    dart.write_text(json.dumps([{"stock_code": "000660", "corp_name": "SK하이닉스", "corp_eng_name": "SK hynix"}]), encoding="utf-8")
    config_rows = {
        "nikkei225_constituents.json": [{"ticker": "7203", "providerSymbol": "7203.T", "label": "トヨタ自動車", "englishName": "Toyota Motor Corporation"}],
        "europe_core_constituents.json": [{"ticker": "GLE.PA", "label": "Societe Generale"}, {"ticker": "OR.PA", "label": "L'Oreal"}],
        "kospi200_constituents.json": [{"ticker": "000660", "label": "SK hynix"}, {"ticker": "005930", "label": "Samsung Electronics"}],
        "foreign_company_aliases.json": {"aliases": {}},
    }
    for name, rows in config_rows.items():
        (tmp_path / name).write_text(json.dumps(rows), encoding="utf-8")
    original_resolve = config_bootstrap.resolve_config
    monkeypatch.setattr(config_bootstrap, "resolve_config", lambda name: tmp_path / name if name in config_rows else original_resolve(name))
    monkeypatch.setattr(resolution, "company_universe", lambda: [
        {"ticker": "000660", "name": "SK hynix", "market": "KR", "aliases": ["SK하이닉스"]},
        {"ticker": "005930", "name": "Samsung Electronics", "market": "KR", "aliases": ["삼성전자"]},
        {"ticker": "NVDA", "name": "NVIDIA", "market": "US"},
        {"ticker": "AMD", "name": "AMD", "market": "US"},
    ])
    monkeypatch.setattr(resolution, "SEC_TICKER_CACHE_PATH", basic)
    monkeypatch.setattr(resolution, "SEC_TICKER_EXCHANGE_PATH", exchange)
    monkeypatch.setattr(resolution, "DART_CORP_CODES_PATH", dart)
    monkeypatch.setattr(resolution, "_INDEX_CACHE", None)
    monkeypatch.setattr(resolution, "_INDEX_STAMP", None)
