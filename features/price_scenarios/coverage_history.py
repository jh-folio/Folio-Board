"""Revision-1 raw-history supplements, before any share-event adjustment.

These functions have no IO. All selected facts and validation inputs remain in
the returned history, so a snapshot can replay without a source cache.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .decimal_ops import number, rounded
from .history import _annual_period

EPS, SHARES, INCOME = "EPS Diluted", "Shares Diluted", "Net Income"
THRESHOLD = Decimal("0.03")


def row_at(history, metric, year):
    rows = [r for r in history["rows"] if r["metric"] == metric and int(r["fiscalYear"]) == year]
    return rows[0] if len(rows) == 1 else None


def observations(row):
    """Materialize a prior fact with its unchanged period and unit metadata."""
    if not row:
        return []
    head = {k: deepcopy(v) for k, v in row.items() if k != "priorValues"}
    return [{**head, **deepcopy(fact)} for fact in [*row.get("priorValues", []), head]]


def same_period(*rows):
    return bool(all(rows) and len({(r["period"].get("start"), r["period"]["end"]) for r in rows}) == 1
                and _annual_period(rows[0]["period"].get("start"), rows[0]["period"]["end"]))


def same_scope(*rows):
    return all(rows) and len({r.get('scope') or 'company_consolidated' for r in rows}) == 1


def same_filing_pair(eps, shares):
    pairs = [(e, s) for e in observations(eps) for s in observations(shares)
             if e.get("accession") and (e["filed"], e["accession"]) == (s["filed"], s.get("accession"))
             and same_period(e, s) and not e.get("derived")]
    return max(pairs, key=lambda p: (p[0]["filed"], p[0]["accession"])) if pairs else None


def source_fact(row):
    keys = ("metric", "fiscalYear", "value", "period", "unit", "filed", "accession", "concept", "form", "precision", "classBasis", "scope", "source")
    return {k: deepcopy(row[k]) for k in keys if k in row}


def derive_missing_eps(history, *, listed_class_pending=False):
    """Fill at most two past gaps only after the same-filing EPS/share checks."""
    out = deepcopy(history)
    if listed_class_pending:
        return out
    excluded = {int(r["fiscalYear"]) for r in out.get("excludedYears", [])}
    years = sorted({int(r["fiscalYear"]) for r in out["rows"] if r["period"].get("start")} - excluded)
    if not years:
        return out
    missing = [y for y in years[:-1] if row_at(out, EPS, y) is None]
    if not 1 <= len(missing) <= 2:
        return out
    currency = out.get("currency")
    if not currency:
        return out
    checks = []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for year in reversed(years):
            eps, shares, income = (row_at(out, m, year) for m in (EPS, SHARES, INCOME))
            pair = same_filing_pair(eps, shares)
            if not pair or not income:
                continue
            e, s = pair
            if (number(e["value"]) <= 0 or number(s["value"]) <= 0 or not same_period(e, s, income)
                    or not same_scope(e, s, income) or e.get('classBasis') != s.get('classBasis')
                    or e["unit"] != currency + "/shares" or s["unit"] != "shares" or income["unit"] != currency):
                continue
            quotient = number(income["value"]) / number(s["value"])
            error = abs(quotient - number(e["value"])) / abs(number(e["value"]))
            checks.append({"fiscalYear": year, "eps": source_fact(e), "shares": source_fact(s),
                           "netIncome": source_fact(income), "quotient": str(quotient),
                           "relativeError": str(error), "passed": error <= THRESHOLD})
            if len(checks) == 5:
                break
        if len(checks) < 3 or not all(c["passed"] for c in checks):
            return out
        added = []
        for year in missing:
            income, shares = row_at(out, INCOME, year), row_at(out, SHARES, year)
            if (not same_period(income, shares) or not same_scope(income, shares) or shares.get('classBasis')
                    or number(shares["value"]) <= 0 or shares["unit"] != "shares"
                    or income["unit"] != currency or not shares.get("filed") or not shares.get("accession")
                    or str(shares.get("form", "")).removesuffix("/A") not in {"10-K", "20-F"}):
                continue
            quotient = number(income["value"]) / number(shares["value"])
            added.append({"fiscalYear": year, "metric": EPS, "value": rounded(quotient, 2),
                          "period": deepcopy(shares["period"]), "unit": currency + "/shares", "precision": 2,
                          "concept": "derived:net_income_over_diluted_shares", "derived": "net_income_over_diluted_shares",
                          "form": shares["form"], "filed": shares["filed"], "accession": shares["accession"],
                          "priorValues": [], "sourceRows": [source_fact(income), source_fact(shares)],
                          "unroundedValue": str(quotient), "validation": {"threshold": str(THRESHOLD), "years": deepcopy(checks)}})
        out["rows"] = sorted([*out["rows"], *added], key=lambda r: (r["fiscalYear"], r["metric"], r["period"]["end"]))
    return out


def history_notices(history):
    years = sorted(r["fiscalYear"] for r in history["rows"] if r.get("derived") == "net_income_over_diluted_shares")
    notices = [{"code": "derived_eps_years", "years": years}] if years else []
    if history.get("listedClass"):
        notices.append({"code": "listed_class_eps", "class": history["listedClass"]["label"]})
    return notices
