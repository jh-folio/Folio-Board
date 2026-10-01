"""Official listed-security identity; annual filing forms are not security types."""
from __future__ import annotations

import re
from bs4 import BeautifulSoup

from .decimal_ops import number

_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "ten": "10"}


def _kind(title):
    text = title.lower()
    if "preferred" in text or "preference" in text:
        return "non_common"
    if "depositary" in text or "depository" in text:
        return "ads"
    if re.search(r"\b(common|ordinary|capital)\s+(stock|shares?)\b", text):
        return "common_share"
    return "unknown"


def _ratio(text):
    matches = re.findall(r"(?:each\s+(?:representing|represents)|each\s+(?:ads|american\s+depositary\s+share)\s+(?:represents|representing))\s+([\d.]+|one|two|three|four|five|six|ten)\s+(?:(?:ordinary|common)\s+)?shares?", text.lower())
    try:
        values = {str(number(_WORDS.get(token, token))) for token in matches}
    except ValueError:
        return None
    return next(iter(values)) if len(values) == 1 and number(next(iter(values))) > 0 else None


def listed_security(markup: str, ticker: str, *, accession: str, provider_kind: str | None = None) -> dict:
    soup = BeautifulSoup(markup, "html.parser")
    for tag in list(soup.find_all(["script", "style", "ix:hidden", "ix:header"])):
        tag.decompose()
    fields = {}
    for tag in soup.find_all(lambda t: t.has_attr("name") and t.get("name", "").split(":")[-1] in {"TradingSymbol", "Security12bTitle"}):
        fields.setdefault(tag.get("contextref", ""), {})[tag["name"].split(":")[-1]] = " ".join(tag.get_text(" ", strip=True).split())
    selected = [f["Security12bTitle"] for f in fields.values() if f.get("TradingSymbol", "").upper() == ticker.upper() and "Security12bTitle" in f]
    equity = [title for title in selected if _kind(title) != "unknown"]
    kinds = {_kind(title) for title in equity}
    result = {"kind": "unknown", "source": "sec_cover" if selected else "unknown", "accession": accession}
    if len(kinds) == 1:
        result.update(kind=next(iter(kinds)), title=equity[0])
        # Some 20-F covers register the underlying shares *not for trading*;
        # the footnote explicitly identifies the listed ADS instead.
        cover = soup.get_text(" ", strip=True)[:20000]
        if result["kind"] == "common_share" and re.search(r"not for trading.{0,240}(?:American Depositary|ADS)", cover, re.I):
            result.update(kind="ads", source="sec_cover_footnote")
        if result["kind"] == "ads":
            ratio = _ratio(result["title"])
            if ratio:
                result["adsRatio"] = {"value": ratio, "source": "sec_cover", "accession": accession}
        return result
    if selected:
        return result  # Conflicting official equity titles do not yield to a provider.
    if provider_kind in {"common_share", "ads", "non_common"}:
        result.update(kind=provider_kind, source="provider")
    return result


def verify_ads_basis(history: dict, ratio: dict | None) -> bool:
    try:
        valid_ratio = bool(ratio and number(ratio.get("value", "0")) > 0)
    except ValueError:
        valid_ratio = False
    if not valid_ratio:
        return False
    years = {}
    for row in history.get("rows", []):
        years.setdefault(row["fiscalYear"], {})[row["metric"]] = row
    relevant = [metrics for metrics in years.values() if "EPS Diluted" in metrics]
    if not relevant:
        return False
    for metrics in relevant:
        if not all(name in metrics for name in ("Net Income", "Shares Diluted")):
            return False
        eps, profit, shares = (metrics[name] for name in ("EPS Diluted", "Net Income", "Shares Diluted"))
        if eps["period"] != profit["period"] or profit["period"] != shares["period"] or number(shares["value"]) <= 0:
            return False
        expected = number(profit["value"]) / number(shares["value"])
        actual = number(eps["value"])
        if expected == 0:
            if actual != 0:
                return False
        elif abs(actual - expected) / abs(expected) > number("0.01"):
            return False
    return True
