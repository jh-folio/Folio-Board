from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_COLLECTION_ID = re.compile(
    r"sc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_APPROVAL_ID = re.compile(
    r"apr_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_HASH = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"rf1_[0-9a-f]{64}")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def normalize_tickers(value: dict[str, str]) -> dict[str, str]:
    if len(value) > 14:
        raise ValueError("too_many_tickers")
    normalized: dict[str, str] = {}
    for raw_ticker, raw_label in value.items():
        ticker = normalize_text(raw_ticker).upper()
        label = normalize_text(raw_label)
        if not 1 <= len(ticker) <= 20 or not 1 <= len(label) <= 160:
            raise ValueError("invalid_ticker")
        if ticker in normalized:
            raise ValueError("ticker_collision")
        normalized[ticker] = label
    return normalized


class CollectionRefRequest(StrictModel):
    id: str
    revision: int = Field(ge=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = normalize_text(value)
        if _COLLECTION_ID.fullmatch(normalized) is None:
            raise ValueError("invalid_collection_id")
        return normalized


class PlanRequest(StrictModel):
    question: str = Field(min_length=1, max_length=500)
    userContext: str = Field(default="", max_length=4000)
    # 엔진을 설정해 둔 사용자는 그 순간부터 Agent 사용을 허락한 것으로 본다.
    # `rules`는 빠른 규칙 계획을 일부러 고를 때만 쓴다.
    plannerEngine: Literal["auto", "rules"] = "auto"
    deepResearch: bool = False
    customTickers: dict[str, str] = Field(default_factory=dict)
    marketStatePolicy: Literal["exclude", "include_current"] = "exclude"
    marketStateScope: Literal["AUTO", "GLOBAL", "US", "KR"] = "AUTO"
    collectionRef: CollectionRefRequest | None = None

    @field_validator("question", "userContext", mode="before")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("string_required")
        return normalize_text(value)

    @field_validator("customTickers", mode="before")
    @classmethod
    def normalize_custom_tickers(cls, value: dict[str, str]) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("ticker_map_required")
        if not all(isinstance(key, str) and isinstance(label, str) for key, label in value.items()):
            raise ValueError("ticker_strings_required")
        return normalize_tickers(value)


from features.topic_report.approved_plan_schema import ReportType, TopicPlanV1
from features.topic_report.resolution_schema import ResearchPreview


class CollectionDefinitionSnapshot(StrictModel):
    query: str = Field(max_length=500)
    market: Literal["ALL", "US", "KR", "GLOBAL", "UNKNOWN"]
    sources: list[str] = Field(max_length=20)
    tickers: list[str] = Field(max_length=20)
    tags: list[str] = Field(max_length=20)


class ApprovedCollectionRef(StrictModel):
    id: str
    revision: int = Field(ge=1)
    definitionHash: str = Field(pattern=_HASH.pattern)
    definitionSnapshot: CollectionDefinitionSnapshot


class DegradedConfirmation(StrictModel):
    reasonCode: Literal["no_index", "zero_matches", "filtered_empty"]
    resolutionFingerprint: str = Field(pattern=_FINGERPRINT.pattern)
    confirmed: Literal[True]
    confirmedAt: str

    @field_validator("confirmedAt")
    @classmethod
    def validate_confirmed_at(cls, value: str) -> str:
        validate_utc_z(value)
        return value


class ApprovedRequest(StrictModel):
    schemaVersion: Literal[1, 2]
    planRevision: Literal[1, 2]
    asOfDate: str
    qualityMode: Literal["diagnose_only"]
    question: str = Field(min_length=1, max_length=500)
    userContext: str = Field(max_length=4000)
    contextLayer: Literal["hypothesis"]
    deepResearch: bool
    customTickers: dict[str, str]
    marketStatePolicy: Literal["exclude", "include_current"]
    marketStateScope: Literal["AUTO", "GLOBAL", "US", "KR"]
    collectionRef: ApprovedCollectionRef | None
    topicPlan: TopicPlanV1
    degradedConfirmation: DegradedConfirmation | None
    planHash: str = Field(pattern=_HASH.pattern)

    @model_validator(mode="after")
    def validate_revision_pair(self) -> "ApprovedRequest":
        if self.schemaVersion != self.planRevision:
            raise ValueError("schema_plan_revision_mismatch")
        return self

    @field_validator("asOfDate")
    @classmethod
    def validate_as_of_date(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("invalid_as_of_date") from exc
        if parsed.isoformat() != value:
            raise ValueError("noncanonical_as_of_date")
        return value

    @field_validator("question", "userContext", mode="before")
    @classmethod
    def normalize_approved_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("string_required")
        return normalize_text(value)

    @field_validator("customTickers", mode="before")
    @classmethod
    def normalize_approved_tickers(cls, value: dict[str, str]) -> dict[str, str]:
        return normalize_tickers(value)


class ApprovalGrant(StrictModel):
    id: str = Field(pattern=_APPROVAL_ID.pattern)
    token: str = Field(pattern=_TOKEN.pattern)
    expiresAt: str


class ApprovalReference(StrictModel):
    id: str = Field(pattern=_APPROVAL_ID.pattern)
    token: str = Field(pattern=_TOKEN.pattern)


class PlanPreviewEnvelope(StrictModel):
    approvedRequest: ApprovedRequest
    approval: ApprovalGrant
    preview: ResearchPreview


class ExecutionRequest(StrictModel):
    # `auto`는 설정(`AI_AGENT_MODE`)이 정한다. 실행 경로는 앱 전체 설정이지
    # 리서치마다 고르는 값이 아니어서, 화면에서 묻지 않는다.
    mode: Literal["direct", "cli", "auto"] = "auto"
    adapter: Literal["auto", "codex", "claude", "antigravity"] = "auto"
    fallbackPolicy: Literal["rules_on_engine_failure"]

    @model_validator(mode="after")
    def validate_direct_adapter(self) -> "ExecutionRequest":
        if self.mode == "direct" and self.adapter != "auto":
            raise ValueError("direct_adapter_must_be_auto")
        return self


class GenerateApprovedRequest(StrictModel):
    approvedRequest: ApprovedRequest
    approval: ApprovalReference
    execution: ExecutionRequest


class AxisEdit(StrictModel):
    """한 분석 축에 대한 수정. 축은 key로 찾으며 새 축은 만들지 않는다."""

    key: str = Field(min_length=1, max_length=60)
    label: str | None = Field(default=None, max_length=160)
    questions: list[str] | None = Field(default=None, max_length=4)
    searchQueries: list[str] | None = Field(default=None, max_length=6)
    removed: bool = False


class PlanEdits(StrictModel):
    """사용자가 승인 전에 고칠 수 있는 범위.

    통째로 받은 계획을 그대로 믿지 않는다. 여기 적힌 필드만 반영하고
    나머지(expectedSections, deepResearch 고정값 등)는 서버가 계속 소유한다.
    """

    topicLabel: str | None = Field(default=None, max_length=200)
    reportType: ReportType | None = None
    researchQuestions: list[str] | None = Field(default=None, max_length=6)
    searchQueries: list[str] | None = Field(default=None, max_length=12)
    axes: list[AxisEdit] = Field(default_factory=list, max_length=6)


class ReplanRequest(StrictModel):
    """계획을 다시 쓰기.

    `instruction`이 있으면 지금 계획을 고쳐 쓰고, 없으면 처음부터 다시 쓴다.
    칸을 하나씩 고치는 것보다 "무엇을 바꿔달라"고 적는 편이 계획 수정에 맞다.
    """

    approvedRequest: ApprovedRequest
    approval: ApprovalReference
    instruction: str = Field(default="", max_length=1000)

    @field_validator("instruction", mode="before")
    @classmethod
    def normalize_instruction(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("string_required")
        return normalize_text(value)


class RevisePlanRequest(StrictModel):
    approvedRequest: ApprovedRequest
    approval: ApprovalReference
    edits: PlanEdits


class ConfirmDegradedRequest(StrictModel):
    approvedRequest: ApprovedRequest
    approval: ApprovalReference
    reasonCode: Literal["no_index", "zero_matches", "filtered_empty"]
    resolutionFingerprint: str = Field(pattern=_FINGERPRINT.pattern)
    confirmed: Literal[True]


def validate_utc_z(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("utc_z_required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid_utc_instant") from exc
    return parsed
