"""Capture and replay the full ten-year DCF inputs, without IO or user writes."""
from __future__ import annotations

from copy import deepcopy
import datetime as dt
from decimal import ROUND_HALF_EVEN, localcontext
import math

from features.company_analysis import dcf
from .dcf_history import dcf_summary
from .decimal_ops import number
from .history import _shift_months


def _strings(value):
    """Persist established float DCF outputs explicitly as decimal strings."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite_dcf_input")
        return str(value)
    if isinstance(value, dict):
        return {key: _strings(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_strings(child) for child in value]
    return deepcopy(value)


def unavailable(code, subcode=None):
    return {"status": "unavailable", "reason": {"code": code, **({"subCode": subcode} if subcode else {})}}


def capture_dcf_inputs(history: dict, price: dict, *, support: dict, share_event_state: str,
                       debt_inputs: dict, beta: dict, risk_free: dict) -> dict:
    """The caller supplies already-adjusted history and resolved support.

    Raw debt observations are kept in the capture. No missing debt is converted
    to zero; incomplete but known positions remain labelled incomplete.
    """
    if support.get("status") != "supported":
        reasons = support.get("reasons") or [{"code": "support_unconfirmed"}]
        return unavailable(reasons[0]["code"], reasons[0].get("subCode"))
    if share_event_state not in {"present", "none_confirmed"}:
        return unavailable("share_event_unknown")
    if history.get("currency") != price.get("currency") or price.get("currency") not in {"USD", "KRW"}:
        return unavailable("currency_mismatch")
    session = dt.date.fromisoformat(price["sessionDate"])
    if number(price["value"]) <= 0:
        return unavailable("dcf_not_computable", "invalid_price")
    financial = [row for row in history["rows"] if row["metric"] in {"Revenue", "Net Income", "Operating Cash Flow"}]
    if not financial:
        return unavailable("dcf_not_computable", "financial_history_missing")
    end = max(row["period"]["end"] for row in financial)
    if dt.date.fromisoformat(end) < _shift_months(session, -15):
        return unavailable("stale_financials")
    if any(row["filed"] > price["sessionDate"] or row["period"]["end"] > price["sessionDate"] for row in history["rows"]):
        return unavailable("dcf_not_computable", "future_financial_input")
    position = debt_inputs.get("position")
    if not debt_inputs.get("ok") or not position or not position.get("ok"):
        return unavailable("dcf_not_computable", debt_inputs.get("reason") or "same_period_debt_unavailable")
    if position["asOf"] > price["sessionDate"]:
        return unavailable("dcf_not_computable", "future_debt_position")
    summary = dcf_summary(history)
    base = dcf.normalized_base_fcf(summary)
    if not base or number(base.get("value", "0")) <= 0:
        return unavailable("dcf_not_computable", "insufficient_fcf")
    shares = [row for row in history["rows"] if row["metric"] == "Shares Diluted" and row["period"]["end"] == end]
    if len(shares) != 1 or number(shares[0]["value"]) <= 0:
        return unavailable("dcf_not_computable", "shares_unavailable_at_financial_end")
    latest = {row["metric"]: row for row in history["rows"] if row["period"]["end"] == end}
    def same_period_ratio(numerator, denominator, *, positive_denominator=True):
        first, second = latest.get(numerator), latest.get(denominator)
        if not first or not second or first["period"] != second["period"]:
            return None
        divisor = number(second["value"])
        if divisor == 0 or (positive_denominator and divisor < 0):
            return None
        return str(number(first["value"]) / divisor)
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        tax_rate = same_period_ratio("Income Tax", "Pretax Income")
        interest, long_debt = latest.get("Interest Expense"), latest.get("Long-Term Debt")
        debt_cost = (str(number(interest["value"]) / number(long_debt["value"]))
                     if interest and long_debt and number(long_debt["value"]) > 0 else None)
        market_cap = str(number(price["value"]) * number(shares[0]["value"]))
    rf = deepcopy(risk_free)
    rf.pop("fetchedAt", None)
    rf.pop("asOf", None)
    try:
        rf_rate = number(rf.get("rate"))
    except (ValueError, TypeError):
        return unavailable("dcf_not_computable", "risk_free_value_unconfirmed")
    if rf.get("source") not in {"fred_dgs10", "yfinance_tnx", "constant"}:
        return unavailable("dcf_not_computable", "risk_free_source_unconfirmed")
    if rf.get("source") != "constant":
        if not rf.get("observedAt") or rf["observedAt"] > price["sessionDate"]:
            return unavailable("dcf_not_computable", "future_risk_free_observation")
        try:
            observed = dt.date.fromisoformat(rf["observedAt"])
        except (ValueError, TypeError):
            return unavailable("dcf_not_computable", "risk_free_date_unconfirmed")
        weekdays = sum((observed + dt.timedelta(days=i)).weekday() < 5 for i in range(1, (session-observed).days+1))
        if weekdays > 10:
            return unavailable("dcf_not_computable", "stale_risk_free_observation")
        raw = rf.get("rawObservation") or {}
        try:
            raw_rate = number(raw.get("value")) / 100
        except (ValueError, TypeError):
            return unavailable("dcf_not_computable", "risk_free_value_unconfirmed")
        if raw.get("unit") != "percent" or raw_rate != rf_rate:
            return unavailable("dcf_not_computable", "risk_free_unit_mismatch")
    beta_value = number(beta["value"]) if beta.get("value") is not None else None
    if beta_value is not None and not beta.get("source"):
        return unavailable("dcf_not_computable", "beta_source_unconfirmed")
    if beta.get("observedAt") and beta["observedAt"] > price["sessionDate"]:
        return unavailable("dcf_not_computable", "future_beta_observation")
    discount = dcf.estimate_discount_rate(beta=float(beta_value) if beta_value is not None else None,
        tax_rate=float(tax_rate) if tax_rate is not None else None, debt_cost=float(debt_cost) if debt_cost is not None else None,
        market_cap=float(market_cap), debt=float(position["totalDebt"]), currency=history["currency"],
        risk_free=float(rf_rate), equity_risk_premium=dcf.EQUITY_RISK_PREMIUM)
    growth = dcf.growth_driver(summary)
    sources = {metric: deepcopy(latest.get(metric)) for metric in ("Income Tax", "Pretax Income", "Interest Expense", "Long-Term Debt")}
    inputs = {"summary": summary, "currency": history["currency"], "sessionDate": price["sessionDate"],
              "price": price["value"], "shares": shares[0]["value"], "shareSource": deepcopy(shares[0]),
              "marketCap": market_cap, "marketCapFormula": "reference_price*adjusted_diluted_shares",
              "baseFcf": _strings(base), "growth": _strings(growth), "growthWindow": _strings(growth["growthWindow"]),
              "financialRates": {"taxRate": tax_rate, "debtCost": debt_cost}, "rateSources": sources,
              "debtPosition": deepcopy(position), "debtObservations": deepcopy(debt_inputs.get("observations", [])),
              "beta": deepcopy(beta), "riskFree": rf, "equityRiskPremium": str(dcf.EQUITY_RISK_PREMIUM),
              "discount": _strings(discount), "terminalGrowth": str(dcf.terminal_growth_for(history["currency"], discount["rate"])),
              "projectionYears": dcf.PROJECTION_YEARS}
    return {"status": "available", "inputs": inputs}


def replay_dcf(inputs: dict) -> dict:
    """One established float DCF path consuming the captured values verbatim."""
    if inputs.get("projectionYears") != dcf.PROJECTION_YEARS:
        return unavailable("dcf_not_computable", "projection_years_mismatch")
    model = dcf.build_dcf(inputs["summary"], captured_inputs=inputs)
    if not model.get("ok"):
        return unavailable("dcf_not_computable", model.get("reason") or "invalid_dcf")
    assumptions = {"nearGrowth": model["growth"]["rate"], "growthBasis": model["growth"]["basis"],
                   "periodYears": model["growth"]["growthWindow"]["periodYears"],
                   "discountRate": model["discountRate"]["rate"], "discountMethod": model["discountRate"]["method"],
                   "clamped": model["discountRate"].get("clamped", False), "marketCap": inputs["marketCap"],
                   "shares": inputs["shares"]}
    fallback = model["growth"]["basis"] == "fallback" or model["discountRate"]["method"] == "fallback_fixed"
    return {"status": "available", "derivedAssumptions": _strings(assumptions), "result": _strings(model),
            "marginOfSafetyJudgment": "unknown" if fallback else "eligible",
            "notices": ["dcf_fallback"] if fallback else []}
