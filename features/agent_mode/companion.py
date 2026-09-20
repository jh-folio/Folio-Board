from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from features.agent_mode.schema import scrub_secrets
from features.common.markets import normalize_saved_market_scope
from features.smart_collections.schema import COLLECTION_ID_PATTERN

SAFE_CONTEXT_FIELDS = {
    "surface",
    "viewId",
    "reportKind",
    "reportId",
    "marketScope",
    "selectedText",
    "visibleSection",
    "portfolioLinked",
}


class AgentCollectionIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    collectionId: str = Field(pattern=f"^{COLLECTION_ID_PATTERN.pattern}$")
    collectionRevision: int = Field(ge=1, strict=True)


class OptionalAgentCollectionIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    collectionId: str | None = None
    collectionRevision: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def require_complete_pair(self):
        if (self.collectionId is None) != (self.collectionRevision is None):
            raise ValueError("collection_identity_pair_required")
        if self.collectionId is not None:
            AgentCollectionIdentity.model_validate(self.model_dump())
        return self

TASK_VERBS = (
    "수정",
    "추가",
    "다시 써",
    "재작성",
    "보강",
    "생성",
    "업데이트",
    "정리해줘",
    "설정",
    "자동화",
    "writeback",
    "rewrite",
    "revise",
    "update",
    "create",
    "schedule",
)


def normalize_agent_context(raw: dict | None) -> dict:
    raw = scrub_secrets(raw or {})
    identity = OptionalAgentCollectionIdentity.model_validate({
        "collectionId": raw.get("collectionId"),
        "collectionRevision": raw.get("collectionRevision"),
    })
    out = {}
    for field in SAFE_CONTEXT_FIELDS:
        value = raw.get(field)
        if field == "portfolioLinked":
            out[field] = bool(value)
        else:
            out[field] = str(value or "").strip()[:2000]
    out.setdefault("portfolioLinked", False)
    normalized = {
        "surface": out.get("surface", ""),
        "viewId": out.get("viewId", ""),
        "reportKind": out.get("reportKind", ""),
        "reportId": out.get("reportId", ""),
        "marketScope": (
            scope.value
            if (scope := normalize_saved_market_scope(out.get("marketScope", ""))) is not None
            else ""
        ),
        "selectedText": out.get("selectedText", ""),
        "visibleSection": out.get("visibleSection", ""),
        "portfolioLinked": bool(out.get("portfolioLinked")),
    }
    if identity.collectionId is not None:
        normalized["collectionId"] = identity.collectionId
        normalized["collectionRevision"] = identity.collectionRevision
    return normalized


def classify_agent_intent(message: str) -> str:
    text = str(message or "").strip().lower()
    if any(verb in text for verb in TASK_VERBS):
        return "task"
    return "companion"


VALID_EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max", "ultra"}

# Agent Dock Stage D. Default `off` so an existing conversation's saved
# options (or a client that never sends this key) keep today's behavior —
# no network change until a caller explicitly asks for `auto`/`on`.
VALID_SEARCH_POLICIES = {"off", "auto", "on"}


# 대화별로 고를 수 있는 CLI. `bridge.ADAPTERS`와 같은 집합이며, 여기서 다시 적어 두는
# 이유는 이 모듈이 bridge를 import하지 않기 때문이다(순환).
CHAT_ADAPTERS = frozenset({"codex", "claude", "antigravity"})


