from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from features.common.jcs import JsonValue, sha256_hex
from features.topic_report.approval_store import (
    ApprovalEntry,
    ApprovalProof,
    ApprovalStore,
    ApprovalStoreRuntime,
    utc_z,
)
from features.topic_report.approved_plan_schema import (
    FALSIFICATION_TRIGGERS,
    REQUIRED_OUTPUTS,
    TopicPlanV1,
)
from features.topic_report.approved_schema import (
    ApprovedCollectionRef,
    ApprovedRequest,
    ConfirmDegradedRequest,
    DegradedConfirmation,
    GenerateApprovedRequest,
    PlanPreviewEnvelope,
    PlanRequest,
    ReplanRequest,
    RevisePlanRequest,
)
from features.topic_report.plan_edits import PlanEditError, apply_plan_edits
from features.topic_report.planner import apply_deep_research_plan, build_topic_plan
from features.topic_report.approved_research import PreparedResearch
from features.topic_report.resolution_schema import ResearchPreview, ResolutionSnapshotV1, ZeroEvidence


@dataclass(frozen=True, slots=True)
class ApprovedRequestRuntime:
    dataDir: Path
    clock: Callable[[], datetime]
    entropy: Callable[[int], bytes]
    uuidFactory: Callable[[], UUID]
    resolver: Callable[[ApprovedRequest], ResolutionSnapshotV1 | PreparedResearch]
    collectionResolver: Callable[[str, int], ApprovedCollectionRef] | None = None


@dataclass(frozen=True, slots=True)
class ApprovedRequestError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


class IntegrityMismatchError(ApprovedRequestError):
    def __init__(self) -> None:
        super().__init__(code="approval_mismatch")


class CollectionResolutionDeferredError(ApprovedRequestError):
    def __init__(self) -> None:
        super().__init__(code="collection_resolution_deferred")


@dataclass(frozen=True, slots=True)
class EvidenceConfirmationRequiredError(ApprovedRequestError):
    preview: ResearchPreview

    def __init__(self, preview: ResearchPreview) -> None:
        ApprovedRequestError.__init__(self, code="evidence_confirmation_required")
        object.__setattr__(self, "preview", preview)


@dataclass(frozen=True, slots=True)
class ResolutionChangedError(ApprovedRequestError):
    preview: ResearchPreview

    def __init__(self, preview: ResearchPreview) -> None:
        ApprovedRequestError.__init__(self, code="resolution_changed")
        object.__setattr__(self, "preview", preview)


@dataclass(frozen=True, slots=True)
class ExecutionPreflight:
    preview: ResearchPreview | None
    replayJobId: str | None
    preparedResearch: PreparedResearch | None


