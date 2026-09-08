import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data import toss_open_api
from features.common.market_data.toss_token_manager import TossTokenManager
from features.common.market_data.toss_token_manager import TossProviderError


@pytest.fixture(autouse=True)
def isolated_token_manager(tmp_path, monkeypatch):
    """Existing REST fixtures must not acquire a lock in the user workspace."""
    manager = TossTokenManager(
        workspace_dir=tmp_path,
        enabled=toss_open_api.toss_open_api_enabled,
        client_id=toss_open_api.toss_open_api_client_id,
        client_secret=toss_open_api.toss_open_api_client_secret,
    )
    monkeypatch.setattr(toss_open_api, "_TOKEN_MANAGER", manager)
    toss_open_api._TOKEN_CACHE.clear()
    yield
    manager.close_for_tests()


def _official_holdings_result() -> dict:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "toss_accounts_holdings_1.2.14.json").read_text(encoding="utf-8"))
    return fixture["holdings"]["result"]


def test_toss_symbol_normalization_supports_us_and_kr_stocks_but_skips_indices():
    assert toss_open_api.toss_symbol_for("AAPL") == "AAPL"
    assert toss_open_api.toss_symbol_for("005930.KS") == "005930"
    assert toss_open_api.toss_symbol_for("035720.KQ") == "035720"
    assert toss_open_api.toss_symbol_for("^GSPC") == ""
    assert toss_open_api.toss_symbol_for("CL=F") == ""
    assert toss_open_api.toss_symbol_for("BTC-USD") == ""
    assert toss_open_api.toss_market_indicator_for("^KS11") == "KOSPI"
    assert toss_open_api.toss_market_indicator_for("^KQ11") == "KOSDAQ"
    assert toss_open_api.toss_market_indicator_for("^GSPC") == ""


