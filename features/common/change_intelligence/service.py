"""ChangeBasis decoration and authority projection facade."""
from __future__ import annotations

from pathlib import Path

from features.common.change_intelligence.adapters.briefing import build_briefing_basis
from features.common.change_intelligence.adapters.company import build_company_basis
from features.common.change_intelligence.adapters.market_memory import build_market_memory_basis
from features.common.change_intelligence.adapters.topic import build_topic_basis
from features.common.change_intelligence.baseline import select_report_baseline
from features.common.change_intelligence.basis import content_hash, normalize_basis
from features.common.change_intelligence.comparator import compare_basis
from features.common.change_intelligence.projection import invalidation_token, project_report
from features.common.change_intelligence.semantic import apply_semantic_verdicts, evaluate_semantic_changes

ADAPTERS = {
    "briefing": build_briefing_basis,
    "company_analysis": build_company_basis,
    "topic_report": build_topic_basis,
    "market_memory": build_market_memory_basis,
}


def build_basis(artifact_kind: str, candidate: dict, *, native_context: dict | None = None) -> dict:
    if artifact_kind not in ADAPTERS:
        raise ValueError("change_adapter_not_found")
    context = native_context or {}
    if artifact_kind == "briefing":
        return build_briefing_basis(candidate, generation_docs=context.get("generationDocs"))
    if artifact_kind == "company_analysis":
        return build_company_basis(candidate, materials=context.get("materials"))
    return ADAPTERS[artifact_kind](candidate)


# 의미 비교를 돌리는 생성 모드. `rules`는 LLM을 부르지 않으므로 제외한다.
SEMANTIC_GENERATION_MODES = frozenset({"llm", "agent"})


def decorate_candidate(artifact_kind: str, candidate: dict, *, data_dir: Path, native_context: dict | None = None, generation_provenance: bool = True) -> dict:
    if not generation_provenance:
        return dict(candidate)
    decorated = dict(candidate)
    basis = normalize_basis(decorated["changeBasis"]) if isinstance(decorated.get("changeBasis"), dict) else build_basis(artifact_kind, decorated, native_context=native_context)
    previous, baseline_ref = select_report_baseline(Path(data_dir), basis) if artifact_kind != "market_memory" else (None, None)
    current_ref = {
        "storageKind": "json_report" if artifact_kind != "market_memory" else "market_state_snapshot",
        "id": basis.get("artifactId"), "revision": None, "contentHash": content_hash(basis),
    }
    summary = compare_basis(basis, previous, current_ref=current_ref, baseline_ref=baseline_ref)
    if artifact_kind == "briefing":
        # 의미 비교는 브리핑 생성이라는 명시적 사용자 action의 연장에서만 실행한다.
        # 규칙 모드 생성은 LLM을 호출하지 않고 not_evaluated 게이트만 적용한다.
        #
        # **`agent`도 그 action이다.** Agent CLI 산출물의 mode는 `agent`인데
        # (`agent_mode/schema.py::agent_generation`) 예전에는 `llm`만 통과시켜,
        # CLI로 브리핑을 만드는 구성에서는 의미 판정이 아예 돌지 않았다.
        generation_mode = str((decorated.get("generation") or {}).get("mode") or "")
        evaluation = (
            evaluate_semantic_changes(summary)
            if generation_mode in SEMANTIC_GENERATION_MODES
            else {"status": "not_evaluated", "verdicts": {}, "reason": "generation_rules_mode"}
        )
        summary = apply_semantic_verdicts(summary, evaluation)
    decorated["changeBasis"] = basis
    decorated["changeSummary"] = summary
    decorated["changeIntelligence"] = {
        "status": summary["status"], "authorityKind": current_ref["storageKind"],
        "projectionStatus": "pending", "invalidationToken": invalidation_token(summary),
    }
    return decorated


def projection_db_for_report(report_path: Path, default_db_path: Path) -> Path:
    """Keep the change projection in the same store as the report being committed.

    Report directories get redirected to temp paths in tests while the module-level
    database constant does not, so a fixed path let fixture reports write change
    events into the user's real database — one such event showed up on the
    dashboard as a live major change.
    """
    report_path = Path(report_path)
    default_db_path = Path(default_db_path)
    data_dir = report_path.parent.parent
    if data_dir == default_db_path.parent:
        return default_db_path
    return data_dir / default_db_path.name


def project_committed_report(db_path: Path, report_path: Path) -> dict:
    return project_report(projection_db_for_report(report_path, db_path), Path(report_path))
