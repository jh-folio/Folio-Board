"""Agent 채팅 실연결 + Task Mode 수정 제안(diff)·승인 writeback.

- Companion 질문은 현재 화면 컨텍스트(보고서 본문 발췌·첨부·노력 단계)를 붙여
  실제 Agent CLI(Codex/Claude)로 답한다. CLI가 없으면 규칙 기반 안내로 fallback.
- Task 의도 + 저장 보고서 컨텍스트면 CLI에 전체 수정본을 받아 unified diff와 함께
  제안(proposal)으로 저장하고, 사용자가 승인해야만 Canonical markdown을 바꾼다.
- 첨부파일·사용자 메시지는 hypothesis 입력이다. evidence로 승격하지 않는다.
"""
from __future__ import annotations

import difflib
import functools
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import assert_never

from features.agent_mode import bridge
from features.agent_mode.attachment_files import StagedImages, image_block
from features.agent_mode.companion import (
    agent_companion_reply,
    classify_agent_intent,
    normalize_agent_context,
    normalize_agent_options,
    public_options,
)
from features.agent_mode.collection_context import prepare_agent_context, render_collection_projection
from features.smart_collections.service import SmartCollectionService
from features.agent_mode.market_state_context import (
    MarketStateSelection,
    project_market_state,
    render_market_state_projection,
)
from features.agent_mode.proposal_schema import ProposalAction
from features.agent_mode.proposal_service import (
    ProposalActionError,
    ProposalPaths,
    act_on_proposal,
    create_proposal,
    get_proposal as get_stored_proposal,
    recover_all,
)
from features.common.canonical_reports import (
    CanonicalIdentityError,
    CanonicalNotFoundError,
    ReportKind,
    resolve_exact_report_path,
)
from features.common.jobs import current_diagnostic_recorder, diagnostic_stage_failure, submit_job
from features.common.markets import market_keys_for_scope, normalize_saved_market_scope
from features.common.utils import read_json
from features.market_memory.attempt_store import AttemptStore
from features.market_memory.market_state_ref import MarketStateRefQuery
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
PROPOSALS_DIR = DATA_DIR / "agent-proposals"
BRIEFINGS_DIR = DATA_DIR / "briefings"
ANALYSIS_DIR = DATA_DIR / "company-analysis"
TOPIC_DIR = DATA_DIR / "topic-reports"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"
RESEARCH_INDEX_PATH = DATA_DIR / "research-index.sqlite3"

REVISABLE_KINDS = {"briefing", "company_analysis", "topic_report"}
MAX_REPORT_PROMPT_CHARS = 24_000
MAX_DIFF_LINES = 400
PROPOSAL_PHASE_HOOK = lambda _phase: None

EFFORT_HINTS = {
    "low": "간결하게 핵심만 3~5문장으로 답한다.",
    "medium": "핵심 근거와 함께 균형 있게 답한다.",
    "high": "근거·반론·확인 포인트까지 깊이 있게 답한다.",
    "max": "가능한 모든 관점(근거, 반론, 리스크, 체크포인트)을 검토해 답한다.",
}


def _market_state_now() -> datetime:
    return datetime.now(timezone.utc)


def _market_state_query() -> MarketStateRefQuery:
    state = AttemptStore(MARKET_MEMORY_DB_PATH.parent / "market-state-update-attempts.json").load()
    attempts = tuple(row.model_dump(mode="json") for row in state.attempts)
    return MarketStateRefQuery(
        MARKET_MEMORY_DB_PATH,
        RESEARCH_INDEX_PATH,
        "GLOBAL",
        _market_state_now(),
        attempts,
    )


