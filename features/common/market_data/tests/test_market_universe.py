import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data.market_universe import (
    build_kospi_heatmap_snapshot,
    build_us_heatmap_snapshot,
    fetch_bulk_daily_prices,
    fetch_toss_then_bulk_daily_prices,
    kospi_frames_to_rows,
    load_last_good_snapshot,
    save_last_good_snapshot,
    _universe_key,
)


class _FakeFrame:
    """Minimal pandas-like frame for kospi_frames_to_rows tests."""

    def __init__(self, rows):
        self._rows = rows  # {ticker: {col: value}}
        self.empty = not rows

    def iterrows(self):
        for ticker, values in self._rows.items():
            yield ticker, dict(values)

    @property
    def loc(self):
        rows = self._rows

        class _Loc:
            def __getitem__(self, key):
                return rows[str(key).zfill(6)]

        return _Loc()


def test_kospi_frames_filter_to_kospi200_members_and_keep_krx_sectors():
    prices = _FakeFrame({
        "005930": {"종가": 80000, "등락률": 1.0},
        "000660": {"종가": 200000, "등락률": -2.0},
        "900110": {"종가": 5000, "등락률": 0.5},  # not in KOSPI200
    })
    caps = _FakeFrame({
        "005930": {"시가총액": 480_000_000_000_000},
        "000660": {"시가총액": 140_000_000_000_000},
        "900110": {"시가총액": 1_000_000_000_000},
    })
    sectors = _FakeFrame({
        "005930": {"종목명": "삼성전자", "업종명": "전기전자"},
        "000660": {"종목명": "SK하이닉스", "업종명": "전기전자"},
        "900110": {"종목명": "이스트소프트", "업종명": "서비스업"},
    })

    rows = kospi_frames_to_rows("2026-06-19", prices, caps, sectors, members=["005930", "000660"])

    assert {row["ticker"] for row in rows} == {"005930", "000660"}
    assert rows[0]["sector"] == "전기전자"


def test_kospi_frames_accept_pykrx_english_column_variants():
    prices = _FakeFrame({
        "005930": {"Close": 80000, "Change": 1.0},
        "000660": {"close": 200000, "change": -2.0},
    })
    caps = _FakeFrame({
        "005930": {"Marcap": 480_000_000_000_000},
        "000660": {"market_cap": 140_000_000_000_000},
    })
    sectors = _FakeFrame({
        "005930": {"Name": "삼성전자", "Sector": "전기전자", "Industry": "반도체"},
        "000660": {"Name": "SK하이닉스", "Sector": "전기전자", "Industry": "반도체"},
    })

    rows = kospi_frames_to_rows("2026-06-19", prices, caps, sectors, members=["005930", "000660"])

    assert {row["ticker"] for row in rows} == {"005930", "000660"}
    assert rows[0]["label"] == "삼성전자"
    assert rows[0]["sector"] == "전기전자"
    assert rows[0]["industry"] == "반도체"
    assert rows[0]["marketCap"] == 480_000_000_000_000


def test_us_heatmap_ranks_sp500_constituents_and_keeps_gics_labels():
    constituents = [
        {"ticker": "SMALL", "providerSymbol": "SMALL", "label": "Small", "sector": "Information Technology", "industry": "Software", "marketCap": 100.0},
        {"ticker": "LARGE", "providerSymbol": "LARGE", "label": "Large", "sector": "Information Technology", "industry": "Technology Hardware", "marketCap": 900.0},
    ]
    prices = {
        "LARGE": {"close": 90, "previousClose": 100, "asOf": "2026-06-19"},
        "SMALL": {"close": 105, "previousClose": 100, "asOf": "2026-06-19"},
    }

    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=constituents,
        price_fetcher=lambda tickers, date: prices,
        limit=1,
    )

    assert result["provider"] == "sp500+yfinance"
    assert [row["ticker"] for row in result["rows"]] == ["LARGE"]
    assert result["rows"][0]["sector"] == "Information Technology"
    assert result["rows"][0]["industry"] == "Technology Hardware"
    assert result["rows"][0]["marketCap"] == 900.0
    assert result["rows"][0]["changePct"] == -10.0
    assert result["coverage"] == {
        "requested": 1, "returned": 1, "ratio": 1.0, "status": "complete",
    }


