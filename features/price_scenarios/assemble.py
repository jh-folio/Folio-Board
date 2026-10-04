"""Collected source packets -> one price snapshot's `inputs` and `results` (spec §4.1).

Pure: nothing here reads the network, a cache or the workspace. A collector
hands in already-captured packets (see `collect.py`), so the same function
rebuilds a snapshot from saved sources. The result is either
{"status": "unavailable", "reason"} (nothing storable: stale price, missing
history) or {"status": "available", "inputs", "results", "meta"}. Support limits,
unverified share events and short histories are *stored* as unavailable blocks.
"""
from __future__ import annotations

import datetime as dt
from copy import deepcopy

from . import METHOD_VERSION, SPEC_VERSION, SPEC_SHA256
from .blocks import unavailable
from .dart_events import bonus_decisions, dated_share_changes
from .dcf_runtime import capture_dcf_inputs, replay_dcf
from .debt_inputs import dart_debt_inputs, sec_debt_inputs
from .dividends import NOTICE as DIVIDEND_NOTICE, read_dividends
from .decimal_ops import number
from .events import adjust_fiscal_prices, adjust_history, event_price_checks, merge_events, reconcile_korean_shares
from .history import dart_dividend_history, dart_history, sec_history
from .prices import fiscal_year_prices
from .scenarios import compute, unavailable_results
from .sec_events import reconcile_sec_events
from .securities import listed_security, verify_ads_basis
from .support import classify, dart_classification

STALE_WEEKDAYS = 10
PER_SHARE_ROWS = {"EPS Diluted", "DPS", "Shares Diluted"}


def _weekdays_between(start: dt.date, end: dt.date) -> int:
    return sum((start + dt.timedelta(days=i)).weekday() < 5 for i in range(1, (end - start).days + 1))


def _fail(code: str, sub_code: str | None = None) -> dict:
    return {"status": "unavailable", **unavailable(code, sub_code)}


def _positive_shares(history: dict) -> bool:
    years = sorted({row["fiscalYear"] for row in history["rows"] if row["metric"] == "Shares Diluted"})
    latest = [row for row in history["rows"] if row["metric"] == "Shares Diluted" and row["fiscalYear"] == (years[-1] if years else None)]
    return len(latest) == 1 and number(latest[0]["value"]) > 0


def _us_history(raw: dict, session: str):
    history = sec_history(raw["companyfacts"], as_of=session)
    recent = (raw.get("submissions") or {}).get("filings", {}).get("recent", {})
    latest_annual = max((day for form, day in zip(recent.get("form", []), recent.get("filingDate", []))
                         if form in {"10-K", "10-K/A", "20-F", "20-F/A"} and day <= session), default=None)
    security = listed_security(raw["annualMarkup"], raw["ticker"], accession=raw["annualAccession"])
    from .coverage_history import derive_missing_eps
    from .class_history import listed_class, supplement_class_history
    pending = bool(listed_class(security) and not any(r["metric"] == "EPS Diluted" and
                   r["fiscalYear"] == max(x["fiscalYear"] for x in history["rows"]) for r in history["rows"])) if history["rows"] else False
    if pending:
        history = supplement_class_history(history, raw.get("annualFilings") or [], security, cik=raw["identity"].get("cik"), as_of=session)
    history = derive_missing_eps(history, listed_class_pending=pending)
    classification = {"code": str((raw.get("submissions") or {}).get("sic") or ""), "source": "sec_submissions",
                      "listedSecurity": security, "adsRatio": security.get("adsRatio"),
                      "is20F": str(raw.get("annualForm") or "").startswith("20-F")}
    classification["quoteType"] = (raw.get("daily") or {}).get("quoteType")
    if pending and not history.get("listedClass"):
        classification["classHistoryReason"] = (history.get("classDiagnostics") or {}).get("reason", "listed_class_source_unavailable")
    if security.get("kind") == "ads":
        classification["adsBasisVerified"] = verify_ads_basis(history, security.get("adsRatio"))
    debt = sec_debt_inputs(raw["companyfacts"], history, as_of=session, borrowings_definition=raw.get("borrowingsDefinition"))
    return history, classification, latest_annual, debt


