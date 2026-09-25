"""Additive Thesis review-state persistence and deterministic date rules."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field

from features.investment_notes.intelligence_schema import (
    CheckpointState,
    Freshness,
    HypothesisCheckpoint,
)
from features.common.research_schema.tracked_checkpoints import checkpoint_labels
from features.thesis_tracking import model as thesis_model


UtcZ = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"),
]
Ticker = Annotated[str, Field(pattern=r"^[A-Z0-9-]{1,12}$")]
DeltaId = Annotated[str, Field(pattern=r"^[A-Za-z0-9:._-]{1,200}$")]
_CYCLE_DAYS = {
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
}


class ReviewStateConflictError(Exception):
    pass


class ReviewState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: Ticker
    lastReviewedAt: UtcZ | None = None
    nextReviewAt: UtcZ | None = None
    latestDeltaId: DeltaId | None = None
    freshness: Freshness = Freshness.UNKNOWN
    checkpoints: Annotated[tuple[HypothesisCheckpoint, ...], Field(max_length=20)] = ()
    revision: Annotated[int, Field(ge=0)] = 0
    updatedAt: UtcZ | None = None


def _ticker(value: str) -> str:
    normalized = str(value or "").strip().upper().replace(".", "-")
    if not normalized or len(normalized) > 12:
        raise ValueError("invalid_ticker")
    if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in normalized):
        raise ValueError("invalid_ticker")
    return normalized


def _datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def utc_z(value: str | datetime | None) -> str | None:
    parsed = _datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def derive_next_review_at(last_reviewed_at: str | datetime | None, review_cycle: str) -> str | None:
    reviewed = _datetime(last_reviewed_at)
    cycle = thesis_model.normalize_review_cycle(review_cycle)
    if reviewed is None or cycle == "event_driven":
        return None
    return utc_z(reviewed + timedelta(days=_CYCLE_DAYS[cycle]))


def derive_freshness(
    next_review_at: str | datetime | None,
    review_cycle: str,
    *,
    now: datetime | None = None,
) -> Freshness:
    due = _datetime(next_review_at)
    if due is None:
        return Freshness.UNKNOWN
    current = _datetime(now or datetime.now(UTC))
    if current is None:
        return Freshness.UNKNOWN
    if current < due:
        return Freshness.FRESH
    cycle = thesis_model.normalize_review_cycle(review_cycle)
    grace_days = _CYCLE_DAYS.get(cycle)
    if grace_days is None:
        return Freshness.DUE
    if current <= due + timedelta(days=grace_days):
        return Freshness.DUE
    return Freshness.STALE


def _checkpoint_id(ticker: str, label: str) -> str:
    digest = hashlib.sha256(f"{ticker}:{label}".encode()).hexdigest()[:20]
    return f"cp_{digest}"


def state_from_thesis(thesis: dict, *, now: datetime | None = None) -> ReviewState:
    ticker = _ticker(thesis.get("ticker"))
    cycle = thesis_model.normalize_review_cycle(thesis.get("review_cycle"))
    reviewed_at = utc_z(thesis.get("last_reviewed_at") or thesis.get("created_at"))
    next_review_at = derive_next_review_at(reviewed_at, cycle)
    checkpoints = tuple(
        HypothesisCheckpoint(
            id=_checkpoint_id(ticker, label),
            label=label,
            state=CheckpointState.OPEN,
            reasonCode="thesis_checkpoint",
        )
        # 구조화 체크포인트(dict)가 섞여 있어도 라벨은 사람이 읽는 한 줄이다.
        for label in checkpoint_labels((thesis.get("next_checkpoints") or [])[:20])
    )
    return ReviewState(
        ticker=ticker,
        lastReviewedAt=reviewed_at,
        nextReviewAt=next_review_at,
        freshness=derive_freshness(next_review_at, cycle, now=now),
        checkpoints=checkpoints,
    )


def _completed_checkpoints(
    ticker: str,
    labels: list,
    previous: tuple[HypothesisCheckpoint, ...],
) -> tuple[HypothesisCheckpoint, ...]:
    retained = {checkpoint.id: checkpoint for checkpoint in previous}
    result: list[HypothesisCheckpoint] = []
    for label in checkpoint_labels(list(labels)[:20]):
        checkpoint_id = _checkpoint_id(ticker, label)
        prior = retained.get(checkpoint_id)
        if prior and prior.state in {CheckpointState.CHECKED, CheckpointState.INVALIDATED}:
            result.append(prior)
        else:
            result.append(
                HypothesisCheckpoint(
                    id=checkpoint_id,
                    label=label,
                    state=CheckpointState.OPEN,
                    reasonCode="delta_checkpoint",
                )
            )
    return tuple(result)


def record_completed_review(
    connection: sqlite3.Connection,
    thesis: dict,
    delta: dict,
) -> ReviewState:
    """Persist bounded review metadata after a normalized Delta was saved."""
    ticker = _ticker(thesis.get("ticker") or delta.get("ticker"))
    current = load_review_state(connection, ticker)
    reviewed_at = utc_z(delta.get("generatedAt") or datetime.now(UTC))
    if reviewed_at is None:
        raise ValueError("reviewed_at_required")
    cycle = thesis_model.normalize_review_cycle(thesis.get("review_cycle"))
    next_review_at = derive_next_review_at(reviewed_at, cycle)
    labels = delta.get("nextCheckpoints")
    if not isinstance(labels, list):
        labels = thesis.get("next_checkpoints") or []
    state = ReviewState(
        ticker=ticker,
        lastReviewedAt=reviewed_at,
        nextReviewAt=next_review_at,
        latestDeltaId=str(delta.get("deltaId") or "") or None,
        freshness=derive_freshness(next_review_at, cycle, now=_datetime(reviewed_at)),
        checkpoints=_completed_checkpoints(ticker, labels, current.checkpoints),
        revision=current.revision,
        updatedAt=reviewed_at,
    )
    return save_review_state(connection, state, expected_revision=current.revision)


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS thesis_review_state (
            ticker TEXT PRIMARY KEY,
            last_reviewed_at TEXT NOT NULL DEFAULT '',
            next_review_at TEXT NOT NULL DEFAULT '',
            latest_delta_id TEXT NOT NULL DEFAULT '',
            freshness TEXT NOT NULL DEFAULT 'unknown',
            checkpoints_json TEXT NOT NULL DEFAULT '[]',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_thesis_review_due "
        "ON thesis_review_state(freshness, next_review_at)"
    )


def empty_review_state(ticker: str) -> ReviewState:
    return ReviewState(ticker=_ticker(ticker))


def _row_to_state(row: sqlite3.Row | None, ticker: str) -> ReviewState:
    if row is None:
        return empty_review_state(ticker)
    try:
        checkpoints = json.loads(row["checkpoints_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        checkpoints = []
    try:
        freshness = Freshness(row["freshness"])
    except ValueError:
        freshness = Freshness.UNKNOWN
    return ReviewState(
        ticker=row["ticker"],
        lastReviewedAt=row["last_reviewed_at"] or None,
        nextReviewAt=row["next_review_at"] or None,
        latestDeltaId=row["latest_delta_id"] or None,
        freshness=freshness,
        checkpoints=checkpoints,
        revision=row["revision"],
        updatedAt=row["updated_at"] or None,
    )


def load_review_state(connection: sqlite3.Connection, ticker: str) -> ReviewState:
    ensure_schema(connection)
    normalized = _ticker(ticker)
    row = connection.execute(
        "SELECT * FROM thesis_review_state WHERE ticker=?",
        (normalized,),
    ).fetchone()
    return _row_to_state(row, normalized)


def save_review_state(
    connection: sqlite3.Connection,
    state: ReviewState,
    *,
    expected_revision: int,
) -> ReviewState:
    ensure_schema(connection)
    current = load_review_state(connection, state.ticker)
    if current.revision != expected_revision:
        raise ReviewStateConflictError("review_state_revision_conflict")
    if state.updatedAt is None:
        raise ValueError("updated_at_required")
    next_revision = current.revision + 1
    connection.execute(
        """
        INSERT INTO thesis_review_state (
            ticker,last_reviewed_at,next_review_at,latest_delta_id,freshness,
            checkpoints_json,revision,updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker) DO UPDATE SET
            last_reviewed_at=excluded.last_reviewed_at,
            next_review_at=excluded.next_review_at,
            latest_delta_id=excluded.latest_delta_id,
            freshness=excluded.freshness,
            checkpoints_json=excluded.checkpoints_json,
            revision=excluded.revision,
            updated_at=excluded.updated_at
        """,
        (
            state.ticker,
            state.lastReviewedAt or "",
            state.nextReviewAt or "",
            state.latestDeltaId or "",
            state.freshness.value,
            json.dumps(
                [checkpoint.model_dump(mode="json") for checkpoint in state.checkpoints],
                ensure_ascii=False,
            ),
            next_revision,
            state.updatedAt,
        ),
    )
    connection.commit()
    return load_review_state(connection, state.ticker)


__all__ = [
    "ReviewState",
    "ReviewStateConflictError",
    "derive_freshness",
    "derive_next_review_at",
    "empty_review_state",
    "ensure_schema",
    "load_review_state",
    "record_completed_review",
    "save_review_state",
    "state_from_thesis",
    "utc_z",
]