def resolve_artifact_path(kind: str, report_id: str, market_scope: str = "") -> Path | None:
    """대화 컨텍스트의 보고서를 저장 파일로 매핑한다. 못 찾으면 None."""
    try:
        report_kind = ReportKind(kind)
    except ValueError:
        return None
    match report_kind:
        case ReportKind.BRIEFING:
            data_root = BRIEFINGS_DIR.parent
        case ReportKind.COMPANY_ANALYSIS:
            data_root = ANALYSIS_DIR.parent
        case ReportKind.TOPIC_REPORT:
            data_root = TOPIC_DIR.parent
        case unreachable:
            assert_never(unreachable)
    scope = str(market_scope or "").strip().lower()
    exact_scope = scope if report_kind == ReportKind.BRIEFING and scope in {"us", "kr", "europe", "jp"} else None
    try:
        return resolve_exact_report_path(data_root, report_kind, str(report_id or ""), exact_scope)
    except (CanonicalIdentityError, CanonicalNotFoundError):
        return None


def load_artifact(kind: str, report_id: str, market_scope: str = "") -> tuple[Path | None, dict | None]:
    path = resolve_artifact_path(kind, report_id, market_scope)
    if not path:
        return None, None
    data = read_json(path, None)
    if not isinstance(data, dict) or not str(data.get("markdown") or "").strip():
        return None, None
    return path, data


def _attachment_block(options: dict) -> str:
    parts = []
    for item in options.get("attachments") or []:
        name = item.get("name", "")
        content = str(item.get("content") or "").strip()
        if content:
            parts.append(f"[첨부: {name}]\n```\n{content}\n```")
        elif str(item.get("imageData") or "").strip():
            # 이미지는 별도 블록이 파일 경로로 싣는다. 여기서 "본문 미포함"이라고
            # 적으면 CLI가 읽을 수 있는 첨부를 못 읽는다고 말하게 된다.
            continue
        else:
            parts.append(f"[첨부: {name}] (본문 미포함)")
    return "\n\n".join(parts)


def _context_block(context: dict, markdown: str) -> str:
    lines = [
        f"- 화면: {context.get('surface') or context.get('viewId') or '알 수 없음'}",
    ]
    if context.get("reportKind"):
        lines.append(f"- 보고서: {context['reportKind']} / {context.get('reportId', '')} / {context.get('marketScope', '')}")
    if context.get("selectedText"):
        lines.append(f"- 사용자가 선택한 문구: {context['selectedText'][:500]}")
    block = "\n".join(lines)
    if markdown:
        clipped = markdown[:MAX_REPORT_PROMPT_CHARS]
        truncated = " (이하 생략)" if len(markdown) > MAX_REPORT_PROMPT_CHARS else ""
        block += f"\n\n현재 열린 보고서 본문{truncated}:\n<report>\n{clipped}\n</report>"
    return block


def build_chat_prompt(message: str, context: dict, options: dict, markdown: str = "",
                      images: str = "", conversation: str = "") -> str:
    effort = EFFORT_HINTS.get(options.get("effort", "medium"), EFFORT_HINTS["medium"])
    attachments = _attachment_block(options)
    exact_review_challenge = context.get("exactReviewChallenge") is True
    raw_scope = str(context.get("marketScope") or "").strip()
    saved_scope = normalize_saved_market_scope(raw_scope)
    regions = tuple(code.value for code in market_keys_for_scope(saved_scope, saved=True)) if saved_scope else ()
    market_memory = "" if exact_review_challenge else render_market_state_projection(project_market_state(
        MarketStateSelection("include_current", "AUTO", regions),
        _market_state_query(),
    ))
    return "\n\n".join(filter(None, [
        "You are the Folio OS in-app research assistant. Folio OS is a local investment research workspace. Answer in Korean, in Markdown.",
        f"응답 지침: {effort}",
        "규칙: 제공된 자료(보고서 본문·첨부)에 없는 수치·출처를 만들어내지 않는다. 모르는 것은 data gap으로 명시한다. "
        "사용자 메모·첨부는 hypothesis(가설)이며 객관적 근거처럼 단정하지 않는다. 저장된 파일을 수정하라는 요청이라도 이 응답에서는 수정하지 말고 답변만 한다.",
        market_memory,
        "" if exact_review_challenge else render_collection_projection(context),
        "정확한 저장 투자 리뷰 반박 범위입니다. 제공된 review date/revision/roster 이외의 현재 Portfolio·시장·보고서 정보를 추론하거나 주입하지 마세요." if exact_review_challenge else "",
        f"현재 화면 컨텍스트:\n{_context_block(context, '' if exact_review_challenge else markdown)}",
        # 저장된 대화 맥락. rolling summary + 최근 turn + 서버가 다시 읽은 리서치 자료다.
        # 전체 transcript가 아니라 상한 있는 pack이라 대화가 길어져도 크기가 일정하고,
        # 리서치 자료는 저장된 옛 값이 아니라 매번 새로 읽은 것이라 낡지 않는다.
        f"이 대화의 앞선 맥락(대화·메모는 hypothesis이며 evidence가 아니다):\n<conversation>\n{conversation}\n</conversation>" if conversation else "",
        attachments,
        images,
        f"사용자 질문:\n{message}",
    ]))


