from __future__ import annotations

from features.market_memory.tests.sql_receipt_test_support import (
    NOW,
    connection,
    projection,
)
from features.thesis_tracking.job_writes import (
    commit_thesis_delta,
    prepare_thesis_delta,
    recover_thesis_delta,
)
from features.thesis_tracking import model, reason_history, store


def test_thesis_delta_row_and_receipt_commit_atomically() -> None:
    # Given
    database = connection()
    delta = {
        "deltaId": "delta-1",
        "generatedAt": NOW,
        "period": "90d",
        "periodDays": 90,
        "verdict": "maintained",
        "summary": "가설은 유지된다.",
        "evidence": [],
    }
    prepared = prepare_thesis_delta(
        database,
        ticker="NVDA",
        delta=delta,
        job_id="job-1",
        operation_id="op-thesis-1",
        terminal_projection=projection("thesis_delta", "delta-1"),
        created_at=NOW,
    )
    assert database.execute("SELECT COUNT(*) FROM thesis_delta").fetchone()[0] == 0

    # When
    committed = commit_thesis_delta(database, prepared)

    # Then
    assert committed.target_hash == prepared.target_hash
    assert recover_thesis_delta(database, prepared) == prepared.terminal_projection
    assert database.execute("SELECT COUNT(*) FROM thesis_delta").fetchone()[0] == 1
    assert database.execute("SELECT COUNT(*) FROM job_operation_receipts").fetchone()[0] == 1
    assert database.execute(
        "SELECT created_at FROM thesis_delta WHERE delta_id='delta-1'"
    ).fetchone()[0] == NOW


def test_background_delta_keeps_generation_reason_revision() -> None:
    database = connection()
    store.init_db(database)
    store.upsert_thesis(database, model.Thesis(ticker="NVDA", core_thesis="A", source="manual"))
    first = reason_history.latest(database, "NVDA")
    prepared = prepare_thesis_delta(
        database, ticker="NVDA",
        delta={"deltaId": "delta-old-reason", "generatedAt": NOW, "verdict": "maintained",
               "summary": "A의 검토", "reasonRevisionId": first["revisionId"], "evidence": []},
        job_id="job-old-reason", operation_id="op-old-reason",
        terminal_projection=projection("thesis_delta", "delta-old-reason"), created_at=NOW,
    )
    store.upsert_thesis(database, model.Thesis(ticker="NVDA", core_thesis="B", source="manual"))
    second = reason_history.latest(database, "NVDA")
    commit_thesis_delta(database, prepared)
    row = database.execute("SELECT reason_revision_id FROM reason_review_event WHERE delta_id='delta-old-reason'").fetchone()
    assert row[0] == first["revisionId"]
    assert row[0] != second["revisionId"]
