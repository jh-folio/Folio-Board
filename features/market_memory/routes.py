from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path
from typing import Literal, Protocol, assert_never

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from features.agent_mode.market_state_context import MarketStateSelection
from features.market_memory.attempt_store import (
    AttemptErrorCode,
    AttemptScope,
    AttemptStoreUnavailableError,
    AttemptTransitionError,
)
from features.market_memory.http_service import (
    ManualSnapshotCommand,
    MarketStateHttpService,
)
from features.market_memory.manual_snapshot import (
    ManualSnapshotRepairRequiredError,
    ManualSnapshotStageError,
)
from features.market_memory.market_state_ref import JsonValue


class ManualSnapshotBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    date: Date | None = None
    scope: AttemptScope = AttemptScope.GLOBAL
    agentAdapter: str = Field(default="", max_length=80)


class MarketStateContextBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: Literal["exclude", "include_current"]
    requestedScope: Literal["AUTO", "GLOBAL", "US", "KR"]
    regions: tuple[str, ...] = Field(default=(), max_length=20)
    collectionMarket: str | None = Field(default=None, max_length=20)


def _inline_mode() -> str:
    return "inline"


class ModeResolver(Protocol):
    def __call__(self) -> str: ...


class SnapshotJobSubmitter(Protocol):
    def __call__(self, task: str, payload: dict[str, str], adapter: str) -> dict[str, JsonValue]: ...


class CombinedJobSubmitter(Protocol):
    def __call__(self, payload: dict[str, str], adapter: str) -> dict[str, JsonValue]: ...