def test_us_heatmap_provider_reflects_toss_enriched_prices():
    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=[{"ticker": "AAPL", "label": "Apple", "sector": "Information Technology", "industry": "Hardware", "marketCap": 10.0}],
        price_fetcher=lambda tickers, date: {
            "AAPL": {
                "close": 210,
                "previousClose": 200,
                "asOf": "2026-06-19",
                "provider": "toss_open_api+yfinance",
            }
        },
    )

    assert result["provider"] == "sp500+toss_open_api+yfinance"
    assert result["rows"][0]["priceProvider"] == "toss_open_api+yfinance"
    assert result["rows"][0]["changePct"] == 5.0


def test_default_us_heatmap_carries_bounded_future_universe_provenance_only(tmp_path, monkeypatch):
    # Verify the shipped baseline/changeset, independent of a user's local
    # snapshot or a previously imported workspace configuration.
    from features.common.market_data import sp500_universe
    for name in ("sp500_constituents.json", sp500_universe.SP500_CHANGESET_FILENAME):
        (tmp_path / name).write_bytes((ROOT / "defaults" / "config" / name).read_bytes())
    monkeypatch.setattr(sp500_universe, "resolve_config", lambda name: tmp_path / name)
    def prices(tickers, date):
        return {
            ticker: {
                "close": 101,
                "previousClose": 100,
                "asOf": date,
                "provider": "fixture",
            }
            for ticker in tickers
        }

    result = build_us_heatmap_snapshot("2026-10-01", price_fetcher=prices)
    provenance = result["universeProvenance"]

    assert provenance["status"] == "latest_known_snapshot"
    assert provenance["snapshotAsOf"] == "2026-09-08"
    assert provenance["verifiedThrough"] == "2026-09-08"
    assert provenance["marketCapVintage"] == "mixed_baseline_2026-06-23_plus_current_overrides_2026-09-08"
    assert provenance["baselineMarketCapAsOf"] == "2026-06-23"
    assert provenance["overridesMarketCapAsOf"] == "2026-09-08"
    assert "changesApplied" not in provenance
    assert "knownChanges" not in provenance

    custom = build_us_heatmap_snapshot(
        "2026-10-01",
        constituents=[{
            "ticker": "CUSTOM",
            "label": "Custom",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 10.0,
        }],
        price_fetcher=prices,
    )
    assert "universeProvenance" not in custom


def test_us_heatmap_default_keeps_every_configured_sp500_constituent():
    constituents = [
        {
            "ticker": f"T{i:03d}",
            "label": f"Company {i}",
            "sector": "Information Technology",
            "industry": "Software",
            "marketCap": float(1000 - i),
        }
        for i in range(502)
    ]

    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=constituents,
        price_fetcher=lambda tickers, date: {
            ticker: {"close": 101, "previousClose": 100, "asOf": "2026-06-19", "provider": "yfinance"}
            for ticker in tickers
        },
    )

    assert result["coverage"] == {"requested": 502, "returned": 502, "ratio": 1.0, "status": "complete"}
    assert len(result["rows"]) == 502
    assert result["rows"][-1]["ticker"] == "T501"


