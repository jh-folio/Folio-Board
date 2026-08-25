from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from features.topic_report.approved_schema import StrictModel, normalize_text, normalize_tickers
from features.topic_report.topic_schema import (
    DEEP_MAX_QUESTIONS,
    DEEP_MAX_ROUND_1_QUESTIONS,
    DEEP_MAX_ROUND_2_QUESTIONS,
    BODY_SECTION_MAX,
    BODY_SECTION_MIN,
    EXPECTED_SECTIONS_V2,
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
)


FALSIFICATION_TRIGGERS = [
    "핵심 가격·지표가 보고서의 기본 시나리오와 반대로 2회 이상 확인된다.",
    "주요 수혜/피해 기업의 실적·가이던스가 예상 작동 경로와 반대로 나온다.",
    "정책·금리·환율 전제가 바뀌어 기존 인과 경로가 더 이상 성립하지 않는다.",
]
REQUIRED_OUTPUTS = [
    "scenario_table",
    "counter_arguments",
    "falsification_triggers",
    "quantitative_evidence_table",
]
ReportType = Literal[
    "macro_analysis",
    "cross_asset_analysis",
    "industry_theme",
    "supply_chain_theme",
    "policy_regulation",
    "geopolitical_risk",
    "earnings_theme",
    "factor_style",
    "company_basket",
    "country_market",
    "portfolio_implication",
    "custom_research",
]


def normalized_list(value: list[str], item_limit: int = 240) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("string_list_required")
    result: list[str] = []
    for item in value:
        normalized = normalize_text(item)
        if not normalized:
            continue
        if len(normalized) > item_limit:
            raise ValueError("string_too_long")
        if normalized not in result:
            result.append(normalized)
    return result


class AnalysisAxis(StrictModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=160)
    questions: list[str] = Field(max_length=4)
    requiredData: list[str] = Field(max_length=8)
    searchQueries: list[str] = Field(max_length=6)

    @field_validator("key", "label", mode="before")
    @classmethod
    def normalize_scalar(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("string_required")
        return normalize_text(value)

    @field_validator("questions", "requiredData", "searchQueries", mode="before")
    @classmethod
    def normalize_arrays(cls, value: list[str]) -> list[str]:
        return normalized_list(value)


class DeepSubQuestion(StrictModel):
    id: str = Field(pattern=r"dq_[0-9]{2}")
    question: str = Field(min_length=1, max_length=240)
    axisKey: str = Field(max_length=60)
    round: int = Field(ge=1, le=2)
    searchQueries: list[str] = Field(max_length=4)

    @field_validator("id", "question", "axisKey", mode="before")
    @classmethod
    def normalize_scalar(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("string_required")
        return normalize_text(value)

    @field_validator("searchQueries", mode="before")
    @classmethod
    def normalize_queries(cls, value: list[str]) -> list[str]:
        return normalized_list(value)


class DeepResearchPlan(StrictModel):
    enabled: bool
    maxRounds: Literal[2]
    subQuestions: list[DeepSubQuestion] = Field(max_length=DEEP_MAX_QUESTIONS)
    falsificationTriggers: list[str]
    requiredOutputs: list[str]

    @model_validator(mode="after")
    def validate_server_owned_fields(self) -> Self:
        if self.falsificationTriggers != FALSIFICATION_TRIGGERS:
            raise ValueError("fixed_falsification_triggers")
        if self.requiredOutputs != REQUIRED_OUTPUTS:
            raise ValueError("fixed_required_outputs")
        if len({question.id for question in self.subQuestions}) != len(self.subQuestions):
            raise ValueError("duplicate_subquestion_id")
        if sum(question.round == 1 for question in self.subQuestions) > DEEP_MAX_ROUND_1_QUESTIONS:
            raise ValueError("too_many_round_1_questions")
        if sum(question.round == 2 for question in self.subQuestions) > DEEP_MAX_ROUND_2_QUESTIONS:
            raise ValueError("too_many_round_2_questions")
        if not self.enabled and self.subQuestions:
            raise ValueError("disabled_deep_questions")
        return self


class TopicPlanV1(StrictModel):
    topic: str = Field(min_length=1, max_length=300)
    topicLabel: str = Field(min_length=1, max_length=200)
    reportType: ReportType
    # 이 계획을 무엇이 썼는가. 화면이 규칙 계획과 LLM 계획을 구분해 보여준다.
    plannerMode: Literal["rules", "llm", "preset", "edited"] = "rules"
    regions: list[str] = Field(max_length=6)
    assetClasses: list[str] = Field(max_length=6)
    timeHorizon: str = Field(max_length=60)
    userIntent: str = Field(max_length=120)
    researchQuestions: list[str] = Field(max_length=6)
    analysisAxes: list[AnalysisAxis] = Field(max_length=6)
    requiredMarketData: list[str] = Field(max_length=14)
    requiredMacroData: list[str] = Field(max_length=10)
    searchQueries: list[str] = Field(max_length=12)
    memoryQueries: list[str] = Field(max_length=10)
    candidateTickers: dict[str, str]
    # 머리 3 + 본문 최대 8 + 꼬리 5. 12로 두면 축이 4개만 돼도 계획이 거부된다.
    expectedSections: list[str] = Field(
        max_length=len(REPORT_HEAD_SECTIONS) + BODY_SECTION_MAX + len(REPORT_TAIL_SECTIONS)
    )
    dataGapsLikely: list[str] = Field(max_length=8)
    deepResearch: DeepResearchPlan

    @field_validator("topic", "topicLabel", "timeHorizon", "userIntent", mode="before")
    @classmethod
    def normalize_scalar(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("string_required")
        return normalize_text(value)

    @field_validator(
        "regions",
        "assetClasses",
        "researchQuestions",
        "requiredMarketData",
        "requiredMacroData",
        "searchQueries",
        "memoryQueries",
        "expectedSections",
        "dataGapsLikely",
        mode="before",
    )
    @classmethod
    def normalize_arrays(cls, value: list[str]) -> list[str]:
        return normalized_list(value)

    @field_validator("candidateTickers", mode="before")
    @classmethod
    def normalize_candidates(cls, value: dict[str, str]) -> dict[str, str]:
        return normalize_tickers(value)

    @model_validator(mode="after")
    def validate_section_shape(self) -> Self:
        """머리·꼬리는 고정, 본문은 계획이 정한다.

        예전에는 전체 목록의 정확 일치를 요구해서, 플래너가 주제에 맞는 구성을 제안해도
        사용자가 계획 화면에서 고쳐도 승인이 거부됐다. 머리·꼬리를 고정하는 건 서식이
        아니라 계약이다 — 꼬리의 반론·시나리오·체크포인트·Source Notes는 확증편향 방지와
        추적성의 집행 장치이고, 체크포인트 추출·품질 평가·리더가 이름으로 찾는다.
        """
        head, tail = list(REPORT_HEAD_SECTIONS), list(REPORT_TAIL_SECTIONS)
        sections = list(self.expectedSections)
        if sections[: len(head)] != head:
            raise ValueError("fixed_head_sections")
        if sections[-len(tail):] != tail:
            raise ValueError("fixed_tail_sections")
        body = sections[len(head): -len(tail)]
        if not BODY_SECTION_MIN <= len(body) <= BODY_SECTION_MAX:
            raise ValueError("body_section_count_out_of_range")
        if len(set(body)) != len(body):
            raise ValueError("duplicate_body_section")
        if set(body) & (set(head) | set(tail)):
            raise ValueError("reserved_body_section")
        return self
