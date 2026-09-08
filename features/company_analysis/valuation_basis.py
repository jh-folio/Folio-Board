"""Deterministic unit/currency eligibility for company-analysis valuation.

The company-analysis input has two independently sourced unit systems:

* SEC/DART financial facts use the filer's reporting currency and share units.
* Market data has a quote currency, and (when the provider supplies it) a
  separate financial/market-value currency.

This module is deliberately a small, feature-owned policy boundary.  It does
not convert currencies, infer ADR ratios, or reject a report.  Callers use the
same result to decide which derived values may be calculated and which fixed
reason should be shown to a reader or sent to a model.
"""
from __future__ import annotations

import math
from typing import Mapping


_UNKNOWN_MARKERS = {"", "-", "N/A", "NA", "NONE", "NULL", "UNKNOWN", "UNAVAILABLE"}

_REASON_TEXT = {
    "reporting_currency_unknown": "신고 통화를 확인하지 못해 통화가 필요한 가치평가를 산출하지 않았습니다.",
    "quote_currency_unknown": "주가 통화를 확인하지 못해 주가와 주당 재무 수치를 비교하는 가치평가를 산출하지 않았습니다.",
    "price_currency_mismatch": "주가 통화와 신고 통화가 달라 환산 근거 없이 주가를 재무 수치와 비교하는 가치평가를 산출하지 않았습니다.",
    "market_value_currency_unknown": "시가총액·기업가치의 통화를 확인하지 못해 해당 시장가치 배수를 산출하지 않았습니다.",
    "market_value_currency_mismatch": "시가총액·기업가치 통화와 신고 통화가 달라 환산 근거 없이 해당 시장가치 배수를 산출하지 않았습니다.",
    "share_unit_unknown": "주식수 단위를 확인하지 못해 주당 가치 산출을 보류했습니다.",
    "share_unit_mismatch": "주식수 단위 또는 주식종류가 맞지 않아 주당 가치 산출을 보류했습니다.",
    "price_unavailable": "현재 주가를 확인하지 못해 주가와 비교하는 가치평가를 산출하지 않았습니다.",
    "market_value_unavailable": "시가총액·기업가치를 확인하지 못해 해당 시장가치 배수를 산출하지 않았습니다.",
}


