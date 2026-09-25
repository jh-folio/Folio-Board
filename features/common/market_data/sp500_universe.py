"""Embedded S&P 500 universe with GICS sector / sub-industry classification.

The US briefing heatmap is built from this committed snapshot rather than a
live "top market caps" screener so that:

* membership matches the actual S&P 500 index, and
* sector / sub-industry labels use the familiar GICS taxonomy (the same
  grouping finviz-style maps use) instead of the Nasdaq screener's own buckets.

The historical file is refreshed periodically with
``build_sp500_constituents_file`` which joins the Wikipedia constituents table
(ticker + GICS) with a market-cap source for box sizing.  A separate,
date-versioned changeset supplies verified current membership and ticker
changes without rewriting that historical file.  At runtime only daily prices
are fetched, so the heatmap no longer depends on a live screener call.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any, Callable
import urllib.request

from features.common.config_bootstrap import resolve_config

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CURRENT_SP500_SNAPSHOT_AS_OF = dt.date(2026, 9, 8)
SP500_CHANGESET_FILENAME = "sp500_constituent_changes_2026.json"


def provider_symbol(ticker: Any) -> str:
    """Return the yfinance-style symbol (``BRK.B`` / ``BF/B`` -> ``BRK-B``)."""
    return re.sub(r"[./]", "-", str(ticker or "").strip().upper())


def _join_key(symbol: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())


def _number(value: Any) -> float:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _strip_tags(cell: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell))).strip()


def parse_wikipedia_constituents(html_text: str) -> list[dict]:
    """Parse the ``#constituents`` table into ticker/label/sector/industry rows."""
    table = re.search(r'<table[^>]*id="constituents".*?</table>', html_text or "", re.S)
    if not table:
        return []
    rows: list[dict] = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)
        if len(cells) < 4:
            continue
        ticker = _strip_tags(cells[0])
        if not ticker or ticker.lower() == "symbol":
            continue
        rows.append({
            "ticker": ticker,
            "providerSymbol": provider_symbol(ticker),
            "label": _strip_tags(cells[1]) or ticker,
            "sector": _strip_tags(cells[2]) or "Other",
            "industry": _strip_tags(cells[3]) or "Other",
        })
    return rows


def join_market_caps(constituents: list[dict], caps: dict) -> tuple[list[dict], list[str]]:
    """Attach market caps (keyed by a separator-insensitive symbol) to rows.

    Returns the rows that found a positive cap plus the tickers that did not.
    """
    cap_by_key = {_join_key(symbol): _number(value) for symbol, value in (caps or {}).items()}
    joined, missing = [], []
    for row in constituents:
        cap = cap_by_key.get(_join_key(row.get("ticker")))
        if not cap or cap <= 0:
            missing.append(str(row.get("ticker") or ""))
            continue
        joined.append({**row, "marketCap": cap})
    return joined, missing


