from __future__ import annotations

import json

from features.common.quality_generation.candidate_store import CandidateStore


JOB_ID = "job_12345678-1234-4234-9234-1234567890ab"


def test_candidate_store_returns_latest_accepted_and_rejects_tamper(tmp_path) -> None:
    store = CandidateStore(tmp_path / "job-context")
    store.write(
        JOB_ID, 0, report_id="report-a", accepted=True,
        validation={"valid": True}, provenance={"pass": 0}, report={"id": "report-a", "markdown": "initial"},
    )
    store.write(
        JOB_ID, 1, report_id="report-a", accepted=False,
        validation={"valid": False}, provenance={"pass": 1}, report={"id": "report-a", "markdown": "bad"},
    )
    assert store.latest_accepted(JOB_ID).candidateIndex == 0
    path = store.path(JOB_ID, 0)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report"]["markdown"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.latest_accepted(JOB_ID) is None
