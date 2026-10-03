"""`assemble()` as a unit: support -> events -> prices -> dividends -> scenarios and DCF, on synthetic sources."""
import datetime as dt
import json
from copy import deepcopy

import pytest

from features.price_scenarios import assemble as asm
from features.price_scenarios.decimal_ops import fingerprint

from .snapshot_fixtures import raw_rows

NOW = "2025-03-05T06:00:00+00:00"


def weekday_closes(first=2014, last=2025):
    """One close per weekday, rising slowly; enough for every fiscal year-end lookup."""
    out, day, price = [], dt.date(first, 1, 1), 10.0
    while day <= dt.date(last, 3, 3):
        if day.weekday() < 5:
            price += 0.01
            out.append({"date": day.isoformat(), "close": f"{price:.2f}"})
        day += dt.timedelta(days=1)
    return out


def us_raw(session="2025-03-03", eps_scale=None):
    rows = raw_rows()
    if eps_scale:
        rows = [dict(row, value=str(float(row["value"]) * eps_scale)) if row["metric"] == "EPS Diluted" else row for row in rows]
    daily = {"price": {"value": "30", "sessionDate": session, "currency": "USD", "provider": "yfinance", "providerSymbol": "ACME"},
             "closes": weekday_closes(), "events": [], "eventSourceState": "received", "exchangeSource": "sec_submissions",
             "fetchedAt": NOW}
    return {"market": "US", "ticker": "ACME", "now": NOW, "identity": {"providerSymbol": "ACME", "cik": "1"}, "daily": daily,
            "rows": rows, "riskFree": {"rate": "0.04", "source": "constant", "fetchedAt": NOW},
            "beta": {"beta": {"value": "1.1", "source": "yfinance_info_beta"}, "fetchedAt": NOW}}


@pytest.fixture
def us(monkeypatch):
    """The SEC readers need real filings; here the history they would return is injected."""
    def history(raw, session):
        data = {"rows": deepcopy(raw["rows"]), "excludedYears": [], "currency": "USD", "sharesBasis": "diluted_weighted_average"}
        classification = {"code": "3571", "source": "sec_submissions", "listedSecurity": {"kind": "common_share"}, "is20F": False}
        return data, classification, "2025-02-01", {"status": "unavailable", "reason": {"code": "debt_unavailable"}}
    monkeypatch.setattr(asm, "_us_history", history)


def test_a_supported_us_company_gives_storable_inputs_and_results(us):
    out = asm.assemble(us_raw())
    assert out["status"] == "available"
    inputs, results = out["inputs"], out["results"]
    assert inputs["instrumentId"] == "US:ACME" and inputs["asOf"] == "2025-03-03"
    assert results["support"]["status"] == "supported" and results["shareEvents"]["state"] == "none_confirmed"
    assert {(row["label"], row["horizon"]) for row in results["scenarios"]} == {(label, h) for label in ("conservative", "base", "optimistic") for h in (5, 10)}
    assert all(row["status"] == "available" for row in results["scenarios"])
    assert json.loads(json.dumps({"inputs": inputs, "results": results})) == {"inputs": inputs, "results": results}  # plain JSON all the way


def test_the_same_sources_give_the_same_fingerprint_and_results_and_one_changed_value_changes_the_fingerprint(us):
    first, second = asm.assemble(us_raw()), asm.assemble(us_raw())
    assert fingerprint(first["inputs"]) == fingerprint(second["inputs"]) and first["results"] == second["results"]
    changed = asm.assemble(us_raw(eps_scale=1.01))
    assert fingerprint(changed["inputs"]) != fingerprint(first["inputs"])


def test_a_stale_price_stores_nothing(us):
    out = asm.assemble(us_raw(session="2025-02-14"))  # 14 weekdays before NOW
    assert out["status"] == "unavailable" and out["reason"]["code"] == "price_stale"
    assert asm.assemble({**us_raw(), "daily": None})["reason"]["code"] == "price_unavailable"
    assert asm.assemble({**us_raw(), "market": "JP"})["reason"]["code"] == "price_unavailable"


def test_a_limited_support_keeps_the_stored_blocks_as_unavailable_with_the_reason(us, monkeypatch):
    original = asm._us_history
    def adr(raw, session):
        history, classification, latest, debt = original(raw, session)
        return history, {**classification, "listedSecurity": {"kind": "ads"}}, latest, debt
    monkeypatch.setattr(asm, "_us_history", adr)
    out = asm.assemble(us_raw())
    assert out["status"] == "available" and out["results"]["support"]["status"] == "limited"
    assert out["results"]["support"]["reasons"][0]["code"] == "adr_ratio_unverified"
    assert all(row["status"] == "unavailable" for row in out["results"]["scenarios"])
    assert out["results"]["dcf"]["status"] == "unavailable" and out["inputs"]["dcfInputs"]["status"] == "unavailable"


