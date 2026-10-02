import datetime as dt

import pytest

from features.price_scenarios import collect
from features.price_scenarios.collect import CollectionError, Collector

NOW = lambda: dt.datetime(2026, 10, 2, 6, 0, tzinfo=dt.timezone.utc)
SUBMISSIONS = {"cik": "0000320193", "sic": "3571", "exchanges": ["Nasdaq"], "tickers": ["AAPL"], "name": "Apple Inc.",
               "filings": {"recent": {"form": ["10-K"], "filingDate": ["2025-10-31"]}}}


@pytest.fixture
def sec(monkeypatch):
    monkeypatch.setattr(collect.sec_companyfacts, "resolve_cik", lambda company, cache: "0000320193")
    monkeypatch.setattr(collect.sec_filings, "get_company_submissions", lambda cik, cache: (SUBMISSIONS, ""))
    monkeypatch.setattr(collect.sec_filings, "latest_annual_report_metadata",
                        lambda cik, cache: {"ok": True, "url": "https://example.test/10k.htm", "accession": "0000320193-25-000079", "form": "10-K"})
    monkeypatch.setattr(collect.sec_filings, "fetch_text", lambda url, path: ("<html>cover</html>", ""))


def collector(tmp_path, **kwargs):
    seen = {}
    def daily(ticker, market, metadata, *, now):
        seen["metadata"] = metadata
        return {"price": {"value": "100", "sessionDate": "2026-10-01", "currency": "USD", "provider": "yfinance", "providerSymbol": ticker},
                "closes": [], "events": [], "eventSourceState": "received", "exchangeSource": "sec_submissions", "fetchedAt": now.isoformat()}
    made = Collector(tmp_path, now=NOW, sec_bytes=lambda url: b'{"facts": {}}', fetch_daily=daily,
                     beta_of=lambda symbol: {"beta": {"value": "1.1", "source": "yfinance_info_beta"}, "fetchedAt": "x"},
                     risk_free_of=lambda session, currency: {"rate": "0.04", "source": "constant"}, **kwargs)
    return made, seen


def test_us_collection_hands_the_official_submissions_to_the_price_reader(tmp_path, sec):
    made, seen = collector(tmp_path)
    raw = made.collect("US", "aapl")
    assert seen["metadata"] is SUBMISSIONS and raw["identity"]["exchange"] == "Nasdaq" and raw["identity"]["cik"] == "0000320193"
    assert raw["annualAccession"] == "0000320193-25-000079" and raw["riskFree"]["fetchedAt"] and raw["beta"]["beta"]["value"] == "1.1"


def test_unsupported_instruments_and_missing_sources_stop_with_stable_codes(tmp_path, sec, monkeypatch):
    made, _ = collector(tmp_path)
    for market, ticker in (("US", "bad ticker!"), ("KR", "5930"), ("JP", "7203")):
        with pytest.raises(CollectionError) as error:
            made.collect(market, ticker)
        assert error.value.code == "instrument_not_supported"
    monkeypatch.setattr(collect.sec_companyfacts, "resolve_cik", lambda company, cache: "")
    with pytest.raises(CollectionError) as error:
        made.collect("US", "ZZZZ")
    assert (error.value.code, error.value.sub_code) == ("company_not_found", "no_cik")


def test_a_price_reader_error_keeps_its_enum_reason(tmp_path, sec):
    def broken(ticker, market, metadata, *, now):
        raise ValueError("exchange_unknown")
    made = Collector(tmp_path, now=NOW, sec_bytes=lambda url: b"{}", fetch_daily=broken)
    with pytest.raises(CollectionError) as error:
        made.collect("US", "AAPL")
    assert (error.value.code, error.value.sub_code) == ("price_unavailable", "exchange_unknown")
