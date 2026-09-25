"""화면은 "계획을 확인하세요"라고 하면서 고칠 수단을 주지 않았다.

계획이 어긋났을 때 사용자가 할 수 있는 일은 질문을 다시 쓰는 것뿐이었다.
수정은 서버가 적용한다 — 클라이언트가 만든 계획을 통째로 받으면 승인 계약이
검증하는 것이 사라진다.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from features.topic_report.approval_store import ApprovalSupersededError
from features.topic_report.approved_request import (
    ApprovedRequestRuntime,
    ApprovedRequestService,
    IntegrityMismatchError,
)
from features.topic_report.approved_schema import (
    ApprovalReference,
    AxisEdit,
    ConfirmDegradedRequest,
    PlanEdits,
    PlanRequest,
    RevisePlanRequest,
)
from features.topic_report.plan_edits import PlanEditError
from features.topic_report.resolution_schema import ProviderGenerations, ResolutionSnapshotV1

QUESTION = "메모리 반도체의 방향성: 피크 아웃인가, 공급 부족인가"


def _resolution() -> ResolutionSnapshotV1:
    return ResolutionSnapshotV1(
        schemaVersion=1,
        collectionId=None,
        collectionRevision=None,
        collectionDefinitionHash=None,
        eligibleTotal=None,
        candidateCap=None,
        truncated=False,
        resolvedCandidateIds=[],
        executionUniverseIds=[],
        unusableCandidates=[],
        selectedEvidenceIds=[],
        providerGenerations=ProviderGenerations(indexGeneration=None, rssGeneration=None),
        inputWatermark=None,
    )


@pytest.fixture
def service(tmp_path):
    ids = iter(UUID(f"{n}2345678-1234-4567-9234-567812345678") for n in range(1, 9))
    return ApprovedRequestService(
        ApprovedRequestRuntime(
            dataDir=tmp_path,
            clock=lambda: datetime(2026, 8, 7, 3, 0, tzinfo=UTC),
            entropy=lambda size: bytes(range(size)),
            uuidFactory=lambda: next(ids),
            resolver=lambda _request: _resolution(),
        )
    )


def _planned(service, deep=False):
    return service.plan(PlanRequest(question=QUESTION, deepResearch=deep))


def _ref(grant):
    return ApprovalReference(id=grant.id, token=grant.token)


def test_editing_a_search_query_replaces_the_plan_and_the_approval(service):
    planned = _planned(service)

    revised = service.revise(RevisePlanRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        edits=PlanEdits(searchQueries=["메모리 반도체 가격", "DRAM 재고"]),
    ))

    assert revised.approvedRequest.topicPlan.searchQueries == ["메모리 반도체 가격", "DRAM 재고"]
    assert revised.approvedRequest.planHash != planned.approvedRequest.planHash
    assert revised.approval.id != planned.approval.id
    # 사람이 손댄 계획은 그렇게 표시한다.
    assert revised.approvedRequest.topicPlan.plannerMode == "edited"


def test_the_old_approval_stops_working(service):
    planned = _planned(service)
    service.revise(RevisePlanRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        edits=PlanEdits(topicLabel="메모리 사이클"),
    ))

    with pytest.raises(ApprovalSupersededError):
        service.revise(RevisePlanRequest(
            approvedRequest=planned.approvedRequest,
            approval=_ref(planned.approval),
            edits=PlanEdits(topicLabel="다시 바꾸기"),
        ))


def test_a_tampered_plan_is_refused(service):
    planned = _planned(service)
    payload = planned.approvedRequest.model_dump(mode="json")
    payload["question"] = "몰래 바꾼 질문"
    tampered = type(planned.approvedRequest).model_validate(payload)

    with pytest.raises(IntegrityMismatchError):
        service.revise(RevisePlanRequest(
            approvedRequest=tampered,
            approval=_ref(planned.approval),
            edits=PlanEdits(topicLabel="아무거나"),
        ))


def test_removing_an_axis_drops_its_deep_questions(service):
    planned = _planned(service, deep=True)
    plan = planned.approvedRequest.topicPlan
    target = plan.analysisAxes[0].key
    assert any(q.axisKey == target for q in plan.deepResearch.subQuestions)

    revised = service.revise(RevisePlanRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        edits=PlanEdits(axes=[AxisEdit(key=target, removed=True)]),
    ))

    keys = {axis.key for axis in revised.approvedRequest.topicPlan.analysisAxes}
    assert target not in keys
    assert all(
        q.axisKey in keys or not q.axisKey
        for q in revised.approvedRequest.topicPlan.deepResearch.subQuestions
    )


def test_an_unknown_axis_key_is_refused(service):
    """축 목록은 보고서 유형이 정한다. 수정이 새 축을 만드는 통로가 되면 안 된다."""
    planned = _planned(service)

    with pytest.raises(PlanEditError):
        service.revise(RevisePlanRequest(
            approvedRequest=planned.approvedRequest,
            approval=_ref(planned.approval),
            edits=PlanEdits(axes=[AxisEdit(key="made_up_axis", questions=["새 질문"])]),
        ))


def test_the_last_axis_cannot_be_removed(service):
    planned = _planned(service)
    every = [AxisEdit(key=axis.key, removed=True) for axis in planned.approvedRequest.topicPlan.analysisAxes]

    with pytest.raises(PlanEditError):
        service.revise(RevisePlanRequest(
            approvedRequest=planned.approvedRequest,
            approval=_ref(planned.approval),
            edits=PlanEdits(axes=every),
        ))


def test_editing_clears_a_prior_zero_evidence_confirmation(service):
    """계획이 바뀌면 앞서 받은 `근거 없음` 확인은 다른 계획에 대한 것이다."""
    planned = _planned(service)
    zero = planned.preview.zeroEvidence
    assert zero.required

    confirmed = service.confirm(ConfirmDegradedRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        reasonCode=zero.reasonCode,
        resolutionFingerprint=zero.resolutionFingerprint,
        confirmed=True,
    ))
    assert confirmed.approvedRequest.degradedConfirmation is not None

    revised = service.revise(RevisePlanRequest(
        approvedRequest=confirmed.approvedRequest,
        approval=_ref(confirmed.approval),
        edits=PlanEdits(searchQueries=["메모리 반도체 가격"]),
    ))
    assert revised.approvedRequest.degradedConfirmation is None


def test_server_owned_fields_survive_editing(service):
    planned = _planned(service)
    before = planned.approvedRequest.topicPlan

    revised = service.revise(RevisePlanRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        edits=PlanEdits(topicLabel="메모리 사이클", researchQuestions=["지금 사이클은 어디인가?"]),
    )).approvedRequest.topicPlan

    assert revised.expectedSections == before.expectedSections
    assert revised.deepResearch.falsificationTriggers == before.deepResearch.falsificationTriggers
    assert revised.deepResearch.requiredOutputs == before.deepResearch.requiredOutputs
    assert revised.topic == before.topic


def test_a_revision_instruction_edits_the_plan_in_place(service, monkeypatch):
    """칸을 하나씩 고치는 대신 무엇을 바꿀지 적는다.

    수정 요청이 있으면 규칙 계획에서 다시 시작하지 않는다. 다시 시작하면 사용자가
    앞서 받아 든 계획이 통째로 사라져 무엇이 반영됐는지 알 수 없다.
    """
    import json as _json

    import features.llm_settings.client as client
    from features.agent_mode import bridge
    from features.topic_report.approved_schema import ReplanRequest

    planned = _planned(service)
    seen = {}

    monkeypatch.setattr(client, "use_llm_analysis", lambda: True)
    monkeypatch.setattr(client, "selected_cli_config", lambda: {"apiKey": ""})
    monkeypatch.setattr(bridge, "bridge_status", lambda *a, **k: {"available": True})

    def fake_prompt(prompt, **_kwargs):
        seen["prompt"] = prompt
        return {"output": _json.dumps({
            "topic": QUESTION,
            "topicLabel": "메모리 사이클",
            "reportType": "supply_chain_theme",
            "searchQueries": ["DRAM 고정거래가격"],
            "analysisAxes": [
                {"key": "supply", "label": "공급 규율", "questions": ["감산은 이어지는가?"], "searchQueries": ["메모리 감산"]}
            ],
        }, ensure_ascii=False)}

    monkeypatch.setattr(bridge, "run_agent_prompt", fake_prompt)

    revised = service.replan(ReplanRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        instruction="밸류에이션 축은 빼고 공급 쪽을 자세히 봐줘",
    ))

    assert "밸류에이션 축은 빼고" in seen["prompt"]
    # 지금 계획을 고치는 것이지 규칙 계획에서 다시 시작하는 게 아니다.
    assert "현재 계획(수정 대상)" in seen["prompt"]
    assert planned.approvedRequest.topicPlan.analysisAxes[0].label in seen["prompt"]

    plan = revised.approvedRequest.topicPlan
    assert plan.topicLabel == "메모리 사이클"
    assert plan.plannerMode == "llm"
    assert revised.approvedRequest.planHash != planned.approvedRequest.planHash


def test_replanning_without_an_engine_keeps_the_current_plan(service, monkeypatch):
    from features.agent_mode import bridge
    from features.topic_report.approved_schema import ReplanRequest

    planned = _planned(service)
    monkeypatch.setattr(bridge, "bridge_status", lambda *a, **k: {"available": False})

    revised = service.replan(ReplanRequest(
        approvedRequest=planned.approvedRequest,
        approval=_ref(planned.approval),
        instruction="검색어를 영어로 바꿔줘",
    ))

    assert revised.approvedRequest.topicPlan.plannerMode == "rules"
    assert revised.approvedRequest.topicPlan.analysisAxes
