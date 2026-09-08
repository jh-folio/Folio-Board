"""Focused LLM rewrite for weak report sections."""
from __future__ import annotations

import json
import os

from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.common.utils import clean_brief_text
from features.llm_settings.client import extract_json_object, request_llm_text, selected_llm_config
from features.common.quality_generation.preflight_enrichment import build_preflight_evidence_context
from features.common.quality_generation.report_format import enforce_report_format, unwrap_markdown_payload
from features.common.quality_generation.telemetry import normalize_token_usage
from features.common.research_schema.data_gaps import data_gap_rows


PROMPT = """당신은 Folio Board의 투자 리서치 품질 편집자입니다.

목표:
- 기존 Canonical 보고서의 약한 섹션만 개선합니다.
- 새 출처, 새 숫자, 새 사실, 새 결론을 만들지 않습니다.
- 아래 sourceLedger/evidenceItems/dataGaps/quality warnings 범위 안에서만 씁니다.
- 사용자 노트나 userContext는 hypothesis이며 evidence가 아닙니다.
- 반론, 불확실성, 체크포인트, Source & Data Notes를 더 구체화하되 과장하지 않습니다.
- 원본 보고서의 제목/섹션 헤더/섹션 순서는 그대로 유지합니다.
- 브리핑, 기업분석, 테마분석의 필수 섹션을 삭제하거나 이름을 바꾸지 않습니다.

반환 형식:
JSON 객체 하나만 반환하세요.
{
  "markdown": "개선된 전체 Markdown",
  "changedSections": ["counterarguments", "checkpoints"],
  "notes": ["무엇을 왜 고쳤는지"]
}
"""


def _json_repair_prompt() -> str:
    return """You convert a model response into valid JSON for Folio Board.

Return only one JSON object:
{
  "markdown": "the full improved Markdown report",
  "changedSections": ["section ids"],
  "notes": ["short notes"]
}

If the input is Markdown rather than JSON, put the full Markdown into the
`markdown` field. Do not summarize or rewrite it."""


def _coerce_rewrite_payload(value: object) -> dict:
    """Normalize nested or stringified rewrite payloads into a dict."""
    if isinstance(value, dict):
        payload = dict(value)
    else:
        text = str(value or "").strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("LLM rewrite payload is not a JSON object")
    markdown = unwrap_markdown_payload(payload.get("markdown") or "")
    if markdown:
        payload["markdown"] = markdown
    return payload


def should_llm_rewrite(quality: dict | None, preflight: dict | None, mode: str, weak_sections: list[dict]) -> bool:
    if mode not in {"llm_section_improve", "strict"}:
        return False
    if not weak_sections:
        return False
    quality = quality or {}
    return int(quality.get("score") or 0) <= int(os.environ.get("QUALITY_LLM_REWRITE_MAX_SCORE", "80"))


def _rewrite_context(artifact_type: str, artifact: dict, quality: dict, preflight: dict, weak_sections: list[dict]) -> str:
    markdown = str(artifact.get("markdown") or "")
    compact_artifact = {
        "title": artifact.get("title") or artifact.get("headline") or artifact.get("topicLabel") or artifact.get("date") or "",
        "generation": artifact.get("generation") or {},
        "sources": (artifact.get("sources") or [])[:12],
        "sourceLedger": (artifact.get("sourceLedger") or [])[:18],
        "evidenceItems": (artifact.get("evidenceItems") or [])[:18],
        "dataGaps": data_gap_rows(artifact.get("dataGaps"))[:10],
        "marketTape": artifact.get("marketTape") or {},
    }
    evidence_block = build_preflight_evidence_context(
        artifact_type,
        preflight=preflight,
        artifact=compact_artifact,
    )
    payload = {
        "artifactType": artifact_type,
        "weakSections": weak_sections,
        "quality": {
            "score": quality.get("score"),
            "grade": quality.get("grade"),
            "status": quality.get("status"),
            "warnings": quality.get("warnings") or [],
            "suggestedFixes": quality.get("suggestedFixes") or [],
            "checks": quality.get("checks") or {},
        },
        "artifact": compact_artifact,
    }
    return "\n\n".join([
        "## Rewrite Request JSON",
        json.dumps(payload, ensure_ascii=False, indent=2),
        evidence_block,
        "## Current Markdown",
        markdown[: int(os.environ.get("QUALITY_SECTION_REWRITE_CONTEXT_CHARS", "18000"))],
        "",
        "중요: 전체 Markdown을 반환하되, weakSections와 직접 관련된 섹션만 바꾸세요.",
    ])