def test_an_unreadable_history_is_a_failure_not_a_snapshot(monkeypatch):
    monkeypatch.setattr(asm, "_us_history", lambda raw, session: (_ for _ in ()).throw(KeyError("companyfacts")))
    assert asm.assemble(us_raw())["reason"]["code"] == "financial_history_unavailable"
    monkeypatch.setattr(asm, "_us_history", lambda raw, session: ({"rows": []}, {}, None, {}))
    assert asm.assemble(us_raw())["reason"]["code"] == "financial_history_unavailable"


# --- Korea: the share-count source tables are part of the fingerprinted inputs (spec §2.4, §4.1) ---------------------------

CORP = "00126380"


def share_row(year, shares, *, label="보통주"):
    return {"rcept_no": f"{year + 1}0401000001", "corp_code": CORP, "se": label, "now_to_isu_stock_totqy": shares, "now_to_dcrs_stock_totqy": "-",
            "istc_totqy": shares, "redc": "-", "profit_incnr": "-", "rdmstk_repy": "-", "etc": "-", "stlm_dt": f"{year}-12-31"}


def kr_raw(shares="1,000"):
    raw = us_raw()
    raw.update(market="KR", identity={"providerSymbol": "000000.KS", "corpCode": CORP})
    raw["daily"]["price"]["currency"] = "KRW"
    stock = {str(year): {"status": "000", "list": [share_row(year, shares)]} for year in range(2022, 2024)}
    irds = {str(year): {"status": "000", "list": [{"corp_code": CORP, "isu_dcrs_de": "-", "isu_dcrs_stle": "-", "isu_dcrs_stock_knd": "-", "isu_dcrs_qy": "-"}]}
            for year in range(2022, 2024)}
    raw["dart"] = {"coverage": {"state": "confirmed", "start": "2015-01-01", "end": "2025-03-03"}, "stockTotqy": stock, "irds": irds,
                   "bonus": {"status": "013", "list": []}, "unitBases": {}}
    return raw


@pytest.fixture
def kr(monkeypatch):
    def history(raw, session):
        data = {"rows": deepcopy(raw["rows"]), "excludedYears": [], "currency": "KRW", "sharesBasis": "diluted_weighted_average"}
        classification = {"code": "26110", "source": "dart_company", "listedSecurity": {"kind": "common_share"}}
        return data, classification, None, {"status": "unavailable", "reason": {"code": "debt_unavailable"}}
    monkeypatch.setattr(asm, "_kr_history", history)
    monkeypatch.setattr(asm, "_positive_shares", lambda history: True)
    monkeypatch.setattr(asm, "listed_security", lambda *args, **kwargs: {"kind": "common_share"})


def test_korean_share_count_tables_are_part_of_the_fingerprinted_inputs(kr):
    first = asm.assemble(kr_raw())
    assert first["status"] == "available"
    sources = first["inputs"]["shareEventSources"]["krShareCounts"]
    assert set(sources) == {"stockTotqySttus", "irdsSttus", "coverage", "unitBases", "observations"}
    assert sources["stockTotqySttus"]["2023"]["list"][0]["istc_totqy"] == "1,000" and [item["year"] for item in sources["observations"]] == [2022, 2023]
    changed = asm.assemble(kr_raw(shares="1,001"))
    assert fingerprint(changed["inputs"]) != fingerprint(first["inputs"])
    assert fingerprint(asm.assemble(kr_raw())["inputs"]) == fingerprint(first["inputs"])


def test_years_read_as_no_dividend_carry_their_basis_and_the_stored_years_do_not(us):
    raw = us_raw()
    with_dps = asm.assemble(raw)["results"]["ranges"]["payout"]
    assert with_dps["zeroReadYears"] == [] and all("dividendBasis" not in item for item in with_dps["values"])
    raw["rows"] = [row for row in raw["rows"] if row["metric"] != "DPS"] + [
        {"fiscalYear": year, "metric": "Operating Cash Flow", "value": "500", "filed": "2025-02-01", "precision": 0, "accession": f"A-{year}",
         "form": "10-K", "period": {"start": f"{year}-01-01", "end": f"{year}-12-31"}} for year in range(2015, 2025)]
    out = asm.assemble(raw)
    payout = out["results"]["ranges"]["payout"]
    assert payout["status"] == "available" and payout["zeroReadYears"] == list(range(2015, 2025))
    assert all(item["dividendBasis"] == "no_dividend_fact" for item in payout["values"])
    assert "dividend_assumed_zero_from_absence" in out["results"]["notices"]
