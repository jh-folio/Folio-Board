from __future__ import annotations

import json
import os
import re
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from features.common.jcs import JsonValue
from features.common.shared_jobs_completion import ArtifactCompletionProof
from features.common.shared_jobs_projection import utc_z
from features.common.shared_jobs_schema import ErrorCode, JOB_ID_PATTERN, JobStatus, TERMINAL_STATUSES
from features.common.shared_jobs_store import JobsStoreUnavailableError, SharedJobStore
from features.common.atomic_replace import ATTEMPTS, BASE_DELAY, replace_with_retry


PACK_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def rmtree_with_retry(
    path: Path,
    *,
    attempts: int = ATTEMPTS,
    base_delay: float = BASE_DELAY,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """`shutil.rmtree()`를 하되, 잠깐 잡혀 있으면 다시 시도한다(§파일 저장).

    Windows에서 백신 실시간 검사나 검색 색인기가 pack 파일 핸들을 잡고 있으면
    `WinError 5/32`(둘 다 `PermissionError`)로 거부되고 보통 수십 밀리초 뒤 풀린다.
    쓰기는 `replace_with_retry()`로 물러났다 다시 쓰는데 삭제만 한 번에 포기하면,
    그 비대칭이 잡 종료와 시작 복구를 통째로 실패시킨다.
    """
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            sleep(base_delay * (2**attempt))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunningLiveDetail(StrictModel):
    noticeCode: str | None
    optionCodes: list[str] = Field(max_length=8)
    reply: None = None
    proposalId: str | None


class TerminalLiveDetail(StrictModel):
    noticeCode: str | None
    optionCodes: list[str] = Field(max_length=8)
    reply: str | None = Field(max_length=12_000)
    proposalId: str | None


@dataclass(frozen=True, slots=True)
class PrivateCleanupError(Exception):
    job_id: str

    def __str__(self) -> str:
        return f"private_cleanup_failed:{self.job_id}"


@dataclass(frozen=True, slots=True)
class OwnedPackIdentityError(Exception):
    job_id: str
    pack_id: str

    def __str__(self) -> str:
        return "invalid owned pack identity"


@dataclass(frozen=True, slots=True)
class TerminalStatusError(Exception):
    status: JobStatus

    def __str__(self) -> str:
        return f"terminal status required: {self.status}"


@dataclass(frozen=True, slots=True)
class LiveRecord:
    detail: TerminalLiveDetail
    terminal_at: datetime


class JobPrivateLifecycle:
    def __init__(
        self,
        context_root: Path,
        *,
        clock: Callable[[], datetime],
        terminal_observer: Callable[[str, JobStatus], None] | None = None,
        cleanup_started: Callable[[str], None] | None = None,
        cleanup_finished: Callable[[str], None] | None = None,
        cleanup_failed: Callable[[str, PrivateCleanupError], None] | None = None,
    ) -> None:
        self.context_root = context_root
        self.clock = clock
        self.worker_private: dict[str, dict[str, JsonValue]] = {}
        self.live_running: dict[str, RunningLiveDetail] = {}
        self.live_terminal: dict[str, LiveRecord] = {}
        self.cleanup_blocked: set[str] = set()
        self.repair_required = False
        self._terminal_observer = terminal_observer
        self._cleanup_started = cleanup_started
        self._cleanup_finished = cleanup_finished
        self._cleanup_failed = cleanup_failed

    def set_repair_required(self, required: bool) -> None:
        self.repair_required = required

    def set_private(self, job_id: str, value: dict[str, JsonValue]) -> None:
        self.worker_private[job_id] = value

    def has_private(self, job_id: str) -> bool:
        return job_id in self.worker_private

    def write_pack(self, job_id: str, pack_id: str, pack: dict[str, JsonValue]) -> Path:
        if JOB_ID_PATTERN.fullmatch(job_id) is None or PACK_ID_PATTERN.fullmatch(pack_id) is None:
            raise OwnedPackIdentityError(job_id, pack_id)
        owner = (self.context_root / job_id).resolve()
        owner.relative_to(self.context_root.resolve())
        owner.mkdir(parents=True, exist_ok=True)
        target = (owner / f"{pack_id}.json").resolve()
        target.relative_to(owner)
        temporary = target.with_name(target.name + ".tmp")
        payload = {**pack, "ownerJobId": job_id}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        replace_with_retry(temporary, target)
        return target

    def cleanup_owner(self, job_id: str) -> bool:
        owner = (self.context_root / job_id).resolve()
        try:
            owner.relative_to(self.context_root.resolve())
            if owner.exists():
                rmtree_with_retry(owner)
            return not owner.exists()
        except OSError:
            return False

    def _prune_live(self) -> None:
        cutoff = self.clock().astimezone(UTC) - timedelta(minutes=30)
        ordered = sorted(
            self.live_terminal.items(),
            key=lambda item: (item[1].terminal_at, item[0]),
            reverse=True,
        )
        self.live_terminal = {
            job_id: record
            for index, (job_id, record) in enumerate(ordered)
            if index < 50 and record.terminal_at >= cutoff
        }

    def _persist_terminal(
        self,
        store: SharedJobStore,
        job_id: str,
        *,
        live_detail: Mapping[str, str | list[str] | None] | None = None,
        persist: Callable[[], object],
    ) -> None:
        if self._cleanup_started is not None:
            try:
                self._cleanup_started(job_id)
            except Exception:
                pass
        if not self.cleanup_owner(job_id):
            self.cleanup_blocked.add(job_id)
            store.mark_private_cleanup_failed(job_id)
            error = PrivateCleanupError(job_id)
            if self._cleanup_failed is not None:
                try:
                    self._cleanup_failed(job_id, error)
                except Exception:
                    pass
            raise error
        if self._cleanup_finished is not None:
            try:
                self._cleanup_finished(job_id)
            except Exception:
                pass
        self.worker_private.pop(job_id, None)
        self.live_running.pop(job_id, None)
        detail = TerminalLiveDetail.model_validate(
            live_detail or {"noticeCode": None, "optionCodes": [], "reply": None, "proposalId": None}
        )
        self.live_terminal[job_id] = LiveRecord(detail, self.clock().astimezone(UTC))
        try:
            persist()
        except Exception:  # noqa: BROAD_EXCEPT_OK
            self.live_terminal.pop(job_id, None)
            self.cleanup_blocked.add(job_id)
            raise
        self.cleanup_blocked.discard(job_id)
        self._prune_live()
        # Authority cleanup + persistence has completed.  An observer cannot
        # become proof or disturb the existing fail-closed lifecycle.
        if self._terminal_observer is not None:
            try:
                current = store.get(job_id)
                if current is not None and current.status in TERMINAL_STATUSES:
                    self._terminal_observer(job_id, current.status)
            except Exception:
                pass

    def terminalize(
        self,
        store: SharedJobStore,
        job_id: str,
        target: JobStatus,
        *,
        result: Mapping[str, str | int | bool | None] | None = None,
        error_code: ErrorCode | str | None = None,
        live_detail: Mapping[str, str | list[str] | None] | None = None,
    ) -> None:
        if target not in TERMINAL_STATUSES:
            raise TerminalStatusError(target)
        self._persist_terminal(
            store,
            job_id,
            live_detail=live_detail,
            persist=lambda: store.transition(
                job_id,
                target,
                result=result,
                error_code=error_code,
            ),
        )

    def terminalize_recovery(
        self,
        store: SharedJobStore,
        job_id: str,
        target: JobStatus,
        *,
        live_detail: Mapping[str, str | list[str] | None] | None = None,
    ) -> None:
        if target not in TERMINAL_STATUSES:
            raise TerminalStatusError(target)
        self._persist_terminal(
            store,
            job_id,
            live_detail=live_detail,
            persist=lambda: store.transition_recovery(
                job_id,
                target,
            ),
        )

    def complete_artifact(
        self,
        store: SharedJobStore,
        job_id: str,
        proof: ArtifactCompletionProof,
        *,
        live_detail: Mapping[str, str | list[str] | None] | None = None,
    ) -> None:
        self._persist_terminal(
            store,
            job_id,
            live_detail=live_detail,
            persist=lambda: store.complete_artifact(job_id, proof),
        )

    def assert_readable(self) -> None:
        if self.cleanup_blocked or self.repair_required:
            raise JobsStoreUnavailableError()

    def recover_startup(self, store: SharedJobStore) -> None:
        """재시작 후 남은 비종료 잡을 종료 상태로 되돌린다.

        pack 삭제가 끝내 실패한 잡은 fail-closed 계약대로 비종료로 남기고
        `cleanup_blocked`에 넣는다(잡 조회는 503). 다만 거기서 멈추지 않고 나머지
        잡의 전환과 orphan 정리를 끝낸 뒤 마지막에 알린다 — 첫 실패에서 빠져나오면
        뒤의 좀비 잡이 그대로 남는다. 호출자는 이 예외로 기동을 멈추지 않는다.
        """
        state = store.load()
        blocked: list[str] = []
        for job in state.jobs:
            if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
                continue
            if not self.cleanup_owner(job.id):
                self.cleanup_blocked.add(job.id)
                store.mark_private_cleanup_failed(job.id)
                blocked.append(job.id)
                continue
            self.worker_private.pop(job.id, None)
            store.transition_recovery(
                job.id,
                JobStatus.FAILED_RESTART,
            )
        active = {job.id for job in store.load().jobs if job.status not in TERMINAL_STATUSES}
        self.cleanup_orphans(active)
        if blocked:
            raise PrivateCleanupError(blocked[0])

    def cleanup_orphans(self, nonterminal_job_ids: set[str]) -> list[str]:
        if not self.context_root.exists():
            return []
        cutoff = self.clock().astimezone(UTC) - timedelta(hours=24)
        removed = []
        for path in sorted(self.context_root.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or JOB_ID_PATTERN.fullmatch(path.name) is None:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if path.name in nonterminal_job_ids or modified > cutoff:
                continue
            try:
                rmtree_with_retry(path)
            except OSError:
                # 24시간 넘게 남은 폴더를 지우는 위생 작업이다. 지금 잠겨 있다고 복구
                # 전체를 실패시키지 않는다 — 다음 시작에서 다시 지운다.
                continue
            removed.append(path.name)
        return removed
