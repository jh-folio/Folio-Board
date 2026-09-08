"""Conditional-GET RSS/Atom adapter shared by approved providers."""
from __future__ import annotations

import datetime as dt
import urllib.error
import urllib.request
from typing import Callable

from features.common.research_library.rss.parser import parse_feed
from features.common.research_library.rss.policy import normalize_url
from features.common.research_library.signals.schema import FastOriginSignal, normalize_signal

USER_AGENT = "FolioBoard/0.4 (+local research RSS reader)"


class SignalFeedThrottled(RuntimeError):
    """Provider asked us to slow down (HTTP 429). Not a provider failure."""

    def __init__(self, retry_after_seconds: int = 0):
        super().__init__("signal_feed_throttled")
        self.retry_after_seconds = int(retry_after_seconds or 0)


def validate_feed_url(url: str, *, allowed_hosts: tuple[str, ...] = ()) -> str:
    from urllib.parse import urlparse

    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("signal_feed_url_invalid")
    host = parsed.hostname.lower()
    if allowed_hosts and not any(host == suffix or host.endswith("." + suffix) for suffix in allowed_hosts):
        raise ValueError("signal_feed_host_not_allowed")
    if parsed.username or parsed.password or parsed.query.lower().find("token=") >= 0 or parsed.query.lower().find("apikey=") >= 0:
        raise ValueError("signal_feed_url_contains_secret")
    return value


def normalize_feed_items(
    xml_bytes: bytes,
    *,
    provider: str,
    source_status: str = "active",
    reliability_tier: int = 3,
    markets: list[str] | None = None,
    received_at: dt.datetime | None = None,
    ticker_resolver: Callable[[dict], list[str]] | None = None,
) -> list[FastOriginSignal]:
    observed = received_at or dt.datetime.now(dt.timezone.utc)
    rows: list[FastOriginSignal] = []
    for item in parse_feed(xml_bytes):
        published = item.get("published_at_utc")
        if not published or published > observed + dt.timedelta(minutes=5):
            continue
        url = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        rows.append(normalize_signal({
            "provider": provider,
            "collector": "rss",
            "title": title,
            "url": url,
            "normalized_url": normalize_url(url),
            "provider_published_at": published,
            "received_at": observed,
            "markets": markets or ["GLOBAL"],
            "related_tickers": ticker_resolver(item) if ticker_resolver else [],
            "source_status": source_status,
            "signal_status": "unconfirmed",
            "reliability_tier": reliability_tier,
        }))
    return rows


def fetch_feed(
    url: str,
    *,
    provider: str,
    previous: dict | None = None,
    timeout: int = 12,
    allowed_hosts: tuple[str, ...] = (),
    source_status: str = "active",
    reliability_tier: int = 3,
    markets: list[str] | None = None,
) -> tuple[list[FastOriginSignal], dict]:
    feed_url = validate_feed_url(url, allowed_hosts=allowed_hosts)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}
    previous = previous or {}
    if previous.get("etag"):
        headers["If-None-Match"] = str(previous["etag"])
    if previous.get("lastModified"):
        headers["If-Modified-Since"] = str(previous["lastModified"])
    request = urllib.request.Request(feed_url, headers=headers)
    observed = dt.datetime.now(dt.timezone.utc)
    try:
        with urllib.request.urlopen(request, timeout=max(3, min(int(timeout), 30))) as response:
            content_type = str(response.headers.get("Content-Type") or "").lower()
            body = response.read(2_000_000)
            if not any(marker in content_type for marker in ("xml", "rss", "atom")) and not body.lstrip().startswith(b"<"):
                raise ValueError("signal_feed_content_type_invalid")
            rows = normalize_feed_items(
                body,
                provider=provider,
                source_status=source_status,
                reliability_tier=reliability_tier,
                markets=markets,
                received_at=observed,
            )
            state = {
                "etag": str(response.headers.get("ETag") or "")[:300],
                "lastModified": str(response.headers.get("Last-Modified") or "")[:300],
                "checkedAt": observed.isoformat(),
                "httpStatus": int(getattr(response, "status", 200)),
                "itemCount": len(rows),
            }
            return rows, state
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return [], {**previous, "checkedAt": observed.isoformat(), "httpStatus": 304, "itemCount": 0}
        if exc.code in {401, 403}:
            raise PermissionError("signal_feed_unauthorized") from exc
        if exc.code == 429:
            # 공개 피드는 짧은 창의 rate limit을 둘 수 있다. 장애가 아니라 대기 상태로 다룬다.
            retry_after = 0
            try:
                retry_after = max(0, int(str(exc.headers.get("Retry-After") or "").strip() or 0))
            except (AttributeError, ValueError):
                retry_after = 0
            raise SignalFeedThrottled(retry_after) from exc
        raise RuntimeError(f"signal_feed_http_{exc.code}") from exc