def _parse_rewrite_response(cfg: dict, text: str, *, max_tokens: int, allow_repair: bool = True) -> tuple[dict, dict, str]:
    """Parse section rewrite output, repairing common non-JSON responses once."""
    try:
        return _coerce_rewrite_payload(extract_json_object(text)), {}, ""
    except Exception:
        pass

    raw_text = str(text or "").strip()
    try:
        return _coerce_rewrite_payload(raw_text), {}, ""
    except Exception:
        pass

    if not allow_repair:
        raise ValueError("rewrite_json_invalid")
    repair_context = "\n\n".join([
        "Original model output:",
        raw_text[:16000],
        "",
        "Required JSON shape: {\"markdown\":\"...\", \"changedSections\":[], \"notes\":[]}",
    ])
    try:
        repaired, _repair_id, repair_usage = request_llm_text(
            cfg,
            _json_repair_prompt(),
            repair_context,
            web_search=False,
            max_output_tokens=min(max_tokens, 2200),
            json_mode=True,
            include_usage=True,
        )
        return _coerce_rewrite_payload(extract_json_object(repaired)), repair_usage, repaired
    except Exception:
        # Some providers ignore JSON mode on long markdown. If the original
        # response looks like a full report, use it as the improved markdown
        # instead of failing the whole quality pass.
        if len(raw_text) >= 800 and ("#" in raw_text[:200] or "\n## " in raw_text):
            return {
                "markdown": raw_text,
                "changedSections": ["unstructured_markdown_fallback"],
                "notes": ["모델이 JSON 대신 Markdown을 반환해 Markdown 본문을 직접 적용했습니다."],
            }, {}, raw_text
        raise


