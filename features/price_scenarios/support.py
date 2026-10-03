"""The frozen support boundary, including guards before legacy unit eligibility."""
from __future__ import annotations


def classify(identity: dict, classification: dict, *, reporting_currency: str, quote_currency: str,
             share_unit_status="unknown", ads_verified=False) -> dict:
    reasons, notices = [], []
    market = identity.get("market")
    if market not in {"US", "KR"}:
        return {"status": "unsupported", "reasons": [{"code": "market_not_supported"}], "notices": []}
    code = str(classification.get("code") or "")
    holding = code == ("6719" if market == "US" else "64992")
    if holding and classification.get("financialHolding"):
        reasons.append({"code": "financial_holding"})
    elif classification.get("quoteType") in {"ETF", "MUTUALFUND"}:
        reasons.append({"code": "fund_not_supported"})
    elif market == "US" and code.isdigit():
        sic = int(code)
        if (6000 <= sic <= 6411 or 6500 <= sic <= 6553 or sic in {6722, 6726, 6770, 6798}):
            reasons.append({"code": "industry_not_supported"})
    elif market == "KR" and any(code.startswith(prefix) for prefix in ("641", "642", "661", "65", "662", "68", "649")) and not holding:
        reasons.append({"code": "industry_not_supported"})
    if reasons:
        return {"status": "unsupported", "reasons": reasons, "notices": notices}
    if not code:
        industry = str(classification.get("industry") or "").lower()
        if any(term in industry for term in ("banks", "capital markets", "insurance", "real estate", "reit")):
            return {"status": "unsupported", "reasons": [{"code": "industry_not_supported"}], "notices": []}
        notices.append("classification_unknown")
    if holding:
        notices.append("holding_company_consolidated")
    security = classification.get("listedSecurity") or {}
    kind = security.get("kind", "unknown")
    if kind == "unknown":
        reasons.append({"code": "share_unit_unknown", "subCode": "listed_security_unknown"})
    elif kind == "non_common":
        reasons.append({"code": "non_common_listing"})
    elif kind == "ads" and not ads_verified:
        item = {"code": "adr_ratio_unverified"}
        if classification.get("adsRatio"):
            item["subCode"] = "per_share_basis_unconfirmed"
        reasons.append(item)
    if classification.get("classEpsDiffers"):
        reasons.append({"code": "class_eps_differs"})
    elif classification.get("shareClassesSameEps"):
        notices.append("share_classes_same_eps")
    if share_unit_status in {"unknown", "mismatch"}:
        reasons.append({"code": "share_unit_" + share_unit_status})
    if not reporting_currency or not quote_currency:
        reasons.append({"code": "currency_unknown"})
    elif reporting_currency != quote_currency:
        reasons.append({"code": "currency_mismatch"})
    return {"status": "limited" if reasons else "supported", "reasons": reasons, "notices": notices}


def dart_classification(metadata: dict, financial_rows: list[dict], *, ticker: str | None = None) -> dict:
    """Official KSIC and the financial-holding exception with account evidence."""
    statement = [row for row in financial_rows if row.get("sj_div") in {"IS", "CIS"}]
    revenue_accounts = [row for row in statement if row.get("account_id") in {"ifrs-full_Revenue", "ifrs_Revenue"}
                        or row.get("account_nm") in {"매출액", "매출"}]
    income_accounts = [row for row in statement if row.get("account_id") in {
        "ifrs-full_RevenueFromInterest", "ifrs_InterestRevenue", "dart_OperatingIncomeInsurance",
        "ifrs-full_InsuranceRevenue", "dart_InsuranceRevenueExpense"}]
    def order(row):
        value = str(row.get("ord") or "")
        return int(value) if value.isdigit() else 999999
    income_accounts.sort(key=order)
    code = str(metadata.get("induty_code") or "")
    return {"code": code, "source": "dart_company", "financialHolding": code == "64992" and not revenue_accounts and bool(income_accounts),
            "accountEvidence": {"revenueAccounts": [row["account_id"] for row in revenue_accounts],
                "firstFinancialIncome": income_accounts[0]["account_id"] if income_accounts else None},
            "ksicRevision": metadata.get("ksicRevision"), "listedSecurity": {
                "kind": "common_share" if ticker and ticker == metadata.get("stock_code") else "unknown",
                "source": "dart_company_stock_code"}}
