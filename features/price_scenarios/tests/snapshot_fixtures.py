"""Synthetic but internally consistent snapshots for store/projection tests."""
from copy import deepcopy
from decimal import Decimal as D

from features.price_scenarios import METHOD_VERSION, SPEC_VERSION, SPEC_SHA256
from features.price_scenarios.scenarios import compute

FILED = "2025-02-01"
PRICE = {"value": "30", "sessionDate": "2025-03-03", "currency": "USD", "provider": "yfinance", "providerSymbol": "ACME"}


def raw_rows(eps_override=None, years=range(2015, 2025), filed=FILED):
    """Ten steady fiscal years: EPS +10% a year, margin 10%, payout 30%, 100 shares."""
    rows = []
    for year in years:
        eps = D("1.1") ** (year - 2015)
        values = {"EPS Diluted": eps, "Shares Diluted": D(100), "Net Income": eps * 100, "Revenue": eps * 1000, "DPS": eps * D("0.3")}
        if eps_override and year in eps_override:
            values["EPS Diluted"] = D(eps_override[year])
        for metric, value in values.items():
            rows.append({"fiscalYear": year, "metric": metric, "value": str(value), "filed": filed, "precision": 2,
                         "accession": f"A-{year}", "form": "10-K", "period": {"start": f"{year}-01-01", "end": f"{year}-12-31"}})
    return rows


def make(price=PRICE, rows=None, events=(), as_of=None, extra_inputs=None, results_patch=None):
    """(inputs, results) with results computed from the same rows via the real engine."""
    rows = rows if rows is not None else raw_rows()
    history = {"rows": deepcopy(rows), "excludedYears": [], "currency": "USD", "sharesBasis": "diluted_weighted_average"}
    closes = [{"fiscalYear": y, "close": str(D("1.1") ** (y - 2015) * 15)} for y in range(2015, 2025)]
    results = compute(history, price, fiscal_prices=closes)
    results["support"] = {"status": "supported", "reasons": [], "notices": []}
    results["shareEvents"] = {"state": "none_confirmed" if not events else "present", "events": list(events)}
    inputs = {"instrumentId": "US:ACME", "asOf": price["sessionDate"], "methodVersion": METHOD_VERSION, "specVersion": SPEC_VERSION, "specSha256": SPEC_SHA256,
              "identity": {"ticker": "ACME", "exchange": "NASDAQ"}, "classificationInputs": {}, "price": dict(price),
              "fiscalYearPrices": closes, "eventPriceChecks": [], "history": {"rows": rows, "excludedYears": []},
              "shareEventSources": {}, "dcfInputs": {"beta": {"value": "1.1", "source": "yfinance_info_beta"}}, **(extra_inputs or {})}
    results.update(results_patch or {})
    return inputs, results
