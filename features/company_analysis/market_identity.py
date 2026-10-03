"""Official Korean listing identity shared by company-analysis price readers."""
from __future__ import annotations

import re
from pathlib import Path

from . import dart_client
from features.price_scenarios.prices import provider_symbol


def market_identity(company: dict, cache_dir: Path) -> dict:
    ticker = str(company.get("ticker") or "").strip().upper()
    if company.get("market") != "KR":
        return {"ok": bool(ticker), "providerSymbol": ticker}
    if not re.fullmatch(r"\d{6}", ticker):
        return {"ok": False, "reason": "invalid_korean_ticker"}
    corp_code = str(company.get("corpCode") or "").strip()
    if not corp_code:
        resolved = dart_client.resolve_dart_company(ticker, cache_dir)
        corp_code = str((resolved or {}).get("corpCode") or "")
    if not corp_code:
        return {"ok": False, "reason": "no_corp_code"}
    result = dart_client.fetch_company_profile(corp_code, cache_dir)
    if not result.get("ok"):
        return {"ok": False, "reason": result["reason"]}
    profile = result["profile"]
    if profile.get("stock_code") != ticker:
        return {"ok": False, "reason": "dart_listing_identity_mismatch"}
    try:
        symbol, source = provider_symbol(ticker, "KR", profile)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}
    return {"ok": True, "providerSymbol": symbol, "exchangeSource": source,
            "exchange": {"Y": "KOSPI", "K": "KOSDAQ"}[profile["corp_cls"]],
            "corpCode": corp_code, "profile": profile, "warning": result.get("warning") or ""}