def test_us_heatmap_recovers_only_missing_symbols_from_a_sparse_first_response():
    constituents = [
        {"ticker": f"T{i:03d}", "label": f"Company {i}", "sector": "Technology", "industry": "Software", "marketCap": 1000 - i}
        for i in range(499)
    ]
    calls = []

    def fetcher(symbols, date):
        calls.append(list(symbols))
        selected = symbols if len(calls) > 1 else symbols[:1]
        return {
            symbol: {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
            for symbol in selected
        }

    result = build_us_heatmap_snapshot("2026-06-19", constituents=constituents, price_fetcher=fetcher)

    assert result["coverage"]["status"] == "complete"
    assert result["coverage"]["requested"] == 499
    assert len(result["rows"]) == 499
    assert calls[0] == [row["ticker"] for row in constituents]
    assert "T000" not in calls[1:]
    assert len(calls[1]) == 25


def test_us_heatmap_permanent_missing_is_partial_and_not_a_normal_snapshot():
    constituents = [
        {"ticker": ticker, "label": ticker, "sector": "Technology", "industry": "Software", "marketCap": 10.0}
        for ticker in ("A", "B", "C")
    ]

    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=constituents,
        price_fetcher=lambda symbols, date: {
            "A": {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
        },
    )

    assert [row["ticker"] for row in result["rows"]] == ["A"]
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["missingCount"] == 2
    assert set(result["coverage"]["missingSymbols"]) == {"B", "C"}
    assert result["freshness"] == "partial"
    assert result["warnings"]


def test_heatmap_rejects_nonfinite_wrong_date_and_invalid_previous_close():
    constituents = [
        {"ticker": ticker, "label": ticker, "sector": "Technology", "industry": "Software", "marketCap": 10.0}
        for ticker in ("INF", "ZERO", "FUTURE")
    ]

    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=constituents,
        price_fetcher=lambda symbols, date: {
            "INF": {"close": float("inf"), "previousClose": 100, "asOf": date},
            "ZERO": {"close": 101, "previousClose": 0, "asOf": date},
            "FUTURE": {"close": 101, "previousClose": 100, "asOf": "2026-06-20"},
        },
    )

    assert result["rows"] == []
    assert result["coverage"]["status"] == "unavailable"
    assert result["coverage"]["missingCount"] == 3
    assert "2026-06-19" in result["warnings"][0]


def test_us_partial_does_not_overwrite_a_complete_last_good_cache(tmp_path):
    constituents = [
        {"ticker": ticker, "label": ticker, "sector": "Technology", "industry": "Software", "marketCap": 10.0}
        for ticker in ("A", "B")
    ]
    good_prices = lambda symbols, date: {
        symbol: {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
        for symbol in symbols
    }
    build_us_heatmap_snapshot("2026-06-19", cache_dir=tmp_path, constituents=constituents, price_fetcher=good_prices)
    cache_path = tmp_path / "sp500-heatmap-last-good.json.gz"
    before = load_last_good_snapshot(cache_path)

    partial = build_us_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        constituents=constituents,
        price_fetcher=lambda symbols, date: {
            "A": {"close": 102, "previousClose": 100, "asOf": date, "provider": "fixture"}
        },
    )

    # A complete cache for the exact session and exact source universe is a
    # safe recovery for a sparse re-fetch; the partial response must not win.
    assert partial["coverage"]["status"] == "complete"
    assert partial["freshness"] == "close_snapshot"
    assert any("same-session last-good" in warning for warning in partial["warnings"])
    assert load_last_good_snapshot(cache_path) == before


def test_same_session_cache_is_not_reused_for_a_different_heatmap_universe(tmp_path):
    original = [
        {"ticker": ticker, "label": ticker, "sector": "Technology", "industry": "Software", "marketCap": 10.0}
        for ticker in ("A", "B")
    ]
    complete = lambda symbols, date: {
        symbol: {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
        for symbol in symbols
    }
    build_us_heatmap_snapshot("2026-06-19", cache_dir=tmp_path, constituents=original, price_fetcher=complete)

    changed = build_us_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        constituents=[*original, {"ticker": "C", "label": "C", "sector": "Technology", "industry": "Software", "marketCap": 9.0}],
        price_fetcher=lambda symbols, date: {
            "A": {"close": 102, "previousClose": 100, "asOf": date, "provider": "fixture"}
        },
    )
    limited = build_us_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        constituents=original,
        limit=1,
        price_fetcher=lambda symbols, date: {},
    )

    assert changed["coverage"]["status"] == "partial"
    assert changed["coverage"]["missingCount"] == 2
    assert limited["coverage"]["status"] == "unavailable"
    assert limited["coverage"]["requested"] == 1


