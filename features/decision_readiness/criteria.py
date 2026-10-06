"""Pure, bounded preparation rules. Reasons, ownership and review length are not inputs."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from features.price_scenarios import known_spec
from features.price_scenarios.decimal_ops import number
from features.price_scenarios.projection import project

STATES = frozenset({"ready_for_review", "incomplete", "criteria_unmet", "stale", "unknown"})
COPY = {
    "ready_for_review": "가격과 내 기준을 검토할 자료가 갖춰졌습니다",
    "incomplete": "검토에 필요한 계산 자료가 일부 빠져 있습니다",
    "criteria_unmet": "입력한 내 기준에 미달하는 항목이 있습니다",
    "stale": "오래되었거나 정정된 자료를 다시 확인해야 합니다",
    "unknown": "기준이나 자료가 없어 준비 상태를 확인할 수 없습니다",
}
SCOPE_COPY = "가격과 내 기준의 확인 범위입니다. 다른 자료 공백은 아래에 남아 있으며 투자 판단이나 안전성을 뜻하지 않습니다."
UNSUPPORTED = frozenset({"fund_not_supported", "market_not_supported", "industry_not_supported",
                         "financial_holding", "non_common_listing", "instrument_not_supported"})


def high_premise(results: dict, requirement: dict, years: int | None, policy: bool | None) -> dict:
    axes = {}
    for axis, range_name, minimum in (("growth", "growth", 3), ("exitPE", "pe", 5), ("netMargin", "netMargin", 5)):
        block = (results.get("ranges") or {}).get(range_name) or {}
        need = (requirement.get(axis) or {}).get(str(years)) or {}
        detail = {"state": "unknown", "reason": "comparison_data_missing", "needed": None,
                  "sampleMin": None, "sampleMax": None, "p75": block.get("p75"), "source": range_name}
        try:
            values = [number(row["value"]) for row in block.get("values", [])]
            if block.get("status") == "available" and len(values) >= minimum and need.get("status") == "available":
                detail.update(sampleMin=str(min(values)), sampleMax=str(max(values)))
                if axis == "exitPE" and need.get("state") == "not_needed":
                    detail.update(state="not_needed", reason="dividends_sufficient")
                elif need.get("value") is not None:
                    value = number(need["value"])
                    detail.update(state="above_sample" if value > max(values) else "within_sample", reason="sample_comparison", needed=str(value))
                else:
                    detail["reason"] = "inverse_search_range" if need.get("range") else "comparison_data_missing"
        except (KeyError, TypeError, ValueError):
            detail["reason"] = "comparison_data_invalid"
        axes[axis] = detail
    all_known = all(row["state"] != "unknown" for row in axes.values())
    above = any(row["state"] == "above_sample" for row in axes.values())
    if policy is None:
        state, reason = "unknown", "criteria_not_set"
    elif policy is False and above:
        state, reason = "unmet", "above_historical_sample"
    elif all_known:
        state, reason = "met", "high_premise_allowed" if above else "within_historical_sample"
    else:
        state, reason = "unknown", "comparison_data_missing"
    return {"state": state, "reason": reason, "configured": policy is not None, "allow": policy,
            "aboveSample": above, "axes": axes,
            "notice": "세 질문은 다른 가정을 과거 중간값으로 둔 별도 역산입니다. 동시에 실현될 조건의 예측이 아닙니다."}


def evaluate(snapshot: dict | None, criteria: dict | None, reviews=(), *, today: dt.date,
             support_status: str = "unknown", attempt: dict | None = None, input_error: str | None = None) -> dict:
    criteria = criteria or {}
    years = criteria.get("holdingYears")
    unknown = {"state": "unknown", "reason": "calculation_missing"}
    projection = None
    fatal, stale, missing = [], [], []
    if input_error:
        fatal.append(input_error)
    if snapshot is None:
        reason = (attempt or {}).get("reason") or {}
        code = reason.get("code") if isinstance(reason, dict) else str(reason)
        if code in UNSUPPORTED:
            fatal.append("unsupported_model")
        elif support_status == "supported":
            missing.append("snapshot_missing")
        else:
            fatal.append("support_not_checked")
        if code in {"price_stale", "stale_financials"}:
            stale.append(code)
    else:
        inputs, results = snapshot.get("inputs") or {}, snapshot.get("results") or {}
        if not known_spec(inputs):
            fatal.append("unknown_price_method")
        if (results.get("support") or {}).get("status") != "supported":
            fatal.append("unsupported_model")
        if not fatal:
            try:
                projection = project(snapshot, criteria or None, None, reviews, today=today)
                if projection.get("ageDays", 0) < 0:
                    fatal.append("snapshot_date_invalid")
                stale.extend(projection.get("notices", []))
                if projection.get("reviewNeeded"):
                    stale.append("snapshot_review_needed")
                rows = [r for r in results.get("scenarios", []) if r.get("label") == "base" and (years is None or r.get("horizon") == years)]
                if not rows or not any(r.get("status") == "available" for r in rows):
                    missing.append("base_scenario_missing")
                dcf = results.get("dcf") or {}
                intrinsic = next((row.get("perShare") for row in (dcf.get("result") or {}).get("scenarios", []) if row.get("name") == "기준"), None)
                if dcf.get("status") != "available" or dcf.get("marginOfSafetyJudgment") != "eligible" or intrinsic is None or number(intrinsic) <= 0:
                    missing.append("eligible_dcf_missing")
                for block in [*rows, results.get("base") or {}, dcf]:
                    reason = (block.get("reason") or {}).get("code")
                    subcode = (block.get("reason") or {}).get("subCode")
                    if reason in {"stale_financials", "price_stale"} or subcode == "stale_risk_free_observation":
                        stale.append(subcode or reason)
            except (KeyError, TypeError, ValueError, ArithmeticError):
                fatal.append("calculation_data_invalid")
    verdict = (projection or {}).get("verdict") or {}
    entries = {
        "requiredReturn": verdict.get("return", dict(unknown)),
        "minMarginOfSafety": verdict.get("marginOfSafety", dict(unknown)),
        "holdingYears": {"state": "met" if years in {5, 10} else "unknown", "reason": "period_configured" if years in {5, 10} else "criteria_not_set"},
        "allowAboveHistoricalRange": high_premise((snapshot or {}).get("results") or {}, (projection or {}).get("requirement") or {}, years, criteria.get("allowAboveHistoricalRange")),
    }
    for key in ("requiredReturn", "minMarginOfSafety"):
        if criteria.get(key) is None:
            entries[key] = {"state": "unknown", "reason": "criteria_not_set"}
    mandatory = {key: value for key, value in entries.items() if key != "allowAboveHistoricalRange" or criteria.get(key) is not None}
    unmet = [key for key, value in mandatory.items() if value["state"] == "unmet"]
    uncertain = [key for key, value in mandatory.items() if value["state"] == "unknown"]
    state = ("unknown" if fatal else "stale" if stale else "criteria_unmet" if unmet else
             "incomplete" if missing else "unknown" if uncertain else "ready_for_review")
    blockers = [*fatal, *stale, *missing, *[f"{key}_unmet" for key in unmet], *[f"{key}_unknown" for key in uncertain]]
    return {"state": state, "scope": "price_and_personal_criteria", "scopeCopy": SCOPE_COPY, "message": COPY[state],
            "snapshotId": (snapshot or {}).get("snapshotId"), "criteriaRevisionId": criteria.get("revisionId"),
            "criteria": entries, "blockingReasons": list(dict.fromkeys(blockers)), "warnings": [],
            "nextChecks": list(dict.fromkeys(blockers)), "projection": projection}