def fetch_wikipedia_html(url: str = WIKIPEDIA_URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Folio-Board/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def build_sp500_constituents_file(
    path: Path | str | None = None,
    *,
    html_fetcher: Callable[[], str] | None = None,
    cap_fetcher: Callable[[], dict] | None = None,
) -> dict:
    """Refresh the embedded S&P 500 universe file (membership + GICS + caps)."""
    from features.common.market_data.market_universe import fetch_nasdaq_screener

    html_text = (html_fetcher or fetch_wikipedia_html)()
    constituents = parse_wikipedia_constituents(html_text)
    if not constituents:
        raise ValueError("Wikipedia constituents table returned no rows")

    def _default_caps() -> dict:
        return {
            str(row.get("symbol") or "").upper(): row.get("marketCap")
            for row in fetch_nasdaq_screener()
        }

    caps = (cap_fetcher or _default_caps)()
    companies, missing = join_market_caps(constituents, caps)
    payload = {
        "asOf": dt.date.today().isoformat(),
        "source": "wikipedia:List_of_S&P_500_companies + nasdaq screener caps",
        "count": len(companies),
        "missingCap": missing,
        "companies": sorted(companies, key=lambda row: row.get("marketCap") or 0, reverse=True),
    }
    target = Path(path) if path is not None else resolve_config("sp500_constituents.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _coerce_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _ticker_fingerprint(companies: list[dict]) -> str:
    """Fingerprint membership, not mutable labels or market-cap observations."""
    tickers = sorted(
        str(row.get("ticker") or "").strip().upper()
        for row in companies
        if isinstance(row, dict) and str(row.get("ticker") or "").strip()
    )
    return hashlib.sha256("\n".join(tickers).encode("utf-8")).hexdigest()


def _changeset_matches_baseline(payload: dict, changeset: dict) -> bool:
    """Only apply our delta to the exact committed baseline lineage."""
    companies = payload.get("companies")
    return bool(
        isinstance(companies, list)
        and str(payload.get("asOf") or "")[:10] == str(changeset.get("baselineAsOf") or "")[:10]
        and _ticker_fingerprint(companies) == changeset.get("baselineTickerFingerprint")
    )


def _changeset_path(snapshot_path: Path, *, allow_repository_fallback: bool = False) -> Path:
    """Resolve the adjacent, date-versioned membership changeset.

    A caller-provided snapshot remains self-contained for tests and historical
    imports.  The production snapshot gets its changes from the committed
    changeset next to the baseline config, rather than mutating that baseline.
    """
    snapshot_path = snapshot_path.resolve()
    adjacent = snapshot_path.with_name(SP500_CHANGESET_FILENAME)
    if adjacent.exists():
        return adjacent
    if snapshot_path.name != "sp500_constituents.json":
        return adjacent
    repo_root = Path(__file__).resolve().parents[3]
    repository_dirs = (repo_root / "config", repo_root / "defaults" / "config")
    if not allow_repository_fallback and snapshot_path.parent not in repository_dirs:
        return adjacent
    # ``resolve_config`` may point at the user's existing Documents workspace,
    # where only the baseline config is seeded.  Keep the immutable changeset in
    # the application checkout instead of copying it into user data.
    for directory in repository_dirs:
        candidate = directory / SP500_CHANGESET_FILENAME
        if candidate.exists():
            return candidate
    return adjacent


def _is_default_config_snapshot(path: Path) -> bool:
    """Whether ``path`` is the active workspace config snapshot.

    ``resolve_config`` is a test seam and may return an arbitrary temporary
    file.  Such a file must remain self-contained: repository changesets are
    only a fallback for the real active config directory when the user
    workspace has not copied the adjacent changeset yet.
    """
    try:
        from features.common.workspace import config_dir

        return path.resolve().parent == config_dir().resolve()
    except (OSError, RuntimeError):
        return False


def _apply_current_changes(companies: list[dict], changeset: dict) -> list[dict]:
    """Apply the verified current membership delta without changing the input."""
    result = [dict(row) for row in companies if isinstance(row, dict)]

    def remove_ticker(ticker: Any) -> None:
        key = _join_key(ticker)
        result[:] = [row for row in result if _join_key(row.get("ticker")) != key]

    def remove_new_ticker(row: dict) -> None:
        remove_ticker(row.get("ticker"))

    for change in changeset.get("changes") or []:
        if not isinstance(change, dict):
            continue
        old_ticker = change.get("oldTicker")
        new_row = change.get("newRow")
        if old_ticker:
            remove_ticker(old_ticker)
        if isinstance(new_row, dict):
            remove_new_ticker(new_row)
            result.append(dict(new_row))
        elif change.get("newTicker"):
            # A pure ticker change retains the historical classification until
            # the current dated row below supplies the current cap/metadata.
            old_row = next(
                (dict(row) for row in companies if _join_key(row.get("ticker")) == _join_key(old_ticker)),
                None,
            )
            if old_row:
                old_row["ticker"] = str(change["newTicker"])
                old_row["providerSymbol"] = provider_symbol(change["newTicker"])
                if change.get("label"):
                    old_row["label"] = change["label"]
                result.append(old_row)

    # Rows in this list carry real, current market-cap observations.  Keeping
    # this override separate makes it impossible to accidentally reuse the old
    # SATS/AVB/EQR/CAG cap for a newly listed ticker.
    for current_row in changeset.get("currentRows") or []:
        if not isinstance(current_row, dict) or not current_row.get("ticker"):
            continue
        remove_new_ticker(current_row)
        result.append(dict(current_row))

    for update in changeset.get("metadataUpdates") or []:
        if not isinstance(update, dict) or not update.get("ticker"):
            continue
        key = _join_key(update["ticker"])
        for row in result:
            if _join_key(row.get("ticker")) == key:
                row.update({name: value for name, value in update.items() if name != "ticker"})

    return sorted(result, key=lambda row: _number(row.get("marketCap")), reverse=True)


def _load_snapshot_payload(path: Path) -> dict:
    payload = _read_json(path)
    companies = payload.get("companies")
    if not isinstance(companies, list):
        return {}
    return payload


def load_sp500_constituents(
    path: Path | str | None = None,
    *,
    as_of_date: dt.date | dt.datetime | str | None = None,
) -> list[dict]:
    """Load the S&P 500 rows for a report date.

    The original ``config/sp500_constituents.json`` is an immutable historical
    baseline (2026-06-23).  Dates on/after the verified 2026-09-08 snapshot
    select the adjacent date-versioned changeset.  This deliberately keeps
    older reports reproducible and makes an unverified future date use the
    latest known snapshot rather than pretending a live index feed exists.
    """
    target = Path(path) if path is not None else resolve_config("sp500_constituents.json")
    payload = _load_snapshot_payload(target)
    companies = payload.get("companies")
    if not isinstance(companies, list):
        return []

    requested = _coerce_date(as_of_date) or dt.date.today()
    if requested < CURRENT_SP500_SNAPSHOT_AS_OF:
        return companies

    changeset = _read_json(
        _changeset_path(
            target,
            allow_repository_fallback=path is None and _is_default_config_snapshot(target),
        )
    )
    if (
        not changeset
        or _coerce_date(changeset.get("snapshotAsOf")) != CURRENT_SP500_SNAPSHOT_AS_OF
        or not _changeset_matches_baseline(payload, changeset)
    ):
        return companies
    return _apply_current_changes(companies, changeset)


def get_sp500_constituent_provenance(
    path: Path | str | None = None,
    *,
    as_of_date: dt.date | dt.datetime | str | None = None,
) -> dict:
    """Return the source/effective-date status used by the date-aware loader."""
    target = Path(path) if path is not None else resolve_config("sp500_constituents.json")
    baseline = _load_snapshot_payload(target)
    changeset = _read_json(
        _changeset_path(
            target,
            allow_repository_fallback=path is None and _is_default_config_snapshot(target),
        )
    )
    requested = _coerce_date(as_of_date) or dt.date.today()
    current = bool(
        changeset
        and _coerce_date(changeset.get("snapshotAsOf")) == CURRENT_SP500_SNAPSHOT_AS_OF
        and requested >= CURRENT_SP500_SNAPSHOT_AS_OF
        and _changeset_matches_baseline(baseline, changeset)
    )
    verified_through = _coerce_date(changeset.get("verifiedThrough")) if changeset else None
    status = (
        "verified_current_snapshot"
        if current and (verified_through is None or requested <= verified_through)
        else "latest_known_snapshot"
        if current
        else "historical_baseline"
    )
    return {
        "requestedAsOf": requested.isoformat(),
        "snapshotAsOf": (
            changeset.get("snapshotAsOf") if current else baseline.get("asOf")
        ),
        "sourceAsOf": changeset.get("sourceAsOf") if current else baseline.get("asOf"),
        "verifiedThrough": changeset.get("verifiedThrough") if changeset else baseline.get("asOf"),
        "status": status,
        "source": changeset.get("source") if current else baseline.get("source"),
        "changesApplied": list(changeset.get("changes") or []) if current else [],
        "knownChanges": list(changeset.get("changes") or []) if changeset else [],
        "marketCapSource": changeset.get("marketCapSource") if current else baseline.get("source"),
        "marketCapAsOf": (
            "mixed" if current else baseline.get("asOf")
        ),
        "baselineMarketCapAsOf": (
            changeset.get("baselineMarketCapAsOf") if current else baseline.get("asOf")
        ),
        "overridesMarketCapAsOf": changeset.get("overridesMarketCapAsOf") if current else None,
        "marketCapVintage": (
            changeset.get("marketCapVintage") if current else "baseline"
        ),
    }


if __name__ == "__main__":  # pragma: no cover - manual refresh entry point
    result = build_sp500_constituents_file()
    print(f"wrote {result['count']} companies, missing caps: {len(result['missingCap'])}")