def test_partial_kospi_prices_are_not_saved_as_a_complete_last_good_snapshot(tmp_path):
    constituents = [
        {"ticker": ticker, "label": ticker, "sector": "전기전자", "industry": "반도체", "marketCap": 10.0}
        for ticker in ("005930", "000660")
    ]
    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        fallback_constituents=constituents,
        krx_fetcher=lambda date: [],
        fallback_price_fetcher=lambda symbols, date: {
            "005930": {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
        },
    )

    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["missingCount"] == 1
    assert not (tmp_path / "kospi-heatmap-last-good.json.gz").exists()


def test_builtin_tiny_kospi_rescue_is_degraded_even_when_its_prices_are_complete(monkeypatch, tmp_path):
    from features.common.market_data import market_universe as module

    monkeypatch.setattr(module, "_default_kospi200_constituents", lambda: list(module.DEFAULT_KOSPI200_FALLBACK_CONSTITUENTS))
    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        krx_fetcher=lambda date: [],
        fallback_price_fetcher=lambda symbols, date: {
            symbol: {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
            for symbol in symbols
        },
    )

    assert result["universeStatus"] == "degraded"
    assert result["coverage"] == {"requested": 200, "returned": 25, "ratio": 0.125, "status": "partial"}
    assert result["freshness"] == "partial"
    assert not (tmp_path / "kospi-heatmap-last-good.json.gz").exists()


def test_krx_rows_without_a_finite_change_are_not_accepted_as_complete(tmp_path):
    constituents = [{
        "ticker": "005930", "label": "삼성전자", "sector": "전기전자", "industry": "반도체", "marketCap": 10.0,
    }]
    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        fallback_constituents=constituents,
        krx_fetcher=lambda date: [{
            "ticker": "005930", "label": "삼성전자", "sector": "전기전자", "industry": "반도체",
            "close": 101, "changePct": float("nan"), "marketCap": 10.0, "asOf": date,
        }],
        fallback_price_fetcher=lambda symbols, date: {},
    )

    assert result["provider"] == "kospi200-static"
    assert result["coverage"]["status"] == "unavailable"
    assert not (tmp_path / "kospi-heatmap-last-good.json.gz").exists()


