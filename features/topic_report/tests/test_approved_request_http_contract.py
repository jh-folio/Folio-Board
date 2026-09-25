from __future__ import annotations

import json
from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path

from starlette.responses import Response

from features.common.jcs import JsonValue, sha256_hex
from features.topic_report.routes import (
    ApprovedRequestBoundary,
    create_approved_request_router,
)


class InlineExecutor:
    def submit(self, function, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as error:
            future.set_exception(error)
        return future


def response_json(response: Response) -> dict[str, JsonValue]:
    payload = json.loads(response.body)
    assert isinstance(payload, dict)
    return payload


def execution_body(envelope: dict[str, JsonValue]) -> dict[str, JsonValue]:
    approval = envelope["approval"]
    assert isinstance(approval, dict)
    return {
        "approvedRequest": deepcopy(envelope["approvedRequest"]),
        "approval": {"id": approval["id"], "token": approval["token"]},
        "execution": {
            "mode": "auto",
            "adapter": "auto",
            "fallbackPolicy": "rules_on_engine_failure",
        },
    }


def test_approved_request_http_boundary_rejects_tampering_and_survives_restart(
    tmp_path: Path,
) -> None:
    # Given: a feature-owned HTTP boundary backed by an isolated approval store.
    boundary = ApprovedRequestBoundary(tmp_path)
    plan_response = boundary.plan(
        {"question": "PRIVATE_QUESTION", "userContext": "PRIVATE_CONTEXT"}
    )
    assert plan_response.status_code == 200
    envelope = response_json(plan_response)
    assert set(envelope) == {"approvedRequest", "approval", "preview"}

    # When: a valid-schema request is changed and rehashed without a new approval.
    tampered = execution_body(envelope)
    approved = tampered["approvedRequest"]
    assert isinstance(approved, dict)
    approved["question"] = "rehashed tamper"
    approved["planHash"] = sha256_hex(
        {key: value for key, value in approved.items() if key != "planHash"}
    )
    tamper_response = boundary.preflight(tampered)

    # Then: opaque authorization rejects the request and no job store is created.
    assert tamper_response.status_code == 409
    assert response_json(tamper_response) == {"error": "approval_mismatch"}
    assert not (tmp_path / "jobs.json").exists()

    zero = envelope["preview"]["zeroEvidence"]
    confirm_response = boundary.confirm(
        {
            "approvedRequest": envelope["approvedRequest"],
            "approval": {
                "id": envelope["approval"]["id"],
                "token": envelope["approval"]["token"],
            },
            "reasonCode": zero["reasonCode"],
            "resolutionFingerprint": zero["resolutionFingerprint"],
            "confirmed": True,
        }
    )
    assert confirm_response.status_code == 200
    replacement = response_json(confirm_response)

    # When: the process-local app is recreated over the same metadata-only store.
    restarted_boundary = ApprovedRequestBoundary(tmp_path, executor=InlineExecutor())
    old_response = restarted_boundary.preflight(execution_body(envelope))
    replacement_response = restarted_boundary.preflight(execution_body(replacement))

    # Then: the old approval remains superseded and the confirmed-zero replacement creates
    # one rules-only SharedJob without invoking an external engine.
    assert old_response.status_code == 409
    assert response_json(old_response) == {"error": "approval_superseded"}
    assert replacement_response.status_code == 202
    job = response_json(replacement_response)["job"]
    assert isinstance(job, dict)
    assert job["kind"] == "topic_report"
    assert job["requestedMode"] == "direct"
    assert job["generationMode"] == "rules"
    assert job["adapter"] == "rules"
    assert job["mode"] == "fallback"
    assert job["attemptedEngine"] == "none"
    assert job["finalEngine"] == "rules"
    assert job["fallbackReason"] == "confirmed_zero_evidence"
    jobs_payload = json.loads((tmp_path / "jobs-v2.json").read_text(encoding="utf-8"))
    terminal = next(item for item in jobs_payload["jobs"] if item["id"] == job["id"])
    assert terminal["status"] == "done"
    assert terminal["resultProjection"]["finalEngine"] == "rules"
    saved = list((tmp_path / "topic-reports").glob("*.json"))
    assert len(saved) == 1
    report = json.loads(saved[0].read_text(encoding="utf-8"))
    assert report["researchResolution"]["resolution"] == replacement["preview"]["resolution"]
    assert report["researchResolution"]["zeroEvidence"] == replacement["preview"]["zeroEvidence"]
    assert report["researchResolution"]["resolvedAt"] >= replacement["preview"]["resolvedAt"]
    assert report["evidenceItems"] == []
    replay_response = restarted_boundary.preflight(execution_body(replacement))
    assert replay_response.status_code == 202
    assert response_json(replay_response)["job"]["id"] == job["id"]
    replay_jobs = json.loads((tmp_path / "jobs-v2.json").read_text(encoding="utf-8"))["jobs"]
    assert [item["id"] for item in replay_jobs] == [job["id"]]


def test_approved_request_http_boundary_rejects_unknown_fields(tmp_path: Path) -> None:
    # Given: an otherwise valid plan request.
    create_approved_request_router(tmp_path)

    # When: an unknown wire field crosses the HTTP boundary.
    response = ApprovedRequestBoundary(tmp_path).plan(
        {"question": "AI 전력 수요", "unknown": True}
    )

    # Then: FastAPI and Pydantic return the schema status without feature execution.
    assert response.status_code == 422
    assert not (tmp_path / "topic-plan-approvals.json").exists()


def test_unconfirmed_zero_evidence_returns_confirmation_required(tmp_path: Path) -> None:
    boundary = ApprovedRequestBoundary(tmp_path)
    envelope = response_json(boundary.plan({"question": "No indexed evidence"}))

    response = boundary.preflight(execution_body(envelope))

    assert response.status_code == 409
    payload = response_json(response)
    assert payload["error"] == "evidence_confirmation_required"
    assert payload["preview"]["resolution"] == envelope["preview"]["resolution"]
    assert payload["preview"]["zeroEvidence"] == envelope["preview"]["zeroEvidence"]
    assert payload["preview"]["resolvedAt"] >= envelope["preview"]["resolvedAt"]
    assert not (tmp_path / "jobs-v2.json").exists()