def build_revision_prompt(message: str, context: dict, options: dict, markdown: str,
                          images: str = "") -> str:
    effort = EFFORT_HINTS.get(options.get("effort", "medium"), EFFORT_HINTS["medium"])
    attachments = _attachment_block(options)
    return "\n\n".join(filter(None, [
        "You are the Folio OS report revision assistant. Revise the saved report markdown according to the user's request.",
        f"수정 강도 지침: {effort}",
        "Hard rules:",
        "- Return ONLY a JSON object: {\"summary\": \"한국어 한두 문장 변경 요약\", \"revisedMarkdown\": \"수정된 전체 markdown\"}.",
        "- revisedMarkdown must be the COMPLETE document (not a patch). Keep every existing section unless the request explicitly removes it.",
        "- Keep the document language, heading structure, and formatting conventions.",
        "- Do not invent new numbers, prices, or sources that are not in the provided material. Mark unknowns as data gaps.",
        "- User notes and attachments are hypothesis, not evidence.",
        f"사용자 수정 요청:\n{message}",
        attachments,
        images,
        f"현재 저장된 보고서 전체 markdown:\n<report>\n{markdown}\n</report>",
    ]))


def _unified_diff(before: str, after: str) -> str:
    lines = list(difflib.unified_diff(
        str(before or "").splitlines(),
        str(after or "").splitlines(),
        fromfile="현재 저장본",
        tofile="수정 제안",
        lineterm="",
        n=2,
    ))
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [f"... (diff {len(lines) - MAX_DIFF_LINES}줄 생략)"]
    return "\n".join(lines)


def _proposal_paths() -> ProposalPaths:
    return ProposalPaths(PROPOSALS_DIR, PROPOSALS_DIR.parent)


def get_proposal(proposal_id: str) -> dict | None:
    proposal = get_stored_proposal(_proposal_paths(), str(proposal_id or ""))
    return proposal.model_dump(mode="json", exclude_none=True) if proposal is not None else None


def create_revision_proposal(*, kind: str, report_id: str, market_scope: str, message: str,
                             summary: str, revised_markdown: str, current_markdown: str,
                             adapter: str = "", model: str = "") -> dict:
    diff = _unified_diff(current_markdown, revised_markdown)
    proposal = create_proposal(
        _proposal_paths(),
        kind=kind,
        report_id=report_id,
        market_scope=market_scope,
        message=message,
        summary=summary,
        revised_markdown=revised_markdown,
        current_markdown=current_markdown,
        diff=diff,
        adapter=adapter,
        model=model,
    )
    projected = proposal.model_dump(mode="json", exclude_none=True)
    projected["artifactKind"] = projected["reportKind"]
    projected["artifactId"] = projected["reportId"]
    return projected


def apply_proposal(proposal_id: str) -> dict:
    return act_on_proposal(_proposal_paths(), proposal_id, ProposalAction.APPROVE, PROPOSAL_PHASE_HOOK)


def reject_proposal(proposal_id: str) -> dict:
    return act_on_proposal(_proposal_paths(), proposal_id, ProposalAction.REJECT, PROPOSAL_PHASE_HOOK)