def normalize_agent_options(raw: dict | None) -> dict:
    """채팅 도구 옵션(모델 버전·노력 단계·첨부파일)을 코드에서 정규화한다.

    첨부파일 본문은 hypothesis/참고 입력일 뿐 evidence로 승격하지 않는다.
    """
    raw = raw if isinstance(raw, dict) else {}
    # `responseDepth` is the canonical name (Agent Dock Stage B) — `effort` is
    # a read-compat alias so existing saved options/clients keep working.
    # Whichever is valid wins; `responseDepth` wins if both are given.
    depth_candidate = str(raw.get("responseDepth") or "").strip().lower()
    effort_candidate = str(raw.get("effort") or "").strip().lower()
    effort = depth_candidate if depth_candidate in VALID_EFFORT_LEVELS else effort_candidate
    attachments = []
    for item in (raw.get("attachments") or [])[:5]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:120]
        if not name:
            continue
        try:
            size = max(0, int(item.get("size") or 0))
        except (TypeError, ValueError):
            size = 0
        row = {
            "name": name,
            "size": size,
            "content": str(item.get("content") or "")[:4000],
        }
        # 이미지 바이트는 프롬프트에 넣지 않고 임시 파일로 내려 CLI가 직접 읽는다
        # (features/agent_mode/attachment_files.py). 여기서는 통과만 시킨다.
        image_data = str(item.get("imageData") or "")
        if image_data:
            row["imageData"] = image_data
        attachments.append(row)
    # 이 대화만 다른 CLI로 돌리고 싶을 때 쓴다. 비어 있으면 설정의 전역 기본을 따른다.
    # 아는 어댑터가 아니면 무시한다 — 틀린 이름으로 전역 기본까지 못 쓰게 되면 안 된다.
    adapter = str(raw.get("adapter") or "").strip().lower()
    resolved_depth = effort if effort in VALID_EFFORT_LEVELS else "medium"
    search_policy = str(raw.get("searchPolicy") or "").strip().lower()
    return {
        "model": str(raw.get("model") or "").strip()[:80],
        # Both keys carry the same resolved value so existing readers of
        # `effort` (e.g. chat.py's EFFORT_HINTS) keep working unchanged.
        "effort": resolved_depth,
        "responseDepth": resolved_depth,
        "adapter": adapter if adapter in CHAT_ADAPTERS else "",
        "searchPolicy": search_policy if search_policy in VALID_SEARCH_POLICIES else "off",
        "attachments": attachments,
    }


def public_options(options: dict) -> dict:
    """Options as they may be stored and returned — never the image bytes.

    A chat result is persisted to `data/jobs.json` and echoed to the client, so
    passing raw options straight through would write an attached screenshot to
    disk under a different name than the screenshot contract forbids.
    """
    rows = []
    for item in (options or {}).get("attachments") or []:
        row = {key: value for key, value in item.items() if key != "imageData"}
        if str(item.get("imageData") or "").strip():
            row["hasImage"] = True
        rows.append(row)
    return {**(options or {}), "attachments": rows}


def _surface_actions(context: dict) -> list[dict]:
    report_kind = context.get("reportKind", "")
    view_id = context.get("viewId", "")
    actions = [
        {"id": "explain_counterpoints", "label": "반대 근거 보기", "requiresApproval": False},
        {"id": "portfolio_impact", "label": "포트폴리오 영향 보기", "requiresApproval": False},
    ]
    if report_kind in {"briefing", "company_analysis", "topic_report"}:
        actions.append({"id": "create_personal_overlay", "label": "Personal Overlay 생성", "requiresApproval": True})
    if view_id in {"memory", "market_memory"}:
        actions.append({"id": "refresh_market_memory_digest", "label": "Market Memory 최신화", "requiresApproval": True})
    return actions


def agent_companion_reply(message: str, context: dict | None = None, options: dict | None = None,
                          *, collection_projection: dict | None = None) -> dict:
    normalized = normalize_agent_context(context)
    if collection_projection is not None:
        normalized["collection"] = collection_projection
    normalized_options = normalize_agent_options(options)
    mode = classify_agent_intent(message)
    if mode == "task":
        return {
            "ok": True,
            "mode": "task",
            "message": "작업 요청으로 이해했습니다. 실행 전에 계획과 저장될 대상을 먼저 확인해야 합니다.",
            "context": normalized,
            "options": public_options(normalized_options),
            "actions": _surface_actions(normalized),
            "requiresApproval": True,
            "writeback": None,
        }
    return {
        "ok": True,
        "mode": "companion",
        "message": "현재 화면을 기준으로 질문에 답할 준비가 되어 있습니다. 저장된 보고서나 메모리는 사용자가 승인하기 전에는 변경하지 않습니다.",
        "context": normalized,
        "options": public_options(normalized_options),
        "actions": _surface_actions(normalized),
        "requiresApproval": False,
        "writeback": None,
    }