def test_bulk_yfinance_recovery_uses_smaller_batches_and_keeps_first_success(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    symbols = [f"T{i:03d}" for i in range(101)]
    calls = []

    def fake_download(batch, date, sequential):
        calls.append((list(batch), sequential))
        selected = batch[:1] if len(calls) == 1 else batch
        return {
            symbol: {"close": 101, "previousClose": 100, "asOf": date, "provider": "fixture"}
            for symbol in selected
        }

    monkeypatch.setattr("features.common.market_data.market_universe._download_daily_batch", fake_download)
    prices = fetch_bulk_daily_prices(symbols, "2026-06-19")

    assert len(prices) == len(symbols)
    assert calls[0][0] == symbols[:100]
    assert calls[0][1] is False
    assert calls[1][0] == symbols[100:]
    assert calls[2][0] == symbols[1:26]
    assert len(calls[2][0]) == 25
    assert symbols[0] not in [symbol for batch, _ in calls[2:] for symbol in batch]


def test_us_heatmap_collapses_duplicate_share_classes_to_one_company_tile():
    constituents = [
        {"ticker": "GOOGL", "label": "Alphabet Inc. (Class A)", "sector": "Communication Services", "industry": "Interactive Media & Services", "marketCap": 1000.0},
        {"ticker": "GOOG", "label": "Alphabet Inc. (Class C)", "sector": "Communication Services", "industry": "Interactive Media & Services", "marketCap": 900.0},
        {"ticker": "BRK.A", "providerSymbol": "BRK-A", "label": "Berkshire Hathaway", "sector": "Financials", "industry": "Multi-Sector Holdings", "marketCap": 800.0},
        {"ticker": "BRK.B", "providerSymbol": "BRK-B", "label": "Berkshire Hathaway", "sector": "Financials", "industry": "Multi-Sector Holdings", "marketCap": 790.0},
        {"ticker": "AAPL", "label": "Apple Inc.", "sector": "Information Technology", "industry": "Technology Hardware", "marketCap": 1200.0},
    ]
    prices = {
        "GOOGL": {"close": 110, "previousClose": 100, "asOf": "2026-06-19", "provider": "fixture"},
        "GOOG": {"close": 90, "previousClose": 100, "asOf": "2026-06-19", "provider": "fixture"},
        "BRK.A": {"close": 105, "previousClose": 100, "asOf": "2026-06-19", "provider": "fixture"},
        "BRK.B": {"close": 103, "previousClose": 100, "asOf": "2026-06-19", "provider": "fixture"},
        "AAPL": {"close": 101, "previousClose": 100, "asOf": "2026-06-19", "provider": "fixture"},
    }

    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=constituents,
        price_fetcher=lambda tickers, date: prices,
    )

    assert result["coverage"] == {"requested": 3, "returned": 3, "ratio": 1.0, "status": "complete"}
    assert [row["ticker"] for row in result["rows"]] == ["AAPL", "GOOGL", "BRK.A"]
    alphabet = next(row for row in result["rows"] if row["ticker"] == "GOOGL")
    berkshire = next(row for row in result["rows"] if row["ticker"] == "BRK.A")
    assert alphabet["label"] == "Alphabet Inc."
    assert alphabet["classTickers"] == ["GOOGL", "GOOG"]
    assert alphabet["marketCap"] == 1000.0
    assert round(alphabet["changePct"], 4) == 0.5263
    assert berkshire["classTickers"] == ["BRK.A", "BRK.B"]
    assert berkshire["marketCap"] == 800.0