class ApprovedRequestService:
    def __init__(self, runtime: ApprovedRequestRuntime) -> None:
        self._runtime = runtime
        self._store = ApprovalStore(
            ApprovalStoreRuntime(
                path=runtime.dataDir / "topic-plan-approvals.json",
                clock=runtime.clock,
                entropy=runtime.entropy,
                uuidFactory=runtime.uuidFactory,
            )
        )

    @property
    def approval_store(self) -> ApprovalStore:
        return self._store

    def hash_approved_payload(self, payload: dict[str, JsonValue]) -> str:
        preimage = {key: value for key, value in payload.items() if key != "planHash"}
        return sha256_hex(preimage)

    def definition_plan_hash(self, approved: ApprovedRequest) -> str:
        payload = approved.model_dump(mode="json")
        payload.pop("planHash")
        payload["degradedConfirmation"] = None
        return sha256_hex(payload)

    def _topic_plan(
        self,
        request: PlanRequest,
        *,
        use_llm: bool | None = None,
        current_plan: TopicPlanV1 | None = None,
        instruction: str = "",
    ) -> TopicPlanV1:
        """계획은 기본적으로 설정된 엔진(API 키 또는 Agent CLI)이 쓴다.

        엔진을 설정해 둔 사용자는 그 순간부터 Agent 사용을 허락한 것으로 본다.
        엔진이 없거나 실패하면 규칙 계획이 그대로 나오고, `plannerMode`가 그 사실을
        말한다. 빠른 규칙 계획이 필요하면 요청에서 `plannerEngine=rules`를 고른다.
        """
        if use_llm is None:
            use_llm = request.plannerEngine != "rules"
        raw = build_topic_plan(
            "custom",
            custom_label=request.question,
            user_context=request.userContext,
            llm_override=use_llm,
            current_plan=current_plan.model_dump(mode="json") if current_plan else None,
            instruction=instruction,
        )
        raw["plannerMode"] = raw.get("plannerMode") or "rules"
        raw["candidateTickers"] = request.customTickers or raw.get("candidateTickers", {})
        if request.deepResearch:
            raw = apply_deep_research_plan(raw)
        else:
            raw["deepResearch"] = {
                "enabled": False,
                "maxRounds": 2,
                "subQuestions": [],
                "falsificationTriggers": FALSIFICATION_TRIGGERS,
                "requiredOutputs": REQUIRED_OUTPUTS,
            }
        return TopicPlanV1.model_validate(raw)

    def _approved(self, request: PlanRequest) -> ApprovedRequest:
        approved_collection = None
        if request.collectionRef is not None:
            if self._runtime.collectionResolver is None:
                raise CollectionResolutionDeferredError
            approved_collection = self._runtime.collectionResolver(
                request.collectionRef.id,
                request.collectionRef.revision,
            )
        now = self._runtime.clock().astimezone(UTC)
        payload: dict[str, JsonValue] = {
            "schemaVersion": 2,
            "planRevision": 2,
            "asOfDate": now.astimezone(timezone(timedelta(hours=9))).date().isoformat(),
            "qualityMode": "diagnose_only",
            "question": request.question,
            "userContext": request.userContext,
            "contextLayer": "hypothesis",
            "deepResearch": request.deepResearch,
            "customTickers": request.customTickers,
            "marketStatePolicy": request.marketStatePolicy,
            "marketStateScope": request.marketStateScope,
            "collectionRef": (
                approved_collection.model_dump(mode="json")
                if approved_collection is not None
                else None
            ),
            "topicPlan": self._topic_plan(request).model_dump(mode="json"),
            "degradedConfirmation": None,
        }
        payload["planHash"] = self.hash_approved_payload(payload)
        return ApprovedRequest.model_validate(payload)

    def _fingerprint(
        self,
        approved: ApprovedRequest,
        reason: str,
        resolution: ResolutionSnapshotV1,
    ) -> str:
        preimage: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "definitionPlanHash": self.definition_plan_hash(approved),
            "reasonCode": reason,
            "resolution": resolution.model_dump(mode="json"),
        }
        return "rf1_" + sha256_hex(preimage)

    def _preview(self, approved: ApprovedRequest) -> tuple[ResearchPreview, PreparedResearch | None]:
        resolved = self._runtime.resolver(approved)
        prepared = resolved if isinstance(resolved, PreparedResearch) else None
        resolution = prepared.resolution if prepared is not None else resolved
        if resolution.selectedEvidenceIds:
            zero = ZeroEvidence(required=False, reasonCode=None, resolutionFingerprint=None)
        else:
            reason = (
                "filtered_empty"
                if approved.collectionRef is not None
                else "no_index"
                if resolution.providerGenerations.indexGeneration is None
                else "zero_matches"
            )
            zero = ZeroEvidence(
                required=True,
                reasonCode=reason,
                resolutionFingerprint=self._fingerprint(approved, reason, resolution),
            )
        return (
            ResearchPreview(
                resolution=resolution,
                resolvedAt=utc_z(self._runtime.clock()),
                zeroEvidence=zero,
            ),
            prepared,
        )

    def _proof(self, approved: ApprovedRequest, approval_id: str, token: str) -> ApprovalProof:
        return ApprovalProof(id=approval_id, token=token, planHash=approved.planHash)

    def approval_proof(self, request: GenerateApprovedRequest) -> ApprovalProof:
        return self._proof(
            request.approvedRequest,
            request.approval.id,
            request.approval.token,
        )

    def _validate_integrity(self, approved: ApprovedRequest) -> None:
        payload = approved.model_dump(mode="json")
        if self.hash_approved_payload(payload) != approved.planHash:
            raise IntegrityMismatchError

    def plan(self, request: PlanRequest) -> PlanPreviewEnvelope:
        approved = self._approved(request)
        preview, _prepared = self._preview(approved)
        grant = self._store.issue(approved.planHash)
        return PlanPreviewEnvelope(approvedRequest=approved, approval=grant, preview=preview)

    def _swap_plan(self, approved: ApprovedRequest, plan: TopicPlanV1, proof) -> PlanPreviewEnvelope:
        """계획만 갈아끼우고 승인을 새 해시로 옮긴다.

        `confirm`과 같은 모양이다 — 서버가 payload를 고치고, 해시를 다시 계산하고,
        기존 승인을 supersede한다. 클라이언트가 계획을 통째로 밀어넣는 통로는 없다.
        """
        payload = approved.model_dump(mode="json")
        payload["topicPlan"] = plan.model_dump(mode="json")
        # 계획이 바뀌면 앞서 받은 `근거 없음` 확인은 다른 계획에 대한 것이다.
        payload["degradedConfirmation"] = None
        payload["planHash"] = self.hash_approved_payload(payload)
        replacement = ApprovedRequest.model_validate(payload)
        grant = self._store.replace(proof, replacement.planHash)
        preview, _prepared = self._preview(replacement)
        return PlanPreviewEnvelope(approvedRequest=replacement, approval=grant, preview=preview)

    def replan(self, request: ReplanRequest) -> PlanPreviewEnvelope:
        """사용자가 눌렀을 때만 LLM/Agent로 계획을 다시 쓴다.

        엔진이 없거나 실패하면 규칙 계획이 그대로 나온다. 그 사실은 `plannerMode`가
        말한다 — 무엇이 쓴 계획인지 모르면 얼마나 믿을지 정할 수 없다.
        """
        approved = request.approvedRequest
        self._validate_integrity(approved)
        proof = self._proof(approved, request.approval.id, request.approval.token)
        self._store.authorize(proof)
        plan_request = PlanRequest(
            question=approved.question,
            userContext=approved.userContext,
            deepResearch=approved.deepResearch,
            customTickers=dict(approved.customTickers),
            marketStatePolicy=approved.marketStatePolicy,
            marketStateScope=approved.marketStateScope,
        )
        revised = self._topic_plan(
            plan_request,
            use_llm=True,
            current_plan=approved.topicPlan,
            instruction=request.instruction,
        )
        return self._swap_plan(approved, revised, proof)

    def revise(self, request: RevisePlanRequest) -> PlanPreviewEnvelope:
        """승인 전 계획 수정. 새 계획 해시로 승인을 갈아끼운다.

        `confirm`과 같은 모양이다 — 무결성 확인 → 권한 확인 → 서버가 payload를 고침
        → 해시 재계산 → 기존 승인 supersede. 클라이언트가 계획을 통째로 밀어넣는
        통로를 만들지 않는 이유가 여기 있다.
        """
        approved = request.approvedRequest
        self._validate_integrity(approved)
        proof = self._proof(approved, request.approval.id, request.approval.token)
        self._store.authorize(proof)
        return self._swap_plan(approved, apply_plan_edits(approved.topicPlan, request.edits), proof)

    def confirm(self, request: ConfirmDegradedRequest) -> PlanPreviewEnvelope:
        approved = request.approvedRequest
        self._validate_integrity(approved)
        proof = self._proof(approved, request.approval.id, request.approval.token)
        self._store.authorize(proof)
        preview, _prepared = self._preview(approved)
        zero = preview.zeroEvidence
        if (
            not zero.required
            or zero.reasonCode != request.reasonCode
            or zero.resolutionFingerprint != request.resolutionFingerprint
        ):
            self._store.supersede(proof)
            raise ResolutionChangedError(preview)
        confirmation = DegradedConfirmation(
            reasonCode=request.reasonCode,
            resolutionFingerprint=request.resolutionFingerprint,
            confirmed=True,
            confirmedAt=utc_z(self._runtime.clock()),
        )
        payload = approved.model_dump(mode="json")
        payload["degradedConfirmation"] = confirmation.model_dump(mode="json")
        payload["planHash"] = self.hash_approved_payload(payload)
        replacement = ApprovedRequest.model_validate(payload)
        grant = self._store.replace(proof, replacement.planHash)
        return PlanPreviewEnvelope(approvedRequest=replacement, approval=grant, preview=preview)

    def preflight(self, request: GenerateApprovedRequest) -> ExecutionPreflight:
        approved = request.approvedRequest
        self._validate_integrity(approved)
        proof = self._proof(approved, request.approval.id, request.approval.token)
        entry: ApprovalEntry = self._store.authorize(proof)
        if entry.status == "consumed":
            return ExecutionPreflight(
                preview=None,
                replayJobId=entry.jobId,
                preparedResearch=None,
            )
        preview, prepared = self._preview(approved)
        confirmation = approved.degradedConfirmation
        if preview.zeroEvidence.required and confirmation is None:
            raise EvidenceConfirmationRequiredError(preview)
        if confirmation is not None and (
            not preview.zeroEvidence.required
            or preview.zeroEvidence.reasonCode != confirmation.reasonCode
            or preview.zeroEvidence.resolutionFingerprint != confirmation.resolutionFingerprint
        ):
            self._store.supersede(proof)
            raise ResolutionChangedError(preview)
        return ExecutionPreflight(
            preview=preview,
            replayJobId=None,
            preparedResearch=prepared,
        )
