"""Parallel facts with explicit comparison limits. No ranking, total score or new analysis generation."""
import re
import datetime as dt
from features.price_scenarios.decimal_ops import number

from features.price_scenarios.attribution import historical_attribution
from features.price_scenarios import known_spec
from .criteria import evaluate
from .portfolio_fit import instrument_for, verified_symbol

DIMENSIONS = ("companyQuality", "scenarioReturn", "uncertainty", "macroFit", "returnSource", "reasonState", "portfolioOverlap")


def cell(status="unavailable", *, value=None, unit=None, currency=None, basis=None, refs=(), gaps=(), freshness="unknown"):
    return {"status": status, "value": value, "unit": unit, "currency": currency, "basis": basis or {},
            "sourceRefs": list(refs), "dataGaps": list(gaps), "freshness": freshness}


def quality_excerpt(report):
    if not report:
        return cell(gaps=["company_report_missing"])
    markdown = report.get("markdown") or ""
    blocks = re.split(r"(?=^#{2,3}\s)", markdown, flags=re.M)
    selected = [block.strip() for block in blocks if re.match(r"^#{2,3}\s.*(?:재무 품질|사업 경쟁력|경쟁우위|기업 품질|재무 안정|핵심 리스크|리스크와 반증|위험 요인)", block)]
    if not selected:
        return cell(gaps=["company_quality_section_unidentified"])
    return cell("available", value="\n\n".join(selected)[:1800], basis={"reportDate": report.get("generatedAt") or report.get("createdAt"), "definition": "source_report_excerpt"},
                gaps=["excerpt_is_not_a_company_score"])


def candidate(data, criteria, at, attribution_years, portfolio, portfolio_composition=None):
    ident, snapshot, refs = data["identity"], data["snapshot"], data["refs"]
    readiness = evaluate(snapshot, criteria, data["reviews"], today=dt.date.fromisoformat(at[:10]),
                         support_status="unsupported" if ident["market"] not in {"US", "KR"} else "unknown", attempt=data["attempt"])
    if ident["market"] not in {"US", "KR"}:
        readiness["state"] = "unknown"
        readiness["blockingReasons"] = list(dict.fromkeys(["unsupported_market", *readiness["blockingReasons"]]))
    inputs, results = (snapshot or {}).get("inputs") or {}, (snapshot or {}).get("results") or {}
    usable = snapshot is not None and known_spec(inputs) and (results.get("support") or {}).get("status") == "supported"
    currency = (inputs.get("price") or {}).get("currency")
    basis = {"asOf": inputs.get("asOf"), "methodVersion": inputs.get("methodVersion"), "specSha256": inputs.get("specSha256"), "definition": "scenario_annual_return",
             "holdingYears": (criteria or {}).get("holdingYears"), "currency": currency}
    stale = readiness["state"] == "stale"
    source = [{"type": "price_snapshot", "id": refs["snapshotId"]}] if snapshot else []
    scenario = cell("stale" if stale else "available", value=results.get("scenarios", []), unit="fraction_per_year", currency=currency, basis=basis, refs=source, freshness="stale" if stale else "current") if usable else cell(gaps=["price_model_unavailable"], basis=basis)
    quality = quality_excerpt(data["report"])
    if data["reportReadErrors"]:
        quality["dataGaps"] = [gap for gap in quality["dataGaps"] if gap != "company_report_missing"] + ["company_report_unreadable"]
        quality["sourceRefs"].extend({"type": "unreadable_company_report", **row} for row in data["reportReadErrors"])
        if data["report"] is None:
            quality["status"] = "unknown"
    if refs["report"]:
        quality["sourceRefs"].append({"type": "company_report", **refs["report"]})
    uncertainty = cell("available", value={"notices": results.get("notices", []), "support": results.get("support"),
                                          "blockingReasons": readiness["blockingReasons"], "reviewRows": data["reviews"],
                                          "exposureGaps": (data["exposure"] or {}).get("dataGaps", [])}, refs=source,
                       gaps=[] if snapshot else ["price_snapshot_missing"])
    macro = cell("available", value=data["macro"], basis={"asOf": at, "methodVersion": "exposure-interpretation-1", "promotion": "shadow"},
                 refs=[{"type": "exposure_profile", "id": refs["exposureProfileId"]}], gaps=["macro_interpretation_shadow", "exposure_is_partial"]) if data["macro"] else cell(gaps=["company_exposure_not_investigated"])
    past = historical_attribution(inputs, attribution_years) if usable else {"status": "unavailable", "reason": {"code": "price_model_unavailable"}}
    history_basis = {"asOf": inputs.get("asOf"), "methodVersion": inputs.get("methodVersion"), "specSha256": inputs.get("specSha256"),
                     "definition": "fiscal_endpoint_return_attribution", "currency": currency, "requestedYears": attribution_years,
                     **{key: past.get(key) for key in ("startDate", "endDate", "startFiscalYear", "endFiscalYear", "startPeriodEnd", "endPeriodEnd")}}
    historical = cell("stale" if stale else "available", value=past, currency=currency, basis=history_basis, refs=source, freshness="stale" if stale else "current") if past.get("status") == "available" else cell(basis=history_basis, gaps=[(past.get("reason") or {}).get("code", "attribution_unavailable")])
    reason_value = data["reason"]
    reason_cell = cell("available" if reason_value["status"] != "unknown" else "unknown", value=reason_value,
                       refs=[{"type": "reason_revision", "id": reason_value["revisionId"], "layer": "hypothesis"}] if reason_value["revisionId"] else [],
                       gaps=[reason_value.get("identityGap") or "reason_history_not_verified"] if reason_value["status"] == "unknown" else [])
    positions = (portfolio or {}).get("positions", [])
    candidate_key = instrument_for(ident)
    holding_keys = []
    for row in positions:
        key = instrument_for(row) if isinstance(row, dict) else None
        symbol = str(row.get("symbol") or (row.get("resolved") or {}).get("providerSymbol") or "").upper() if isinstance(row, dict) else ""
        if key and symbol and not verified_symbol({"market": key.split(":", 1)[0], "ticker": key.split(":", 1)[1]}, symbol):
            key = None
        holding_keys.append(key)
    held = [row for row, key in zip(positions, holding_keys) if key is not None and key == candidate_key]
    unresolved = candidate_key is None or any(key is None for key in holding_keys)
    overlap = cell("unknown" if unresolved else "available", value={"heldSameSecurity": True if held else None if unresolved else False,
                    "holdings": held, "industry": (inputs.get("classificationInputs") or {}).get("industry"), "quoteCurrency": currency,
                    "disclosedFactors": [{"factor": item["factor"], "direction": item["direction"]} for item in (data["exposure"] or {}).get("items", [])]},
                   gaps=["holding_identity_not_verified"] if unresolved else ["overlap_weights_not_captured", "economic_currency_not_investigated"])
    if portfolio_composition is not None:
        industry = (inputs.get("classificationInputs") or {}).get("industry")
        factors = overlap["value"]["disclosedFactors"]
        overlap["value"]["confirmedWeights"] = {
            "sameSecurity": portfolio_composition["security"].get(candidate_key, "0") if candidate_key is not None else None,
            "sameIndustry": portfolio_composition["industry"].get(industry, "0") if industry else None,
            "sameQuoteCurrency": portfolio_composition["currency"].get(currency, "0") if currency else None,
            "disclosedFactors": [{**row, "weight": portfolio_composition["macro"].get(f'{row["factor"]}:{row["direction"]}', "0")} for row in factors],
            "uninvestigatedHoldingWeight": portfolio_composition["uninvestigatedHoldingWeight"],
        }
        overlap["dataGaps"] = [gap for gap in overlap["dataGaps"] if gap != "overlap_weights_not_captured"] + ["exposure_is_partial"]
    dimensions = dict(zip(DIMENSIONS, (quality, scenario, uncertainty, macro, historical, reason_cell, overlap)))
    warnings = list(dict.fromkeys(gap for dimension in dimensions.values() for gap in dimension["dataGaps"]))
    readiness["warnings"] = warnings
    readiness.pop("projection", None)
    return {"identity": ident, "readiness": readiness, "dimensions": dimensions, "sourceRefs": refs,
            "tradeoffs": {"criteriaMet": [key for key, entry in readiness["criteria"].items() if entry["state"] == "met"],
                          "criteriaUnmet": [key for key, entry in readiness["criteria"].items() if entry["state"] == "unmet"], "uncertainties": warnings}}


