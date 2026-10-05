"""spec-5 historical holding comparison. Capture is pure; every read replays immutable inputs."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import re

from . import METHOD_VERSION, known_spec
from .blocks import not_applicable, unavailable
from .decimal_ops import number, rounded
from .events import adjust_history, event_price_checks

ZERO, ONE = Decimal(0), Decimal(1)


def _price_failure(error: ValueError) -> dict:
    """Return only fixed public reason codes, never arbitrary exception text."""
    if error.args == ("invalid_period",):
        return unavailable("invalid_period")
    if error.args == ("share_event_unknown",):
        return unavailable("share_event_unknown")
    if error.args == ("price_event_unverified",):
        return unavailable("price_event_unverified")
    if error.args == ("endpoint_price_missing",):
        return unavailable("endpoint_price_missing")
    return unavailable("invalid_number")


def capture(raw: dict, inputs: dict, support: dict, shares: dict) -> dict:
    """Add only new inputs; never change fiscal prices, history or old result blocks."""
    daily, session = raw["daily"], inputs["asOf"]
    closes = deepcopy([r for r in daily.get("closes", []) if r["date"] <= session])
    history = inputs["history"]
    periods = {}
    for row in history["rows"]:
        periods.setdefault(int(row["fiscalYear"]), set()).add(row["period"]["end"])
    annual = [{"fiscalYear": y, "periodEnd": next(iter(ends)) if len(ends) == 1 else None}
              for y, ends in sorted(periods.items()) if y not in {r["fiscalYear"] for r in history.get("excludedYears", [])}]
    checked, checks = event_price_checks(shares.get("events", []), closes, [])
    first = min((r["period"].get("start") or r["period"]["end"] for r in history["rows"]), default=session)
    raw_bars = deepcopy([r for r in daily.get("rawBars", []) if r["date"] <= session])
    request = deepcopy(daily.get("request", {}))
    stock = {"request": request, "sourceVersion": daily.get("sourceVersion"),
             "identity": deepcopy(daily.get("quoteMetadata", {})), "closes": closes, "rawBars": raw_bars,
             "sourceState": "received", "currency": inputs["price"].get("currency"),
             "dividendCoverage": "received" if daily.get("dividendColumnPresent") and raw_bars else "unknown",
             "cashDividends": [], "distributionEvents": []}
    dates = {r["date"] for r in closes}
    stock["coverage"] = {"returnedStart": min(dates) if dates else None, "returnedEnd": max(dates) if dates else None,
                         "requestedStart": request.get("start"), "requestedEnd": request.get("endExclusive"),
                         "continuityBasis": "provider_rows_max_10_weekday_observation_gap"}
    for bar in raw_bars:
        value = bar.get("dividend")
        if value is not None and number(value) > 0:
            stock["cashDividends"].append({"exDate": bar["date"], "rawAmount": value, "currency": stock["currency"],
                "shareUnitBasis": "raw_close_unit", "dateBasis": "provider_daily_cash_event",
                "listedUnit": daily.get("dividendListedUnit") or ("per_listed_ads_unverified" if
                    (inputs.get("classificationInputs", {}).get("listedSecurity") or {}).get("kind") == "ads" else "per_listed_share"),
                "basisEvidence": "requires_price_factor_replay", "normalizationDate": session})
        if bar.get("capitalGain") is not None and number(bar["capitalGain"]) != 0:
            stock["distributionEvents"].append({"date": bar["date"], "kind": "unverified_distribution"})
    benchmark = deepcopy(raw.get("benchmarkDaily") or {"sourceState": "unavailable", "reason": {"code": "benchmark_source_failed"}})
    if "closes" in benchmark:
        benchmark["closes"] = [r for r in benchmark["closes"] if r["date"] <= session]
    packet = {"schemaVersion": 1, "priceBasis": "dividend_unadjusted", "snapshotShareUnitDate": session,
            "annualPeriods": annual, "stockDaily": stock, "benchmarkDaily": benchmark,
            "shareEvents": {"state": shares["state"], "events": checked, "priceChecks": checks,
                "coverageStart": max(first, min(dates)) if dates else first, "coverageEnd": session},
            "support": deepcopy(support)}
    # Keep every provider cash event even when its price bar is missing. The
    # saved per-event proof makes the unit decision inspectable without I/O.
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for row in stock["cashDividends"]:
            try:
                row.update(_cash_event(packet, row))
            except ValueError:
                row["unitValidation"] = {"status": "unavailable", "code": "dividend_unit_unverified"}
    return packet


def _packet(inputs: dict, *, earnings=True) -> tuple[dict | None, dict | None]:
    if inputs.get("methodVersion") != METHOD_VERSION or not known_spec(inputs):
        return None, not_applicable("comparison_inputs_missing")
    packet = inputs.get("returnAttributionInputs")
    if not packet or packet.get("schemaVersion") != 1:
        return None, not_applicable("comparison_inputs_missing")
    actual = next((r["close"] for r in packet["stockDaily"]["closes"] if r["date"] == inputs["price"]["sessionDate"]), None)
    if actual is None or number(actual) != number(inputs["price"]["value"]):
        return None, unavailable("comparison_input_conflict")
    if earnings and packet["support"]["status"] != "supported":
        return None, not_applicable(packet["support"]["reasons"][0]["code"])
    return packet, None


def _prices(packet: dict, start: str, end: str) -> tuple[Decimal, Decimal, list[dict]]:
    if start >= end:
        raise ValueError("invalid_period")
    shares = packet["shareEvents"]
    if shares["state"] not in {"present", "none_confirmed"}:
        raise ValueError("share_event_unknown")
    if not shares["coverageStart"] <= start < end <= shares["coverageEnd"]:
        raise ValueError("price_event_unverified")
    rows = packet["stockDaily"]["closes"]
    by_date = {r["date"]: number(r["close"]) for r in rows}
    if len(by_date) != len(rows) or start not in by_date or end not in by_date:
        raise ValueError("endpoint_price_missing")
    events = [e for e in shares["events"] if start < e["eventDate"] <= shares["coverageEnd"]]
    if any(e["priceCheck"] not in {"reflected", "not_reflected"} for e in events):
        raise ValueError("price_event_unverified")
    def adjusted(day):
        factor = ONE
        for e in events:
            if day < e["eventDate"] and e["priceCheck"] == "not_reflected":
                factor *= number(e["ratio"])
        return by_date[day] / factor
    p0, p1 = adjusted(start), adjusted(end)
    if min(p0, p1) <= 0:
        raise ValueError("endpoint_price_missing")
    return p0, p1, events


def _shown(value: Decimal) -> Decimal:
    return (value * 100).quantize(Decimal(".1"), rounding=ROUND_HALF_EVEN) + ZERO


def _benchmark(packet: dict, start: str, end: str, rp: Decimal) -> dict:
    block = packet["benchmarkDaily"]
    if block.get("sourceState") != "received":
        return unavailable("benchmark_unavailable", (block.get("reason") or {}).get("code"))
    market = block.get("market")
    identity = {"US": ("^GSPC", "USD", "America/New_York"), "KR": ("^KS11", "KRW", "Asia/Seoul")}.get(market)
    if (not identity or (block.get("providerSymbol"), block.get("currency"), block.get("exchangeTimezone")) != identity
            or block.get("kind") != "price" or block.get("currency") != packet["stockDaily"]["currency"]):
        return unavailable("benchmark_unavailable", "identity_unverified")
    prices = {r["date"]: number(r["close"]) for r in block["closes"]}
    if len(prices) != len(block["closes"]) or start not in prices or end not in prices or min(prices[start], prices[end]) <= 0:
        missing = [name for name, day in (("start", start), ("end", end)) if day not in prices or prices[day] <= 0]
        return unavailable({"code": "benchmark_date_missing", "endpoints": missing or ["start", "end"], "startDate": start, "endDate": end})
    ri = prices[end] / prices[start] - ONE
    ri4, rp4 = number(rounded(ri, 4)), number(rounded(rp, 4))
    return {"status": "available", "id": block["id"], "priceReturn": str(ri4), "rawDifference": str(rp-ri),
            "display": {"stock": str(_shown(rp4)), "index": str(_shown(ri4)), "difference": str(_shown(rp4)-_shown(ri4))},
            "startDate": start, "endDate": end, "startClose": str(prices[start]), "endClose": str(prices[end])}


def _cash_event(packet: dict, row: dict) -> dict:
    stock, day = packet["stockDaily"], row["exDate"]
    bars = {r["date"]: r for r in stock["rawBars"]}
    closes = {r["date"] for r in stock["closes"]}
    events = [e for e in packet["shareEvents"]["events"] if day < e["eventDate"] <= packet["shareEvents"]["coverageEnd"]]
    if (day not in closes or row["currency"] != stock["currency"] or row["listedUnit"] not in {"per_listed_share", "per_listed_ads"}
            or any(e["eventDate"] == day for e in packet["shareEvents"]["events"])
            or any(e["priceCheck"] not in {"reflected", "not_reflected"} for e in events)):
        raise ValueError("dividend_unit_unverified")
    previous = max((d for d in closes if d < day), default=None)
    before, after = bars.get(previous, {}), bars.get(day, {})
    try:
        c0, c1, a0, a1, raw = map(number, (before.get("close"), after.get("close"), before.get("adjClose"), after.get("adjClose"), row["rawAmount"]))
        if min(c0, c1, a0, a1, raw) <= 0:
            raise ValueError()
        implied = c0 * (ONE-(a0/c0)/(a1/c1))
        if abs(implied-raw)/raw > Decimal(".01"):
            raise ValueError()
        factor, alternative = ONE, ONE
        for event in events:
            ratio = number(event["ratio"])
            alternative *= ratio
            if event["priceCheck"] == "not_reflected": factor *= ratio
        if alternative != ONE and abs(implied-raw/alternative)/(raw/alternative) <= Decimal(".01"):
            raise ValueError()
        return {"amount": str(raw/factor), "normalizationFactor": str(factor), "basisEvidence": "provider_price_unit_consistent",
                "unitValidation": {"status": "available", "previousDate": previous, "impliedDividend": str(implied)}}
    except (ValueError, ArithmeticError):
        raise ValueError("dividend_unit_unverified") from None


def _dividend(packet: dict, start: str, end: str, p0: Decimal, events: list[dict]) -> dict:
    stock = packet["stockDaily"]
    if stock["dividendCoverage"] != "received":
        return unavailable("dividend_history_unavailable")
    if any(start < e["date"] <= end for e in stock["distributionEvents"]):
        return unavailable("unsupported_distribution_event")
    bars = {r["date"]: r for r in stock["rawBars"]}
    closes = {r["date"] for r in stock["closes"]}
    needed = {d for d in closes if start <= d <= end}
    if (not needed <= bars.keys() or any(bars[d].get("dividend") is None for d in needed)
            or any(start < day <= end and (bar.get("dividend") is None or number(bar["dividend"]) < 0) for day, bar in bars.items())):
        return unavailable("dividend_history_unavailable")
    # A successful response with an internal missing year/month is still not a
    # full dividend record. Reuse the endpoint observation budget conservatively;
    # this does not invent exchange holidays or fill a missing observation.
    observed = sorted(day for day in bars if start <= day <= end)
    for left, right in zip(observed, observed[1:]):
        a, b = date.fromisoformat(left), date.fromisoformat(right)
        missing_weekdays = sum((a+timedelta(days=i)).weekday() < 5 for i in range(1, (b-a).days))
        if missing_weekdays > 10:
            return unavailable({"code": "dividend_history_unavailable", "subCode": "internal_coverage_gap", "startDate": left, "endDate": right})
    total, used = ZERO, []
    for row in stock["cashDividends"]:
        day = row["exDate"]
        if not start < day <= end:
            continue
        try:
            proof = _cash_event(packet, row)
        except ValueError:
            return unavailable("dividend_unit_unverified")
        total += number(proof["amount"])
        used.append({**row, **proof})
    return {"status": "available", "amount": str(total), "rawContribution": str(total/p0), "contribution": rounded(total/p0, 4),
            "events": used, "basis": "provider_record_no_dividend" if not used else "ex_date_gross_no_reinvestment"}


def movement(inputs: dict, start: str, end: str) -> dict:
    """Exact date read; never select a nearby date or fetch a missing series."""
    if any(not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) for day in (start, end)):
        raise ValueError("invalid_comparison_dates")
    date.fromisoformat(start); date.fromisoformat(end)
    if start >= end:
        raise ValueError("invalid_comparison_dates")
    packet, error = _packet(inputs, earnings=False)
    if error:
        return error
    requested_start, requested_end = start, end
    if end > inputs["asOf"]:
        return unavailable({"code": "endpoint_price_missing", "endpoint": "end", "requestedDate": end})
    dates = [r["date"] for r in packet["stockDaily"]["closes"]]
    def completed_before(day):
        chosen = max((d for d in dates if d <= day), default=None)
        if not chosen:
            raise ValueError("endpoint_price_missing")
        a, b = date.fromisoformat(chosen), date.fromisoformat(day)
        weekdays = sum((a+timedelta(days=i)).weekday()<5 for i in range(1, (b-a).days+1))
        if weekdays > 10:
            raise ValueError("endpoint_price_missing")
        return chosen
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        try:
            for side, requested in (("start", start), ("end", end)):
                try:
                    chosen = completed_before(requested)
                except ValueError:
                    return unavailable({"code": "endpoint_price_missing", "endpoint": side, "requestedDate": requested})
                if side == "start": start = chosen
                else: end = chosen
            p0, p1, _ = _prices(packet, start, end)
        except ValueError as error:
            return _price_failure(error)
        rp = p1/p0-ONE
        return {"status": "available", "instrumentId": inputs["instrumentId"], "asOf": inputs["asOf"],
                "requestedStartDate": requested_start, "requestedEndDate": requested_end,
                "methodVersion": inputs["methodVersion"], "specSha256": inputs["specSha256"],
                "startDate": start, "endDate": end, "startClose": str(p0), "endClose": str(p1),
                "priceReturn": rounded(rp, 4), "displayPriceReturn": str(_shown(number(rounded(rp, 4)))),
                "benchmark": _benchmark(packet, start, end, rp)}


def historical_attribution(inputs: dict, years: int = 5) -> dict:
    if type(years) is not int or years not in {1, 3, 5}:
        raise ValueError("invalid_attribution_years")
    packet, error = _packet(inputs)
    if error:
        return error
    periods = {r["fiscalYear"]: r["periodEnd"] for r in packet["annualPeriods"]}
    if not periods:
        return unavailable("attribution_history_too_short", "years_too_few")
    end_year = max(periods); start_year = end_year-years
    if not periods.get(start_year) or not periods.get(end_year):
        return unavailable({"code": "attribution_history_too_short", "subCode": "years_too_few", "firstFiscalYear": min(periods),
                            "endFiscalYear": end_year, "startFiscalYear": start_year, "requestedYears": years})
    dates = [r["date"] for r in packet["stockDaily"]["closes"]]
    def endpoint(period):
        selected = max((d for d in dates if d <= period), default=None)
        if not selected:
            raise ValueError("endpoint_price_missing")
        a, b = date.fromisoformat(selected), date.fromisoformat(period)
        weekdays = sum((a+timedelta(days=i)).weekday()<5 for i in range(1, (b-a).days+1))
        if weekdays > 10:
            raise ValueError("endpoint_price_missing")
        return selected
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        try:
            for side, period in (("start", periods[start_year]), ("end", periods[end_year])):
                try:
                    chosen = endpoint(period)
                except ValueError:
                    return unavailable({"code": "endpoint_price_missing", "endpoint": side, "requestedDate": period})
                if side == "start": start = chosen
                else: end = chosen
            p0, p1, events = _prices(packet, start, end)
        except ValueError as error:
            return _price_failure(error)
        rp = p1/p0-ONE; rp4 = number(rounded(rp, 4))
        earnings = unavailable({"code": "attribution_history_too_short", "subCode": "missing_endpoint_eps", "startFiscalYear": start_year, "endFiscalYear": end_year})
        history = adjust_history(inputs["history"], packet["shareEvents"]["events"], session_date=inputs["asOf"],
                                 state=packet["shareEvents"]["state"], ads_ratio=(inputs.get("classificationInputs", {}).get("adsRatio") or {}).get("value"))
        eps = {r["fiscalYear"]: number(r["value"]) for r in history["rows"] if r["metric"] == "EPS Diluted"}
        eps_rows = {r["fiscalYear"]: r for r in history["rows"] if r["metric"] == "EPS Diluted"}
        earnings["reason"]["endpoints"] = [side for side, year in (("start", start_year), ("end", end_year)) if year not in eps]
        if start_year in eps and end_year in eps:
            if min(eps[start_year], eps[end_year]) <= 0:
                code = "non_positive_both_eps" if max(eps[start_year], eps[end_year]) <= 0 else "non_positive_start_eps" if eps[start_year] <= 0 else "non_positive_end_eps"
                earnings = unavailable({"code": code, "startFiscalYear": start_year, "endFiscalYear": end_year})
            else:
                g = eps[end_year]/eps[start_year]-ONE; g4 = number(rounded(g, 4)); m4 = rp4-g4
                earnings = {"status": "available", "growth": str(g4), "rerating": str(m4),
                            "rawGrowth": str(g), "rawRerating": str(rp-g), "startEps": str(eps[start_year]),
                            "endEps": str(eps[end_year]), "startPE": str(p0/eps[start_year]), "endPE": str(p1/eps[end_year])}
        dividend = _dividend(packet, start, end, p0, events)
        total = unavailable(dividend["reason"]) if dividend["status"] != "available" else {
            "status": "available", "value": str(rp4+number(dividend["contribution"]))}
        display = {"price": str(_shown(rp4))}
        if total["status"] == "available":
            display.update(total=str(_shown(number(total["value"]))), dividend=str(_shown(number(dividend["contribution"]))))
        if earnings["status"] == "available":
            display["growth"] = str(_shown(number(earnings["growth"])))
            display["rerating"] = str((number(display["total"])-number(display["growth"])-number(display["dividend"]))
                                     if "total" in display else _shown(rp4)-number(display["growth"]))
        def endpoint_basis(year, day, price):
            row = eps_rows.get(year)
            return {"fiscalYear": year, "periodEnd": periods[year], "priceDate": day, "close": str(price),
                    "eps": None if row is None else deepcopy({k: row[k] for k in (
                        "value", "rawValue", "period", "form", "filed", "accession", "receiptNo", "concept", "sourceField", "unit", "adjustment") if k in row})}
        calculation = {"rawPriceReturn": str(rp), "rawGrowth": earnings.get("rawGrowth"),
                       "rawRerating": earnings.get("rawRerating"), "rawDividend": dividend.get("rawContribution"),
                       "rawTotal": str(rp+number(dividend["rawContribution"])) if total["status"] == "available" else None,
                       "response": {"price": str(rp4), "growth": earnings.get("growth"), "rerating": earnings.get("rerating"),
                                    "dividend": dividend.get("contribution"), "total": total.get("value")},
                       "display": deepcopy(display)}
        return {"status": "available", "requestedYears": years, "startFiscalYear": start_year, "endFiscalYear": end_year,
                "startPeriodEnd": periods[start_year], "endPeriodEnd": periods[end_year], "startDate": start, "endDate": end,
                "startClose": str(p0), "endClose": str(p1), "priceReturn": str(rp4), "rawPriceReturn": str(rp),
                "earnings": earnings, "dividend": dividend, "total": total, "display": display,
                "benchmark": _benchmark(packet, start, end, rp), "calculation": calculation,
                "basis": {"start": endpoint_basis(start_year, start, p0), "end": endpoint_basis(end_year, end, p1),
                          "priceSource": {k: deepcopy(packet["stockDaily"].get(k)) for k in ("request", "sourceVersion", "identity", "currency")}}}