def normalize_currency(value) -> str | None:
    """Return a comparable currency/unit code, or ``None`` when unknown.

    ``GBp``/``GBX`` are pence quote units, not pounds.  They remain distinct
    from ``GBP`` because this policy never performs a 100x value conversion.
    This function intentionally does not turn an absent value into USD.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in _UNKNOWN_MARKERS:
        return None
    if text == "GBp" or text.upper() == "GBX":
        return "GBp" if text == "GBp" else "GBX"
    if text.upper() in {"GBPENCE", "GBPENNY", "PENCE"}:
        return "GBp"
    return text.upper()


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _known_field_currency(data: Mapping, names: tuple[str, ...], *, known_flag: str | None = None) -> str | None:
    """Read an explicitly supplied currency without treating a fallback as known."""
    if known_flag and data.get(known_flag) is False:
        return None
    for name in names:
        if name not in data:
            continue
        value = normalize_currency(data.get(name))
        if value:
            return value
    return None


def _status(left: str | None, right: str | None) -> str:
    if not left or not right:
        return "unknown"
    return "same" if left == right else "mismatch"


def _normalized_unit(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "")
    if text in {"share", "shares", "commonstock", "ordinaryshares"}:
        return "shares"
    return text or None


def _explicit_share_ratio(market: Mapping) -> float | None:
    """Return a provider-supplied ratio only when a known key carries one.

    yfinance does not normally expose an ADR ratio in this path.  Keeping the
    detection generic lets deterministic fixtures (or a future provider
    envelope) express an explicit mismatch without inventing one from ticker
    shape, exchange, or company nationality.
    """
    for key in (
        "shareRatio",
        "adrRatio",
        "sharesPerAdr",
        "adrShares",
        "listingShareRatio",
    ):
        if key not in market:
            continue
        try:
            ratio = float(market.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(ratio) and ratio > 0:
            return ratio
    return None


def _share_status(sec_summary: Mapping, market: Mapping, share_count) -> tuple[str, str]:
    """Assess share-unit compatibility without guessing share-class ratios."""
    explicit_status = str(
        market.get("shareUnitStatus") or market.get("shareCountStatus") or ""
    ).strip().lower()
    if explicit_status in {"mismatch", "incompatible"}:
        return "mismatch", "explicit_share_metadata"

    ratio = _explicit_share_ratio(market)
    if ratio is not None and abs(ratio - 1.0) > 1e-9:
        return "mismatch", "explicit_share_ratio"

    sec_unit = _normalized_unit(sec_summary.get("shareUnit") or sec_summary.get("sharesUnit"))
    market_unit = _normalized_unit(
        market.get("shareUnit") or market.get("sharesUnit") or market.get("shareCountUnit")
    )
    if sec_unit and market_unit and sec_unit != market_unit:
        return "mismatch", "explicit_share_unit"

    explicit_class_mismatch = market.get("shareClassMismatch")
    if explicit_class_mismatch is True:
        return "mismatch", "explicit_share_class"
    sec_class = str(sec_summary.get("shareClass") or "").strip().lower()
    market_class = str(market.get("shareClass") or "").strip().lower()
    if sec_class and market_class and sec_class != market_class:
        return "mismatch", "explicit_share_class"

    if _positive(share_count) is None:
        return "unknown", "share_count_missing"

    # Both SEC/DART share counts and yfinance's sharesOutstanding are counts of
    # shares.  The path has no verified ADR/share-class ratio, so absence of
    # that optional metadata is not promoted to a mismatch.
    return "compatible", "share_count_in_shares"


def fixed_reason(code: str, basis: Mapping | None = None) -> str:
    """Return the stable, reader-safe reason text for a policy code."""
    return _REASON_TEXT.get(str(code), "필요한 단위 정보를 확인하지 못해 해당 가치평가를 산출하지 않았습니다.")


def _eligibility(
    basis: Mapping,
    *,
    needs_price: bool = False,
    needs_market_value: bool = False,
    needs_share: bool = False,
    reject_share_mismatch: bool = False,
) -> dict:
    codes: list[str] = []

    if not basis.get("reportingCurrencyKnown"):
        codes.append("reporting_currency_unknown")

    if needs_price:
        if not basis.get("priceAvailable"):
            codes.append("price_unavailable")
        elif basis.get("priceCurrencyStatus") == "unknown":
            codes.append("quote_currency_unknown")
        elif basis.get("priceCurrencyStatus") == "mismatch":
            codes.append("price_currency_mismatch")

    if needs_market_value:
        if not basis.get("marketValueAvailable"):
            codes.append("market_value_unavailable")
        elif basis.get("marketValueUsable"):
            # A market value derived from a verified same-currency quote and
            # share count is safe even when the provider omitted a dedicated
            # financial-currency field.  This does not relabel the provider's
            # raw market value; callers must use the derived value explicitly.
            pass
        elif basis.get("marketValueCurrencyStatus") == "unknown":
            codes.append("market_value_currency_unknown")
        elif basis.get("marketValueCurrencyStatus") == "mismatch":
            codes.append("market_value_currency_mismatch")

    if needs_share:
        share_status = basis.get("shareUnitStatus")
        if share_status == "unknown":
            codes.append("share_unit_unknown")
        elif share_status == "mismatch":
            codes.append("share_unit_mismatch")
    elif reject_share_mismatch and basis.get("shareUnitStatus") == "mismatch":
        # PER itself does not need a share count, so a missing count must not
        # block a valid price/EPS ratio.  An explicit ADR/share-class/unit
        # mismatch, however, makes downstream per-share comparisons unsafe.
        codes.append("share_unit_mismatch")

    # Preserve first occurrence order for deterministic serialized/context
    # output.  A code's text is fixed and contains no provider error details.
    codes = list(dict.fromkeys(codes))
    return {
        "eligible": not codes,
        "reasonCodes": codes,
        "reason": " ".join(fixed_reason(code, basis) for code in codes),
    }


def build_valuation_basis(
    sec_summary: Mapping | None,
    market_data: Mapping | None,
    *,
    share_count=None,
) -> dict:
    """Build the shared valuation unit contract.

    ``currency`` on old market payloads is a display/quote field.  It is read
    as a quote currency only when it was not explicitly marked as a provider
    fallback.  Market-cap/EV/cash-flow currency comes from the provider's
    separate ``financialCurrency``/explicit value-currency fields; it is never
    inferred from quote currency.
    """
    sec = sec_summary if isinstance(sec_summary, Mapping) else {}
    market = market_data if isinstance(market_data, Mapping) else {}

    reporting = _known_field_currency(
        sec,
        ("reportingCurrency", "currency"),
        known_flag="reportingCurrencyKnown",
    )
    quote = _known_field_currency(
        market,
        ("quoteCurrency", "currency"),
        known_flag="currencyKnown",
    )
    # These are intentionally two independent fields.  A provider's
    # `financialCurrency` describes financial statements/cash flows; it is not
    # a substitute for the currency in which marketCap/enterpriseValue is
    # quoted, and vice versa.
    financial = _known_field_currency(
        market,
        ("financialCurrency", "financialStatementCurrency"),
        known_flag="financialCurrencyKnown",
    )
    market_value_currency = _known_field_currency(
        market,
        ("marketValueCurrency", "marketCapCurrency", "enterpriseValueCurrency"),
        known_flag="marketValueCurrencyKnown",
    )

    price_available = _positive(market.get("price")) is not None
    market_value_available = any(
        _positive(market.get(key)) is not None
        for key in ("marketCap", "enterpriseValue")
    )
    effective_shares = share_count
    if effective_shares is None:
        effective_shares = market.get("sharesOutstanding")
    if effective_shares is None:
        effective_shares = market.get("shares")
    share_status, share_basis = _share_status(sec, market, effective_shares)

    # `price * shares` establishes a market-cap unit only when both inputs are
    # known to be compatible.  It must not be used to infer the provider's
    # financial-statement/cash-flow currency.
    derived_market_value_safe = bool(
        price_available
        and _status(quote, reporting) == "same"
        and share_status in {"compatible", "same"}
        and _positive(effective_shares) is not None
    )

    basis = {
        "reportingCurrency": reporting,
        "reportingCurrencyKnown": bool(reporting),
        "quoteCurrency": quote,
        "quoteCurrencyKnown": bool(quote),
        "financialCurrency": financial,
        "financialCurrencyKnown": bool(financial),
        "marketValueCurrency": market_value_currency,
        "marketValueCurrencyKnown": bool(market_value_currency),
        "priceCurrencyStatus": _status(quote, reporting),
        "marketValueCurrencyStatus": _status(market_value_currency, reporting),
        "cashflowCurrencyStatus": _status(
            _known_field_currency(market, ("cashflowCurrency",), known_flag="cashflowCurrencyKnown")
            or financial,
            reporting,
        ),
        "priceAvailable": price_available,
        "marketValueAvailable": bool(market_value_available or derived_market_value_safe),
        "marketValueUsable": bool(
            _status(market_value_currency, reporting) == "same" or derived_market_value_safe
        ),
        "marketValueDerivedSafe": derived_market_value_safe,
        "shareUnitStatus": share_status,
        "shareUnitBasis": share_basis,
        "shareCountAvailable": _positive(effective_shares) is not None,
    }

    # PER compares quote-currency price with reporting-currency EPS.  DCF also
    # needs a share count; it may omit market cap and use the documented fixed
    # discount fallback when market-value currency is unavailable.  Market
    # multiples separately require a known market-value currency.
    basis["eligibility"] = {
        "per": _eligibility(basis, needs_price=True, reject_share_mismatch=True),
        "marketMultiples": _eligibility(basis, needs_market_value=True),
        "fcfYield": _eligibility(basis, needs_market_value=True),
        "dcf": _eligibility(basis, needs_price=price_available, needs_share=True),
        "buybackYield": _eligibility(basis, needs_price=True, needs_share=True),
    }
    all_codes: list[str] = []
    for item in basis["eligibility"].values():
        for code in item.get("reasonCodes", []):
            if code not in all_codes:
                all_codes.append(code)
    basis["unavailableReasonCodes"] = all_codes
    basis["unavailableReasons"] = [fixed_reason(code, basis) for code in all_codes]
    return basis


def market_cashflow_is_compatible(basis: Mapping | None) -> bool:
    return bool(basis and basis.get("cashflowCurrencyStatus") == "same")


def market_value_is_compatible(basis: Mapping | None) -> bool:
    return bool(basis and basis.get("marketValueCurrencyStatus") == "same")


def render_valuation_basis_context(basis: Mapping | None) -> str:
    """Render only safe unit status/reasons for the shared LLM context."""
    if not basis:
        return ""
    def shown(value) -> str:
        return str(value) if value else "확인 필요"

    lines = [
        "## 밸류에이션 단위 점검",
        "",
        f"- 신고 통화: {shown(basis.get('reportingCurrency'))}",
        f"- 주가 통화: {shown(basis.get('quoteCurrency'))}",
        f"- 시가총액·기업가치 통화: {shown(basis.get('marketValueCurrency'))}",
        f"- 공급자 재무·현금흐름 통화: {shown(basis.get('financialCurrency'))}",
        f"- 주식수 단위 상태: {basis.get('shareUnitStatus') or 'unknown'}",
    ]
    labels = {
        "per": "PER",
        "marketMultiples": "PSR·EV/EBITDA",
        "fcfYield": "FCF Yield",
        "dcf": "DCF",
        "buybackYield": "매입 수익률",
    }
    for key, label in labels.items():
        item = (basis.get("eligibility") or {}).get(key) or {}
        if not item.get("eligible"):
            lines.append(f"- {label}: 계산하지 않음 — {item.get('reason') or '필요한 단위 정보를 확인하지 못했습니다.'}")
    if basis.get("cashflowCurrencyStatus") != "same":
        lines.append("- 공급자 재무·현금흐름 통화가 신고 통화와 확인되지 않아 해당 값을 SEC/DART와 합치지 않았습니다.")
    if basis.get("marketValueCurrencyStatus") != "same" and basis.get("marketValueDerivedSafe"):
        lines.append("- 공급자 시가총액 통화가 확인되지 않아 주가×주식수로 유도한 시장가치만 사용했습니다.")
    if basis.get("unavailableReasonCodes"):
        lines.append("- 통화 환산이나 ADR/주식 변환을 하지 않았습니다. 위에서 계산하지 않은 값은 숫자를 추정하지 마세요.")
    else:
        lines.append("- 위 단위가 확인된 값만 앱 계산 결과로 사용하세요. 숫자를 다시 계산하지 마세요.")
    return "\n".join(lines)


__all__ = [
    "build_valuation_basis",
    "fixed_reason",
    "market_cashflow_is_compatible",
    "market_value_is_compatible",
    "normalize_currency",
    "render_valuation_basis_context",
]
