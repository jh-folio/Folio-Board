"""Bounded independent verification for briefing web candidates.

The model lookup is discovery only.  This module optionally fetches the
allow-listed public page and promotes a candidate only when the fetched public
article contains an exact quote plus bounded proofs for instrument, date,
metric, unit, and numeric value.  It never bypasses paywalls.
"""
from __future__ import annotations

import hashlib
import ipaddress
import math
import re
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

from features.common.research_library.rss.article import extract_article_text, normalize_text
from features.common.research_library.rss.policy import looks_paywalled
from features.common.web_search_scope import REJECTED, SourceScope, load_source_scope

MAX_FETCHES = 6
MAX_BYTES = 1_000_000
TIMEOUT_SECONDS = 2.0
_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
_DATE = re.compile(r"(?:19|20)\d{2}-\d{2}-\d{2}")

_INSTRUMENT_TERMS = {
    "SPY": ("spy",),
    "QQQ": ("qqq",),
    "N225": ("n225", "nikkei 225", "nikkei225"),
    "TOPIX": ("topix",),
    "KOSPI": ("kospi",),
    "KOSDAQ": ("kosdaq",),
    "USDKRW": ("usd/krw", "usdkrw", "dollar-won", "원/달러"),
}
_METRIC_TERMS = {
    "close": ("close", "closing", "종가", "마감"),
    "oneDayPct": ("one-day", "1-day", "daily change", "일간", "하루"),
    "weeklyPct": ("weekly", "week", "주간"),
    "changePct": ("change", "change percent", "등락률", "변동률"),
}
_UNIT_TERMS = {
    "points": ("point", "points", "pts", "지수"),
    "percent": ("%", "percent", "pct", "등락률", "변동률"),
    "USD": ("usd", "us dollar", "$"),
    "KRW": ("krw", "원", "won"),
    "quote": ("exchange rate", "환율", "quote"),
}


def _public_host(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not addresses:
        return False
    for row in addresses:
        try:
            address = ipaddress.ip_address(row[4][0])
        except (ValueError, IndexError):
            return False
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            return False
    return True


def _allowed_url(url: str, scope: SourceScope) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    tier, label = scope.classify(url)
    return tier != REJECTED and bool(label)


class _ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, scope: SourceScope):
        super().__init__()
        self.scope = scope

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        target = urljoin(req.full_url, newurl)
        if not _allowed_url(target, self.scope) or not _public_host(urlparse(target).hostname or ""):
            raise urllib.error.URLError("redirect_outside_allowlist")
        return super().redirect_request(req, fp, code, msg, headers, target)


def fetch_public_html(url: str, scope: SourceScope, *, fetcher: Callable | None = None) -> str:
    """Fetch bounded public HTML. ``fetcher`` exists solely for deterministic tests."""
    if not _allowed_url(url, scope):
        raise ValueError("source_not_allowed")
    host = urlparse(url).hostname or ""
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise ValueError("private_or_unresolved_host")
    except ValueError as exc:
        if str(exc) == "private_or_unresolved_host":
            raise
    if fetcher is not None:
        try:
            return str(fetcher(url, TIMEOUT_SECONDS, MAX_BYTES) or "")[:MAX_BYTES]
        except TypeError:
            return str(fetcher(url) or "")[:MAX_BYTES]
    if not _public_host(host):
        raise ValueError("private_or_unresolved_host")
    request = urllib.request.Request(url, headers={"User-Agent": "Folio-OS-Briefing-Evidence/1.0", "Accept": "text/html"})
    opener = urllib.request.build_opener(_ScopedRedirect(scope))
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        chunks: list[bytes] = []
        total = 0
        while total < MAX_BYTES and time.monotonic() < deadline:
            chunk = response.read(min(64 * 1024, MAX_BYTES - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")


def _numbers(text: str) -> list[float]:
    values = []
    for token in _NUMBER.findall(str(text or "")):
        try:
            value = float(token.replace(",", ""))
            if math.isfinite(value):
                values.append(value)
        except ValueError:
            continue
    return values


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    hay = normalize_text(text).lower()
    return any(re.search(r"(?<![\w])" + re.escape(term.lower()) + r"(?![\w])", hay) for term in terms)


def _proof(candidate: dict, gap: dict, body: str) -> bool:
    text = normalize_text(body)
    quote = normalize_text(candidate.get("quote") or "")
    if not quote or quote not in text:
        return False
    # The evidence is the *same short quote*, not unrelated tokens elsewhere
    # on a page (for example a Nasdaq headline plus a SPY number in a sidebar).
    text = quote
    if str(candidate.get("market") or "").lower() not in {"us", "kr", "jp", "europe"}:
        return False
    if not _contains_term(text, _INSTRUMENT_TERMS.get(str(candidate.get("instrument") or "").upper(), ())):
        return False
    if not _contains_term(text, _METRIC_TERMS.get(str(candidate.get("metric") or ""), ())):
        return False
    if not _contains_term(text, _UNIT_TERMS.get(str(candidate.get("unit") or ""), ())):
        return False
    if str(candidate.get("sessionDate") or "") not in _DATE.findall(text):
        return False
    values = _numbers(candidate.get("value"))
    numeric_text = _DATE.sub("", text)
    for term in _INSTRUMENT_TERMS.get(str(candidate.get("instrument") or "").upper(), ()):
        numeric_text = re.sub(re.escape(term), "", numeric_text, flags=re.I)
    body_values = _numbers(numeric_text)
    if len(values) != 1 or len(body_values) != 1 or abs(values[0] - body_values[0]) > 1e-9:
        return False
    if candidate.get("metric") == "weeklyPct":
        if not all(str(candidate.get(k) or "") and str(candidate[k]) in text for k in ("periodStart", "periodEnd")):
            return False
    return True


def public_evidence_resolver(*, scope: SourceScope | None = None, fetcher: Callable | None = None) -> Callable[[dict, dict], dict]:
    """Return a resolver with at most six independent bounded fetches."""
    source_scope = scope or load_source_scope(None)
    used: set[str] = set()

    def resolve(candidate: dict, gap: dict) -> dict:
        from features.common.quality_generation.call_budget import current_briefing_budget
        budget = current_briefing_budget()
        if budget:
            budget.check_active()
        url = str(candidate.get("url") or "")
        if len(used) >= MAX_FETCHES or url in used:
            return {"verified": False, "reason": "fetch_budget"}
        used.add(url)
        try:
            body = fetch_public_html(url, source_scope, fetcher=fetcher)
            if budget:
                budget.check_active()
            article = extract_article_text(body)
            if not article or looks_paywalled(article) or looks_paywalled(body):
                return {"verified": False, "reason": "public_body_unavailable"}
            if not _proof(candidate, gap, article):
                return {"verified": False, "reason": "proof_incomplete"}
            quote = normalize_text(candidate.get("quote") or "")
            source_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
            identity = "|".join(str(candidate.get(key) or "") for key in ("market", "instrument", "metric", "sessionDate", "unit"))
            source_id = "web_" + hashlib.sha256((url + "|" + identity).encode("utf-8")).hexdigest()[:16]
            return {
                "verified": True,
                "evidenceMethod": "public_quote_exact",
                "sourceId": source_id,
                "sourceEvidenceHash": source_hash,
            }
        except Exception:
            return {"verified": False, "reason": "evidence_fetch_failed"}

    return resolve


__all__ = ["MAX_BYTES", "MAX_FETCHES", "TIMEOUT_SECONDS", "fetch_public_html", "public_evidence_resolver"]