class MemoryRunner(Protocol):
    def __call__(self, date_value: str) -> dict[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class MarketStateRouteAdapters:
    modeResolver: ModeResolver = _inline_mode
    snapshotJobSubmitter: SnapshotJobSubmitter | None = None
    combinedJobSubmitter: CombinedJobSubmitter | None = None
    memoryRunner: MemoryRunner | None = None


type RouteFailure = (
    AttemptStoreUnavailableError
    | AttemptTransitionError
    | ManualSnapshotRepairRequiredError
    | ManualSnapshotStageError
)


def _failure(error: RouteFailure) -> JSONResponse:
    match error:
        case AttemptStoreUnavailableError():
            return JSONResponse({"error": "attempt_store_unavailable"}, status_code=503)
        case ManualSnapshotRepairRequiredError():
            return JSONResponse({"error": "manual_snapshot_repair_required"}, status_code=503)
        case ManualSnapshotStageError(code=AttemptErrorCode.ADAPTER_UNAVAILABLE):
            return JSONResponse({"error": "adapter_unavailable"}, status_code=503)
        case ManualSnapshotStageError(code=AttemptErrorCode.ADAPTER_FAILED):
            return JSONResponse({"error": "adapter_failed"}, status_code=502)
        case ManualSnapshotStageError(code=AttemptErrorCode.VALIDATION_FAILED):
            return JSONResponse({"error": "validation_failed"}, status_code=422)
        case ManualSnapshotStageError(
            code=(
                AttemptErrorCode.SAVE_FAILED
                | AttemptErrorCode.INTERNAL_ERROR
                | AttemptErrorCode.INTERRUPTED
                | AttemptErrorCode.COMMIT_RECOVERY_FAILED
            ) as code
        ):
            return JSONResponse({"error": code.value}, status_code=500)
        case AttemptTransitionError(code=code):
            return JSONResponse({"error": code}, status_code=409)
        case unreachable:
            assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class MarketStateBoundary:
    service: MarketStateHttpService
    adapters: MarketStateRouteAdapters = MarketStateRouteAdapters()

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/api/memory", tags=["market-state"])

        @router.post("/state-snapshot")
        def create_snapshot(body: ManualSnapshotBody):
            mode = self.adapters.modeResolver()
            if mode == "llm_cli":
                if self.adapters.snapshotJobSubmitter is None:
                    return JSONResponse({"error": "adapter_unavailable"}, status_code=503)
                payload = {"date": body.date.isoformat() if body.date else "", "scope": body.scope.value}
                return self.adapters.snapshotJobSubmitter("market_state_snapshot", payload, body.agentAdapter)
            if mode == "rules":
                return {
                    "ok": False,
                    "status": "rules_unavailable",
                    "message": "시장 상태 스냅샷은 AI Agent CLI가 활성화되어 있을 때 생성할 수 있습니다.",
                }
            if mode != "inline":
                return JSONResponse({"error": "llm_api_removed"}, status_code=409)
            try:
                return self.service.run_manual(
                    ManualSnapshotCommand(body.scope, body.date.isoformat() if body.date else None)
                )
            except (
                AttemptStoreUnavailableError,
                AttemptTransitionError,
                ManualSnapshotRepairRequiredError,
                ManualSnapshotStageError,
            ) as error:
                return _failure(error)

        @router.post("/update")
        def update_memory(body: ManualSnapshotBody):
            date_value = body.date.isoformat() if body.date else ""
            mode = self.adapters.modeResolver()
            if mode == "llm_cli":
                if self.adapters.combinedJobSubmitter is None:
                    return JSONResponse({"error": "adapter_unavailable"}, status_code=503)
                return self.adapters.combinedJobSubmitter(
                    {"date": date_value, "scope": body.scope.value},
                    body.agentAdapter,
                )
            if mode == "rules":
                return {
                    "ok": False,
                    "status": "rules_unavailable",
                    "message": "시장 메모리 업데이트는 화면용 시장 상태 스냅샷 생성을 위해 AI Agent CLI가 필요합니다.",
                }
            if mode != "inline":
                return JSONResponse({"error": "llm_api_removed"}, status_code=409)
            if self.adapters.memoryRunner is None:
                return JSONResponse({"error": "adapter_unavailable"}, status_code=503)
            memory = self.adapters.memoryRunner(date_value)
            try:
                manual = self.service.run_manual(ManualSnapshotCommand(body.scope, date_value or None))
            except (
                AttemptStoreUnavailableError,
                AttemptTransitionError,
                ManualSnapshotRepairRequiredError,
                ManualSnapshotStageError,
            ) as error:
                return _failure(error)
            snapshot = manual["snapshot"]
            snapshot_dict = snapshot if isinstance(snapshot, dict) else {}
            return {
                "ok": bool(memory.get("ok", True) and manual.get("ok", True)),
                "status": "ok",
                "message": "시장 메모리와 화면용 시장 상태 스냅샷을 모두 업데이트했습니다.",
                "memory": memory,
                "snapshot": snapshot,
                "attempt": manual["attempt"],
                "marketStateRef": manual["marketStateRef"],
                "savedCount": len(memory.get("saved") or []),
                "snapshotId": snapshot_dict.get("id", ""),
                "title": snapshot_dict.get("headline", ""),
                "date": date_value,
            }

        @router.get("/state-snapshot")
        def current_snapshot(scope: AttemptScope = Query(default=AttemptScope.GLOBAL)):
            try:
                return self.service.current(scope)
            except (AttemptStoreUnavailableError, ManualSnapshotRepairRequiredError) as error:
                return _failure(error)

        @router.get("/state-dashboard")
        def dashboard(
            limit: int = Query(default=5, ge=1, le=20),
            scope: AttemptScope = Query(default=AttemptScope.GLOBAL),
        ):
            try:
                return self.service.dashboard(scope, limit)
            except (AttemptStoreUnavailableError, ManualSnapshotRepairRequiredError) as error:
                return _failure(error)

        @router.post("/state-context")
        def context(body: MarketStateContextBody):
            try:
                projection = self.service.context(
                    MarketStateSelection(
                        body.policy,
                        body.requestedScope,
                        body.regions,
                        body.collectionMarket,
                    )
                )
                return {
                    "marketStateResolution": projection.resolution,
                    "marketStateContext": projection.context,
                }
            except (AttemptStoreUnavailableError, ManualSnapshotRepairRequiredError) as error:
                return _failure(error)

        return router


def create_market_state_router(data_dir: Path) -> APIRouter:
    from features.agent_mode.bridge import submit_agent_task, submit_market_memory_update
    from features.llm_settings.client import default_generation_mode
    from features.market_memory.direct_observer import run_direct_market_memory
    from features.market_memory.http_runtime import create_market_state_service
    from features.market_memory.service import run_llm_market_memory

    service = create_market_state_service(data_dir)
    adapters = MarketStateRouteAdapters(
        modeResolver=default_generation_mode,
        snapshotJobSubmitter=lambda task, payload, adapter: submit_agent_task(task, payload, adapter=adapter),
        combinedJobSubmitter=lambda payload, adapter: submit_market_memory_update(payload, adapter=adapter),
        memoryRunner=lambda date_value: run_direct_market_memory(
            date_value,
            generate=lambda value: run_llm_market_memory(value or None),
        ),
    )
    return MarketStateBoundary(service, adapters).router()