def test_toss_heatmap_price_fetcher_batches_more_than_200_symbols(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    tickers = [f"T{i:03d}" for i in range(250)]
    batch_sizes = []

    def fake_toss_prices(symbols):
        batch_sizes.append(len(symbols))
        return [
            {
                "symbol": symbol,
                "timestamp": "2026-06-19T16:00:00+09:00",
                "lastPrice": 105,
                "provider": "toss_open_api",
            }
            for symbol in symbols
        ]

    def fake_yfinance_prices(symbols, date):
        return {
            symbol: {"close": 100, "previousClose": 99, "asOf": "2026-06-18", "provider": "yfinance"}
            for symbol in symbols
        }

    monkeypatch.setattr("features.common.market_data.toss_open_api.fetch_toss_prices", fake_toss_prices)
    monkeypatch.setattr("features.common.market_data.market_universe.fetch_bulk_daily_prices", fake_yfinance_prices)

    prices = fetch_toss_then_bulk_daily_prices(tickers, "2026-06-19")

    assert batch_sizes == [200, 50]
    assert len(prices) == 250
    assert prices["T249"]["provider"] == "toss_open_api+yfinance"


def test_toss_heatmap_price_fetcher_uses_yfinance_when_release_flag_is_off(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "0")
    tickers = ["AAPL"]
    toss_calls = []

    def fake_toss_prices(symbols):
        toss_calls.append(symbols)
        return [{"symbol": "AAPL", "timestamp": "2026-06-19T16:00:00-04:00", "lastPrice": 105}]

    def fake_yfinance_prices(symbols, date):
        return {
            symbol: {"close": 100, "previousClose": 99, "asOf": date, "provider": "yfinance"}
            for symbol in symbols
        }

    monkeypatch.setattr("features.common.market_data.toss_open_api.fetch_toss_prices", fake_toss_prices)
    monkeypatch.setattr("features.common.market_data.market_universe.fetch_bulk_daily_prices", fake_yfinance_prices)

    prices = fetch_toss_then_bulk_daily_prices(tickers, "2026-06-19")

    assert toss_calls == []
    assert prices["AAPL"]["provider"] == "yfinance"


def test_toss_daily_alternate_is_limited_to_yfinance_missing_symbols(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setattr("features.llm_settings.client.toss_open_api_enabled", lambda: True)
    monkeypatch.setattr("features.common.market_data.toss_open_api.fetch_toss_prices", lambda symbols: [])
    monkeypatch.setattr("features.common.market_data.toss_open_api.toss_credentials_available", lambda: True)
    yfinance_calls = []
    toss_calls = []

    def fake_yfinance(symbols, date):
        yfinance_calls.append(list(symbols))
        return {"A": {"close": 101, "previousClose": 100, "asOf": date, "provider": "yfinance"}}

    def fake_toss_candles(symbol, **kwargs):
        toss_calls.append(symbol)
        return [
            {"time": "2026-06-18", "close": 100},
            {"time": "2026-06-19", "close": 102},
        ]

    monkeypatch.setattr("features.common.market_data.market_universe.fetch_bulk_daily_prices", fake_yfinance)
    monkeypatch.setattr("features.common.market_data.toss_open_api.download_toss_candle_rows", fake_toss_candles)

    prices = fetch_toss_then_bulk_daily_prices(["A", "B"], "2026-06-19")

    assert yfinance_calls == [["A", "B"]]
    assert toss_calls == ["B"]
    assert prices["A"]["provider"] == "yfinance"
    assert prices["B"] == {
        "close": 102,
        "previousClose": 100,
        "asOf": "2026-06-19",
        "provider": "toss_open_api",
    }


def test_us_heatmap_does_not_mix_a_different_price_date():
    result = build_us_heatmap_snapshot(
        "2026-06-19",
        constituents=[{"ticker": "A", "label": "A", "sector": "Energy", "industry": "Oil", "marketCap": 10.0}],
        price_fetcher=lambda tickers, date: {"A": {"close": 10, "previousClose": 9, "asOf": "2026-06-18"}},
    )
    assert result["rows"] == []
    assert result["freshness"] == "unavailable"
    assert result["coverage"]["status"] == "unavailable"


def test_us_heatmap_unavailable_when_universe_empty():
    result = build_us_heatmap_snapshot("2026-06-19", constituents=[])
    assert result["rows"] == []
    assert result["freshness"] == "unavailable"
    assert result["provider"] == "sp500+yfinance"


def test_kospi_failure_uses_last_good_cache_without_symbol_fanout(tmp_path):
    cached = {
        "market": "KR",
        "asOf": "2026-06-18",
        "provider": "pykrx",
        "freshness": "close_snapshot",
        "coverage": {"requested": 1, "returned": 1, "ratio": 1.0, "status": "complete"},
        "rows": [{
            "ticker": "005930", "label": "삼성전자", "sector": "전기전자", "industry": "전기전자",
            "close": 80000, "changePct": 1.0, "marketCap": 480000000000000, "asOf": "2026-06-18",
        }],
        "warnings": [],
    }
    cached["universeKey"] = _universe_key(["005930"])
    save_last_good_snapshot(tmp_path / "kospi-heatmap-last-good.json.gz", cached)

    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        krx_fetcher=lambda date: (_ for _ in ()).throw(ValueError("non-json response")),
        fallback_constituents=[{"ticker": "005930", "label": "삼성전자", "sector": "전기전자", "industry": "반도체", "marketCap": 480000000000000}],
        fallback_price_fetcher=lambda tickers, date: {},
    )

    assert result["freshness"] == "stale"
    assert result["asOf"] == "2026-06-18"
    assert result["rows"] == cached["rows"]
    assert result["warnings"][-1] == "KRX unavailable; last-good snapshot used"


def test_kospi_failure_without_cache_uses_static_fallback_universe(tmp_path):
    fallback_constituents = [
        {
            "ticker": "005930",
            "label": "삼성전자",
            "sector": "전기전자",
            "industry": "반도체",
            "marketCap": 480_000_000_000_000,
        },
        {
            "ticker": "000660",
            "label": "SK하이닉스",
            "sector": "전기전자",
            "industry": "반도체",
            "marketCap": 140_000_000_000_000,
        },
    ]

    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        krx_fetcher=lambda date: (_ for _ in ()).throw(ValueError("KRX unavailable")),
        fallback_constituents=fallback_constituents,
        fallback_price_fetcher=lambda tickers, date: {},
    )

    assert result["provider"] == "kospi200-static"
    assert result["freshness"] == "fallback_universe"
    assert result["coverage"]["requested"] == 2
    assert result["coverage"]["returned"] == 0
    assert result["coverage"]["status"] == "unavailable"
    assert result["coverage"]["missingCount"] == 2
    assert [row["ticker"] for row in result["rows"]] == ["005930", "000660"]
    assert result["rows"][0]["close"] is None
    assert result["warnings"][-1] == (
        "krx_unavailable; static KOSPI fallback universe used. "
        "Live prices/change rates are unavailable."
    )


