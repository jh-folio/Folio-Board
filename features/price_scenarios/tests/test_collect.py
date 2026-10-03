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


# --- Korea: eight report years, the unfiled current year, and the separate-statement fallback -----------------------------

def kr_collector(tmp_path, monkeypatch, dart_get):
    monkeypatch.setattr(collect.dart_client, "dart_api_key", lambda: "test-key")
    monkeypatch.setattr(collect, "market_identity", lambda company, cache: {
        "ok": True, "corpCode": "00126380", "profile": {"stock_code": "005930"}, "providerSymbol": "005930.KS",
        "exchangeSource": "dart_company", "exchange": "KOSPI"})
    def daily(ticker, market, metadata, *, now):
        return {"price": {"value": "70000", "sessionDate": "2026-10-01", "currency": "KRW", "provider": "yfinance", "providerSymbol": "005930.KS"},
                "closes": [], "events": [], "eventSourceState": "received", "exchangeSource": "dart_company", "fetchedAt": now.isoformat(),
                "request": {"start": "2015-10-02"}}
    return Collector(tmp_path, now=NOW, dart_get=dart_get, fetch_daily=daily,
                     beta_of=lambda symbol: {"beta": {"value": "1", "source": "x"}, "fetchedAt": "x"},
                     risk_free_of=lambda session, currency: {"rate": "0.03", "source": "constant"})


def fake_dart(calls, *, consolidated=True):
    def get(endpoint, params):
        calls.append((endpoint, params.get("bsns_year"), params.get("fs_div")))
        year = int(params.get("bsns_year", 0))
        if endpoint == "fricDecsn":
            return {"status": "013", "list": []}
        if year == 2026:  # this year's annual report is not filed yet
            return {"status": "013", "list": []}
        if endpoint == "fnlttSinglAcntAll":
            if params["fs_div"] == "CFS" and not consolidated:
                return {"status": "013", "list": []}
            return {"status": "000", "list": [{"account_id": "x", "fs_div": params["fs_div"]}]}
        if endpoint == "stockTotqySttus":
            return {"status": "000", "list": [{"stlm_dt": f"{year}-12-31", "se": "보통주"}]}
        return {"status": "000", "list": []}
    return get


def test_korean_collection_reads_eight_years_and_leaves_the_unfiled_current_year_to_the_assembler(tmp_path, monkeypatch):
    calls = []
    raw = kr_collector(tmp_path, monkeypatch, fake_dart(calls)).collect("KR", "005930")
    years = sorted({year for endpoint, year, _ in calls if endpoint == "stockTotqySttus"})
    assert years == [str(year) for year in range(2019, 2027)] and set(raw["dart"]["stockTotqy"]) == set(years)
    assert raw["dart"]["stockTotqy"]["2026"]["status"] == "013"
    assert [batch["periodEnd"][:4] for batch in raw["dart"]["batches"]] == [str(year) for year in range(2019, 2026)]
    assert {batch["basis"] for batch in raw["dart"]["batches"]} == {"CFS"} and not any(fs == "OFS" for _, _, fs in calls)


def test_a_company_without_consolidated_statements_uses_the_separate_ones_throughout(tmp_path, monkeypatch):
    calls = []
    raw = kr_collector(tmp_path, monkeypatch, fake_dart(calls, consolidated=False)).collect("KR", "005930")
    assert {batch["basis"] for batch in raw["dart"]["batches"]} == {"OFS"} and len(raw["dart"]["batches"]) == 7
    assert {row["fs_div"] for batch in raw["dart"]["batches"] for row in batch["rows"]} == {"OFS"}


def test_a_failed_dart_call_stops_the_collection_with_the_endpoint_in_the_sub_code(tmp_path, monkeypatch):
    def broken(endpoint, params):
        raise OSError("boom")
    with pytest.raises(CollectionError) as error:
        kr_collector(tmp_path, monkeypatch, broken).collect("KR", "005930")
    assert (error.value.code, error.value.sub_code) == ("financial_history_unavailable", "dart_fnlttSinglAcntAll_failed")