def _kr_history(raw: dict, session: str):
    dart = raw["dart"]
    history = dart_history(dart["batches"], as_of=session)
    history["rows"] += dart_dividend_history(dart["dividends"], as_of=session)["rows"]
    history["rows"].sort(key=lambda row: (row["fiscalYear"], row["metric"]))
    history["dividendCoverage"] = dividend_coverage(dart["dividends"])
    classification = dart_classification(dart["profile"], dart["latestFinancialRows"], ticker=raw["ticker"])
    classification["quoteType"] = (raw.get("daily") or {}).get("quoteType")
    debt = dart_debt_inputs(dart["batches"], history, as_of=session)
    return history, classification, None, debt


def _kr_events(raw: dict, daily: dict, session: str) -> dict:
    """Merged price/DART events plus the year-by-year share-count reconciliation (spec §2.4)."""
    dart = raw["dart"]
    corp_code = raw["identity"]["corpCode"]
    decisions = bonus_decisions(dart["bonus"], corp_code=corp_code, trading_dates=[row["date"] for row in daily["closes"]], as_of=session)
    if decisions["state"] != "received" or daily["eventSourceState"] != "received":
        return {"state": "unknown", "reason": decisions.get("reason") or "event_source_unavailable", "events": [], "evidence": []}
    merged = merge_events(daily["events"], decisions["events"])
    if merged["state"] != "merged":
        return {"state": "unknown", "reason": merged.get("reason") or "event_merge_unknown", "events": [], "evidence": []}
    return {"state": "present" if merged["events"] else "none_confirmed", "reason": None, "events": merged["events"],
            "evidence": [], "decisions": decisions}


def _kr_share_reconciliation(raw: dict, events: list[dict], session: str, *, spec3: bool = False) -> dict:
    """Every adjacent pair of year-end share counts must reconcile; any unknown keeps the state unknown."""
    from .korean_shares import dart_observation
    from . import korean_table
    dart = raw["dart"]
    corp_code = raw["identity"]["corpCode"]
    unit_bases = dart.get("unitBases") or {}
    observed, notices = [], set()
    stored = lambda: [{"year": year, "observation": observation} for year, observation in observed]
    for year, packet in sorted((dart.get("stockTotqy") or {}).items()):
        if packet.get("status") == "013":  # that year's report is not filed yet; a gap in the middle is caught below
            continue
        adapted = (korean_table.observation(packet, corp_code=corp_code, as_of=session) if spec3 else
                   dart_observation(packet, corp_code=corp_code, as_of=session, unit_bases=unit_bases.get(str(year))))
        if adapted["state"] != "received":
            return {"state": "unknown", "reason": adapted["reason"], "pairs": [], "observations": stored()}
        if adapted.get("notice"):
            notices.add(adapted["notice"])
        observed.append((int(year), adapted["observation"]))
    checks = []
    for (year_a, first), (year_b, second) in zip(observed, observed[1:]):
        if year_b != year_a + 1:
            return {"state": "unknown", "reason": "share_count_gap", "pairs": checks, "observations": stored()}
        packet = (dart.get("irds") or {}).get(str(year_b))
        changes = dated_share_changes(packet or {}, corp_code=corp_code, as_of=session)
        if changes["state"] != "received":
            return {"state": "unknown", "reason": changes["reason"], "pairs": checks, "observations": stored()}
        interval = [c for c in changes["changes"] if first["periodEnd"] < c["date"] <= second["periodEnd"]]
        coverage = dart.get("coverage") or {"state": "unknown"}
        outcome = reconcile_korean_shares(first, second, events, interval, coverage=coverage, as_of=session)
        checks.append({"start": year_a, "end": year_b, **outcome})
        if outcome["state"] != "matched":
            return {"state": "unknown", "reason": outcome["reason"], "pairs": checks, "observations": stored()}
    return {"state": "matched" if checks else "unknown", "reason": None if checks else "share_count_evidence_unavailable",
            "pairs": checks, "notices": sorted(notices), "observations": stored()}


