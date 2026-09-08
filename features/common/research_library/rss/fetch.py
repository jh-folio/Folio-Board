"""HTTP fetch layer for Folio Board Evidence Intake collectors.

Network access is isolated here so the parser/article/policy layers stay
pure and testable. Retries use a short capped backoff and never bypass
paywalls — only public feed XML and public article HTML are fetched.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request


FEED_USER_AGENT = "Folio-OS-Evidence-Intake/1.0"
# Standard browser UA: several free outlets (MarketWatch, CNBC 등) return
# 403 to unknown tool UAs on public article pages. Paywalled content is still
# out of scope — paywall gates are detected downstream and never bypassed.
ARTICLE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ARTICLE_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ARTICLE_ACCEPT_LANGUAGE = "en-US,en;q=0.9,ko-KR;q=0.8,ko;q=0.7"
MAX_ARTICLE_BYTES = 1_500_000


def _backoff(attempt: int) -> None:
    time.sleep(min(2 ** attempt, 6))


def fetch_xml(url: str, timeout: int = 25, retries: int = 2) -> bytes:
    """Fetch raw feed bytes with a capped retry on transient errors."""
    request = urllib.request.Request(url, headers={"User-Agent": FEED_USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 or attempt >= retries:
                break
        except Exception as exc:  # noqa: BLE001 - network errors are broad
            last_error = exc
            if attempt >= retries:
                break
        _backoff(attempt)
    raise last_error if last_error else RuntimeError(f"fetch_xml failed: {url}")


def fetch_url_text(url: str, timeout: int = 20, retries: int = 2) -> str:
    """Fetch public article HTML as decoded text, honouring declared charset."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": ARTICLE_USER_AGENT,
            "Accept": ARTICLE_ACCEPT,
            "Accept-Language": ARTICLE_ACCEPT_LANGUAGE,
        },
    )
    last_error: Exception | None = None
    content_type = ""
    raw = b""
    for attempt in range(max(0, retries) + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read(MAX_ARTICLE_BYTES)
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 or attempt >= retries:
                raise
        except Exception as exc:  # noqa: BLE001 - network errors are broad
            last_error = exc
            if attempt >= retries:
                raise
        _backoff(attempt)
    else:
        raise last_error if last_error else RuntimeError(f"fetch_url_text failed: {url}")
    encoding = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    return raw.decode(encoding, errors="replace")
