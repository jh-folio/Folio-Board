"""Closed-loop quality evaluation and limited repair."""
from __future__ import annotations

from features.common.research_quality.evaluator import evaluate_artifact
from features.common.quality_generation.llm_section_rewrite import improve_sections_with_llm, should_llm_rewrite
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.schema import loop_shell, normalize_quality_mode
from features.common.quality_generation.telemetry import evidence_coverage
from features.common.quality_generation.weak_sections import detect_weak_sections


_STATUS_RANK = {"fail": 0, "warn": 1, "pass": 2}


def _merge_gaps(artifact: dict, preflight: dict) -> dict:
    """Add preflight-derived gaps without destroying the artifact's own shape.

    기업분석은 dataGaps를 {"gaps": [...], "summary": {...}} dict로 저장하고 나머지는
    list로 저장한다. dict를 list()로 감싸면 키 이름만 남아("gaps", "summary")
    resolutionAttempts에 남아 있던 진짜 gap이 통째로 사라진다. 실제로 저장된
    보고서가 그 상태였다.
    """
    raw = artifact.get("dataGaps")
    nested = isinstance(raw, dict)
    existing = list(raw.get("gaps") or []) if nested else list(raw or [])
    seen = {str(g.get("message") or "").lower() for g in existing if isinstance(g, dict)}
    added = False
    for gap in preflight.get("derivedDataGaps") or []:
        message = str(gap.get("message") or "").lower()
        if message and message not in seen:
            existing.append(gap)
            seen.add(message)
            added = True
    if not existing or (nested and not added):
        return artifact
    merged = {**raw, "gaps": existing} if nested else existing
    return {**artifact, "dataGaps": merged}


def _quality_regressed(before: dict | None, after: dict | None, weak_before: list[dict], weak_after: list[dict]) -> bool:
    before = before or {}
    after = after or {}
    before_score = int(before.get("score") or 0)
    after_score = int(after.get("score") or 0)
    if after_score < before_score:
        return True
    before_status = _STATUS_RANK.get(str(before.get("status") or ""), -1)
    after_status = _STATUS_RANK.get(str(after.get("status") or ""), -1)
    if after_status < before_status:
        return True
    if after_score == before_score and len(weak_after or []) > len(weak_before or []):
        return True
    return False


def apply_quality_loop(
    artifact_type: str,
    artifact: dict,
    *,
    mode: str = "diagnose_only",
    preflight: dict | None = None,
    context: dict | None = None,
    repair_budget=None,
) -> dict:
    mode = normalize_quality_mode(mode)
    artifact = dict(artifact or {})
    preflight = preflight or preflight_from_context(artifact_type, artifact, context)
    artifact = _merge_gaps(artifact, preflight)

    quality_before = evaluate_artifact(artifact_type, artifact)
    weak_before = detect_weak_sections(quality_before, preflight)
    loop = loop_shell(mode, preflight)
    loop["qualityBefore"] = quality_before
    loop["weakSectionsBefore"] = weak_before
    artifact["quality"] = quality_before

    if should_llm_rewrite(quality_before, preflight, mode, weak_before):
        original_artifact = dict(artifact)
        repaired = improve_sections_with_llm(
            artifact_type,
            artifact,
            quality_before,
            preflight,
            weak_before,
            mode=mode,
            **({"repair_budget": repair_budget} if artifact_type == "briefing" and repair_budget is not None else {}),
        )
        loop["warnings"].extend(repaired.get("warnings") or [])
        loop["repairReason"] = repaired.get("repairReason", "")
        if repaired.get("repairApplied"):
            candidate_artifact = dict(repaired.get("artifact") or artifact)
            quality_after = evaluate_artifact(artifact_type, candidate_artifact)
            weak_after = detect_weak_sections(quality_after, preflight)
            loop["repairType"] = "llm_section_rewrite"
            loop["changedSections"] = repaired.get("changedSections") or []
            if repaired.get("formatGuard"):
                loop["formatGuard"] = repaired.get("formatGuard")
            loop["llm"] = {
                "provider": repaired.get("provider", ""),
                "model": repaired.get("model", ""),
                "responseId": repaired.get("responseId", ""),
                "tokenUsage": repaired.get("tokenUsage") or {},
            }
            if _quality_regressed(quality_before, quality_after, weak_before, weak_after):
                artifact = original_artifact
                artifact["quality"] = quality_before
                loop["repairApplied"] = False
                loop["repairAttempted"] = True
                loop["repairCount"] = 0
                loop["repairReason"] = "llm_section_rewrite_quality_regression"
                loop["rejectedQualityAfter"] = quality_after
                loop["rejectedWeakSectionsAfter"] = weak_after
                loop["qualityAfter"] = quality_before
                loop["weakSectionsAfter"] = weak_before
                before_score = int(quality_before.get("score") or 0)
                after_score = int(quality_after.get("score") or 0)
                loop["warnings"].append(f"LLM 섹션 개선 후보가 품질 점수를 낮춰 적용하지 않았습니다({before_score} → {after_score}).")
            else:
                artifact = candidate_artifact
                loop["repairApplied"] = True
                loop["repairCount"] = 1
                loop["qualityAfter"] = quality_after
                loop["weakSectionsAfter"] = weak_after
                artifact["quality"] = quality_after
        else:
            loop["qualityAfter"] = quality_before
            loop["weakSectionsAfter"] = weak_before
    else:
        loop["qualityAfter"] = quality_before
        loop["weakSectionsAfter"] = weak_before
        if mode in {"llm_section_improve", "strict"} and weak_before:
            score = int(quality_before.get("score") or 0)
            if score > 80:
                loop["repairReason"] = "llm_section_rewrite_skipped_score_above_threshold"
                loop["warnings"].append(f"품질 점수 {score}점으로 LLM 섹션 개선 기준(80점 이하)을 넘어서 토큰 사용 없이 건너뛰었습니다.")

    after = loop["qualityAfter"] or {}
    if mode == "strict" and (after.get("status") != "pass" or int(after.get("score") or 0) < 85):
        loop["warnings"].append("엄격 검토 기준(A- / 85점 이상)을 완전히 통과하지 못했습니다. 저장 전 자료 보강을 검토하세요.")
    if preflight.get("status") == "fail":
        loop["warnings"].append("blocking dataGap 또는 입력 부족이 있어 자료 보강 없이는 품질 개선에 한계가 있습니다.")

    loop["telemetry"] = {
        "evidenceCoverage": evidence_coverage(artifact),
        "qualityBefore": {
            "score": quality_before.get("score"),
            "grade": quality_before.get("grade"),
            "status": quality_before.get("status"),
        },
        "qualityAfter": {
            "score": after.get("score"),
            "grade": after.get("grade"),
            "status": after.get("status"),
        },
        "weakSectionCountBefore": len(weak_before),
        "weakSectionCountAfter": len(loop.get("weakSectionsAfter") or []),
    }
    artifact["qualityGeneration"] = loop
    return artifact
