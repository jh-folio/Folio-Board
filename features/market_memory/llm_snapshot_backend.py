from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from features.llm_settings.client import (
    extract_json_object,
    request_cli_text,
    selected_cli_config,
)
from features.market_memory.attempt_store import AttemptErrorCode
from features.market_memory.http_service import SnapshotPreparation
from features.market_memory.manual_snapshot import (
    Clock,
    CommittedManualSnapshot,
    ManualSnapshotCandidate,
    ManualSnapshotStageError,
)
from features.market_memory.service import (
    MARKET_STATE_SCOPES,
    _market_state_scope_prompt,
    _merge_context_refs,
    _payload_to_market_view,
)
from features.market_memory.snapshot import (
    build_market_state_context,
    save_market_state_snapshot,
    validate_market_state_snapshot,
)


DEFAULT_MAX_TOKENS: Final = 2200


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class LlmManualSnapshotBackend:
    marketDbPath: Path
    clock: Clock

    def prepare(self, request: SnapshotPreparation) -> ManualSnapshotCandidate:
        cfg = selected_cli_config()
        if not cfg["enabled"]:
            raise ManualSnapshotStageError(AttemptErrorCode.ADAPTER_UNAVAILABLE)
        max_tokens = int(os.environ.get("LLM_MARKET_STATE_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_TOKENS)))
        payloads: dict[str, dict] = {}
        contexts: dict[str, dict] = {}
        try:
            for scope in MARKET_STATE_SCOPES:
                context_payload = build_market_state_context(market_scope=scope)
                context = json.dumps(context_payload, ensure_ascii=False, indent=2)
                text, _response_id, _usage = request_cli_text(
                    cfg,
                    _market_state_scope_prompt(scope),
                    context,
                    web_search=False,
                    max_output_tokens=max_tokens,
                    json_mode=True,
                    include_usage=True,
                )
                payloads[scope] = extract_json_object(text)
                contexts[scope] = context_payload
        except (RuntimeError, OSError) as error:
            raise ManualSnapshotStageError(AttemptErrorCode.ADAPTER_FAILED) from error
        except (KeyError, TypeError, ValueError) as error:
            raise ManualSnapshotStageError(AttemptErrorCode.VALIDATION_FAILED) from error
        payload = dict(payloads["overall"])
        payload["asOf"] = _utc_text(self.clock())
        payload["marketViews"] = {
            scope: _payload_to_market_view(payloads[scope], scope)
            for scope in MARKET_STATE_SCOPES
        }
        context = _merge_context_refs(contexts)
        context["inputWatermarks"] = request.inputWatermarks
        context["updateAttemptRef"] = request.updateAttemptRef.model_dump(mode="json")
        try:
            normalized = validate_market_state_snapshot(payload, context=context)
            return ManualSnapshotCandidate(
                payload=normalized,
                updateAttemptRef=request.updateAttemptRef,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ManualSnapshotStageError(AttemptErrorCode.VALIDATION_FAILED) from error

    def save(self, candidate: ManualSnapshotCandidate) -> CommittedManualSnapshot:
        try:
            snapshot = save_market_state_snapshot(self.marketDbPath, candidate.payload)
        except (OSError, sqlite3.Error, ValueError) as error:
            raise ManualSnapshotStageError(AttemptErrorCode.SAVE_FAILED) from error
        return CommittedManualSnapshot(
            snapshotId=str(snapshot["id"]),
            savedAt=self.clock(),
            updateAttemptRef=candidate.updateAttemptRef,
        )
