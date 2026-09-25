"""API facade for quality-improving generation."""
from __future__ import annotations

from features.common.quality_generation.loop import apply_quality_loop
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.schema import normalize_quality_mode


def preflight_payload(body: dict | None = None) -> dict:
    body = body or {}
    artifact_type = str(body.get("artifactType") or body.get("artifact_type") or "topic_report")
    return {"preflight": preflight_from_context(artifact_type, body.get("artifact") or {}, body.get("context") or {})}


def repair_payload(body: dict | None = None) -> dict:
    body = body or {}
    artifact_type = str(body.get("artifactType") or body.get("artifact_type") or "topic_report")
    artifact = body.get("artifact") or {}
    preflight = body.get("preflight") or preflight_from_context(artifact_type, artifact, body.get("context") or {})
    updated = apply_quality_loop(
        artifact_type,
        artifact,
        mode="llm_section_improve",
        preflight=preflight,
        context=body.get("context") or {},
        allow_briefing_repair=artifact_type == "briefing",
    )
    return {
        "artifact": updated,
        "repairApplied": (updated.get("qualityGeneration") or {}).get("repairApplied", False),
        "repairReason": (updated.get("qualityGeneration") or {}).get("repairReason", ""),
        "qualityGeneration": updated.get("qualityGeneration") or {},
    }


def run_payload(body: dict | None = None) -> dict:
    body = body or {}
    artifact_type = str(body.get("artifactType") or body.get("artifact_type") or "topic_report")
    mode = normalize_quality_mode(body.get("qualityMode") or body.get("mode"))
    artifact = apply_quality_loop(
        artifact_type,
        body.get("artifact") or {},
        mode=mode,
        preflight=body.get("preflight"),
        context=body.get("context") or {},
    )
    return {"artifact": artifact, "quality": artifact.get("quality"), "qualityGeneration": artifact.get("qualityGeneration")}
