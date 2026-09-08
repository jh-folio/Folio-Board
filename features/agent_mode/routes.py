from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from features.agent_mode.collection_context import prepare_agent_context
from features.agent_mode.chat import submit_agent_chat
from features.agent_mode.companion import agent_companion_reply
from features.agent_mode.investment_context import (
    InvestmentExplanationRequest,
    default_evidence_loader,
)
from features.agent_mode.service import submit_investment_explanation
from features.investment_review.service import InvestmentContextRuntime, InvestmentContextService
from features.smart_collections.routes import failure_response
from features.smart_collections.service import CollectionServiceError, SmartCollectionService
from features.smart_collections.store import CollectionStoreUnavailableError
from features.agent_mode.consultation_store import (
    ConsultationNotEmptyError,
    append_user_message,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from features.agent_mode.job_runtime import submit_consultation_job
from features.agent_mode.consultation_schema import NOTE_TYPES
from features.investment_notes.service import save_note


class AgentCompanionBoundary:
    def __init__(
        self,
        collection_service: SmartCollectionService,
        *,
        data_dir: Path | None = None,
        investment_context_service=None,
        evidence_loader=None,
    ) -> None:
        self.collection_service = collection_service
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.investment_context_service = investment_context_service
        self.evidence_loader = evidence_loader
        if self.investment_context_service is None and data_dir is not None:
            self.investment_context_service = InvestmentContextService(
                InvestmentContextRuntime(
                    dataDir=data_dir,
                    clock=lambda: datetime.now(UTC),
                    collectionService=collection_service,
                )
            )
        if self.evidence_loader is None and data_dir is not None:
            self.evidence_loader = default_evidence_loader(data_dir)

    def companion(self, body: dict | None = Body(default=None)):
        body = body or {}
        try:
            context = prepare_agent_context(body.get("context") or {}, self.collection_service)
        except (ValidationError, CollectionServiceError, CollectionStoreUnavailableError) as error:
            return failure_response(error)
        projection = context.pop("collection", None)
        return agent_companion_reply(
            body.get("message", ""),
            context,
            body.get("options") or {},
            collection_projection=projection,
        )

    def chat(self, body: dict | None = Body(default=None)):
        body = body or {}
        try:
            context = prepare_agent_context(body.get("context") or {}, self.collection_service)
        except (ValidationError, CollectionServiceError, CollectionStoreUnavailableError) as error:
            return failure_response(error)
        return submit_agent_chat(
            body.get("message", ""),
            context,
            body.get("options") or {},
            collection_service=self.collection_service,
            prepared_context=True,
        )

    def explain_investment_context(self, body: dict | None = Body(default=None)):
        if self.investment_context_service is None or self.evidence_loader is None:
            return JSONResponse(
                status_code=503,
                content={"error": "investment_context_unavailable"},
            )
        try:
            request = InvestmentExplanationRequest.model_validate(body or {})
        except ValidationError as error:
            return failure_response(error)
        return submit_investment_explanation(
            request.tickers,
            self.investment_context_service,
            self.evidence_loader,
        )

    def _consultation_data_dir(self) -> Path:
        if self.data_dir is None:
            raise HTTPException(status_code=503, detail="consultation_unavailable")
        return self.data_dir

    def create_consultation(self, body: dict | None = Body(default=None)):
        return create_session(self._consultation_data_dir(), body or {})

    def list_consultations(self, scope: str = "", status: str = "", cursor: str = "", limit: int = Query(default=30, ge=1, le=100)):
        return list_sessions(self._consultation_data_dir(), scope=scope, status=status, cursor=cursor, limit=limit)

    def get_consultation(self, consultation_id: str):
        session = get_session(self._consultation_data_dir(), consultation_id)
        if not session:
            raise HTTPException(status_code=404, detail="consultation_not_found")
        return session

    def update_consultation(self, consultation_id: str, body: dict | None = Body(default=None)):
        try:
            return update_session(self._consultation_data_dir(), consultation_id, body or {})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="consultation_not_found") from exc

    def add_consultation_message(self, consultation_id: str, body: dict | None = Body(default=None)):
        body = body or {}
        try:
            appended = append_user_message(
                self._consultation_data_dir(),
                consultation_id,
                str(body.get("message") or ""),
                operation_id=str(body.get("operationId") or ""),
                retry_message_id=str(body.get("retryMessageId") or ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="consultation_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409 if str(exc) == "consultation_archived" else 400, detail=str(exc)) from exc
        # 도크가 보내는 화면 맥락·첨부·모델 옵션을 그대로 넘긴다. 이게 있어야 보고서
        # 수정 제안과 이미지 첨부가 스레드 경로에서도 동작한다.
        job = submit_consultation_job(
            self._consultation_data_dir(), appended["session"]["id"], appended["message"]["id"],
            screen_context=body.get("context") if isinstance(body.get("context"), dict) else None,
            options=body.get("options") if isinstance(body.get("options"), dict) else None,
        )
        return {"sessionId": appended["session"]["id"], "messageId": appended["message"]["id"], "revision": appended["session"].get("revision"), "job": job, "idempotent": appended["idempotent"]}

    def archive_consultation(self, consultation_id: str):
        try:
            return update_session(self._consultation_data_dir(), consultation_id, {"status": "archived"})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="consultation_not_found") from exc

    def delete_consultation(self, consultation_id: str, body: dict | None = Body(default=None)):
        try:
            # 삭제는 되돌릴 수 없으므로 JSON true만 동의로 본다. bool()은 "false" 같은
            # 문자열도 참으로 만들어 store의 명시적 확인 계약보다 느슨해진다.
            deleted = delete_session(self._consultation_data_dir(), consultation_id, confirmed=(body or {}).get("confirm") is True)
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ConsultationNotEmptyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="consultation_not_found")
        return {"deleted": True, "id": consultation_id}

    def consultation_note(self, consultation_id: str, body: dict | None = Body(default=None)):
        body = body or {}
        session = get_session(self._consultation_data_dir(), consultation_id)
        if not session:
            raise HTTPException(status_code=404, detail="consultation_not_found")
        note_type = str(body.get("noteType") or "investment_note")
        if note_type not in NOTE_TYPES:
            raise HTTPException(status_code=400, detail="consultation_note_type_invalid")
        messages = session.get("messages") or []
        selected = str(body.get("messageId") or "")
        assistant = next((row for row in reversed(messages) if row.get("role") == "assistant" and (not selected or row.get("id") == selected)), {})
        user = next((row for row in reversed(messages) if row.get("role") == "user" and (not assistant or row.get("id") == assistant.get("inReplyTo"))), {})
        note_payload = {
            "noteType": note_type,
            "title": str(body.get("title") or session.get("title") or "상담 정리")[:160],
            "body": str(body.get("body") or "\n\n".join(filter(None, [f"## 질문\n{user.get('content','')}" if user else "", f"## 상담 정리\n{assistant.get('content','')}" if assistant else ""])))[:24_000],
            "ticker": str(body.get("ticker") or ((session.get("scope") or {}).get("tickers") or [""])[0]),
            "consultationRef": consultation_id,
            "sourceLayer": "user_consultation",
            "reuseAsEvidence": False,
        }
        if body.get("preview") is not False:
            return {"preview": True, "note": note_payload, "persisted": False}
        return {"preview": False, "persisted": True, "note": save_note(note_payload)}

    def router(self) -> APIRouter:
        router = APIRouter(tags=["agent"])
        router.add_api_route("/api/agent/companion", self.companion, methods=["POST"])
        router.add_api_route("/api/agent/chat", self.chat, methods=["POST"])
        router.add_api_route(
            "/api/agent/investment-context/explain",
            self.explain_investment_context,
            methods=["POST"],
        )
        # 도크가 대화의 집이다. 주제가 붙은 대화도 같은 스레드라 경로가 하나다.
        # 호환 alias를 두지 않는다(2026-08-06 사용자 결정) — 로컬 앱이라 구 클라이언트가 없다.
        router.add_api_route("/api/agent/threads", self.create_consultation, methods=["POST"])
        router.add_api_route("/api/agent/threads", self.list_consultations, methods=["GET"])
        router.add_api_route("/api/agent/threads/{consultation_id}", self.get_consultation, methods=["GET"])
        router.add_api_route("/api/agent/threads/{consultation_id}", self.update_consultation, methods=["POST"])
        router.add_api_route("/api/agent/threads/{consultation_id}", self.delete_consultation, methods=["DELETE"])
        router.add_api_route("/api/agent/threads/{consultation_id}/messages", self.add_consultation_message, methods=["POST"])
        router.add_api_route("/api/agent/threads/{consultation_id}/archive", self.archive_consultation, methods=["POST"])
        router.add_api_route("/api/agent/threads/{consultation_id}/note", self.consultation_note, methods=["POST"])
        return router
