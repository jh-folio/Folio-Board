import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data.sp500_universe import (
    CURRENT_SP500_SNAPSHOT_AS_OF,
    get_sp500_constituent_provenance,
    join_market_caps,
    load_sp500_constituents,
    parse_wikipedia_constituents,
    provider_symbol,
)


SAMPLE_HTML = """
<table id="constituents">
<tbody>
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>HQ</th></tr>
<tr>
  <td><a href="/x">MMM</a></td><td><a>3M</a></td>
  <td>Industrials</td><td>Industrial Conglomerates</td><td>St. Paul</td>
</tr>
<tr>
  <td><a href="/y">BRK.B</a></td><td><a>Berkshire Hathaway</a></td>
  <td>Financials</td><td>Multi-Sector Holdings</td><td>Omaha</td>
</tr>
<tr>
  <td>AMP&amp;T</td><td>Amp &amp; T</td><td>Utilities</td><td>Electric Utilities</td><td>NY</td>
</tr>
</tbody>
</table>
"""


def test_parse_extracts_ticker_name_gics_sector_and_sub_industry():
    rows = parse_wikipedia_constituents(SAMPLE_HTML)
    assert len(rows) == 3
    assert rows[0] == {
        "ticker": "MMM",
        "providerSymbol": "MMM",
        "label": "3M",
        "sector": "Industrials",
        "industry": "Industrial Conglomerates",
    }
    # dotted tickers keep their display form but expose a yfinance provider symbol
    assert rows[1]["ticker"] == "BRK.B"
    assert rows[1]["providerSymbol"] == "BRK-B"
    # html entities are unescaped
    assert rows[2]["ticker"] == "AMP&T"
    assert rows[2]["label"] == "Amp & T"


def test_provider_symbol_normalizes_separators():
    assert provider_symbol("BRK.B") == "BRK-B"
    assert provider_symbol("BF/B") == "BF-B"
    assert provider_symbol("aapl") == "AAPL"


def test_join_market_caps_matches_on_separator_insensitive_key():
    constituents = [
        {"ticker": "AAPL", "providerSymbol": "AAPL", "label": "Apple", "sector": "Information Technology", "industry": "Tech HW"},
        {"ticker": "BRK.B", "providerSymbol": "BRK-B", "label": "Berkshire", "sector": "Financials", "industry": "Holdings"},
        {"ticker": "ZZZZ", "providerSymbol": "ZZZZ", "label": "Missing", "sector": "Energy", "industry": "Oil"},
    ]
    caps = {"AAPL": "4362291605560.00", "BRK/B": "1078202303894.00"}
    joined, missing = join_market_caps(constituents, caps)
    by_ticker = {row["ticker"]: row for row in joined}
    assert by_ticker["AAPL"]["marketCap"] == 4362291605560.0
    assert by_ticker["BRK.B"]["marketCap"] == 1078202303894.0
    # rows without a cap match are reported and excluded
    assert "ZZZZ" not in by_ticker
    assert missing == ["ZZZZ"]


def test_load_sp500_constituents_reads_companies(tmp_path):
    path = tmp_path / "sp500.json"
    path.write_text(
        '{"asOf":"2026-06-23","companies":[{"ticker":"AAPL","marketCap":1.0}]}',
        encoding="utf-8",
    )
    rows = load_sp500_constituents(path)
    assert rows == [{"ticker": "AAPL", "marketCap": 1.0}]


def test_explicit_named_snapshot_does_not_inherit_repository_changeset(tmp_path):
    path = tmp_path / "sp500_constituents.json"
    path.write_text(
        '{"asOf":"2026-06-23","companies":[{"ticker":"AAPL","marketCap":1.0}]}',
        encoding="utf-8",
    )

    assert load_sp500_constituents(path, as_of_date="2026-09-08") == [
        {"ticker": "AAPL", "marketCap": 1.0}
    ]
    assert get_sp500_constituent_provenance(path, as_of_date="2026-09-08")["status"] == "historical_baseline"


@pytest.mark.parametrize("as_of", ["2026-06-23", "2026-09-09"])
def test_custom_bootstrapped_snapshot_never_inherits_changeset_by_date_only(tmp_path, as_of):
    path = tmp_path / "sp500_constituents.json"
    path.write_text(
        json.dumps({"asOf": as_of, "companies": [{"ticker": "ACME", "label": "Acme"}]}),
        encoding="utf-8",
    )

    rows = load_sp500_constituents(path, as_of_date="2026-09-08")
    assert rows[0]["ticker"] == "ACME"


def test_current_dated_snapshot_applies_verified_changes_without_mutating_baseline():
    baseline_path = ROOT / "config" / "sp500_constituents.json"
    historical = load_sp500_constituents(baseline_path, as_of_date="2026-06-23")
    current = load_sp500_constituents(baseline_path, as_of_date=CURRENT_SP500_SNAPSHOT_AS_OF)

    assert len(historical) == 502
    assert {row["ticker"] for row in historical} >= {"CAG", "EA", "SATS", "AVB", "EQR"}
    assert len(current) == 503
    current_by_ticker = {row["ticker"]: row for row in current}
    assert {"CAG", "EA", "SATS", "AVB", "EQR"}.isdisjoint(current_by_ticker)
    assert current_by_ticker["ECHO"]["providerSymbol"] == "ECHO"
    assert current_by_ticker["HON"]["label"] == "Honeywell Technologies"
    assert current_by_ticker["BF.B"]["providerSymbol"] == "BF-B"
    assert current_by_ticker["BF.B"]["marketCap"] > 0
    assert current_by_ticker["HONA"]["marketCapAsOf"] == "2026-09-08"
    # A current load must not rewrite the committed historical rows in memory.
    assert {row["ticker"] for row in historical} >= {"CAG", "EA", "SATS", "AVB", "EQR"}


def test_provenance_exposes_effective_dates_and_future_age_boundary():
    path = ROOT / "config" / "sp500_constituents.json"
    historical = get_sp500_constituent_provenance(path, as_of_date="2026-09-07")
    current = get_sp500_constituent_provenance(path, as_of_date="2026-09-08")
    future = get_sp500_constituent_provenance(path, as_of_date="2026-10-01")

    assert historical["status"] == "historical_baseline"
    assert historical["changesApplied"] == []
    assert current["status"] == "verified_current_snapshot"
    assert current["snapshotAsOf"] == "2026-09-08"
    assert {change["effectiveDate"] for change in current["changesApplied"]} == {
        "2026-06-24", "2026-06-30", "2026-08-05", "2026-08-18",
    }
    hona_change = next(change for change in current["changesApplied"] if change["oldTicker"] == "CAG")
    assert hona_change["additionEffectiveDate"] == "2026-06-29"
    assert any(change["oldTicker"] == "SATS" and change["newTicker"] == "ECHO" for change in current["changesApplied"])
    assert any("spglobal.com/2026-07-31" in change["source"] for change in current["changesApplied"])
    assert future["status"] == "latest_known_snapshot"
    assert future["verifiedThrough"] == "2026-09-08"
    assert current["marketCapAsOf"] == "mixed"
    assert current["baselineMarketCapAsOf"] == "2026-06-23"
    assert current["overridesMarketCapAsOf"] == "2026-09-08"