def dividend_coverage(packets: list[dict]) -> list[int]:
    """Fiscal years a successful DART dividend table covers (stored in the input history)."""
    covered: set[int] = set()
    for packet in packets:
        if packet.get("status") != "000":
            continue
        for row in packet.get("list", []):
            end = str(row.get("stlm_dt") or "")
            if end[:4].isdigit() and row.get("se") == "주당 현금배당금(원)":
                covered.update(int(end[:4]) - offset for offset in range(3))
    return sorted(covered)


def unreadable_dividend_years(history: dict) -> set[int]:
    """Years outside `history.dividendCoverage` are lookup failures, not "no dividend" (Korea only)."""
    if "dividendCoverage" not in history:
        return set()
    return {int(row["fiscalYear"]) for row in history["rows"]} - set(history["dividendCoverage"])


def assemble(raw: dict, *, spec3: bool | None = None) -> dict:
    from . import method_at_least
    spec3 = method_at_least(METHOD_VERSION, 3) if spec3 is None else spec3
    now = dt.datetime.fromisoformat(raw["now"])
    market, daily = raw["market"], raw.get("daily")
    if market not in {"US", "KR"} or not daily:
        return _fail("price_unavailable")
    price = deepcopy(daily["price"])
    session = price["sessionDate"]
    local_today = now.astimezone(dt.timezone.utc).date()
    if _weekdays_between(dt.date.fromisoformat(session), local_today) > STALE_WEEKDAYS:
        return _fail("price_stale")
    try:
        history, classification, latest_annual, debt = (_us_history if market == "US" else _kr_history)(raw, session)
    except (KeyError, ValueError, TypeError):
        return _fail("financial_history_unavailable")
    if not history["rows"]:
        return _fail("financial_history_unavailable")
    classification["currencies"] = {"reporting": history.get("currency"), "quote": price.get("currency")}
    support = classify({"market": market}, classification, reporting_currency=history.get("currency"),
                       quote_currency=price.get("currency"),
                       share_unit_status="confirmed" if _positive_shares(history) else "unknown",
                       ads_verified=bool(classification.get("adsBasisVerified")))
    periods = [{"fiscalYear": row["fiscalYear"], "periodEnd": row["period"]["end"]} for row in history["rows"]
               if row["metric"] == "EPS Diluted"]
    fiscal = fiscal_year_prices(daily["closes"], periods)

    shares_block, evidence = {"state": "unknown", "reason": "support_limited", "events": [], "evidence": []}, []
    results: dict
    adjusted = None
    dcf_inputs = {"status": "unavailable", "reason": {"code": "support_limited"}}
    price_checks: list[dict] = []
    share_sources: dict = {"providerEvents": deepcopy(daily["events"]), "eventSourceState": daily["eventSourceState"]}
    if support["status"] != "supported":
        code = support["reasons"][0]["code"]
        results = unavailable_results(code, support["reasons"][0].get("subCode"))
        results["dcf"] = unavailable(code, support["reasons"][0].get("subCode"))
    else:
        if market == "US":
            merged = merge_events(daily["events"], [])
            events_state = reconcile_sec_events(history, merged["events"], source_state=daily["eventSourceState"],
                                                session_date=session, security_kind=classification["listedSecurity"]["kind"],
                                                latest_annual_filed=latest_annual)
            shares_block = {"state": events_state["state"], "reason": events_state.get("reason"),
                            "events": events_state["events"], "evidence": events_state["filingPairChecks"]}
        else:
            kr_notices = []
            kr = _kr_events(raw, daily, session)
            share_sources["dartDecisions"] = (kr.get("decisions") or {}).get("events", [])
            dart = raw["dart"]
            share_sources["krShareCounts"] = {"stockTotqySttus": deepcopy(dart.get("stockTotqy") or {}),
                                              "irdsSttus": deepcopy(dart.get("irds") or {}),
                                              "coverage": deepcopy(dart.get("coverage")),
                                              "unitBases": deepcopy(dart.get("unitBases") or {}), "observations": []}
            shares_block = {"state": kr["state"], "reason": kr["reason"], "events": kr["events"], "evidence": []}
            if kr["state"] != "unknown":
                recon = _kr_share_reconciliation(raw, kr["events"], session, spec3=spec3)
                shares_block["evidence"] = recon["pairs"]
                share_sources["krShareCounts"]["observations"] = recon["observations"]
                kr_notices = recon.get("notices", [])
                if recon["state"] != "matched":
                    shares_block.update(state="unknown", reason=recon["reason"])
        if shares_block["state"] not in {"present", "none_confirmed"}:
            results = unavailable_results("share_event_unknown", shares_block.get("reason"))
            results["dcf"] = unavailable("share_event_unknown", shares_block.get("reason"))
        else:
            checked, price_checks = event_price_checks(shares_block["events"], daily["closes"], fiscal)
            shares_block["events"] = checked
            ads = (classification.get("adsRatio") or {}).get("value")
            adjusted = adjust_history(history, checked, state=shares_block["state"], session_date=session, ads_ratio=ads)
            try:
                fiscal_adjusted, reason = adjust_fiscal_prices(fiscal, checked), None
            except ValueError:
                fiscal_adjusted, reason = None, {"code": "price_event_unverified"}
            dividends, zero_years = (None, [])
            if spec3:
                blocked = unreadable_dividend_years(history) if market == "KR" else None
                dividends, zero_years = read_dividends(adjusted, unreadable_years=blocked)
            results = compute(adjusted, price, fiscal_prices=fiscal_adjusted, prices_reason=reason, dividends=dividends)
            used = sorted({row["fiscalYear"] for row in results["ranges"]["payout"].get("values", [])} & set(zero_years))
            if spec3:
                results["ranges"]["payout"]["zeroReadYears"] = used
                for item in results["ranges"]["payout"].get("values", []):
                    if item["fiscalYear"] in used:  # only the years read as "no dividend" carry the basis (§3.1-3)
                        item["dividendBasis"] = "no_dividend_fact"
                if used:
                    results["notices"] = [*results["notices"], DIVIDEND_NOTICE]
                if market == "KR" and kr_notices:
                    support = {**support, "notices": [*support["notices"], *kr_notices]}
            results["adjusted"] = {"rows": [row for row in adjusted["rows"] if row["metric"] in PER_SHARE_ROWS],
                                   "fiscalYearPrices": fiscal_adjusted}
            beta = (raw.get("beta") or {}).get("beta") or {"value": None, "source": "not_measured"}
            captured = capture_dcf_inputs(adjusted, price, support=support, share_event_state=shares_block["state"],
                                          debt_inputs=debt, beta=beta, risk_free=raw["riskFree"])
            if captured["status"] == "available":
                dcf_inputs = captured["inputs"]
                results["dcf"] = replay_dcf(dcf_inputs)
            else:
                dcf_inputs = {"status": "unavailable", "reason": captured["reason"]}
                results["dcf"] = captured
    results = {"support": support, "shareEvents": shares_block, **results}
    from .crosschecks import cash_conversion
    results["cashConversion"] = cash_conversion(history, support, market, session)
    from .reference_facts import reference_facts
    results["referenceFacts"] = reference_facts(history, adjusted, price, support, shares_block, results["cashConversion"])
    from .coverage_history import history_notices
    results["notices"] = [*results.get("notices", []), *history_notices(history)]
    identity = dict(raw["identity"], ticker=raw["ticker"], market=market)
    inputs = {"instrumentId": f"{market}:{raw['ticker']}", "asOf": session, "methodVersion": METHOD_VERSION,
              "specVersion": SPEC_VERSION, "specSha256": SPEC_SHA256, "identity": identity, "classificationInputs": classification, "price": price,
              "fiscalYearPrices": fiscal, "eventPriceChecks": price_checks, "history": history,
              "shareEventSources": share_sources, "dcfInputs": dcf_inputs}
    meta = {"priceFetchedAt": daily.get("fetchedAt"), "riskFreeFetchedAt": (raw.get("riskFree") or {}).get("fetchedAt"),
            "betaFetchedAt": (raw.get("beta") or {}).get("fetchedAt")}
    return {"status": "available", "inputs": inputs, "results": results, "meta": meta}