def test_kospi200_primary_uses_embedded_universe_and_toss_prices_before_krx(tmp_path):
    fallback_constituents = [{
        "ticker": "005930",
        "label": "삼성전자",
        "sector": "전기전자",
        "industry": "반도체",
        "marketCap": 480_000_000_000_000,
    }]
    krx_calls = []

    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        krx_fetcher=lambda date: krx_calls.append(date) or (_ for _ in ()).throw(ValueError("KRX should not be first")),
        fallback_constituents=fallback_constituents,
        fallback_price_fetcher=lambda tickers, date: {
            "005930": {
                "close": 80000,
                "previousClose": 79000,
                "asOf": "2026-06-19",
                "provider": "toss_open_api+yfinance",
            }
        },
    )

    assert krx_calls == []
    assert result["provider"] == "kospi200+toss_open_api+yfinance"
    assert result["freshness"] == "close_snapshot"
    assert result["coverage"] == {"requested": 1, "returned": 1, "ratio": 1.0, "status": "complete"}
    assert result["rows"][0]["priceProvider"] == "toss_open_api+yfinance"


def test_kospi_primary_uses_toss_price_fetcher_when_available(tmp_path):
    fallback_constituents = [{
        "ticker": "005930",
        "label": "삼성전자",
        "sector": "전기전자",
        "industry": "반도체",
        "marketCap": 480_000_000_000_000,
    }]

    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        krx_fetcher=lambda date: (_ for _ in ()).throw(ValueError("KRX unavailable")),
        fallback_constituents=fallback_constituents,
        fallback_price_fetcher=lambda tickers, date: {
            "005930": {
                "close": 80000,
                "previousClose": 79000,
                "asOf": "2026-06-19",
                "provider": "toss_open_api+yfinance",
            }
        },
    )

    assert result["provider"] == "kospi200+toss_open_api+yfinance"
    assert result["rows"][0]["close"] == 80000
    assert round(result["rows"][0]["changePct"], 4) == 1.2658


def test_kospi_empty_krx_rows_use_static_fallback_universe(tmp_path):
    fallback_constituents = [{
        "ticker": "005930",
        "label": "삼성전자",
        "sector": "전기전자",
        "industry": "반도체",
        "marketCap": 480_000_000_000_000,
    }]

    result = build_kospi_heatmap_snapshot(
        "2026-06-19",
        cache_dir=tmp_path,
        krx_fetcher=lambda date: [],
        fallback_constituents=fallback_constituents,
        fallback_price_fetcher=lambda tickers, date: {},
    )

    assert result["provider"] == "kospi200-static"
    assert result["rows"][0]["ticker"] == "005930"
    assert "returned no KOSPI200 rows" in result["warnings"][-1]
