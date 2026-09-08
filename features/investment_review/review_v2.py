"""Stage E v2 review assembly, freshness and compare/commit seam.

This module has no network clients.  A read request only consults local
authorities (portfolio JSON, market-memory SQLite and saved report/backtest
files), which keeps opening the Portfolio tab side-effect free.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from zoneinfo import ZoneInfo

from features.common.canonical_report_io import artifact_lock, atomic_write
from features.investment_review.context_links import normalize_research_ticker
from features.investment_review.schema import empty_review, normalize_review

_MAX = 24
_REVIEW_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TERMINAL_CHECKPOINT_STATUSES = {"confirmed", "challenged", "expired"}
_REPORT_SELECTION_U5 = "u5-v1"
_KST = ZoneInfo("Asia/Seoul")
_RO_SNAPSHOTS: dict[int, tempfile.TemporaryDirectory] = {}


class ReviewRevisionConflict(RuntimeError):
    code = "investment_review_revision_conflict"

    def __init__(self, latest: dict, code: str | None = None):
        super().__init__(code or self.code)
        self.latest = latest
        self.code = code or self.code


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean(value: object, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _file_identity(path: Path, data: Mapping) -> dict:
    revision = data.get("revision")
    identifier = _clean(data.get("id") or path.stem, 160)
    if isinstance(revision, int) or (isinstance(revision, str) and revision.isdigit()):
        identity = {"revision": int(revision)}
    else:
        identity = {"contentHash": _json_hash(data)}
    return {"kind": _clean(data.get("kind") or path.parent.name, 32), "id": identifier,
            **identity, "asOf": _clean(data.get("asOf") or data.get("date") or data.get("generatedAt"), 64)}


def _position_markets(positions: object) -> dict[str, set[str]]:
    markets: dict[str, set[str]] = {}
    for position in positions or []:
        if not isinstance(position, Mapping):
            continue
        ticker = normalize_research_ticker(position.get("ticker") or position.get("symbol"))
        market = _clean(position.get("marketScope") or position.get("market"), 16).casefold()
        if ticker and market in {"us", "kr"}:
            markets.setdefault(ticker, set()).add(market)
    return markets


def _report_row(path: Path, row: Mapping, kind: str, tickers: set[str], holding_markets: Mapping[str, set[str]]) -> tuple[dict, set[str], set[str]] | None:
    """Return one safe reference, its directly named holders and backgrounds."""
    row_tickers = {normalize_research_ticker(value) for value in (row.get("tickers") or [])}
    company = row.get("company") if isinstance(row.get("company"), Mapping) else {}
    row_tickers.add(normalize_research_ticker(row.get("ticker") or company.get("ticker")))
    row_tickers.discard("")
    market_scope = _clean(row.get("marketScope") or row.get("market"), 16).casefold()
    direct = row_tickers & tickers
    if market_scope in {"us", "kr"}:
        direct = {ticker for ticker in direct if not holding_markets.get(ticker) or market_scope in holding_markets[ticker]}
    background = ({ticker for ticker in tickers if market_scope and market_scope in holding_markets.get(ticker, set())}
                  if kind == "briefing" else set())
    if not direct and not background:
        return None
    item = _file_identity(path, row)
    display_kind = _clean(row.get("kind") or row.get("reportKind"), 32)
    if kind == "briefing":
        display_kind = display_kind if display_kind in {"briefing", "daily", "weekly"} else "briefing"
    else:
        display_kind = kind
    item.update({"kind": kind, "reportKind": display_kind, "marketScope": market_scope if market_scope in {"us", "kr"} else "",
                 "marketWide": bool(background and kind == "briefing"),
                 "title": _clean(row.get("title") or row.get("headline") or row.get("name") or item.get("id"), 240)})
    return item, direct, background


def _used_reports_legacy(data_dir: Path, tickers: set[str], *, positions: object = ()) -> list[dict]:
    if not tickers:
        return []
    rows_by_ticker: dict[str, list[dict]] = {ticker: [] for ticker in tickers}
    holding_markets = _position_markets(positions)
    for dirname, kind in (("briefings", "briefing"), ("company-analysis", "company_analysis"), ("topic-reports", "topic_report")):
        folder = data_dir / dirname
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json"), reverse=True)[:40]:
            row = _load_json(path, {})
            if not isinstance(row, Mapping):
                continue
            row_tickers = {normalize_research_ticker(value) for value in (row.get("tickers") or [])}
            company = row.get("company") if isinstance(row.get("company"), Mapping) else {}
            row_tickers.add(normalize_research_ticker(row.get("ticker") or company.get("ticker")))
            row_tickers.discard("")
            market_scope = _clean(row.get("marketScope") or row.get("market"), 16).casefold()
            # A briefing can be market-wide only for an explicitly known
            # holding market.  Do not turn every recent US/KR briefing into a
            # reference for every holding merely because it lives in a folder.
            market_holders = sorted(ticker for ticker in tickers if market_scope and market_scope in holding_markets.get(ticker, set()))
            market_wide = kind == "briefing" and bool(market_holders)
            used_tickers = sorted(row_tickers & tickers)
            if market_scope in {"us", "kr"}:
                # A report that names a ticker but declares the other market
                # is not a usable reference for an explicitly scoped holding.
                used_tickers = [ticker for ticker in used_tickers if not holding_markets.get(ticker) or market_scope in holding_markets[ticker]]
            if not used_tickers and not market_wide:
                continue
            item = _file_identity(path, row)
            item["kind"] = kind
            item["tickers"] = sorted(set(used_tickers) | set(market_holders))
            item["marketWide"] = market_wide
            item["marketScope"] = market_scope if market_scope in {"us", "kr"} else ""
            for ticker in item["tickers"]:
                # The structured position projection allows eight references.
                # Bound provenance at the same source so inputBasis is exactly
                # the final union it can consume, never a recency scan.
                if len(rows_by_ticker[ticker]) < 8:
                    rows_by_ticker[ticker].append(item)
    union: dict[tuple[str, str], dict] = {}
    for refs in rows_by_ticker.values():
        for item in refs:
            key = (_clean(item.get("kind"), 32), _clean(item.get("id"), 160))
            union[key] = item
    return sorted(union.values(), key=lambda item: (item.get("kind", ""), item.get("id", "")))[:_MAX]


def _used_reports(data_dir: Path, tickers: set[str], *, positions: object = (), legacy: bool = False,
                  with_selection: bool = False):
    """Select bounded Canonical references without starving company material.

    ``legacy`` is intentionally an explicit compatibility switch.  Old v2
    snapshots must reconstruct their exact historical basis/fingerprint;
    fresh explicit generations use the U.5 round-robin policy.
    """
    if legacy:
        rows = _used_reports_legacy(data_dir, tickers, positions=positions)
        return (rows, {"candidateCount": len(rows), "includedCount": len(rows), "excludedCount": 0}) if with_selection else rows
    if not tickers:
        empty = []
        return (empty, {"candidateCount": 0, "includedCount": 0, "excludedCount": 0}) if with_selection else empty
    holding_markets = _position_markets(positions)
    ordered_tickers = sorted(tickers)
    # priority 0/1 are ticker-specific material; priority 2 is market
    # background. A per-holder round-robin happens inside each tier.
    pools: dict[str, list[list[dict]]] = {ticker: [[], [], []] for ticker in ordered_tickers}
    candidates: dict[tuple[str, str], dict] = {}
    for dirname, kind in (("company-analysis", "company_analysis"), ("topic-reports", "topic_report"), ("briefings", "briefing")):
        folder = data_dir / dirname
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json"), reverse=True)[:40]:
            raw = _load_json(path, {})
            if not isinstance(raw, Mapping):
                continue
            projected = _report_row(path, raw, kind, tickers, holding_markets)
            if projected is None:
                continue
            item, direct, background = projected
            key = (_clean(item.get("kind"), 32), _clean(item.get("id"), 160))
            candidates[key] = item
            tier = 0 if kind in {"company_analysis", "topic_report"} else 1 if direct else 2
            holders = direct if tier < 2 else background
            for ticker in sorted(holders):
                # A market-wide briefing is background even when it carries a
                # ticker list; preserving this distinction is the point of
                # the U.5 policy.
                pools[ticker][tier].append({"key": key, "item": item,
                                             "relatedReason": "종목 직접 자료" if tier < 2 else "시장 배경 자료"})
    assigned: dict[str, list[dict]] = {ticker: [] for ticker in ordered_tickers}
    selected: dict[tuple[str, str], dict] = {}
    for tier in range(3):
        cursor = {ticker: 0 for ticker in ordered_tickers}
        progressed = True
        while progressed:
            progressed = False
            for ticker in ordered_tickers:
                if len(assigned[ticker]) >= 8:
                    continue
                pool = pools[ticker][tier]
                while cursor[ticker] < len(pool):
                    candidate = pool[cursor[ticker]]; cursor[ticker] += 1
                    key = candidate["key"]
                    if any(ref["key"] == key for ref in assigned[ticker]):
                        continue
                    if key not in selected and len(selected) >= _MAX:
                        break
                    selected.setdefault(key, candidate["item"])
                    assigned[ticker].append(candidate)
                    progressed = True
                    break
    union: dict[tuple[str, str], dict] = {}
    for ticker, refs in assigned.items():
        for ref in refs:
            item = dict(ref["item"])
            key = ref["key"]
            current = union.setdefault(key, {**item, "tickers": [], "relatedReason": ref["relatedReason"]})
            current["tickers"].append(ticker)
    rows = sorted(({**row, "tickers": sorted(set(row["tickers"]))} for row in union.values()), key=lambda row: (row["kind"], row["id"]))
    selection = {"candidateCount": len(candidates), "includedCount": len(rows), "excludedCount": max(0, len(candidates) - len(rows))}
    return (rows, selection) if with_selection else rows


def _read_json_list(value: object) -> list:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        decoded = []
    return decoded if isinstance(decoded, list) else []


def _ro_connection(data_dir: Path) -> sqlite3.Connection | None:
    """Read a private DB/WAL snapshot without touching user SQLite sidecars."""
    path = data_dir / "market-memory.sqlite3"
    if not path.is_file():
        return None
    snapshot = tempfile.TemporaryDirectory(prefix="folio-review-ro-")
    try:
        copied = Path(snapshot.name) / path.name
        # Opening even mode=ro against a live WAL database can update its
        # shared-memory sidecar. Copy the database and existing WAL/SHM first,
        # then let SQLite perform all recovery/read bookkeeping in temp only.
        for suffix in ("", "-wal", "-shm"):
            source = Path(f"{path}{suffix}")
            if source.is_file():
                shutil.copyfile(source, Path(f"{copied}{suffix}"))
        conn = sqlite3.connect(f"{copied.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        _RO_SNAPSHOTS[id(conn)] = snapshot
        return conn
    except (sqlite3.Error, OSError):
        snapshot.cleanup()
        return None


def _close_ro_connection(conn: sqlite3.Connection) -> None:
    snapshot = _RO_SNAPSHOTS.pop(id(conn), None)
    try:
        conn.close()
    finally:
        if snapshot is not None:
            snapshot.cleanup()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
    except sqlite3.Error:
        return False


def _tracked_checkpoint_rows(theses: list[dict], states: list[dict], links: Mapping[str, set[str]]) -> list[dict]:
    """Project stored Stage-A tracked checkpoints without Delta aggregation.

    The authority is the stored Thesis/State checkpoint dict, including its
    status/history.  Delta's human text projection intentionally cannot
    substitute for it.
    """
    from features.common.research_schema.tracked_checkpoints import normalize_tracked_checkpoint

    rows: list[dict] = []
    for thesis in theses:
        ticker = normalize_research_ticker(thesis.get("ticker"))
        if not ticker:
            continue
        for raw in _read_json_list(thesis.get("next_checkpoints")):
            checkpoint = normalize_tracked_checkpoint(raw, scope="thesis", scope_key=ticker, trusted=True)
            if checkpoint is None:
                continue
            rows.append({**checkpoint, "dueAt": checkpoint.get("dueBy") or "", "owner": "thesis", "ticker": ticker, "linkedTickers": [ticker]})
    for state in states:
        state_id, state_key, _label = _state_identity(state)
        linked = sorted(ticker for ticker, state_ids in links.items() if state_id in state_ids)
        if not state_id or not linked:
            continue
        for raw in _read_json_list(state.get("nextCheckpoints") or state.get("next_checkpoints")):
            checkpoint = normalize_tracked_checkpoint(raw, scope="narrative", scope_key=state_key, trusted=True)
            if checkpoint is None:
                continue
            rows.append({**checkpoint, "dueAt": checkpoint.get("dueBy") or "", "owner": "state", "stateId": state_id, "stateKey": state_key, "linkedTickers": linked})
    return rows[:40]


def _current_states(data_dir: Path) -> list[dict]:
    conn = _ro_connection(data_dir)
    if conn is None:
        return []
    try:
        if not _table_exists(conn, "market_narrative_states"):
            return []
        rows = conn.execute("SELECT * FROM market_narrative_states WHERE status IN ('active', 'watch') ORDER BY updated_at DESC LIMIT 80").fetchall()
        return [{
            "id": row["state_id"], "stateId": row["state_id"], "stateKey": row["state_key"],
            "stateLabel": row["state_label"], "status": row["status"], "momentum": row["momentum"] if "momentum" in row.keys() else "stable",
            "updatedAt": row["updated_at"], "nextCheckpoints": _read_json_list(row["next_checkpoints_json"]) if "next_checkpoints_json" in row.keys() else [],
        } for row in rows]
    except sqlite3.Error:
        return []
    finally:
        _close_ro_connection(conn)


def _theses_result(data_dir: Path) -> tuple[list[dict], bool]:
    conn = _ro_connection(data_dir)
    if conn is None:
        # A missing authority is a known empty workspace; an unreadable
        # existing DB is not evidence that every thesis is absent.
        return [], not (data_dir / "market-memory.sqlite3").exists()
    try:
        if not _table_exists(conn, "thesis"):
            return [], True
        has_delta = _table_exists(conn, "thesis_delta")
        out = []
        for row in conn.execute("SELECT * FROM thesis ORDER BY updated_at DESC, ticker ASC").fetchall():
            ticker = normalize_research_ticker(row["ticker"])
            if not ticker:
                continue
            latest: dict = {}
            if has_delta:
                delta = conn.execute("SELECT * FROM thesis_delta WHERE ticker=? ORDER BY generated_at DESC LIMIT 1", (ticker,)).fetchone()
                if delta is not None:
                    try: analysis = json.loads(delta["analysis_json"] or "{}")
                    except (TypeError, json.JSONDecodeError): analysis = {}
                    latest = {**(analysis if isinstance(analysis, dict) else {}), "deltaId": delta["delta_id"], "verdict": delta["verdict"], "generatedAt": delta["generated_at"]}
            out.append({"ticker": ticker, "company": row["company"], "updated_at": row["updated_at"],
                        "linked_regimes": _read_json_list(row["linked_regimes_json"]) if "linked_regimes_json" in row.keys() else [],
                        "next_checkpoints": _read_json_list(row["next_checkpoints_json"]) if "next_checkpoints_json" in row.keys() else [],
                        "latestDelta": latest})
        return out, True
    except sqlite3.Error:
        return [], False
    finally:
        _close_ro_connection(conn)


def _theses(data_dir: Path) -> list[dict]:
    return _theses_result(data_dir)[0]


def _manual_links(data_dir: Path, states: list[dict]) -> dict[str, set[str]]:
    """Resolve declared/manual links to the *current* active/watch lineage.

    A manual relationship can point to an overridden state id.  Its stable
    ``state_key`` is allowed to carry the explicit relationship forward, but
    an old id itself is never shown as a current exposure.  This intentionally
    does not inspect evidence-derived ``linkedCompanies``.
    """
    result: dict[str, set[str]] = {}
    current_by_id: dict[str, str] = {}
    current_by_key: dict[str, str] = {}
    for state in states:
        if not isinstance(state, Mapping):
            continue
        state_id, state_key, _label = _state_identity(state)
        if state_id:
            current_by_id[state_id] = state_id
        if state_key and state_id:
            current_by_key[state_key.casefold()] = state_id
    conn = _ro_connection(data_dir)
    if conn is None:
        return result
    try:
        if not (_table_exists(conn, "market_regime_thesis_links") and _table_exists(conn, "market_narrative_states")):
            return result
        with conn:
            rows = conn.execute("""
                SELECT linked.state_id, linked.thesis_ticker, linked.relationship, linked.method,
                       historical.state_key
                FROM market_regime_thesis_links AS linked
                LEFT JOIN market_narrative_states AS historical ON historical.state_id = linked.state_id
            """).fetchall()
        for state_id, ticker, relationship, method, state_key in rows:
            if str(relationship) != "linked_regimes" and str(method) != "manual":
                continue
            resolved = current_by_id.get(_clean(state_id, 200))
            if not resolved and state_key:
                resolved = current_by_key.get(_clean(state_key, 200).casefold())
            if resolved:
                result.setdefault(normalize_research_ticker(ticker), set()).add(resolved)
    except sqlite3.Error:
        pass
    finally:
        _close_ro_connection(conn)
    return result


def _state_identity(row: Mapping) -> tuple[str, str, str]:
    state_id = _clean(row.get("id") or row.get("stateId") or row.get("stateKey"), 200)
    key = _clean(row.get("stateKey") or state_id, 200)
    label = _clean(row.get("stateLabel") or row.get("storyFamily") or row.get("story"), 200)
    return state_id, key, label


def _weight(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 8) if number >= 0 else None


def _position_signature(rows: list[dict], *, weight_key: str = "weight") -> dict[str, tuple[float | None, str]]:
    signature: dict[str, tuple[float | None, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ticker = normalize_research_ticker(row.get("ticker") or row.get("symbol"))
        if ticker:
            signature[ticker] = (_weight(row.get(weight_key)), _clean(row.get("currency") or row.get("quoteCurrency"), 12).upper())
    return signature


def _compatibility_signature(analytics: Mapping) -> dict:
    positions = _position_signature([dict(row) for row in (analytics.get("positions") or []) if isinstance(row, Mapping)])
    return {
        "positions": [{"ticker": ticker, "weight": weight, "currency": currency} for ticker, (weight, currency) in sorted(positions.items())],
        "baseCurrency": _clean(analytics.get("baseCurrency"), 12).upper(),
    }


def _analytics_snapshot(data_dir: Path, positions: list[dict], *, include_analytics: bool) -> dict:
    """Capture Portfolio's existing analytics projection only on generation.

    ``portfolio_analytics`` may fetch quotes/FX, so it is forbidden on the
    read/freshness path.  The snapshot is descriptive; no provider timestamp
    is promoted to a fake price/FX as-of in the review basis.
    """
    base = {
        "methodVersion": "portfolio-analytics-v1",
        "baseCurrency": "",
        "positions": [], "sectorWeights": [], "currencyWeights": [],
        "concentration": {}, "window": "", "available": False, "compatibilitySignature": {"positions": [], "baseCurrency": ""},
    }
    if not include_analytics:
        return base
    try:
        from features.portfolio.service import portfolio_analytics
        from features.common.workspace import data_dir as workspace_data_dir
        # The production projection is process-global today.  A temporary
        # workspace used by tests/CLI preparation must not accidentally query
        # the user's live portfolio or the network.
        if data_dir.resolve(strict=False) != workspace_data_dir().resolve(strict=False):
            return base
        projection = portfolio_analytics()
        analytics = projection.get("analytics") if isinstance(projection, Mapping) else {}
        if not isinstance(analytics, Mapping):
            return base
        rows = analytics.get("positionWeights") if isinstance(analytics.get("positionWeights"), list) else []
        snapshot = {
            **base,
            "baseCurrency": _clean(analytics.get("baseCurrency"), 12).upper(),
            "positions": [dict(row) for row in rows if isinstance(row, Mapping)],
            "sectorWeights": [dict(row) for row in (analytics.get("sectorWeights") or []) if isinstance(row, Mapping)][:12],
            "currencyWeights": [dict(row) for row in (analytics.get("currencyWeights") or []) if isinstance(row, Mapping)][:12],
            "concentration": dict(analytics.get("concentration") or {}) if isinstance(analytics.get("concentration"), Mapping) else {},
            "available": bool(rows),
        }
        snapshot["fingerprint"] = _json_hash({key: snapshot[key] for key in ("methodVersion", "baseCurrency", "positions", "sectorWeights", "currencyWeights", "concentration")})
        snapshot["compatibilitySignature"] = _compatibility_signature(snapshot)
        return snapshot
    except Exception:
        return base


def _backtest_ref(data_dir: Path, positions: list[dict], analytics: Mapping) -> tuple[dict | None, list[dict]]:
    """Use only a compatible, already saved run; never run a backtest here."""
    current = _position_signature(list(analytics.get("positions") or positions))
    if not current or not analytics.get("available"):
        return None, [{"code": "portfolio_analytics_projection_unavailable"}]
    wanted_currency = _clean(analytics.get("baseCurrency"), 12).upper()
    # Live Portfolio analytics has no selected historical period/window.  A
    # saved run supplies those immutable reference semantics; we only accept
    # the supported engine and a complete saved identity, never invent one.
    supported_methods = {"portfolio-backtest-v1"}
    folder = data_dir / "portfolio-backtests"
    if not folder.is_dir():
        return None, [{"code": "compatible_saved_backtest_missing"}]
    for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        row = _load_json(path, {})
        if not isinstance(row, Mapping) or row.get("type") == "comparison":
            continue
        holdings = _position_signature([dict(item) for item in (row.get("positions") or []) if isinstance(item, Mapping)])
        method = _clean(row.get("methodVersion") or row.get("method") or "portfolio-backtest-v1", 80)
        window = _clean(row.get("window") or row.get("rebalance"), 80)
        start, end = _clean(row.get("start"), 24), _clean(row.get("end"), 24)
        if (holdings != current or not wanted_currency or _clean(row.get("baseCurrency"), 12).upper() != wanted_currency
                or method not in supported_methods or not window or not start or not end):
            continue
        return {"id": _clean(row.get("id") or path.stem, 100), "methodVersion": method, "baseCurrency": _clean(row.get("baseCurrency"), 12),
                "window": window, "start": start, "end": end,
                "riskContributions": [dict(item) for item in (row.get("riskContributions") or []) if isinstance(item, Mapping)][:12],
                "fingerprint": _json_hash({"positions": row.get("positions"), "method": method, "window": window, "start": start, "end": end, "currency": row.get("baseCurrency")})}, []
    return None, [{"code": "compatible_saved_backtest_missing"}]


def _date_only_overdue(due_at: object, evaluated_at: object) -> bool:
    """Treat a date-only due date as ending in its local (Korea) day.

    Stored checkpoint dates are product dates, not UTC midnights.  Therefore
    `2026-09-04` is not overdue at 2026-09-04 09:00 KST; a timestamp keeps its
    explicit instant.  This is additive U.5 display logic and does not alter
    E.1's historical `dueCount` comparison.
    """
    due = _clean(due_at, 64)
    evaluated = _clean(evaluated_at, 64)
    if not due or not evaluated:
        return False
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            return dt.date.fromisoformat(due) < dt.datetime.fromisoformat(evaluated.replace("Z", "+00:00")).astimezone(_KST).date()
        due_value = dt.datetime.fromisoformat(due.replace("Z", "+00:00"))
        evaluated_value = dt.datetime.fromisoformat(evaluated.replace("Z", "+00:00"))
        # Legacy local timestamps are interpreted as KST rather than being
        # compared naively with a UTC value (which would crash a GET path).
        if due_value.tzinfo is None:
            due_value = due_value.replace(tzinfo=_KST)
        if evaluated_value.tzinfo is None:
            evaluated_value = evaluated_value.replace(tzinfo=dt.UTC)
        return due_value <= evaluated_value
    except (TypeError, ValueError):
        return False


def _detail_priority_rows(inputs: Mapping) -> list[str]:
    theses = {normalize_research_ticker(row.get("ticker")): row for row in inputs.get("theses") or [] if isinstance(row, Mapping)}
    authority_available = inputs.get("thesisAuthorityAvailable") is True
    ranked = []
    for raw in inputs.get("positions") or []:
        if not isinstance(raw, Mapping):
            continue
        ticker = normalize_research_ticker(raw.get("ticker") or raw.get("symbol"))
        if not ticker:
            continue
        thesis = theses.get(ticker)
        delta = thesis.get("latestDelta") if isinstance((thesis or {}).get("latestDelta"), Mapping) else {}
        verdict = _clean(delta.get("verdict"), 40) or "insufficient_evidence"
        # Reference membership is authority/fingerprint material.  It may not
        # rotate just because a wall clock crosses a checkpoint due date.
        due = any(_clean(row.get("status"), 32) not in _TERMINAL_CHECKPOINT_STATUSES
                  and (normalize_research_ticker(row.get("ticker")) == ticker or ticker in (row.get("linkedTickers") or []))
                  and _clean(row.get("dueAt") or row.get("due_at") or row.get("dueBy"), 64)
                  for row in inputs.get("checkpoints") or [] if isinstance(row, Mapping))
        bucket = ({"broken": 0, "at_risk": 1, "weakened": 2}.get(verdict,
                  3 if due else 4 if authority_available and not thesis else 5 if thesis and not delta else 6 if verdict == "insufficient_evidence" else 7))
        ranked.append((bucket, ticker))
    return [ticker for _bucket, ticker in sorted(ranked)]


def gather_inputs(data_dir: Path, *, include_portfolio: bool = True, include_watchlist: bool = False, include_obsidian: bool = False, include_analytics: bool = False, analytics_authority: Mapping | None = None, report_selection_version: str = _REPORT_SELECTION_U5) -> dict:
    """Read current local authorities.  Watchlist is intentionally ignored for v2 positions."""
    from features.portfolio.service import get_portfolio
    portfolio = get_portfolio(data_dir) if include_portfolio else {"revision": 0, "positions": [], "updatedAt": ""}
    positions = [dict(row) for row in (portfolio.get("positions") or []) if isinstance(row, Mapping) and normalize_research_ticker(row.get("ticker") or row.get("symbol"))]
    holding_tickers = {normalize_research_ticker(row.get("ticker") or row.get("symbol")) for row in positions}
    holding_tickers.discard("")
    thesis_rows, thesis_authority_available = _theses_result(data_dir)
    theses = [row for row in thesis_rows if normalize_research_ticker(row.get("ticker")) in holding_tickers]
    all_states = _current_states(data_dir)
    manual_links = _manual_links(data_dir, all_states)
    explicit_inputs = {"states": all_states, "manualLinks": manual_links}
    linked_ids = {
        link["stateId"] for thesis in theses
        for link in _explicit_state_links(explicit_inputs, normalize_research_ticker(thesis.get("ticker")), thesis)
    }
    states = [row for row in all_states if _state_identity(row)[0] in linked_ids]
    resolved_links = {ticker: set(ids) for ticker, ids in manual_links.items()}
    for thesis in theses:
        ticker = normalize_research_ticker(thesis.get("ticker"))
        for link in _explicit_state_links(explicit_inputs, ticker, thesis):
            resolved_links.setdefault(ticker, set()).add(link["stateId"])
    checkpoints = _tracked_checkpoint_rows(theses, states, resolved_links)
    analytics = _analytics_snapshot(data_dir, positions, include_analytics=include_analytics)
    if not include_analytics and isinstance(analytics_authority, Mapping):
        signature = analytics_authority.get("compatibilitySignature")
        if isinstance(signature, Mapping):
            signature_positions = [dict(row) for row in (signature.get("positions") or []) if isinstance(row, Mapping)]
            analytics.update({
                "methodVersion": "portfolio-analytics-v1",
                "baseCurrency": _clean(signature.get("baseCurrency"), 12).upper(),
                "positions": signature_positions,
                "available": bool(signature_positions),
                "compatibilitySignature": {"positions": signature_positions, "baseCurrency": _clean(signature.get("baseCurrency"), 12).upper()},
            })
    selection_version = _REPORT_SELECTION_U5 if report_selection_version == _REPORT_SELECTION_U5 else ""
    detail_tickers = set(_detail_priority_rows({"positions": positions, "theses": theses, "checkpoints": checkpoints,
                                                "thesisAuthorityAvailable": thesis_authority_available})[:_MAX])
    report_tickers = detail_tickers if selection_version else holding_tickers
    report_refs, report_selection = _used_reports(data_dir, report_tickers, positions=positions,
                                                   legacy=not bool(selection_version), with_selection=True)
    backtest, backtest_uncertainties = _backtest_ref(data_dir, positions, analytics)
    return {"portfolio": portfolio, "positions": positions, "theses": theses, "states": states,
            "checkpoints": checkpoints, "analytics": dict(analytics), "reportRefs": report_refs,
            "backtest": backtest, "backtestUncertainties": backtest_uncertainties,
            "manualLinks": {ticker: set(ids) for ticker, ids in manual_links.items() if ticker in holding_tickers}, "capturedAt": _now(),
            "thesisAuthorityAvailable": thesis_authority_available, "reportSelectionVersion": selection_version,
            "reportSelection": report_selection, "detailTickers": detail_tickers}


def build_input_basis(inputs: Mapping, *, previous: Mapping | None = None) -> dict:
    portfolio = inputs.get("portfolio") if isinstance(inputs.get("portfolio"), Mapping) else {}
    states = []
    for row in inputs.get("states") or []:
        if not isinstance(row, Mapping): continue
        state_id, key, _label = _state_identity(row)
        states.append({"stateId": state_id, "stateKey": key, "updatedAt": _clean(row.get("updatedAt") or row.get("updated_at"), 64), "momentum": _clean(row.get("momentum"), 32)})
    theses = []
    for row in inputs.get("theses") or []:
        if not isinstance(row, Mapping): continue
        delta = row.get("latestDelta") if isinstance(row.get("latestDelta"), Mapping) else {}
        theses.append({"ticker": normalize_research_ticker(row.get("ticker")), "thesisUpdatedAt": _clean(row.get("updated_at") or row.get("updatedAt"), 64),
                       "deltaId": _clean(delta.get("deltaId") or delta.get("delta_id"), 120), "verdict": _clean(delta.get("verdict"), 40), "deltaGeneratedAt": _clean(delta.get("generatedAt") or delta.get("generated_at"), 64)})
    def checkpoint_authority(row: Mapping) -> dict:
        # Hash the complete trusted tracked-checkpoint projection. In
        # particular lastVerdict.at/evidence and history are authority, not a
        # display string, so same-verdict later evidence must stale a review.
        last = row.get("lastVerdict") if isinstance(row.get("lastVerdict"), Mapping) else None
        history = row.get("history") if isinstance(row.get("history"), list) else []
        matchers = row.get("matchers") if isinstance(row.get("matchers"), Mapping) else {}
        return {
            "id": _clean(row.get("id"), 160), "item": _clean(row.get("checkpoint") or row.get("item") or row.get("label"), 240),
            "direction": _clean(row.get("direction"), 40), "status": _clean(row.get("status"), 32),
            "dueBy": _clean(row.get("dueAt") or row.get("due_at") or row.get("dueBy"), 64), "createdAt": _clean(row.get("createdAt") or row.get("created_at"), 64),
            "matchers": {"tickers": [_clean(value, 24) for value in (matchers.get("tickers") or [])][:6], "keywords": [_clean(value, 40) for value in (matchers.get("keywords") or [])][:6]},
            "lastVerdict": last,
            "history": history[:20],
            "owner": _clean(row.get("owner"), 16), "ticker": normalize_research_ticker(row.get("ticker")),
            "stateId": _clean(row.get("stateId"), 160), "stateKey": _clean(row.get("stateKey"), 160),
            "linkedTickers": sorted(normalize_research_ticker(value) for value in (row.get("linkedTickers") or []) if normalize_research_ticker(value)),
        }
    checkpoint_watermark = _json_hash([checkpoint_authority(row) for row in inputs.get("checkpoints") or [] if isinstance(row, Mapping)])
    analytics = inputs.get("analytics") if isinstance(inputs.get("analytics"), Mapping) else {}
    selection_version = _clean(inputs.get("reportSelectionVersion"), 16)
    # Keep the legacy list's historical field shape byte-for-byte.  U.5
    # display metadata never participates in the authority hash.
    canonical_reports = []
    for row in inputs.get("reportRefs") or []:
        if not isinstance(row, Mapping):
            continue
        item = {key: row.get(key) for key in ("kind", "id", "asOf", "tickers", "marketWide", "marketScope", "revision", "contentHash") if key in row}
        canonical_reports.append(item)
    display_reports = []
    if selection_version == _REPORT_SELECTION_U5:
        for row in canonical_reports:
            visual = dict(row)
            source = next((item for item in inputs.get("reportRefs") or [] if isinstance(item, Mapping)
                           and _clean(item.get("kind"), 32) == _clean(row.get("kind"), 32)
                           and _clean(item.get("id"), 160) == _clean(row.get("id"), 160)), {})
            for key in ("title", "reportKind", "relatedReason"):
                if _clean(source.get(key), 240):
                    visual[key] = _clean(source.get(key), 240)
            display_reports.append(visual)
    basis = {"status": "partial", "capturedAt": _clean(inputs.get("capturedAt"), 64),
             "portfolio": {"revision": portfolio.get("revision", 0), "updatedAt": _clean(portfolio.get("updatedAt"), 64)},
             # Quote/FX provider observation time is not authoritative here;
             # never manufacture an as-of timestamp from generation time.
             "marketData": {"status": "partial", "reason": "provider_observed_at_unknown", "priceAsOf": "", "fxAsOf": ""},
             "theses": sorted(theses, key=lambda row: row["ticker"]), "marketStates": sorted(states, key=lambda row: row["stateKey"]),
             "checkpointWatermark": checkpoint_watermark, "canonicalReports": sorted(display_reports if selection_version == _REPORT_SELECTION_U5 else canonical_reports, key=lambda row: (row.get("kind", ""), row.get("id", "")))[:_MAX],
             # Quote/FX-derived analytics is a generation snapshot, not a
             # read-time authority watermark.  Keeping its dynamic hash out of
             # the fingerprint prevents every read-only open from becoming
             # stale while still recording the saved-backtest compatibility.
             "analytics": {"methodVersion": _clean(analytics.get("methodVersion"), 80), "snapshotFingerprint": _clean(analytics.get("fingerprint"), 128),
                           "compatibilitySignature": _compatibility_signature(analytics), "backtest": inputs.get("backtest") or None},
             "previousReview": {"date": _clean((previous or {}).get("date"), 10), "reviewRevision": (previous or {}).get("reviewRevision", 0)}}
    if selection_version == _REPORT_SELECTION_U5:
        basis["reportSelectionVersion"] = _REPORT_SELECTION_U5
        basis["thesisAuthorityStatus"] = "available" if inputs.get("thesisAuthorityAvailable") is True else "unavailable"
    required = bool(basis["portfolio"]["revision"] is not None and basis["marketStates"] is not None and basis["theses"] is not None)
    # Quote/FX observation time is unknown; an input basis containing it is
    # necessarily partial, even when every local authority was readable.
    basis["status"] = "partial"
    fingerprint_value = {key: value for key, value in basis.items() if key not in {"capturedAt", "marketData", "previousReview", "thesisAuthorityStatus"}}
    # The U.5 basis exposes title/read reason for navigation, but its
    # authority fingerprint remains the old identity-only projection.
    fingerprint_value["canonicalReports"] = sorted(canonical_reports, key=lambda row: (row.get("kind", ""), row.get("id", "")))[:_MAX]
    fingerprint_value["analytics"] = {
        "methodVersion": basis["analytics"]["methodVersion"],
        "compatibilitySignature": basis["analytics"]["compatibilitySignature"],
        "backtest": basis["analytics"]["backtest"],
    }
    basis["fingerprint"] = _json_hash(fingerprint_value)
    return basis


def _explicit_state_links(inputs: Mapping, ticker: str, thesis: Mapping | None) -> list[dict]:
    manual = (inputs.get("manualLinks") or {}).get(ticker, set())
    declared = {_clean(value, 200).casefold() for value in ((thesis or {}).get("linked_regimes") or []) if _clean(value, 200)}
    rows = []
    for state in inputs.get("states") or []:
        if not isinstance(state, Mapping): continue
        state_id, key, label = _state_identity(state)
        candidates = {state_id, key, label}
        if state_id in manual or any(candidate.casefold() in declared for candidate in candidates if candidate):
            rows.append({"stateId": state_id, "stateKey": key, "label": label or key, "momentum": _clean(state.get("momentum"), 32) or "stable"})
    return sorted(rows, key=lambda row: row["stateKey"])[:8]


def build_structured_review(inputs: Mapping, basis: Mapping) -> dict:
    thesis_by_ticker = {normalize_research_ticker(row.get("ticker")): row for row in inputs.get("theses") or [] if isinstance(row, Mapping)}
    positions, shared, risks, counter, uncertainties = [], {}, [], [], list(inputs.get("backtestUncertainties") or [])
    authority_available = inputs.get("thesisAuthorityAvailable") is True
    for raw in inputs.get("positions") or []:
        if not isinstance(raw, Mapping): continue
        ticker = normalize_research_ticker(raw.get("ticker") or raw.get("symbol"))
        if not ticker: continue
        thesis = thesis_by_ticker.get(ticker, {})
        delta = thesis.get("latestDelta") if isinstance(thesis.get("latestDelta"), Mapping) else {}
        links = _explicit_state_links(inputs, ticker, thesis)
        due = [row for row in inputs.get("checkpoints") or [] if isinstance(row, Mapping)
               and _clean(row.get("status"), 32) not in _TERMINAL_CHECKPOINT_STATUSES
               and (normalize_research_ticker(row.get("ticker")) == ticker or ticker in (row.get("linkedTickers") or []))][:8]
        canonical_refs = [dict(ref) for ref in (inputs.get("reportRefs") or []) if isinstance(ref, Mapping)
                          and ticker in (ref.get("tickers") or [])][:8]
        reason_codes = []
        verdict = _clean(delta.get("verdict"), 40) or "insufficient_evidence"
        if verdict in {"weakened", "at_risk", "broken", "insufficient_evidence"}: reason_codes.append("thesis_review_needed")
        if due: reason_codes.append("checkpoint_due" if any(_clean(row.get("dueAt") or row.get("due_at")) for row in due) else "checkpoint_pending")
        if not thesis and authority_available: uncertainties.append({"code": "thesis_missing", "ticker": ticker})
        position_uncertainties = []
        if not links and thesis:
            position_uncertainties.append({"code": "explicit_narrative_link_missing", "ticker": ticker})
        analytics_position = next((row for row in (inputs.get("analytics") or {}).get("positions", []) if isinstance(row, Mapping) and normalize_research_ticker(row.get("ticker") or row.get("symbol")) == ticker), {})
        signals = ([{"kind": "current_weight", "weight": analytics_position.get("weight"), "baseCurrency": _clean((inputs.get("analytics") or {}).get("baseCurrency"), 12)}]
                   if isinstance(analytics_position, Mapping) and analytics_position.get("weight") is not None else [])
        position = {"ticker": ticker, "name": _clean(raw.get("name"), 160) or ticker, "thesisVerdict": verdict,
                          "narrativeLinks": links, "quantitativeRiskSignals": signals, "reviewReasons": reason_codes[:8],
                          "canonicalReferences": canonical_refs,
                          # Stored tracked checkpoints use ``item``.  Keep
                          # the older synthetic ``checkpoint`` value first,
                          # then the authoritative tracked field, with label
                          # only as a final display fallback.
                          "dueCheckpoints": [{"id": _clean(row.get("id"), 160), "label": _clean(row.get("checkpoint") or row.get("item") or row.get("label"), 240), "dueAt": _clean(row.get("dueAt") or row.get("due_at") or row.get("dueBy"), 64)} for row in due],
                          "counterEvidence": list(delta.get("counterEvidence") or [])[:4], "uncertainties": position_uncertainties}
        if authority_available:
            position["thesisPresent"] = bool(thesis)
            position["latestReviewPresent"] = bool(delta)
        positions.append(position)
        counter.extend(list(delta.get("counterEvidence") or [])[:3])
        for link in links:
            entry = shared.setdefault("narrative:" + link["stateKey"], {"type": "narrative", "key": link["stateKey"], "stateKey": link["stateKey"], "label": link["label"], "stateId": link["stateId"], "tickers": [], "momentum": link["momentum"]})
            entry["tickers"].append(ticker)
        sector = _clean(raw.get("sector"), 120)
        currency = _clean(raw.get("currency"), 12).upper()
        for kind, value in (("sector", sector), ("currency", currency)):
            if value:
                shared.setdefault(f"{kind}:{value}", {"type": kind, "key": value, "label": value, "tickers": []})["tickers"].append(ticker)
    analytics = inputs.get("analytics") if isinstance(inputs.get("analytics"), Mapping) else {}
    backtest = inputs.get("backtest")
    concentration = analytics.get("concentration") if isinstance(analytics.get("concentration"), Mapping) else {}
    if concentration:
        risks.append({"riskKey": "portfolio_concentration", "methodVersion": _clean(analytics.get("methodVersion"), 80), "status": "available", "concentration": dict(concentration)})
    for kind, rows in (("sector", analytics.get("sectorWeights") or []), ("currency", analytics.get("currencyWeights") or [])):
        for row in rows[:12] if isinstance(rows, list) else []:
            if not isinstance(row, Mapping) or not _clean(row.get("label"), 120):
                continue
            key = _clean(row.get("label"), 120)
            item = shared.setdefault(f"{kind}:{key}", {"type": kind, "key": key, "label": key, "tickers": []})
            item["weight"] = row.get("weight")
    if isinstance(backtest, Mapping):
        risks.append({"riskKey": "saved_backtest", "methodVersion": _clean(backtest.get("methodVersion"), 80), "backtestRef": dict(backtest), "riskContributions": list(backtest.get("riskContributions") or [])[:12], "status": "available"})
    else:
        risks.append({"riskKey": "correlation_volatility", "methodVersion": "portfolio-backtest-v1", "status": "unavailable", "uncertainty": "compatible_saved_backtest_missing"})
    shared_rows = [{**row, "tickers": sorted(set(row["tickers"]))[:_MAX]} for row in shared.values()]
    checkpoint_reviews = [{"id": _clean(row.get("id"), 160), "ticker": normalize_research_ticker(row.get("ticker")),
                           "item": _clean(row.get("checkpoint") or row.get("item") or row.get("label"), 240), "direction": _clean(row.get("direction"), 40),
                           "status": _clean(row.get("status"), 32), "lastVerdict": (dict(row.get("lastVerdict") or row.get("last_verdict")) if isinstance(row.get("lastVerdict") or row.get("last_verdict"), Mapping) else _clean(row.get("lastVerdict") or row.get("last_verdict"), 40)),
                           "dueBy": _clean(row.get("dueAt") or row.get("due_at") or row.get("dueBy"), 64)}
                          for row in inputs.get("checkpoints") or [] if isinstance(row, Mapping) and _clean(row.get("id"), 160)]
    priority_order = {"broken": 0, "at_risk": 1, "weakened": 2, "insufficient_evidence": 6}
    evaluated_at = _clean(inputs.get("capturedAt"), 64)
    def priority(row: Mapping) -> tuple[int, str]:
        verdict = _clean(row.get("thesisVerdict"), 40)
        if verdict in priority_order and verdict != "insufficient_evidence":
            return priority_order[verdict], _clean(row.get("ticker"), 24)
        open_checkpoint = any(_clean(checkpoint.get("dueAt"), 64) for checkpoint in row.get("dueCheckpoints") or [] if isinstance(checkpoint, Mapping))
        if open_checkpoint: return 3, _clean(row.get("ticker"), 24)
        if row.get("thesisPresent") is False: return 4, _clean(row.get("ticker"), 24)
        if row.get("latestReviewPresent") is False: return 5, _clean(row.get("ticker"), 24)
        if verdict == "insufficient_evidence": return 6, _clean(row.get("ticker"), 24)
        return 7, _clean(row.get("ticker"), 24)
    details = sorted(positions, key=priority)[:_MAX]
    roster = []
    for row in positions[:100]:
        roster_row = {"ticker": row["ticker"], "thesisVerdict": row["thesisVerdict"]}
        for readiness_key in ("thesisPresent", "latestReviewPresent"):
            if isinstance(row.get(readiness_key), bool): roster_row[readiness_key] = row[readiness_key]
        roster.append(roster_row)
    total = len(positions)
    coverage = {"totalPositionCount": total, "rosterIncludedCount": len(roster), "detailIncludedCount": len(details),
                "omittedRosterCount": max(0, total - len(roster)), "omittedDetailCount": max(0, total - len(details))}
    # This projection is deliberately private to candidate assembly: summary
    # counts must use every captured holding, not the 100/24 display caps.
    # ``normalize_review`` does not persist unknown top-level keys.
    summary_rows = [{key: row.get(key) for key in ("ticker", "thesisVerdict", "thesisPresent", "latestReviewPresent")}
                    for row in positions]
    return {"positionReviews": details, "positionRoster": roster, "coverage": coverage,
            "_summaryRows": summary_rows,
            "reportSelection": dict(inputs.get("reportSelection") or {}),
            "sharedExposures": shared_rows[:_MAX], "portfolioRisks": risks[:12], "checkpointReviews": checkpoint_reviews[:_MAX],
            "counterEvidence": [row for row in counter if isinstance(row, (dict, str))][:12], "uncertainties": uncertainties[:_MAX]}


def compare_previous(current: Mapping, previous: Mapping | None, *, current_basis: Mapping | None = None) -> tuple[list[dict], list[dict]]:
    if not previous or int(previous.get("sourceSchemaVersion") or 0) != 2:
        return [], ([{"code": "previous_review_not_comparable"}] if previous else [{"code": "first_review"}])
    changes, uncertainties = [], []
    def _index(rows: object, key_for):
        indexed: dict[str, Mapping] = {}
        invalid = False
        for row in rows or []:
            if not isinstance(row, Mapping):
                invalid = True
                continue
            key = key_for(row)
            if not key:
                invalid = True
                continue
            indexed[key] = row
        return indexed, invalid

    def _shared_key(row: Mapping) -> str:
        kind = _clean(row.get("type"), 32)
        value = _clean(row.get("stateKey") if kind == "narrative" else row.get("key"), 160)
        return value if kind == "narrative" else (f"{kind}:{value}" if kind in {"sector", "currency"} and value else "")

    def _risk_change_value(row: Mapping) -> dict:
        """Compare the same typed risk shape that reaches the public reader."""
        value = {"status": _clean(row.get("status"), 24)}
        concentration = row.get("concentration") if isinstance(row.get("concentration"), Mapping) else {}
        safe_concentration = {key: _weight(concentration.get(key)) for key in ("top1", "top3", "top5")
                              if _weight(concentration.get(key)) is not None}
        holdings = concentration.get("holdings")
        if isinstance(holdings, int) and 0 <= holdings <= 10000:
            safe_concentration["holdings"] = holdings
        if safe_concentration:
            value["concentration"] = safe_concentration
        contributions = []
        for item in row.get("riskContributions") or []:
            if not isinstance(item, Mapping):
                continue
            ticker = normalize_research_ticker(item.get("ticker"))
            weight = _weight(item.get("weight"))
            if ticker and weight is not None:
                contributions.append({"ticker": ticker, "weight": weight})
        if contributions:
            value["riskContributions"] = contributions[:16]
        return value

    specs = (
        ("verdict", "positionReviews", lambda row: _clean(row.get("ticker"), 40), lambda row: row.get("thesisVerdict")),
        ("checkpoint", "checkpointReviews", lambda row: _clean(row.get("id"), 160), lambda row: {key: row.get(key) for key in ("status", "lastVerdict", "direction", "dueBy")}),
        ("narrative", "sharedExposures", _shared_key, lambda row: {"tickers": list(row.get("tickers") or []), "momentum": _clean(row.get("momentum"), 32), "weight": _weight(row.get("weight"))}),
        ("risk", "portfolioRisks", lambda row: (f"{_clean(row.get('riskKey'), 120)}+{_clean(row.get('methodVersion'), 80)}" if _clean(row.get("riskKey"), 120) and _clean(row.get("methodVersion"), 80) else ""), _risk_change_value),
    )
    for label, source, key_for, value_for in specs:
        skip_risk_keys: set[str] = set()
        if label == "risk":
            previous_ref = ((previous.get("inputBasis") or {}).get("analytics") or {}).get("backtest")
            current_ref = ((current_basis or {}).get("analytics") or {}).get("backtest")
            fields = ("id", "methodVersion", "baseCurrency", "window", "start", "end")
            if (not isinstance(previous_ref, Mapping) or not isinstance(current_ref, Mapping)
                    or any(_clean(previous_ref.get(field), 120) != _clean(current_ref.get(field), 120) for field in fields)):
                uncertainties.append({"code": "previous_risk_not_comparable"})
                # This applies only to the saved correlation/volatility
                # reference. Concentration remains a local Portfolio risk and
                # is still comparable by its own key/method/projection.
                skip_risk_keys.update({"saved_backtest", "correlation_volatility"})
        old_rows, new_rows = previous.get(source), current.get(source)
        if label == "verdict":
            def roster_state(review: Mapping) -> tuple[str, list | None]:
                roster = review.get("positionRoster")
                coverage = review.get("coverage") if isinstance(review.get("coverage"), Mapping) else {}
                if not isinstance(roster, list):
                    return "absent", None
                total, included = coverage.get("totalPositionCount"), coverage.get("rosterIncludedCount")
                if isinstance(total, int) and isinstance(included, int) and total == included == len(roster):
                    return "complete", roster
                if isinstance(total, int) and isinstance(included, int) and total > included:
                    return "partial", roster
                return "unknown", roster
            old_state, old_roster = roster_state(previous)
            new_state, new_roster = roster_state(current)
            if "partial" in {old_state, new_state}:
                # A capped roster cannot prove that an absent ticker was
                # removed. Avoid turning cap rotation into a verdict change.
                uncertainties.append({"code": "previous_verdict_not_comparable"})
                continue
            if (old_state == "complete") != (new_state == "complete"):
                uncertainties.append({"code": "previous_verdict_not_comparable"})
                continue
            if old_state == new_state == "complete":
                old_rows, new_rows = old_roster, new_roster
        old, old_invalid = _index(old_rows, key_for)
        new, new_invalid = _index(new_rows, key_for)
        if skip_risk_keys:
            old = {key: row for key, row in old.items() if _clean(row.get("riskKey"), 120) not in skip_risk_keys}
            new = {key: row for key, row in new.items() if _clean(row.get("riskKey"), 120) not in skip_risk_keys}
        if old_invalid or new_invalid:
            uncertainties.append({"code": f"previous_{label}_not_comparable"})
            continue
        for item_key in sorted(set(old) | set(new)):
            if len(changes) >= _MAX:
                break
            if item_key not in old:
                changes.append({"kind": label, "key": item_key, "change": "added", "from": None, "to": value_for(new[item_key])})
            elif item_key not in new:
                changes.append({"kind": label, "key": item_key, "change": "removed", "from": value_for(old[item_key]), "to": None})
            elif value_for(old[item_key]) != value_for(new[item_key]):
                changes.append({"kind": label, "key": item_key, "change": "changed", "from": value_for(old[item_key]), "to": value_for(new[item_key])})
    return changes[:_MAX], uncertainties


def render_v2_markdown(review: Mapping) -> str:
    lines = [f"# 투자 리뷰 — {_clean(review.get('date'), 10)}", "", "## 저장 리뷰 요약", _clean(review.get("summary")) or "규칙 기반 입력을 확인하세요.", "", "## 우선 검토할 포지션"]
    rows = review.get("positionReviews") or []
    lines.extend([f"- **{_clean(row.get('ticker'), 24)}**: {_clean(row.get('thesisVerdict'), 48)}" for row in rows[:12] if isinstance(row, Mapping)] or ["- 현재 보유 포지션이 없습니다."])
    lines.extend(["", "## 공동 위험"])
    lines.extend([f"- {_clean(row.get('label') or row.get('key'), 160)}" for row in (review.get("sharedExposures") or [])[:12] if isinstance(row, Mapping)] or ["- 명시적으로 연결된 공동 노출이 없습니다."])
    lines.extend(["", "> 투자 리뷰는 개인 해석 보조이며 매수·매도 지시가 아닙니다."])
    return "\n".join(lines)


def build_rules_summary(structured: Mapping) -> str:
    """Describe the saved readiness projection without inventing a verdict.

    This runs only for a newly requested rules snapshot.  Read paths preserve
    the original saved summary verbatim, including older v2/legacy wording.
    """
    coverage = structured.get("coverage") if isinstance(structured.get("coverage"), Mapping) else {}
    total = coverage.get("totalPositionCount") if isinstance(coverage.get("totalPositionCount"), int) else 0
    detail = coverage.get("detailIncludedCount") if isinstance(coverage.get("detailIncludedCount"), int) else 0
    roster = structured.get("positionRoster") if isinstance(structured.get("positionRoster"), list) else []
    all_rows = structured.get("_summaryRows")
    rows = all_rows if isinstance(all_rows, list) else roster
    rows = [row for row in rows if isinstance(row, Mapping)]
    if total == 0:
        return "저장된 보유 포지션이 없어 규칙으로 점검할 대상이 없습니다."
    lead = f"저장된 보유 {total}개를 규칙 기준으로 집계했고, 우선 상세는 {detail}개입니다."
    parts = [lead]
    if len(rows) < total:
        parts.append(f"준비 상태 집계는 저장 최소 목록 {len(rows)}개 중 확인된 범위입니다.")
    thesis_known = [row for row in rows if isinstance(row.get("thesisPresent"), bool)]
    review_known = [row for row in thesis_known if row.get("thesisPresent") is False or isinstance(row.get("latestReviewPresent"), bool)]
    unknown_count = max(0, len(rows) - len(review_known))
    if not thesis_known:
        parts.append("Thesis와 최신 검토 준비 상태는 이 저장 입력에서 확인할 수 없습니다.")
    else:
        missing = sum(row.get("thesisPresent") is False for row in thesis_known)
        unreviewed = sum(row.get("thesisPresent") is True and row.get("latestReviewPresent") is False for row in review_known)
        insufficient = sum(row.get("thesisPresent") is True and row.get("latestReviewPresent") is True
                           and row.get("thesisVerdict") == "insufficient_evidence" for row in review_known)
        if missing:
            parts.append(f"Thesis 미작성 {missing}개가 있습니다.")
        if unreviewed:
            parts.append(f"저장된 최신 검토가 없는 Thesis {unreviewed}개가 있습니다.")
        if insufficient:
            parts.append(f"검토 후 근거가 부족한 종목 {insufficient}개가 있습니다.")
    if unknown_count:
        parts.append(f"준비 상태를 확인할 수 없는 종목 {unknown_count}개가 있습니다.")
    weak = sum(_clean(row.get("thesisVerdict"), 32) in {"weakened", "at_risk", "broken"} for row in rows)
    if weak:
        parts.append(f"약화 또는 이탈 주의 판정 {weak}개가 있습니다.")
    return " ".join(parts)


def review_path(review_dir: Path, date: str) -> Path:
    return review_dir / f"{date}.json"


def load_raw(review_dir: Path, date: str) -> dict | None:
    row = _load_json(review_path(review_dir, date), None)
    return row if isinstance(row, dict) else None


def find_previous(review_dir: Path, date: str) -> dict | None:
    if not review_dir.is_dir(): return None
    for path in sorted((item for item in review_dir.glob("*.json") if item.stem < date), reverse=True):
        row = load_raw(review_dir, path.stem)
        if row and normalize_review(row, date=path.stem).get("sourceSchemaVersion") == 2:
            return normalize_review(row, date=path.stem)
    return None


def list_history(review_dir: Path, *, limit: int = 60) -> list[dict]:
    if not review_dir.is_dir():
        return []
    rows = []
    for path in sorted(review_dir.glob("*.json"), reverse=True):
        raw = load_raw(review_dir, path.stem)
        if not raw:
            continue
        row = normalize_review(raw, date=path.stem)
        rows.append({"date": row.get("date"), "reviewRevision": row.get("reviewRevision"), "reviewState": row.get("reviewState"), "reviewedAt": row.get("reviewedAt"), "generatedAt": row.get("generatedAt"), "sourceSchemaVersion": row.get("sourceSchemaVersion")})
        if len(rows) >= limit: break
    return rows


def effective_freshness(stored: Mapping, current_basis: Mapping) -> tuple[str, dict, list[dict]]:
    review = normalize_review(dict(stored), date=_clean(stored.get("date"), 10))
    if review.get("sourceSchemaVersion") == 1:
        return "stale", {"status": "unknown", "dueCount": 0, "reasons": [{"code": "legacy_input_basis_unknown"}]}, [{"code": "legacy_input_basis_unknown"}]
    saved_fp = _clean((review.get("inputBasis") or {}).get("fingerprint"), 128)
    current_fp = _clean(current_basis.get("fingerprint"), 128)
    anchor = _clean(review.get("reviewedAt") or review.get("generatedAt"), 64)
    now = _now()
    due = [
        checkpoint for row in review.get("positionReviews") or [] if isinstance(row, Mapping)
        for checkpoint in (row.get("dueCheckpoints") or []) if isinstance(checkpoint, Mapping)
        and (due_at := _clean(checkpoint.get("dueAt"), 64)) and due_at <= now and due_at > anchor
    ]
    evaluated_at = _now()
    unresolved_ids: set[str] = set()
    checkpoint_snapshot = review.get("checkpointReviews") or []
    if not checkpoint_snapshot:
        # Earlier v2 rows had only non-terminal per-position due actions.
        # They are a bounded saved snapshot, not proof that nothing exists.
        checkpoint_snapshot = [
            {"id": item.get("id"), "status": "open", "dueBy": item.get("dueAt")}
            for row in review.get("positionReviews") or [] if isinstance(row, Mapping)
            for item in row.get("dueCheckpoints") or [] if isinstance(item, Mapping)
        ]
    for checkpoint in checkpoint_snapshot:
        if not isinstance(checkpoint, Mapping):
            continue
        identifier = _clean(checkpoint.get("id"), 160)
        status = _clean(checkpoint.get("status"), 32)
        due_at = _clean(checkpoint.get("dueBy"), 64)
        if identifier and status not in _TERMINAL_CHECKPOINT_STATUSES and _date_only_overdue(due_at, evaluated_at):
            unresolved_ids.add(identifier)
    freshness = {"status": "fresh" if (review.get("inputBasis") or {}).get("status") == "complete" else "partial", "dueCount": len(due), "reasons": [],
                 # This is a bounded stored-checkpoint snapshot, never a
                 # claim about omitted authority rows. Date-only values are
                 # evaluated at end of their Asia/Seoul calendar day.
                 "overdueUnresolvedCount": len(unresolved_ids), "evaluatedAt": evaluated_at}
    if not saved_fp or saved_fp != current_fp:
        return "stale", {**freshness, "status": "stale", "reasons": [{"code": "input_fingerprint_changed"}]}, [{"code": "input_fingerprint_changed"}]
    if due:
        return "due", freshness, []
    state = review.get("reviewState") if review.get("reviewState") in {"draft", "reviewed"} else "draft"
    return state, freshness, []


def build_candidate(data_dir: Path, review_dir: Path, date: str, *, include_portfolio=True, include_watchlist=False, include_obsidian=False) -> dict:
    existing = load_raw(review_dir, date)
    existing_view = normalize_review(existing, date=date) if existing else None
    previous = find_previous(review_dir, date)
    inputs = gather_inputs(data_dir, include_portfolio=include_portfolio, include_watchlist=include_watchlist, include_obsidian=include_obsidian, include_analytics=True)
    basis = build_input_basis(inputs, previous=previous)
    structured = build_structured_review(inputs, basis)
    changes, compare_uncertainties = compare_previous(structured, previous, current_basis=basis)
    revision = (existing_view.get("reviewRevision", 0) if existing_view and existing_view.get("sourceSchemaVersion") == 2 else 0) + 1
    summary = build_rules_summary(structured)
    # Candidate-only summary input is never part of the stored review shape.
    structured = {key: value for key, value in structured.items() if key != "_summaryRows"}
    candidate = empty_review(date)
    candidate.update({"schemaVersion": 2, "sourceSchemaVersion": 2, "date": date, "generatedAt": _now(), "mode": "rule", "reviewRevision": revision,
                      "reviewState": "draft", "reviewedAt": "", "previousReviewedAt": _clean((existing_view or {}).get("reviewedAt"), 64) or _clean((existing_view or {}).get("previousReviewedAt"), 64),
                      "inputBasis": basis, **structured, "changesSincePrevious": changes, "uncertainties": (structured["uncertainties"] + compare_uncertainties)[:_MAX],
                      "staleReasons": [], "summary": summary,
                      "baseReviewRevision": existing_view.get("reviewRevision", 0) if existing_view else 0})
    candidate["markdown"] = render_v2_markdown(candidate)
    return normalize_review(candidate, date=date)


def prepare_commit_candidate(data_dir: Path, review_dir: Path, candidate: Mapping, *, current_raw: Mapping | None = None) -> dict:
    """Apply review CAS/freshness rules without writing an authoritative file.

    The JSON-job stager calls this while holding the exact artifact lock, then
    promotes its staged file once.  Direct routes call it under the same lock
    and perform the one durable write themselves.
    """
    date = _clean(candidate.get("date"), 10)
    raw = current_raw if current_raw is not None else load_raw(review_dir, date)
    current = normalize_review(raw, date=date) if raw else None
    base = int(candidate.get("baseReviewRevision") or 0)
    current_revision = int((current or {}).get("reviewRevision") or 0)
    # A legacy v1 snapshot has no durable revision and is intentionally
    # replaceable only by the explicit refresh path (base=0).  It is not a
    # read-time migration, but its first v2 replacement is revision 1.
    if raw and (current is None or (current.get("sourceSchemaVersion") == 2 and current_revision != base)):
        raise ReviewRevisionConflict(current or empty_review(date))
    selection_version = _clean((candidate.get("inputBasis") or {}).get("reportSelectionVersion"), 16)
    latest_inputs = gather_inputs(data_dir, analytics_authority=(candidate.get("inputBasis") or {}).get("analytics"),
                                  report_selection_version=selection_version)
    latest_basis = build_input_basis(latest_inputs, previous=find_previous(review_dir, date))
    out = normalize_review(dict(candidate), date=date)
    out.pop("baseReviewRevision", None)
    out["reviewRevision"] = current_revision + 1
    if _clean((out.get("inputBasis") or {}).get("fingerprint"), 128) != _clean(latest_basis.get("fingerprint"), 128):
        out["reviewState"] = "stale"; out["stale"] = True
        out["staleReasons"] = [{"code": "input_changed_during_generation"}]
        out["freshness"] = {"status": "stale", "dueCount": 0, "reasons": out["staleReasons"]}
    return out


def finalize_and_commit(data_dir: Path, review_dir: Path, candidate: Mapping) -> dict:
    date = _clean(candidate.get("date"), 10)
    path = review_path(review_dir, date)
    with artifact_lock(path):
        out = prepare_commit_candidate(data_dir, review_dir, candidate)
        atomic_write(path, json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))
        return out


def mark_reviewed(data_dir: Path, review_dir: Path, date: str, expected_revision: object) -> dict:
    try: expected = int(expected_revision)
    except (TypeError, ValueError): raise ReviewRevisionConflict(empty_review(date))
    path = review_path(review_dir, date)
    with artifact_lock(path):
        raw = load_raw(review_dir, date)
        review = normalize_review(raw, date=date) if raw else empty_review(date)
        if not raw or review.get("sourceSchemaVersion") == 1 or review.get("reviewRevision") != expected:
            raise ReviewRevisionConflict(review)
        selection_version = _clean((review.get("inputBasis") or {}).get("reportSelectionVersion"), 16)
        basis = build_input_basis(gather_inputs(data_dir, analytics_authority=(review.get("inputBasis") or {}).get("analytics"),
                                                report_selection_version=selection_version), previous=find_previous(review_dir, date))
        effective, _freshness, _reasons = effective_freshness(review, basis)
        if effective == "stale": raise ReviewRevisionConflict(review, "investment_review_stale")
        review["reviewState"] = "reviewed"; review["reviewedAt"] = _now(); review["reviewRevision"] += 1; review["stale"] = False
        atomic_write(path, json.dumps(review, ensure_ascii=False, indent=2).encode("utf-8"))
        return review


def challenge_context(data_dir: Path, review_dir: Path, date: str, revision: object) -> dict:
    """Return the exact bounded review snapshot for a challenge turn.

    Never fall back to generic Portfolio context: a same-day refresh means the
    user must consciously reopen the action against the new revision.
    """
    if _REVIEW_DATE_RE.fullmatch(str(date or "")) is None:
        return {"dataGaps": [{"code": "review_changed_reopen_challenge"}], "layer": "hypothesis", "review": None}
    try:
        expected = int(revision)
    except (TypeError, ValueError):
        expected = -1
    raw = load_raw(review_dir, date)
    review = normalize_review(raw, date=date) if raw else None
    if not review or review.get("sourceSchemaVersion") != 2 or review.get("reviewRevision") != expected:
        return {"dataGaps": [{"code": "review_changed_reopen_challenge"}], "layer": "hypothesis", "review": None}
    coverage = review.get("coverage") if isinstance(review.get("coverage"), Mapping) else {}
    roster = list(review.get("positionRoster") or [])
    if not roster:
        # Older v2 snapshots never stored a roster. Use only their saved
        # detail as a bounded minimum projection; never read today's holdings.
        roster = [{key: row.get(key) for key in ("ticker", "thesisVerdict", "thesisPresent", "latestReviewPresent") if key in row}
                  for row in review.get("positionReviews") or [] if isinstance(row, Mapping)]
        if roster:
            coverage = {"rosterIncludedCount": len(roster), "detailIncludedCount": len(review.get("positionReviews") or [])}
    raw_details = list(review.get("positionReviews") or [])
    def compact_detail(row: Mapping) -> dict:
        out = {key: row.get(key) for key in ("ticker", "name", "thesisVerdict", "thesisPresent", "latestReviewPresent") if key in row}
        counters = []
        for item in row.get("counterEvidence") or []:
            title = _clean(item.get("title") if isinstance(item, Mapping) else item, 240)
            if title:
                counters.append({"title": title})
            if len(counters) >= 1:
                break
        if counters:
            out["counterEvidence"] = counters
        due = []
        for item in row.get("dueCheckpoints") or []:
            if not isinstance(item, Mapping):
                continue
            identifier = _clean(item.get("id"), 160)
            if identifier:
                due.append({"id": identifier, "label": _clean(item.get("label"), 120), "dueAt": _clean(item.get("dueAt"), 32)})
            if len(due) >= 2:
                break
        if due:
            out["dueCheckpoints"] = due
        refs = []
        for item in row.get("canonicalReferences") or []:
            if not isinstance(item, Mapping):
                continue
            kind, identifier = _clean(item.get("kind"), 32), _clean(item.get("id"), 160)
            if kind and identifier:
                refs.append({"kind": kind, "reportKind": _clean(item.get("reportKind"), 32), "id": identifier,
                             "title": _clean(item.get("title"), 120), "relatedReason": _clean(item.get("relatedReason"), 120)})
            if len(refs) >= 2:
                break
        if refs:
            out["canonicalReferences"] = refs
        return out
    detail_rows = [compact_detail(row) for row in raw_details if isinstance(row, Mapping)][:12]
    # Details were priority-selected when the snapshot was generated; preserve
    # that stored order rather than introducing a second ordering contract.
    detail_rows = detail_rows[:12]
    gaps = []
    if int(coverage.get("omittedRosterCount") or 0) > 0:
        gaps.append({"code": "position_roster_truncated", "count": int(coverage.get("omittedRosterCount") or 0)})
    if int(coverage.get("omittedDetailCount") or 0) > 0:
        gaps.append({"code": "checkpoint_snapshot_limited", "count": int(coverage.get("omittedDetailCount") or 0)})
    compacted = len(raw_details) > len(detail_rows)
    compacted = compacted or any(
        len(row.get("counterEvidence") or []) > 1
        or len(row.get("canonicalReferences") or []) > 2
        or len(row.get("dueCheckpoints") or []) > 2
        for row in raw_details if isinstance(row, Mapping)
    )
    if compacted:
        gaps.append({"code": "context_detail_truncated", "reason": "정확한 저장 리뷰의 roster와 핵심 반증을 보존하기 위해 Agent 상세 입력을 제한했습니다."})
    core_counter, seen_counter = [], set()
    # Position details are already stored in review-priority order. Preserve a
    # late broken holding's unique counter before the legacy global aggregate
    # (which was historically capped in raw holdings order).
    priority_sources = [(row.get("ticker"), row.get("counterEvidence") or []) for row in raw_details if isinstance(row, Mapping)]
    priority_sources.append(("", review.get("counterEvidence") or []))
    for ticker, source in priority_sources:
        for item in source:
            title = _clean(item.get("title") if isinstance(item, Mapping) else item, 240)
            if title and title not in seen_counter:
                seen_counter.add(title)
                entry = {"title": title}
                if _clean(ticker, 24):
                    entry["ticker"] = _clean(ticker, 24)
                core_counter.append(entry)
            if len(core_counter) >= 12:
                break
        if len(core_counter) >= 12:
            break
    return {"investmentReview": {
        "date": review.get("date"), "reviewRevision": review.get("reviewRevision"),
        "reviewState": review.get("reviewState"), "summary": review.get("summary"),
        "positionRoster": roster[:100], "coverage": coverage,
        "positionReviews": detail_rows,
        "sharedExposures": (review.get("sharedExposures") or [])[:6],
        "portfolioRisks": (review.get("portfolioRisks") or [])[:6],
        "counterEvidence": core_counter,
        "uncertainties": (review.get("uncertainties") or [])[:12],
        "changesSincePrevious": (review.get("changesSincePrevious") or [])[:12],
    }, "dataGaps": gaps, "layer": "hypothesis", "reuseAsEvidence": False}