def comparability(candidates):
    pairs = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1:]:
            limits = {}
            for dimension in DIMENSIONS:
                a, b = left["dimensions"][dimension], right["dimensions"][dimension]
                reasons = []
                numeric = dimension in {"scenarioReturn", "returnSource"}
                if numeric:
                    if a["status"] != "available" or b["status"] != "available":
                        reasons.append("missing_or_stale")
                    keys = ("asOf", "methodVersion", "specSha256", "currency", "definition", "holdingYears") if dimension == "scenarioReturn" else ("asOf", "methodVersion", "specSha256", "currency", "definition", "requestedYears", "startDate", "endDate", "startFiscalYear", "endFiscalYear", "startPeriodEnd", "endPeriodEnd")
                    for key in keys:
                        if a["basis"].get(key) != b["basis"].get(key):
                            reasons.append(f"{key}_different")
                    if any(a["basis"].get(key) is None or b["basis"].get(key) is None for key in ("asOf", "methodVersion", "specSha256", "currency")):
                        reasons.append("basis_missing")
                    if dimension == "scenarioReturn" and (a["basis"].get("holdingYears") is None or b["basis"].get("holdingYears") is None):
                        reasons.append("holding_period_not_set")
                    if dimension == "scenarioReturn":
                        ar = {(row.get("label"), row.get("horizon")): row.get("status") for row in a.get("value") or []}
                        br = {(row.get("label"), row.get("horizon")): row.get("status") for row in b.get("value") or []}
                        numeric_rows = True
                        for row in [*(a.get("value") or []), *(b.get("value") or [])]:
                            try:
                                number(row.get("irr"))
                            except ValueError:
                                numeric_rows = False
                            if row.get("irrRange") is not None:
                                numeric_rows = False
                        if not ar or not br or ar != br or not numeric_rows or any(value != "available" for value in [*ar.values(), *br.values()]):
                            reasons.append("scenario_cells_missing")
                else:
                    if a["status"] not in {"available", "stale"} or b["status"] not in {"available", "stale"}:
                        reasons.append("context_missing")
                    reasons.extend(["context_has_different_basis"] if a["basis"] != b["basis"] else [])
                limits[dimension] = {"status": "incomparable" if reasons else "same_basis" if numeric else "context_only", "reasons": reasons}
            pairs.append({"left": left["identity"]["instrumentId"], "right": right["identity"]["instrumentId"], "dimensions": limits})
    return pairs