def recover_proposals() -> int:
    return recover_all(_proposal_paths(), PROPOSAL_PHASE_HOOK)


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _clean_cli_error(error: Exception) -> str:
    text = _ANSI_RE.sub("", str(error))
    # CLI 배너/헤더를 걷어내고 실제 오류 줄을 우선 보여준다.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if "ERROR:" in line:
            return line.replace("ERROR:", "").strip()[:400]
    return text[-400:]


def _revision_payload(output: str) -> dict:
    payload = bridge._json_payload(output)
    revised = str(payload.get("revisedMarkdown") or "").strip()
    if not revised:
        raise ValueError("Agent가 수정된 markdown을 반환하지 않았습니다.")
    return {"summary": str(payload.get("summary") or "").strip(), "revisedMarkdown": revised}


def _run_with_images(build_prompt, options: dict, *, model: str, job_id: str) -> dict:
    """Run the CLI while the attached images exist on disk, then remove them.

    The scratch files must outlive prompt building and the CLI call and nothing
    else, so their lifetime is scoped to exactly this call — cleanup runs on
    success, on CLI failure, and on cancellation alike.

    `options["adapter"]`가 있으면 이 대화만 그 CLI로 돌린다. 비어 있으면
    `_select_adapter("")`가 설정의 전역 기본을 고른다.
    """
    with StagedImages(options.get("attachments")) as staged:
        prompt = build_prompt(image_block(staged))
        return bridge.run_agent_prompt(
            prompt, adapter=options.get("adapter", ""), model=model, job_id=job_id,
        )


