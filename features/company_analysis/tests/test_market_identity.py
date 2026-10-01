import json
from types import SimpleNamespace

import pytest

from features.company_analysis import dart_client, report_rules
from features.company_analysis.market_identity import market_identity


def profile(cls="K", ticker="196170"):
    return {"status": "000", "corp_code": "00989619", "stock_code": ticker,
            "corp_cls": cls, "acc_mt": "12", "induty_code": "21210"}


@pytest.mark.parametrize("cls,symbol,exchange", [("K", "196170.KQ", "KOSDAQ"), ("Y", "196170.KS", "KOSPI")])
def test_official_exchange_drives_the_actual_company_analysis_provider_request(monkeypatch, tmp_path, cls, symbol, exchange):
    import yfinance
    import pandas as pd
    called = []
    monkeypatch.setattr(dart_client, "fetch_company_profile", lambda *a: {"ok": True, "profile": profile(cls)})
    monkeypatch.setattr(report_rules, "data_dir", lambda: tmp_path)
    def stock(requested):
        called.append(requested)
        return SimpleNamespace(fast_info={}, get_info=lambda: {"currency": "KRW", "currentPrice": 100},
                               cashflow=pd.DataFrame({pd.Timestamp("2025-12-31"): [30, -10]},
                                                     index=["Operating Cash Flow", "Capital Expenditure"]))
    monkeypatch.setattr(yfinance, "Ticker", stock)
    company = {"market": "KR", "ticker": "196170", "corpCode": "00989619"}
    result = report_rules.fetch_market_valuation_data(company)
    assert called == [symbol]
    assert result["ticker"] == symbol and result["exchange"] == exchange
    assert result["exchangeSource"] == "dart_corp_cls"
    assert report_rules.fetch_market_valuation_data(company) == result
    assert called == [symbol]  # cache uses the same confirmed exchange
    monkeypatch.setattr(dart_client, "fetch_company_profile", lambda *a: {
        "ok": True, "profile": profile(cls), "warning": "using cached DART data after fetch error"})
    assert report_rules.fetch_market_valuation_data(company)["exchangeWarning"] == "using cached DART data after fetch error"
    assert called == [symbol]


@pytest.mark.parametrize("packet,reason", [
    ({"ok": False, "reason": "dart_company_unavailable"}, "dart_company_unavailable"),
    ({"ok": True, "profile": profile("N")}, "exchange_not_supported"),
    ({"ok": True, "profile": profile("E")}, "exchange_not_supported"),
    ({"ok": True, "profile": profile(ticker="196175")}, "dart_listing_identity_mismatch"),
])
def test_unconfirmed_or_other_listing_never_tries_a_suffix(monkeypatch, tmp_path, packet, reason):
    import yfinance
    monkeypatch.setattr(dart_client, "fetch_company_profile", lambda *a: packet)
    monkeypatch.setattr(report_rules, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(yfinance, "Ticker", lambda *a: pytest.fail("must not query guessed exchange"))
    result = report_rules.fetch_market_valuation_data({"market": "KR", "ticker": "196170", "corpCode": "00989619"})
    assert result == {"ok": False, "reason": reason}


def test_corp_resolution_and_identity_confirmation_remain_separate(monkeypatch, tmp_path):
    monkeypatch.setattr(dart_client, "resolve_dart_company", lambda *a: {"corpCode": "00989619"})
    monkeypatch.setattr(dart_client, "fetch_company_profile", lambda *a: {"ok": True, "profile": profile()})
    assert market_identity({"market": "KR", "ticker": "196170"}, tmp_path)["providerSymbol"] == "196170.KQ"
    assert market_identity({"market": "US", "ticker": "MSFT"}, tmp_path)["providerSymbol"] == "MSFT"


def test_fresh_official_cache_is_readable_without_key_and_preserves_metadata(monkeypatch, tmp_path):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    packet = profile()
    path = tmp_path / "companies" / "00989619.json"
    dart_client._write_json(path, packet)
    monkeypatch.setattr(dart_client, "_request_json", lambda *a, **kw: pytest.fail("cache must be read without network"))
    result = dart_client.fetch_company_profile("00989619", tmp_path)
    assert result["ok"] is True and result["profile"] == packet
    assert not list(path.parent.glob("*.tmp"))
    monkeypatch.setattr(dart_client, "_fresh", lambda *a, **kw: False)
    assert dart_client.fetch_company_profile("00989619", tmp_path)["reason"] == "missing_dart_api_key"


@pytest.mark.parametrize("packet,reason", [(None, "dart_company_unavailable"),
    ({"status": "013"}, "dart_company_unavailable"),
    ({**profile(), "corp_code": "00126380"}, "dart_company_identity_mismatch")])
def test_company_api_errors_and_wrong_corporation_are_not_metadata(monkeypatch, tmp_path, packet, reason):
    monkeypatch.setattr(dart_client, "_request_json", lambda *a, **kw: (packet, ""))
    assert dart_client.fetch_company_profile("00989619", tmp_path, api_key="test")["reason"] == reason


def test_durable_cache_failure_preserves_previous_packet(monkeypatch, tmp_path):
    path = tmp_path / "companies" / "00989619.json"
    previous = profile("Y")
    dart_client._write_json(path, previous)
    monkeypatch.setattr(dart_client, "_fresh", lambda *a, **kw: False)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(profile("K")).encode()
    monkeypatch.setattr(dart_client.urllib.request, "urlopen", lambda *a, **kw: Response())
    def failed(*args): raise PermissionError("cache locked")
    monkeypatch.setattr(dart_client, "write_bytes_atomic", failed)
    result = dart_client.fetch_company_profile("00989619", tmp_path, api_key="test")
    assert result["ok"] and result["warning"] == "using cached DART data after fetch error"
    assert json.loads(path.read_text()) == previous


@pytest.mark.parametrize("shape,known", [(4, True), (3, False)])
def test_exchange_cache_upgrade_does_not_discard_verified_legacy_currency(monkeypatch, tmp_path, shape, known):
    import datetime as dt
    import yfinance
    monkeypatch.setattr(report_rules, "data_dir", lambda: tmp_path)
    def unavailable(*a): raise RuntimeError("provider unavailable")
    monkeypatch.setattr(yfinance, "Ticker", unavailable)
    packet = {"shape": shape, "ok": True, "currency": "USD", "quoteCurrency": "USD", "currencyKnown": True,
              "financialCurrency": "USD", "financialCurrencyKnown": True,
              "marketValueCurrency": "USD", "marketValueCurrencyKnown": True}
    report_rules._write_json(tmp_path / "company-analysis" / "market-cache" / "MSFT.json",
                             {"fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "data": packet})
    result = report_rules.fetch_market_valuation_data({"market": "US", "ticker": "MSFT"})
    assert result["currencyKnown"] is known and result["financialCurrencyKnown"] is known
    assert result["quoteCurrency"] == ("USD" if known else None)
    assert result["warning"] == "using cached market data after provider error"
