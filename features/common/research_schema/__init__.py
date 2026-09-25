"""features.common.research_schema — Folio Board 공통 구조화 데이터 스키마 (Step 6).

대시보드(Step 8)와 품질 평가(Step 7)가 마크다운 파싱 없이 읽을 수 있도록
checkpoint / evidence / source ledger / data gap / market tape의 최소 공통 구조를 제공한다.

현재(Phase 0): 공통 enum + normalize 헬퍼.
이후 Phase에서 checkpoints.py / evidence.py / source_ledger.py / data_gaps.py가 추가된다.
"""
from __future__ import annotations

from features.common.research_schema.enums import (
    ARTIFACT_TYPE_CHOICES,
    CHECKPOINT_CONFIDENCE_CHOICES,
    CHECKPOINT_SCOPE_CHOICES,
    DATA_GAP_SEVERITY_CHOICES,
    EVIDENCE_FRESHNESS_CHOICES,
    EVIDENCE_ROLE_CHOICES,
    EVIDENCE_TYPE_CHOICES,
    HYPOTHESIS_EVIDENCE_TYPES,
    MARKET_TAPE_STATUS_CHOICES,
    RELIABILITY_CHOICES,
    is_hypothesis_evidence_type,
    normalize_artifact_type,
    normalize_checkpoint_confidence,
    normalize_checkpoint_scope,
    normalize_data_gap_severity,
    normalize_evidence_freshness,
    normalize_evidence_role,
    normalize_evidence_type,
    normalize_market_tape_status,
    normalize_reliability,
)
from features.common.research_schema.checkpoints import (
    checkpoints_from_list,
    checkpoints_from_markdown,
    checkpoints_from_regime_state,
    checkpoints_from_thesis_delta,
    normalize_checkpoint,
)
from features.common.research_schema.data_gaps import data_gaps_from_messages, normalize_data_gap
from features.common.research_schema.evidence import (
    evidence_items_from_list,
    is_countable_evidence,
    normalize_evidence_item,
)
from features.common.research_schema.source_ledger import (
    normalize_source_entry,
    source_ledger_from_items,
)

__all__ = [
    "ARTIFACT_TYPE_CHOICES",
    "CHECKPOINT_CONFIDENCE_CHOICES",
    "CHECKPOINT_SCOPE_CHOICES",
    "DATA_GAP_SEVERITY_CHOICES",
    "EVIDENCE_FRESHNESS_CHOICES",
    "EVIDENCE_ROLE_CHOICES",
    "EVIDENCE_TYPE_CHOICES",
    "HYPOTHESIS_EVIDENCE_TYPES",
    "MARKET_TAPE_STATUS_CHOICES",
    "RELIABILITY_CHOICES",
    "is_hypothesis_evidence_type",
    "normalize_artifact_type",
    "normalize_checkpoint_confidence",
    "normalize_checkpoint_scope",
    "normalize_data_gap_severity",
    "normalize_evidence_freshness",
    "normalize_evidence_role",
    "normalize_evidence_type",
    "normalize_market_tape_status",
    "normalize_reliability",
    "checkpoints_from_list",
    "checkpoints_from_markdown",
    "checkpoints_from_regime_state",
    "checkpoints_from_thesis_delta",
    "normalize_checkpoint",
    "data_gaps_from_messages",
    "normalize_data_gap",
    "evidence_items_from_list",
    "is_countable_evidence",
    "normalize_evidence_item",
    "normalize_source_entry",
    "source_ledger_from_items",
]
