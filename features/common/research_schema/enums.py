"""Folio Board 공통 research_schema enum — Step 6 Data Foundation Lite.

대시보드(Step 8)·품질 평가(Step 7)가 의존하는 구조화 데이터의 enum을 한 곳에서
정의한다. 모든 normalize_*는 잘못된 값을 안전한 기본값으로 떨어뜨린다
(CLAUDE.md 원칙 4: 결론·분류는 enum으로 통제, LLM 자유 텍스트를 그대로 신뢰하지 않는다).

주의(원칙 2, 3계층 위계): evidence type에 ``user_note``가 있어도 사용자 노트는
hypothesis이며 evidence로 집계하지 않는다. 이 모듈은 enum만 정의하고, 실제 집계 제외는
``is_hypothesis_evidence_type``를 쓰는 evidence.py에서 강제한다.
"""
from __future__ import annotations

# --- Evidence ---------------------------------------------------------------
# role 집합은 topic_report.topic_schema와 동일하게 유지한다(일반화 시 호환).
EVIDENCE_ROLE_CHOICES = {"supporting", "challenging", "neutral", "background", "data_point"}
EVIDENCE_ROLE_DEFAULT = "neutral"

EVIDENCE_TYPE_CHOICES = {
    "news",
    "rss",
    "filing",
    "report",
    "market_data",
    "macro_data",
    "memory",
    "regime",
    "thesis",
    "user_note",
}
EVIDENCE_TYPE_DEFAULT = "news"

# evidence로 승격하면 안 되는 hypothesis 계열 type
HYPOTHESIS_EVIDENCE_TYPES = {"user_note"}

EVIDENCE_FRESHNESS_CHOICES = {"fresh", "recent", "stale", "unknown"}
EVIDENCE_FRESHNESS_DEFAULT = "unknown"

# --- Checkpoint -------------------------------------------------------------
CHECKPOINT_CONFIDENCE_CHOICES = {"low", "medium", "high"}
CHECKPOINT_CONFIDENCE_DEFAULT = "medium"

CHECKPOINT_SCOPE_CHOICES = {"market", "sector", "company", "portfolio", "macro"}
CHECKPOINT_SCOPE_DEFAULT = "market"

# --- Data Gap ---------------------------------------------------------------
DATA_GAP_SEVERITY_CHOICES = {"low", "medium", "high", "blocking"}
DATA_GAP_SEVERITY_DEFAULT = "medium"

# --- Market Tape ------------------------------------------------------------
MARKET_TAPE_STATUS_CHOICES = {"fresh", "stale", "missing", "conflicting", "estimated"}
MARKET_TAPE_STATUS_DEFAULT = "missing"

# --- Artifact (모든 구조화 객체 공통) ---------------------------------------
ARTIFACT_TYPE_CHOICES = {
    "briefing",
    "company_analysis",
    "topic_report",
    "personal_overlay",
    "thesis_delta",
    "regime_state",
}
ARTIFACT_TYPE_DEFAULT = "topic_report"

# 신뢰도(reliability) — source ledger 공통
RELIABILITY_CHOICES = {"high", "medium", "low", "unknown"}
RELIABILITY_DEFAULT = "medium"


def _normalize(value, choices: set, default: str) -> str:
    v = str(value or "").strip().lower()
    return v if v in choices else default


def normalize_evidence_role(value, default: str = EVIDENCE_ROLE_DEFAULT) -> str:
    return _normalize(value, EVIDENCE_ROLE_CHOICES, default)


def normalize_evidence_type(value, default: str = EVIDENCE_TYPE_DEFAULT) -> str:
    return _normalize(value, EVIDENCE_TYPE_CHOICES, default)


def normalize_evidence_freshness(value, default: str = EVIDENCE_FRESHNESS_DEFAULT) -> str:
    aliases = {"current": "recent", "dated": "stale"}
    v = str(value or "").strip().lower()
    return _normalize(aliases.get(v, v), EVIDENCE_FRESHNESS_CHOICES, default)


def normalize_checkpoint_confidence(value, default: str = CHECKPOINT_CONFIDENCE_DEFAULT) -> str:
    return _normalize(value, CHECKPOINT_CONFIDENCE_CHOICES, default)


def normalize_checkpoint_scope(value, default: str = CHECKPOINT_SCOPE_DEFAULT) -> str:
    return _normalize(value, CHECKPOINT_SCOPE_CHOICES, default)


def normalize_data_gap_severity(value, default: str = DATA_GAP_SEVERITY_DEFAULT) -> str:
    return _normalize(value, DATA_GAP_SEVERITY_CHOICES, default)


def normalize_market_tape_status(value, default: str = MARKET_TAPE_STATUS_DEFAULT) -> str:
    return _normalize(value, MARKET_TAPE_STATUS_CHOICES, default)


def normalize_artifact_type(value, default: str = ARTIFACT_TYPE_DEFAULT) -> str:
    return _normalize(value, ARTIFACT_TYPE_CHOICES, default)


def normalize_reliability(value, default: str = RELIABILITY_DEFAULT) -> str:
    return _normalize(value, RELIABILITY_CHOICES, default)


def is_hypothesis_evidence_type(value) -> bool:
    """user_note 등 hypothesis 계열이면 True. evidence 집계 제외 판단에 사용한다."""
    return normalize_evidence_type(value) in HYPOTHESIS_EVIDENCE_TYPES
