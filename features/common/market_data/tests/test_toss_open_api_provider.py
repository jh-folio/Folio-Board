import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data import toss_open_api
from features.common.market_data.providers import TossOpenApiKoreaMarketProvider, _fetch_usdkrw
from features.llm_settings.client import TOSS_OPEN_API_DEFAULT_BASE_URL, toss_open_api_base_url, toss_open_api_enabled
from features.llm_settings.settings_service import public_settings


def test_toss_open_api_provider_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "0")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")

    payload = TossOpenApiKoreaMarketProvider().fetch_korea_market("2026-06-23")

    assert payload["ok"] is False
    assert payload["provider"] == "toss_open_api"
    assert "disabled or key not configured" in payload["warnings"][0]


def test_toss_open_api_provider_is_safe_stub_until_endpoint_is_enabled(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("TOSS_OPEN_API_BASE_URL", "https://example.invalid")

    payload = TossOpenApiKoreaMarketProvider().fetch_korea_market("2026-06-23")

    assert payload["ok"] is False
    assert payload["provider"] == "toss_open_api"
    assert "aggregate market payload remains on yfinance" in payload["warnings"][0]
    assert "native chart uses Toss market-indicator candles" in payload["warnings"][0]
    assert "client-secret" not in repr(payload)


def _enable_toss(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")


def _block_yfinance(monkeypatch):
    """yfinance 폴백이 네트워크를 타지 않게 막는다."""
    stub = types.SimpleNamespace(Ticker=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setitem(sys.modules, "yfinance", stub)


def test_toss_usdkrw_is_requested_for_the_session_date(monkeypatch):
    _enable_toss(monkeypatch)
    calls = []

    def fake_rate(*, date_time=None, transport=None):
        calls.append(date_time)
        return {"USDKRW": {"label": "원·달러 환율", "asOfDate": "2026-08-07", "close": 1380.0,
                           "changePct": None, "source": "toss_open_api"}}

    monkeypatch.setattr(toss_open_api, "fetch_usdkrw_exchange_rate", fake_rate)

    fx = _fetch_usdkrw("2026-08-07")

    assert calls == ["2026-08-07"]
    assert fx["USDKRW"]["source"] == "toss_open_api"
    assert fx["USDKRW"]["asOfDate"] == "2026-08-07"


def test_toss_usdkrw_newer_than_the_session_date_falls_back(monkeypatch):
    _enable_toss(monkeypatch)
    _block_yfinance(monkeypatch)

    def fake_rate(*, date_time=None, transport=None):
        # 세션일을 넘겨도 provider가 최신 값을 주면 그 세션의 환율이 아니다.
        return {"USDKRW": {"label": "원·달러 환율", "asOfDate": "2026-08-10", "close": 1390.0,
                           "changePct": None, "source": "toss_open_api"}}

    monkeypatch.setattr(toss_open_api, "fetch_usdkrw_exchange_rate", fake_rate)

    fx = _fetch_usdkrw("2026-08-07")

    assert "USDKRW" not in fx
    assert fx["error"] == "market_data_unavailable"


def test_example_shaped_toss_credentials_stay_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "false")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "demo-client-value")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "safe-holder-value")
    monkeypatch.setenv("TOSS_OPEN_API_BASE_URL", TOSS_OPEN_API_DEFAULT_BASE_URL)

    settings = public_settings()

    assert toss_open_api_enabled() is False
    assert toss_open_api.toss_credentials_available() is False
    assert settings["toss"]["enabled"] is False
    assert settings["toss"]["ready"] is False
    assert settings["toss"]["hasClientId"] is True
    assert settings["toss"]["hasClientSecret"] is True
    assert settings["toss"]["health"]["status"] == "disabled"
    assert "safe-holder-value" not in repr(settings)


def test_public_settings_reports_toss_key_without_exposing_secret_when_enabled(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "demo-client-value")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "safe-holder-value")
    monkeypatch.setenv("TOSS_OPEN_API_BASE_URL", "https://example.invalid")

    settings = public_settings()

    assert settings["toss"]["enabled"] is True
    assert settings["toss"]["hasApiKey"] is True
    assert settings["toss"]["ready"] is True
    assert settings["toss"]["baseUrl"] == "https://example.invalid"
    assert settings["toss"]["clientIdMasked"] == "dem...alue"
    assert settings["toss"]["clientSecretMasked"] == "saf...alue"
    assert settings["toss"]["health"]["configured"] is True
    assert "safe-holder-value" not in repr(settings["toss"]["health"])
    assert "safe-holder-value" not in repr(settings)


def test_opted_in_blank_toss_base_url_uses_pinned_default_in_public_health(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "true")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "demo-client-value")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "safe-holder-value")
    monkeypatch.setenv("TOSS_OPEN_API_BASE_URL", "  \t ")

    settings = public_settings()

    assert toss_open_api_base_url() == TOSS_OPEN_API_DEFAULT_BASE_URL
    assert toss_open_api._base_url() == TOSS_OPEN_API_DEFAULT_BASE_URL
    assert settings["toss"]["baseUrl"] == TOSS_OPEN_API_DEFAULT_BASE_URL
    assert set(settings["toss"]["health"]) <= {"configured", "enabled", "status", "lastErrorCode", "rateLimit", "authFailures", "authFailureCount"}
    assert "safe-holder-value" not in repr(settings["toss"])