def test_fetch_toss_prices_uses_oauth_token_and_normalizes_decimal_fields(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_open_api._TOKEN_CACHE.clear()
    calls = []

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append({"method": method, "url": url, "headers": headers or {}, "data": data})
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-1", "token_type": "Bearer", "expires_in": 3600}
        assert headers["Authorization"] == "Bearer token-1"
        return {"result": [
            {"symbol": "AAPL", "timestamp": "2026-06-22T16:00:00-04:00", "lastPrice": "201.50", "currency": "USD"},
            {"symbol": "005930", "timestamp": "2026-06-23T15:30:00+09:00", "lastPrice": "72000", "currency": "KRW"},
        ]}

    rows = toss_open_api.fetch_toss_prices(["AAPL", "005930.KS"], transport=fake_transport)

    assert [row["symbol"] for row in rows] == ["AAPL", "005930"]
    assert rows[0]["lastPrice"] == 201.5
    assert rows[1]["lastPrice"] == 72000.0
    assert calls[0]["method"] == "POST" and calls[1]["method"] == "GET"
    assert "client-secret" not in repr(rows)


def test_download_toss_candle_rows_maps_ohlcv_and_filters_to_date_window(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_open_api._TOKEN_CACHE.clear()

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-1", "token_type": "Bearer", "expires_in": 3600}
        return {"result": {"candles": [
            {"timestamp": "2026-06-21T00:00:00+09:00", "openPrice": "98", "highPrice": "101", "lowPrice": "97", "closePrice": "100", "volume": "10", "currency": "USD"},
            {"timestamp": "2026-06-22T00:00:00+09:00", "openPrice": "100", "highPrice": "105", "lowPrice": "99", "closePrice": "104", "volume": "20", "currency": "USD"},
            {"timestamp": "2026-06-24T00:00:00+09:00", "openPrice": "104", "highPrice": "106", "lowPrice": "103", "closePrice": "105", "volume": "30", "currency": "USD"},
        ], "nextBefore": None}}

    rows = toss_open_api.download_toss_candle_rows(
        "AAPL",
        start="2026-06-22",
        end="2026-06-23",
        interval="1d",
        transport=fake_transport,
    )

    assert rows == [{
        "time": "2026-06-22",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 20.0,
        "provider": "toss_open_api",
    }]


def test_kospi_candles_use_market_indicator_path_without_stock_only_parameters(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    calls = []

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append(url)
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-1", "expires_in": 3600}
        return {"result": {"candles": [], "nextBefore": None}}

    page = toss_open_api.fetch_toss_candle_page("^KS11", interval="1m", transport=fake_transport)

    assert page == {"candles": [], "nextBefore": ""}
    request_url = calls[-1]
    assert "/api/v1/market-indicators/KOSPI/candles?" in request_url
    assert "interval=1m" in request_url
    assert "symbol=" not in request_url
    assert "adjusted=" not in request_url


def test_fetch_toss_kr_market_calendar_normalizes_open_session(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_open_api._TOKEN_CACHE.clear()

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-1", "expires_in": 3600}
        assert "/api/v1/market-calendar/KR?date=2026-08-04" in url
        return {"result": {
            "today": {
                "date": "2026-08-04",
                "integrated": {"regularMarket": {"startTime": "09:00:00", "endTime": "15:30:00"}},
            },
            "previousBusinessDay": {"date": "2026-08-03"},
            "nextBusinessDay": {"date": "2026-08-05"},
        }}

    status = toss_open_api.fetch_toss_market_calendar("KR", date="2026-08-04", transport=fake_transport)

    assert status["isOpen"] is True
    assert status["previousBusinessDay"] == "2026-08-03"
    assert status["provider"] == "toss_open_api"


def test_fetch_toss_us_market_calendar_normalizes_holiday(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_open_api._TOKEN_CACHE.clear()

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-1", "expires_in": 3600}
        return {"result": {
            "today": {
                "date": "2026-07-03",
                "dayMarket": None,
                "preMarket": None,
                "regularMarket": None,
                "afterMarket": None,
            },
            "previousBusinessDay": {"date": "2026-07-02"},
            "nextBusinessDay": {"date": "2026-07-06"},
        }}

    status = toss_open_api.fetch_toss_market_calendar("US", date="2026-07-03", transport=fake_transport)

    assert status["isOpen"] is False
    assert status["previousBusinessDay"] == "2026-07-02"
    assert status["nextBusinessDay"] == "2026-07-06"


def test_toss_credentials_are_disabled_without_release_flag(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "0")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_open_api._TOKEN_CACHE.clear()

    assert toss_open_api.toss_credentials_available() is False
    assert toss_open_api.download_toss_candle_rows(
        "AAPL",
        start="2026-06-22",
        end="2026-06-23",
        interval="1d",
    ) == []


def test_toss_does_not_request_hourly_candles(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    calls = []

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append(url)
        return {"result": {"candles": []}}

    assert toss_open_api.download_toss_candle_rows(
        "AAPL", start="2026-06-22", end="2026-06-23", interval="1h", transport=fake_transport,
    ) == []
    assert toss_open_api.fetch_toss_candle_page(
        "AAPL", interval="1h", transport=fake_transport,
    ) == {"candles": [], "nextBefore": ""}
    assert calls == []


def test_pinned_accounts_and_holdings_wire_uses_no_account_query(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    calls = []

    def fake_transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, url, headers or {}))
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-1", "expires_in": 3600}
        if url.endswith("/api/v1/accounts"):
            assert headers == {"Authorization": "Bearer token-1"}
            return {"result": [{"accountNo": "123456789012", "accountSeq": 7, "accountType": "BROKERAGE"}]}
        assert url.endswith("/api/v1/holdings") and "?" not in url
        assert headers == {"Authorization": "Bearer token-1", "X-Tossinvest-Account": "7"}
        result = _official_holdings_result()
        return {"result": {**result, "items": []}}

    accounts = toss_open_api.fetch_toss_accounts(transport=fake_transport)
    holdings = toss_open_api.fetch_toss_holdings(7, transport=fake_transport)

    assert accounts[0]["accountSeq"] == 7
    assert holdings["items"] == []
    assert toss_open_api.TOSS_REST_OPENAPI_VERSION == "1.2.14"
    assert all("latest" not in url for _method, url, _headers in calls)


def test_pinned_1_2_14_fixture_keeps_required_accounts_and_holdings_shape():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "toss_accounts_holdings_1.2.14.json").read_text(encoding="utf-8"))
    assert fixture["openApiVersion"] == toss_open_api.TOSS_REST_OPENAPI_VERSION
    assert fixture["wireSchema"]["accounts"]["required"] == toss_open_api._ACCOUNT_REQUIRED_FIELDS
    assert tuple(fixture["wireSchema"]["holdings"]["overviewObjectFields"]) == toss_open_api._HOLDINGS_OVERVIEW_OBJECT_FIELDS
    assert tuple(fixture["wireSchema"]["holdings"]["itemStringFields"]) == toss_open_api._HOLDINGS_ITEM_STRING_FIELDS
    assert tuple(fixture["wireSchema"]["holdings"]["itemDecimalStrings"]) == toss_open_api._HOLDINGS_ITEM_DECIMAL_FIELDS
    assert tuple(fixture["wireSchema"]["holdings"]["itemObjectFields"]) == toss_open_api._HOLDINGS_ITEM_OBJECT_FIELDS
    assert set(toss_open_api._ACCOUNT_REQUIRED_FIELDS) <= set(fixture["accounts"]["result"][0])
    item = fixture["holdings"]["result"]["items"][0]
    assert {"symbol", "name", "marketCountry", "currency", "quantity", "lastPrice", "averagePurchasePrice", "marketValue", "profitLoss", "dailyProfitLoss", "cost"} <= set(item)


@pytest.mark.parametrize("payload,call", [
    ({"result": [{"accountNo": "0000", "accountSeq": 1}]}, lambda transport: toss_open_api.fetch_toss_accounts(transport=transport)),
    ({"result": {**_official_holdings_result(), "items": [{}]}}, lambda transport: toss_open_api.fetch_toss_holdings(1, transport=transport)),
    ({"result": {}}, lambda transport: toss_open_api.fetch_toss_holdings(1, transport=transport)),
])
def test_accounts_holdings_partial_openapi_envelopes_fail_closed(monkeypatch, payload, call):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    def transport(method, url, *, headers=None, data=None, timeout=10):
        return {"access_token": "token-1", "expires_in": 3600} if url.endswith("/oauth2/token") else payload
    with pytest.raises(TossProviderError) as error:
        call(transport)
    assert error.value.code == "provider_contract_invalid"
    assert "0000" not in repr(error.value)


def test_empty_valid_holdings_items_remain_distinct_from_contract_failure(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    def transport(method, url, *, headers=None, data=None, timeout=10):
        return {"access_token": "token-1", "expires_in": 3600} if url.endswith("/oauth2/token") else {"result": {**_official_holdings_result(), "items": []}}
    assert toss_open_api.fetch_toss_holdings(1, transport=transport)["items"] == []


def test_every_pinned_required_account_and_holding_field_is_enforced(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    account = {"accountNo": "000000000000", "accountSeq": 1, "accountType": "BROKERAGE"}
    overview = _official_holdings_result()
    item = overview["items"][0]
    def transport_for(payload):
        return lambda method, url, **_kwargs: {"access_token": "token-1", "expires_in": 3600} if url.endswith("/oauth2/token") else payload
    for field in tuple(account):
        malformed = dict(account); malformed.pop(field)
        with pytest.raises(TossProviderError): toss_open_api.fetch_toss_accounts(transport=transport_for({"result": [malformed]}))
    for field in (*toss_open_api._HOLDINGS_OVERVIEW_OBJECT_FIELDS, "items"):
        malformed = dict(overview); malformed.pop(field)
        with pytest.raises(TossProviderError): toss_open_api.fetch_toss_holdings(1, transport=transport_for({"result": malformed}))
    for field in tuple(item):
        malformed_item = dict(item); malformed_item.pop(field)
        with pytest.raises(TossProviderError): toss_open_api.fetch_toss_holdings(1, transport=transport_for({"result": {**overview, "items": [malformed_item]}}))


def test_pinned_wire_rejects_wrong_types_nulls_and_int64_boundaries(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    account = {"accountNo": "000000000000", "accountSeq": 1, "accountType": "BROKERAGE"}
    overview = _official_holdings_result()
    item = overview["items"][0]

    def transport_for(payload):
        return lambda method, url, **_kwargs: {"access_token": "token-1", "expires_in": 3600} if url.endswith("/oauth2/token") else payload

    for field in ("accountNo", "accountType"):
        for wrong in (None, {}, [], False, 1):
            malformed = dict(account); malformed[field] = wrong
            with pytest.raises(TossProviderError, match="provider_contract_invalid"):
                toss_open_api.fetch_toss_accounts(transport=transport_for({"result": [malformed]}))
    for sequence in (False, None, {}, [], toss_open_api._INT64_MIN - 1, toss_open_api._INT64_MAX + 1):
        malformed = dict(account); malformed["accountSeq"] = sequence
        with pytest.raises(TossProviderError, match="provider_contract_invalid"):
            toss_open_api.fetch_toss_accounts(transport=transport_for({"result": [malformed]}))
    for sequence in (toss_open_api._INT64_MIN, toss_open_api._INT64_MAX):
        valid = dict(account); valid["accountSeq"] = sequence
        assert toss_open_api.fetch_toss_accounts(transport=transport_for({"result": [valid]}))[0]["accountSeq"] == sequence

    for field in toss_open_api._HOLDINGS_OVERVIEW_OBJECT_FIELDS:
        for wrong in (None, [], False, 1, "NaN", "Infinity"):
            malformed = dict(overview); malformed[field] = wrong
            with pytest.raises(TossProviderError, match="provider_contract_invalid"):
                toss_open_api.fetch_toss_holdings(1, transport=transport_for({"result": malformed}))
    for field in toss_open_api._HOLDINGS_ITEM_STRING_FIELDS:
        for wrong in (None, {}, [], False, 1):
            malformed_item = dict(item); malformed_item[field] = wrong
            with pytest.raises(TossProviderError, match="provider_contract_invalid"):
                toss_open_api.fetch_toss_holdings(1, transport=transport_for({"result": {**overview, "items": [malformed_item]}}))
    for field in toss_open_api._HOLDINGS_ITEM_DECIMAL_FIELDS:
        for wrong in (None, {}, [], False, 1, "NaN", "-Infinity"):
            malformed_item = dict(item); malformed_item[field] = wrong
            with pytest.raises(TossProviderError, match="provider_contract_invalid"):
                toss_open_api.fetch_toss_holdings(1, transport=transport_for({"result": {**overview, "items": [malformed_item]}}))
    for field in toss_open_api._HOLDINGS_ITEM_OBJECT_FIELDS:
        for wrong in (None, [], False, 1, "NaN"):
            malformed_item = dict(item); malformed_item[field] = wrong
            with pytest.raises(TossProviderError, match="provider_contract_invalid"):
                toss_open_api.fetch_toss_holdings(1, transport=transport_for({"result": {**overview, "items": [malformed_item]}}))
