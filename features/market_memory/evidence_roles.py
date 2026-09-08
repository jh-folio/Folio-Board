"""Durable evidence-role classification for market narrative states.

The model is allowed to label a bounded state/evidence pair only.  This module
owns the pair identity, validation and SQLite persistence so API and Agent CLI
writeback cannot drift apart.  It deliberately does not create a third
``pending`` role: in an LLM configuration an absent current durable row is
pending and is omitted from the Regime projection.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Iterable

from features.common.jobs import current_diagnostic_recorder, diagnostic_stage_failure
from features.common.diagnostics.runtime import _trusted_frame
from features.common.diagnostics.schema import safe_failure
from features.common.diagnostics.support import remember_failure, remembered_failure
from features.market_memory.memory import connect, init_db, normalize


CLASSIFIER_VERSION = "narrative-role-v1"
ROLE_CHOICES = frozenset({"supporting", "challenging", "neutral"})
ROLE_SOURCES = frozenset({"llm", "rule"})
MAX_ROLE_CANDIDATES = 50
ROLE_WINDOW_DAYS = 90
_RETRY_HOURS = (24, 72, 168)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_date(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc)
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _date_text(value: object) -> str:
    parsed = _parse_date(value)
    return parsed.date().isoformat() if parsed else ""


def _canonical_text(value: object) -> str:
    """NFKC + whitespace collapse used by the versioned input hash."""
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def basis_payload(state: dict, memory: dict) -> dict[str, dict[str, str]]:
    """The exact semantic inputs to a role classification.

    Keep this intentionally narrow.  In particular, ``netEffect`` is an
    internal slug and must neither change a role nor invalidate one.
    """
    def value(row: dict, snake: str, camel: str = "") -> str:
        return _canonical_text(row.get(snake) if snake in row else row.get(camel or snake))

    # Keep the two ``summary`` values structurally distinct.  This is the
    # one source of truth both for hashing and for the model-facing candidate;
    # a flat payload would silently lose one of them.
    return {
        "state": {
            "stateKey": value(state, "state_key", "stateKey"),
            "stateLabel": value(state, "state_label", "stateLabel"),
            "story": value(state, "story"),
            "storyFamily": value(state, "story_family", "storyFamily"),
            "summary": value(state, "summary"),
            "rationale": value(state, "rationale"),
            "bias": value(state, "bias"),
        },
        "memory": {
            "memoryId": value(memory, "memory_id", "memoryId"),
            "date": value(memory, "date"),
            "title": value(memory, "title"),
            "summary": value(memory, "summary"),
            "storyThesis": value(memory, "story_thesis", "storyThesis"),
        },
    }


def basis_hash(state: dict, memory: dict) -> str:
    encoded = json.dumps(basis_payload(state, memory), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _latest_current_states(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT state.*, ROW_NUMBER() OVER (
                PARTITION BY state_key ORDER BY updated_at DESC, state_id DESC
            ) AS row_number
            FROM market_narrative_states AS state
            WHERE status IN ('active', 'watch') AND TRIM(state_key) != ''
        ) WHERE row_number = 1
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _recent_memories(conn: sqlite3.Connection, *, as_of: str) -> list[dict]:
    anchor = _parse_date(as_of) or dt.datetime.now(dt.timezone.utc)
    cutoff = (anchor - dt.timedelta(days=ROLE_WINDOW_DAYS)).date().isoformat()
    today = anchor.date().isoformat()
    rows = conn.execute(
        """
        SELECT * FROM market_memory
        WHERE date >= ? AND date <= ?
        ORDER BY date DESC, memory_id ASC
        """,
        (cutoff, today),
    ).fetchall()
    return [dict(row) for row in rows]


def _matches(memory: dict, state: dict) -> tuple[bool, list[str]]:
    # The matcher remains owned by the Regime layer.  Import lazily to avoid a
    # module cycle while making candidate selection and projection use exactly
    # the same relation.
    from features.market_memory.regime_v2 import _memory_matches_state

    return _memory_matches_state(memory, state)


def _current_role(conn: sqlite3.Connection, state_key: str, memory_id: str, current_hash: str):
    row = conn.execute(
        """
        SELECT * FROM market_evidence_roles
        WHERE state_key=? AND memory_id=? AND basis_hash=? AND classifier_version=?
        """,
        (state_key, memory_id, current_hash, CLASSIFIER_VERSION),
    ).fetchone()
    return dict(row) if row else None


def _role_candidate(state: dict, memory: dict, matched_terms: list[str], *, upgrade: bool = False) -> dict:
    basis = basis_payload(state, memory)
    state_basis = basis["state"]
    memory_basis = basis["memory"]
    return {
        "stateKey": state_basis["stateKey"],
        "stateId": str(state.get("state_id") or ""),
        "memoryId": memory_basis["memoryId"],
        "evidenceDate": memory_basis["date"],
        "basis": basis,
        "basisHash": basis_hash(state, memory),
        "matchedTerms": list(matched_terms or [])[:8],
        "upgrade": bool(upgrade),
        # Persistence must re-read durable data, but retaining these here lets
        # rule fallback use the same classifier when nothing changed.
        "_state": state,
        "_memory": memory,
    }


def build_role_candidates(
    db_path: str | Path,
    *,
    as_of: str = "",
    limit: int = MAX_ROLE_CANDIDATES,
) -> dict:
    """Select at most one deterministic role batch.

    A current rule row is not primary backlog: it can be upgraded only after
    all missing/stale pairs are cleared and only at its retry time.
    """
    now = as_of or _now()
    conn = connect(db_path)
    init_db(conn)
    try:
        primary: list[dict] = []
        upgrades: list[dict] = []
        for state in _latest_current_states(conn):
            for memory in _recent_memories(conn, as_of=now):
                matches, terms = _matches(memory, state)
                if not matches:
                    continue
                candidate = _role_candidate(state, memory, terms)
                durable = _current_role(conn, candidate["stateKey"], candidate["memoryId"], candidate["basisHash"])
                if durable is None:
                    primary.append(candidate)
                elif durable.get("role_source") == "rule":
                    retry = _parse_date(durable.get("next_llm_retry_at"))
                    if retry is None or retry <= (_parse_date(now) or dt.datetime.now(dt.timezone.utc)):
                        candidate["upgrade"] = True
                        upgrades.append(candidate)
        key = lambda item: (-int((_parse_date(item["evidenceDate"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)).timestamp()), item["stateKey"], item["memoryId"])
        # datetime.min.timestamp can be platform-dependent; invalid dates are
        # excluded above in normal data but retain a deterministic fallback.
        def order(item: dict) -> tuple[str, str, str]:
            return (str(item.get("evidenceDate") or ""), str(item.get("stateKey") or ""), str(item.get("memoryId") or ""))
        primary.sort(key=order, reverse=True)
        # reverse=True would reverse tie keys too, so apply the exact required
        # date DESC / state_key ASC / memory_id ASC ordering explicitly.
        primary.sort(key=lambda item: (str(item.get("stateKey") or ""), str(item.get("memoryId") or "")))
        primary.sort(key=lambda item: str(item.get("evidenceDate") or ""), reverse=True)
        upgrades.sort(key=lambda item: (str(item.get("stateKey") or ""), str(item.get("memoryId") or "")))
        upgrades.sort(key=lambda item: str(item.get("evidenceDate") or ""), reverse=True)
        selected_source = primary if primary else upgrades
        selected = selected_source[: max(0, min(int(limit or MAX_ROLE_CANDIDATES), MAX_ROLE_CANDIDATES))]
        return {
            "asOf": now,
            "candidateCount": len(primary) if primary else len(upgrades),
            "primaryCount": len(primary),
            "selected": selected,
            "selection": "primary" if primary else "upgrade",
        }
    finally:
        conn.close()


def safe_build_role_candidates(
    db_path: str | Path,
    *,
    as_of: str = "",
    limit: int = MAX_ROLE_CANDIDATES,
) -> dict:
    """Never let optional role selection abort its parent generation/job."""
    try:
        return build_role_candidates(db_path, as_of=as_of, limit=limit)
    except Exception as error:
        # No raw DB/matcher exception is carried into model context or a job
        # result.  Finalization recognizes this marker and does not retry the
        # failed selection operation.
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="context", boundary="generic",
        )
        return {
            "asOf": as_of or _now(),
            "candidateCount": 0,
            "primaryCount": 0,
            "selected": [],
            "selection": "primary",
            "roleFailureCode": "role_persistence_failed",
        }


def rebuild_selected_role_candidates(db_path: str | Path, selection: dict) -> dict:
    """Re-read only the pairs that were in an already-issued batch.

    A market-memory write can create additional matching evidence before its
    piggybacked role payload is finalized.  Those new pairs were never shown
    to the model, so they must remain ordinary primary backlog rather than
    being pulled into this call's fallback batch.
    """
    now = str(selection.get("asOf") or _now())
    anchor = _parse_date(now) or dt.datetime.now(dt.timezone.utc)
    cutoff = (anchor - dt.timedelta(days=ROLE_WINDOW_DAYS)).date().isoformat()
    today = anchor.date().isoformat()
    conn = connect(db_path)
    init_db(conn)
    try:
        current: list[dict] = []
        for original in list(selection.get("selected") or [])[:MAX_ROLE_CANDIDATES]:
            state_key = str(original.get("stateKey") or "")
            memory_id = str(original.get("memoryId") or "")
            if not state_key or not memory_id:
                continue
            fresh = _fresh_candidate(conn, state_key, memory_id)
            if fresh is None:
                continue
            state, memory, terms = fresh
            date = str(memory.get("date") or "")
            if not (cutoff <= date <= today):
                continue
            current.append(_role_candidate(state, memory, terms, upgrade=bool(original.get("upgrade"))))
        # The summary remains the issued batch's start-of-call meaning.  Only
        # ``remainingBacklogCount`` is computed against the post-write DB.
        return {
            "asOf": now,
            "candidateCount": int(selection.get("candidateCount") or 0),
            "primaryCount": int(selection.get("primaryCount") or 0),
            "selected": current,
            "selection": str(selection.get("selection") or "primary"),
        }
    finally:
        conn.close()


def role_candidates_for_context(candidates: Iterable[dict]) -> list[dict]:
    """The LLM sees semantic input, never the internally owned hash/version."""
    out = []
    for candidate in list(candidates)[:MAX_ROLE_CANDIDATES]:
        basis = candidate.get("basis") or basis_payload(candidate.get("_state") or {}, candidate.get("_memory") or {})
        state = dict(basis.get("state") or {})
        memory = dict(basis.get("memory") or {})
        out.append({
            # Flat identifiers make the required output pair unambiguous;
            # every classifier input itself stays in the exact nested SSoT.
            "stateKey": state.get("stateKey", ""),
            "memoryId": memory.get("memoryId", ""),
            "state": state,
            "memory": memory,
        })
    return out


def _retry_at(now: str, count: int) -> str:
    anchor = _parse_date(now) or dt.datetime.now(dt.timezone.utc)
    hours = _RETRY_HOURS[min(max(0, count - 1), len(_RETRY_HOURS) - 1)]
    return (anchor + dt.timedelta(hours=hours)).isoformat()


def _safe_error_code(value: object) -> str:
    text = "".join(ch for ch in str(value or "") if ch.isascii() and (ch.isalnum() or ch in {"_", "-"}))
    return text[:48] or "llm_failed"


def _fresh_candidate(conn: sqlite3.Connection, state_key: str, memory_id: str) -> tuple[dict, dict, list[str]] | None:
    state_row = conn.execute(
        """
        SELECT * FROM market_narrative_states
        WHERE state_key=? AND status IN ('active','watch')
        ORDER BY updated_at DESC, state_id DESC LIMIT 1
        """,
        (state_key,),
    ).fetchone()
    memory_row = conn.execute("SELECT * FROM market_memory WHERE memory_id=?", (memory_id,)).fetchone()
    if not state_row or not memory_row:
        return None
    state, memory = dict(state_row), dict(memory_row)
    matches, terms = _matches(memory, state)
    if not matches:
        return None
    return state, memory, terms


def _rule_role(state: dict, memory: dict) -> str:
    from features.market_memory.regime_v2 import classify_evidence

    text = " ".join(str(memory.get(key) or "") for key in ("title", "summary", "story_thesis", "story_checkpoint"))
    return classify_evidence(text, state)


def _persist_outcomes(
    db_path: str | Path,
    outcomes: Iterable[dict],
    *,
    now: str,
) -> tuple[int, int]:
    """Atomically write a role batch after re-reading every semantic input."""
    conn = connect(db_path)
    init_db(conn)
    persisted = 0
    rejected = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for outcome in outcomes:
            fresh = _fresh_candidate(conn, outcome["stateKey"], outcome["memoryId"])
            if fresh is None:
                rejected += 1
                continue
            state, memory, _terms = fresh
            current_hash = basis_hash(state, memory)
            if current_hash != outcome["basisHash"]:
                rejected += 1
                continue
            role = str(outcome.get("role") or "")
            source = str(outcome.get("source") or "")
            if role not in ROLE_CHOICES or source not in ROLE_SOURCES:
                rejected += 1
                continue
            prior = conn.execute(
                "SELECT basis_hash, classifier_version, llm_failure_count FROM market_evidence_roles WHERE state_key=? AND memory_id=?",
                (outcome["stateKey"], outcome["memoryId"]),
            ).fetchone()
            # A changed semantic basis is a new classification problem.  Do
            # not inherit an old pair's exponential retry delay.
            prior_matches = bool(prior) and (
                str(prior["basis_hash"] or "") == current_hash
                and str(prior["classifier_version"] or "") == CLASSIFIER_VERSION
            )
            prior_count = int(prior["llm_failure_count"] or 0) if prior_matches else 0
            failure_increment = bool(outcome.get("failureIncrement"))
            failure_count = prior_count + 1 if failure_increment else (0 if source == "llm" else prior_count)
            next_retry = ""
            error_code = ""
            if source == "rule":
                # A provider budget/quota stop is not another failed model
                # attempt.  Preserve its existing index, but retry this
                # piggybacked work at the fixed first 24h cadence.
                retry_index = 1 if outcome.get("budgetExhausted") else (failure_count or 1)
                next_retry = _retry_at(now, retry_index)
                error_code = _safe_error_code(outcome.get("failureCode"))
            conn.execute(
                """
                INSERT INTO market_evidence_roles (
                    state_key, memory_id, basis_hash, classifier_version, role, role_source,
                    classified_at, llm_failure_count, last_llm_attempt_at, next_llm_retry_at, last_error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_key, memory_id) DO UPDATE SET
                    basis_hash=excluded.basis_hash,
                    classifier_version=excluded.classifier_version,
                    role=excluded.role,
                    role_source=excluded.role_source,
                    classified_at=excluded.classified_at,
                    llm_failure_count=excluded.llm_failure_count,
                    last_llm_attempt_at=excluded.last_llm_attempt_at,
                    next_llm_retry_at=excluded.next_llm_retry_at,
                    last_error_code=excluded.last_error_code
                """,
                (
                    outcome["stateKey"], outcome["memoryId"], current_hash, CLASSIFIER_VERSION,
                    role, source, now, failure_count,
                    now if outcome.get("attempted", True) else "", next_retry, error_code,
                ),
            )
            outcome["_persisted"] = True
            persisted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return persisted, rejected


def _remaining_primary(db_path: str | Path, *, as_of: str) -> int:
    return int(build_role_candidates(db_path, as_of=as_of, limit=0).get("primaryCount") or 0)


def _bounded_remaining(selection: dict) -> int:
    """Safe backlog value when the role database itself cannot be read."""
    try:
        return max(0, int(selection.get("primaryCount") or 0))
    except (TypeError, ValueError):
        return 0


def _safe_remaining_primary(db_path: str | Path, selection: dict, *, as_of: str) -> tuple[int, bool]:
    try:
        return _remaining_primary(db_path, as_of=as_of), False
    except sqlite3.Error as error:
        # A locked/broken role DB must not turn a successfully committed
        # narrative/snapshot job into a failed parent job.
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="commit", boundary="save",
        )
        return _bounded_remaining(selection), True


def _record_role_transaction_failure(error: sqlite3.Error) -> None:
    """Record the one known role-write boundary without retaining SQL detail.

    ``sqlite3.Error`` elsewhere is deliberately not a blanket save failure:
    this helper is called only for ``_persist_outcomes``' transaction.  The
    original exception supplies a verified source frame, while the persisted
    model contains only closed diagnostic codes.
    """
    recorder = current_diagnostic_recorder()
    if recorder is None:
        return
    try:
        failure = remembered_failure(error)
        if failure is None:
            failure = safe_failure(
                stage_code="commit",
                reason_code="save_failed",
                exception_code="other",
                confirmation="observed",
                frames=_trusted_frame(error),
            )
        error_id = recorder.failure(failure)
        if error_id is not None:
            stored = next((item for item in recorder.record.errors if item.error_id == error_id), None)
            if stored is not None:
                remember_failure(error, stored)
    except Exception:
        return


def classify_role_payload(
    db_path: str | Path,
    selection: dict,
    payload: dict | None,
    *,
    failure_code: str = "",
    budget_exhausted: bool = False,
    force_rule_pairs: Iterable[tuple[str, str]] = (),
) -> dict:
    """Validate output item-by-item, persist valid LLM rows and rule-fallback rest."""
    candidates = list(selection.get("selected") or [])[:MAX_ROLE_CANDIDATES]
    forced_rules = {(str(state_key), str(memory_id)) for state_key, memory_id in force_rule_pairs}
    now = str(selection.get("asOf") or _now())
    summary = {
        "candidateCount": int(selection.get("candidateCount") or 0),
        "classifiedCount": 0,
        "ruleFallbackCount": 0,
        "invalidCount": 0,
        "remainingBacklogCount": 0,
    }
    if not candidates:
        summary["remainingBacklogCount"], read_failed = _safe_remaining_primary(db_path, selection, as_of=now)
        if read_failed:
            summary["failureCode"] = "role_persistence_failed"
        return summary

    supplied = payload.get("evidenceRoles") if isinstance(payload, dict) else None
    whole_failure = bool(failure_code) or not isinstance(supplied, list)
    accepted: dict[tuple[str, str], str] = {}
    invalid = 0
    if not whole_failure:
        candidate_by_pair = {(item["stateKey"], item["memoryId"]): item for item in candidates}
        seen: set[tuple[str, str]] = set()
        for raw in supplied:
            if not isinstance(raw, dict):
                invalid += 1
                continue
            pair = (str(raw.get("stateKey") or ""), str(raw.get("memoryId") or ""))
            candidate = candidate_by_pair.get(pair)
            role = str(raw.get("role") or "")
            # basisHash/classifierVersion are deliberately not part of the
            # model contract.  Pair identity is checked against our internal
            # selection; untrusted extra fields must not alter acceptance.
            if candidate is None or pair in seen or pair in forced_rules or role not in ROLE_CHOICES:
                invalid += 1
                continue
            seen.add(pair)
            accepted[pair] = role
        invalid += len([item for item in candidates if (item["stateKey"], item["memoryId"]) not in forced_rules]) - len(accepted)
    else:
        failure_code = failure_code or "invalid_output"
        invalid = 0 if budget_exhausted else len(candidates)

    outcomes: list[dict] = []
    for candidate in candidates:
        pair = (candidate["stateKey"], candidate["memoryId"])
        if pair in accepted:
            outcomes.append({**candidate, "role": accepted[pair], "source": "llm", "attempted": True})
        else:
            state, memory = candidate["_state"], candidate["_memory"]
            outcomes.append({
                **candidate,
                "role": _rule_role(state, memory),
                "source": "rule",
                "attempted": pair not in forced_rules,
                "failureCode": failure_code or ("basis_reconciled" if pair in forced_rules else "invalid_output"),
                "failureIncrement": pair not in forced_rules and not budget_exhausted,
                "budgetExhausted": budget_exhausted,
            })
    try:
        persisted, rejected = _persist_outcomes(db_path, outcomes, now=now)
    except sqlite3.Error as error:
        # Role persistence must not unwind the narrative/snapshot job.  No raw
        # SQLite message is stored or returned.  Do not re-query this DB here:
        # an OperationalError (for example ``locked``) can affect both writes
        # and the immediately following backlog read.
        _record_role_transaction_failure(error)
        summary["failureCode"] = "role_persistence_failed"
        summary["remainingBacklogCount"] = _bounded_remaining(selection)
        return summary
    summary["classifiedCount"] = sum(
        1 for item in outcomes if item["source"] == "llm" and item.get("_persisted")
    )
    summary["ruleFallbackCount"] = sum(
        1 for item in outcomes if item["source"] == "rule" and item.get("_persisted")
    )
    summary["invalidCount"] = invalid + rejected
    summary["remainingBacklogCount"], read_failed = _safe_remaining_primary(db_path, selection, as_of=now)
    if read_failed:
        summary["failureCode"] = "role_persistence_failed"
    if failure_code:
        summary["failureCode"] = _safe_error_code(failure_code)
    return summary


def current_role(conn: sqlite3.Connection, state: dict, memory: dict) -> dict | None:
    state_key = str(state.get("state_key") or state.get("stateKey") or "")
    memory_id = str(memory.get("memory_id") or memory.get("memoryId") or "")
    if not state_key or not memory_id:
        return None
    return _current_role(conn, state_key, memory_id, basis_hash(state, memory))


def pending_pairs_for_state(conn: sqlite3.Connection, state: dict, *, as_of: str = "") -> list[dict]:
    """Pairs absent from the current durable role projection (LLM mode only)."""
    now = as_of or _now()
    out: list[dict] = []
    for memory in _recent_memories(conn, as_of=now):
        matches, terms = _matches(memory, state)
        if matches and current_role(conn, state, memory) is None:
            out.append({
                "memoryId": str(memory.get("memory_id") or ""),
                "evidenceDate": str(memory.get("date") or ""),
                "title": str(memory.get("title") or ""),
                "summary": str(memory.get("summary") or ""),
                "matchedTerms": terms,
            })
    return out


def is_llm_mode(role_mode: str = "auto") -> bool:
    mode = str(role_mode or "auto").lower()
    if mode == "llm":
        return True
    if mode == "rules":
        return False
    try:
        from features.llm_settings.client import default_generation_mode

        return default_generation_mode() in {"llm", "llm_cli"}
    except Exception:
        return False


__all__ = [
    "CLASSIFIER_VERSION", "MAX_ROLE_CANDIDATES", "ROLE_CHOICES", "basis_hash", "basis_payload",
    "build_role_candidates", "safe_build_role_candidates", "rebuild_selected_role_candidates", "classify_role_payload", "current_role", "is_llm_mode",
    "pending_pairs_for_state", "role_candidates_for_context",
]