def run_agent_chat(message: str, context: dict | None = None, options: dict | None = None,
                   *, progress=None, job_id: str = "",
                   collection_service: SmartCollectionService | None = None,
                   prepared_context: bool = False, conversation: str = "", exact_review_challenge: bool = False) -> dict:
    progress = progress or (lambda *args, **kwargs: None)
    normalized = (
        dict(context or {})
        if prepared_context
        else prepare_agent_context(context, collection_service)
    )
    # This is server-owned job scope, never a raw client context flag.  It is
    # set after normalisation so collection/report fields cannot revive it.
    if exact_review_challenge:
        normalized["exactReviewChallenge"] = True
    collection_projection = normalized.get("collection")
    normalized_options = normalize_agent_options(options)
    intent = classify_agent_intent(message)

    # CLI가 없으면 기존 규칙 기반 companion 응답으로 fallback(LLM 없이도 동작 원칙).
    status = bridge.bridge_status()
    if not status.get("available"):
        fallback = agent_companion_reply(
            message, normalized, normalized_options, collection_projection=collection_projection
        )
        fallback["engine"] = "rules"
        fallback["reply"] = fallback.pop("message", "")
        fallback["notice"] = " ".join(filter(None, [
            status.get("message") or "Agent CLI를 사용할 수 없어 규칙 기반으로 답합니다.",
            # 이미지를 읽는 것은 CLI뿐이다. 조용히 무시하면 사용자는 첨부가 반영된 줄 안다.
            image_block(StagedImages(normalized_options.get("attachments")), cli_available=False),
        ]))
        from features.common.jobs import diagnostic_execution

        diagnostic_execution(final_engine="rules", fallback_reason="engine_unavailable")
        return fallback

    kind = normalized.get("reportKind", "")
    path, artifact = (None, None)
    if kind in REVISABLE_KINDS:
        path, artifact = load_artifact(kind, normalized.get("reportId", ""), normalized.get("marketScope", ""))
    markdown = (artifact or {}).get("markdown", "")

    adapter = ""
    if intent == "task" and artifact is not None:
        progress("보고서 수정안을 작성하고 있습니다.", 20)
        try:
            result = _run_with_images(
                lambda images: build_revision_prompt(message, normalized, normalized_options, markdown, images),
                normalized_options,
                model=normalized_options.get("model", ""),
                job_id=job_id,
            )
        except Exception as exc:
            # 수정안 생성 실패는 사용자가 알아야 하므로 정리된 메시지로 실패시킨다.
            raise RuntimeError(f"Agent 수정안 생성 실패: {_clean_cli_error(exc)}") from exc
        adapter = result["adapter"]
        payload = _revision_payload(result["output"])
        if payload["revisedMarkdown"].strip() == str(markdown or "").strip():
            return {
                "ok": True,
                "mode": "companion",
                "engine": "cli",
                "adapter": adapter,
                "reply": "요청을 검토했지만 실제로 바꿀 내용이 없다고 판단했습니다. 더 구체적으로 요청해 주세요.",
                "context": normalized,
                "options": public_options(normalized_options),
            }
        progress("수정 제안 diff를 준비하고 있습니다.", 80)
        proposal = create_revision_proposal(
            kind=kind,
            report_id=normalized.get("reportId", ""),
            market_scope=normalized.get("marketScope", ""),
            message=message,
            summary=payload["summary"],
            revised_markdown=payload["revisedMarkdown"],
            current_markdown=markdown,
            adapter=adapter,
            model=normalized_options.get("model", ""),
        )
        return {
            "ok": True,
            "mode": "task",
            "engine": "cli",
            "adapter": adapter,
            "reply": payload["summary"] or "보고서 수정안을 준비했습니다. diff를 확인하고 승인해 주세요.",
            "proposal": {
                "id": proposal["id"],
                "summary": proposal["summary"],
                "diff": proposal["diff"],
                "artifactKind": proposal["artifactKind"],
                "artifactId": proposal["artifactId"],
                "marketScope": proposal["marketScope"],
            },
            "context": normalized,
            "options": public_options(normalized_options),
        }

    progress("Agent가 답변을 작성하고 있습니다.", 30)
    # Calling the bridge is the concrete execution attempt.  The selected
    # adapter is observed only after the bridge has verified it.
    from features.common.jobs import diagnostic_execution

    diagnostic_execution(attempted_engine="cli")
    try:
        result = _run_with_images(
            lambda images: build_chat_prompt(message, normalized, normalized_options, markdown, images, conversation),
            normalized_options,
            model=normalized_options.get("model", ""),
            job_id=job_id,
        )
    except Exception as exc:
        # 질문형은 규칙 기반으로 답을 이어가고, CLI 실패 사유는 정리해서 알려준다.
        # The fallback is an existing user-visible contract.  Record the
        # concrete executor failure before swallowing it, without retaining
        # the prompt, transcript, or provider message.
        diagnostic_stage_failure(
            current_diagnostic_recorder(),
            exc,
            stage_id=None,
            stage_code="generate",
            boundary="adapter",
        )
        diagnostic_execution(final_engine="rules", fallback_reason="engine_failed")
        fallback = agent_companion_reply(
            message, normalized, normalized_options, collection_projection=collection_projection
        )
        fallback["engine"] = "rules"
        fallback["reply"] = fallback.pop("message", "")
        fallback["notice"] = f"Agent CLI 실행 실패로 규칙 기반으로 답합니다: {_clean_cli_error(exc)}"
        return fallback
    reply = result["output"]
    notice = ""
    if intent == "task" and artifact is None and kind in REVISABLE_KINDS:
        notice = "저장된 보고서를 찾지 못해 수정 대신 답변만 제공합니다. 보고서를 연 상태에서 다시 요청해 주세요."
    elif intent == "task":
        notice = "보고서를 연 상태에서 요청하면 수정안(diff)을 만들어 승인 후 반영할 수 있습니다."
    return {
        "ok": True,
        "mode": "companion",
        "engine": "cli",
        "adapter": result["adapter"],
        "reply": reply,
        "notice": notice,
        "context": normalized,
        "options": public_options(normalized_options),
    }


def submit_agent_chat(message: str, context: dict | None = None, options: dict | None = None,
                      *, collection_service: SmartCollectionService | None = None,
                      prepared_context: bool = False) -> dict:
    runner = functools.partial(
        run_agent_chat,
        collection_service=collection_service,
        prepared_context=prepared_context,
    )
    job = submit_job(
        "agent_bridge",
        "Agent 채팅",
        runner,
        message,
        context or {},
        options or {},
        pass_job_id=True,
        dedicated_thread=True,
    )
    job["generationMode"] = "llm_cli"
    return job