def improve_sections_with_llm(
    artifact_type: str,
    artifact: dict,
    quality: dict,
    preflight: dict,
    weak_sections: list[dict],
    *,
    mode: str,
    repair_budget=None,
) -> dict:
    artifact = dict(artifact or {})
    generation = artifact.get("generation") or {}
    if generation.get("mode") != "llm":
        return {
            "artifact": artifact,
            "repairApplied": False,
            "repairReason": "llm_section_rewrite_skipped_non_llm_generation",
            "warnings": ["LLM 섹션 개선은 LLM으로 생성된 보고서에만 적용했습니다."],
        }
    cfg = selected_llm_config()
    if not cfg.get("enabled"):
        return {"artifact": artifact, "repairApplied": False, "repairReason": "llm_disabled", "warnings": ["LLM 설정이 꺼져 있어 섹션 개선을 건너뜁니다."]}
    if not cfg.get("apiKey"):
        return {"artifact": artifact, "repairApplied": False, "repairReason": f"missing_{cfg.get('provider')}_api_key", "warnings": ["선택한 LLM Provider API 키가 없어 섹션 개선을 건너뜁니다."]}

    max_tokens = int(os.environ.get("QUALITY_SECTION_REWRITE_MAX_OUTPUT_TOKENS", "4500"))
    context = _rewrite_context(artifact_type, artifact, quality, preflight, weak_sections)
    request_options = {}
    if artifact_type == "briefing":
        if repair_budget is None:
            from features.common.quality_generation.call_budget import SharedRepairBudget, current_briefing_budget
            import time
            repair_budget = current_briefing_budget() or SharedRepairBudget(deadline=time.monotonic() + 60)
        repair_budget.check_active()
        try:
            repair_budget.claim("quality")
        except RuntimeError:
            return {"artifact": artifact, "repairApplied": False, "repairReason": "shared_repair_budget_exhausted", "warnings": []}
        request_options["timeout_seconds"] = repair_budget.remaining_seconds()
    try:
        text, response_id, usage = request_llm_text(
            cfg,
            PROMPT,
            context,
            web_search=False,
            max_output_tokens=max_tokens,
            json_mode=True,
            include_usage=True,
            **request_options,
        )
        if artifact_type == "briefing":
            repair_budget.check_active()
        raw, repair_usage, repaired_text = _parse_rewrite_response(cfg, text, max_tokens=max_tokens, allow_repair=artifact_type != "briefing")
        markdown = str(raw.get("markdown") or "").strip()
        if len(markdown) < 400:
            return {"artifact": artifact, "repairApplied": False, "repairReason": "llm_section_rewrite_empty", "warnings": ["LLM 섹션 개선 결과가 너무 짧아 적용하지 않았습니다."]}
        guard = enforce_report_format(artifact_type, str(artifact.get("markdown") or ""), markdown)
        if guard.mode == "rejected":
            return {
                "artifact": artifact,
                "repairApplied": False,
                "repairReason": "llm_section_rewrite_format_rejected",
                "changedSections": [],
                "notes": raw.get("notes") if isinstance(raw.get("notes"), list) else [],
                "responseId": response_id,
                "provider": cfg.get("provider", ""),
                "model": cfg.get("model", ""),
                "tokenUsage": normalize_token_usage(usage, prompt=PROMPT, context=context, output=text, max_output_tokens=max_tokens),
                "repairTokenUsage": normalize_token_usage(repair_usage, prompt=_json_repair_prompt(), context=text, output=repaired_text, max_output_tokens=min(max_tokens, 2200)) if repair_usage else {},
                "warnings": guard.warnings + [f"형식 검사: {issue}" for issue in guard.issues[:3]],
            }
        markdown = guard.markdown
        if artifact_type == "briefing":
            from features.common.quality_generation.repair_grounding import preserves_briefing_input
            if not preserves_briefing_input(artifact.get("markdown", ""), markdown, artifact.get("sources") or []):
                return {"artifact": artifact, "repairApplied": False, "repairReason": "rewrite_outside_input", "warnings": []}
        updated = {**artifact, "markdown": markdown}
        updated["checkpoints"] = checkpoints_from_markdown(
            markdown,
            artifact_type=artifact_type,
            artifact_id=str(updated.get("id") or updated.get("date") or ""),
            headings=["다음 체크포인트", "앞으로 확인할 체크포인트", "체크포인트"],
            scope="company" if artifact_type == "company_analysis" else "market",
            topic=str(updated.get("title") or updated.get("headline") or updated.get("topicLabel") or ""),
        ) or updated.get("checkpoints") or []
        return {
            "artifact": updated,
            "repairApplied": True,
            "repairReason": "llm_section_rewrite" if guard.mode == "full_markdown" else "llm_section_rewrite_format_preserved",
            "changedSections": raw.get("changedSections") if isinstance(raw.get("changedSections"), list) else [s.get("section") for s in weak_sections],
            "notes": raw.get("notes") if isinstance(raw.get("notes"), list) else [],
            "responseId": response_id,
            "provider": cfg.get("provider", ""),
            "model": cfg.get("model", ""),
            "tokenUsage": normalize_token_usage(usage, prompt=PROMPT, context=context, output=text, max_output_tokens=max_tokens),
            "repairTokenUsage": normalize_token_usage(repair_usage, prompt=_json_repair_prompt(), context=text, output=repaired_text, max_output_tokens=min(max_tokens, 2200)) if repair_usage else {},
            "formatGuard": {"mode": guard.mode, "issues": guard.issues[:6]},
            "warnings": guard.warnings,
        }
    except Exception:
        if artifact_type == "briefing":
            repair_budget.check_active()
        return {
            "artifact": artifact,
            "repairApplied": False,
            "repairReason": "llm_section_rewrite_error",
            "warnings": ["LLM 섹션 개선에 실패했습니다."],
        }
