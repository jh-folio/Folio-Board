from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from features.common.canonical_json import JsonValue, canonical_json_bytes
from features.common.sqlite_receipts import (
    ReceiptExpectation,
    ReceiptRecord,
    ReceiptVerificationError,
    verify_receipt_set,
    write_receipt,
)
from features.thesis_tracking import store


@dataclass(frozen=True, slots=True)
class PreparedThesisDelta:
    ticker: str
    delta_id: str
    delta: dict[str, JsonValue]
    job_id: str
    operation_id: str
    base_hash: str | None
    target_hash: str
    terminal_projection: dict[str, JsonValue]
    created_at: str


@dataclass(frozen=True, slots=True)
class CommittedThesisDelta:
    delta_id: str
    target_hash: str
    terminal_projection: dict[str, JsonValue]


def _hash(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _logical_row(connection: sqlite3.Connection, delta_id: str) -> dict[str, JsonValue] | None:
    row = connection.execute("SELECT * FROM thesis_delta WHERE delta_id=?", (delta_id,)).fetchone()
    if row is None:
        return None
    logical: dict[str, JsonValue] = {}
    for key in row.keys():
        value = row[key]
        if key in {"analysis_json", "evidence_json"}:
            try:
                logical[key.removesuffix("_json")] = json.loads(value)
            except (json.JSONDecodeError, TypeError) as error:
                raise ReceiptVerificationError(code="thesis_row_json_invalid") from error
        elif value is None or isinstance(value, str | int | float | bool):
            logical[key] = value
        else:
            raise ReceiptVerificationError(code="thesis_row_invalid")
    return logical


def _row_hash(connection: sqlite3.Connection, delta_id: str) -> str | None:
    row = _logical_row(connection, delta_id)
    return _hash(row) if row is not None else None


def prepare_thesis_delta(
    connection: sqlite3.Connection,
    *,
    ticker: str,
    delta: Mapping[str, JsonValue],
    job_id: str,
    operation_id: str,
    terminal_projection: Mapping[str, JsonValue],
    created_at: str,
) -> PreparedThesisDelta:
    delta_id = str(delta.get("deltaId") or "")
    if not delta_id:
        raise ReceiptVerificationError(code="delta_id_required")
    base_hash = _row_hash(connection, delta_id)
    clone = sqlite3.connect(":memory:")
    clone.row_factory = sqlite3.Row
    try:
        connection.backup(clone)
        store.init_db(clone)
        store.save_delta(clone, ticker, dict(delta), commit=False, created_at=created_at)
        target_hash = _row_hash(clone, delta_id)
    finally:
        clone.close()
    if target_hash is None:
        raise ReceiptVerificationError(code="thesis_target_missing")
    return PreparedThesisDelta(
        ticker=ticker.strip().upper(),
        delta_id=delta_id,
        delta=dict(delta),
        job_id=job_id,
        operation_id=operation_id,
        base_hash=base_hash,
        target_hash=target_hash,
        terminal_projection=dict(terminal_projection),
        created_at=created_at,
    )


def commit_thesis_delta(
    connection: sqlite3.Connection,
    prepared: PreparedThesisDelta,
) -> CommittedThesisDelta:
    try:
        connection.execute("BEGIN IMMEDIATE")
        if _row_hash(connection, prepared.delta_id) != prepared.base_hash:
            raise ReceiptVerificationError(code="thesis_base_hash_mismatch")
        store.save_delta(
            connection,
            prepared.ticker,
            prepared.delta,
            commit=False,
            created_at=prepared.created_at,
        )
        # A generated Delta belongs to the exact reason revision that existed
        # when it was committed. A background job is not a completed user review.
        from features.thesis_tracking import reason_history as RH
        from features.thesis_tracking import reason_review as RR
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reason_revision'").fetchone():
            revision = RH.latest(connection, prepared.ticker)
            if revision:
                RR.record(connection, prepared.ticker, revision["revisionId"],
                          source="delta_generation", outcome="evidence_gap" if prepared.delta.get("verdict") == "insufficient_evidence" else "reviewed",
                          checked_scope=["저장된 Delta의 자료 범위"], delta_id=prepared.delta_id,
                          event_id=f"delta:{prepared.delta_id}")
        if _row_hash(connection, prepared.delta_id) != prepared.target_hash:
            raise ReceiptVerificationError(code="thesis_target_hash_mismatch")
        write_receipt(
            connection,
            ReceiptRecord(
                operation_id=prepared.operation_id,
                job_id=prepared.job_id,
                artifact_type="thesis_delta",
                artifact_id=prepared.delta_id,
                result_hash=prepared.target_hash,
                terminal_projection=prepared.terminal_projection,
                created_at=prepared.created_at,
            ),
        )
        connection.commit()
    except (sqlite3.Error, ReceiptVerificationError):
        connection.rollback()
        raise
    return CommittedThesisDelta(
        delta_id=prepared.delta_id,
        target_hash=prepared.target_hash,
        terminal_projection=prepared.terminal_projection,
    )


def recover_thesis_delta(
    connection: sqlite3.Connection,
    prepared: PreparedThesisDelta,
) -> dict[str, JsonValue]:
    if _row_hash(connection, prepared.delta_id) != prepared.target_hash:
        raise ReceiptVerificationError(code="thesis_recovery_hash_mismatch")
    return verify_receipt_set(
        connection,
        prepared.job_id,
        prepared.operation_id,
        (ReceiptExpectation("thesis_delta", prepared.delta_id, prepared.target_hash),),
    )


def recover_thesis_receipt(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    operation_id: str,
    delta_id: str,
    target_hash: str,
) -> dict[str, JsonValue]:
    if _row_hash(connection, delta_id) != target_hash:
        raise ReceiptVerificationError(code="thesis_recovery_hash_mismatch")
    return verify_receipt_set(
        connection,
        job_id,
        operation_id,
        (ReceiptExpectation("thesis_delta", delta_id, target_hash),),
    )


__all__ = [
    "CommittedThesisDelta",
    "PreparedThesisDelta",
    "commit_thesis_delta",
    "prepare_thesis_delta",
    "recover_thesis_delta",
    "recover_thesis_receipt",
]
