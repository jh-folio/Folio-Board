from __future__ import annotations

from datetime import UTC, datetime

from features.common.jcs import JsonValue
from features.common.shared_jobs_private import TerminalLiveDetail
from features.common.shared_jobs_schema import (
    Adapter,
    Engine,
    GenerationMode,
    JobKind,
    JobMode,
    SharedJob,
    TaskType,
)


LABELS = {
    "index_rebuild": "자료 폴더 다시 읽기",
    "rss_import": "RSS 수집/가져오기",
    "setup": "설정 작업",
    "agent_chat": "Agent 채팅",
    "agent_cli_install": "Agent CLI 설치",
    "agent_task": "Agent 작업",
    "briefing": "브리핑",
    "company_analysis": "기업 분석",
    "topic_report": "딥 리서치",
    "market_state": "시장 상태",
}
MESSAGES = {
    "queued": "작업 대기 중입니다.",
    "running": "작업을 실행하고 있습니다.",
    "cancel_requested": "취소를 처리하고 있습니다.",
    "committing": "결과를 안전하게 저장하고 있습니다.",
    "done": "작업이 완료되었습니다.",
    "cancelled": "사용자가 작업을 취소했습니다.",
    "failed": "작업을 완료하지 못했습니다.",
    "failed_cancel": "작업 취소를 완료하지 못했습니다.",
    "failed_commit": "결과 저장을 완료하지 못했습니다.",
    "failed_restart": "서버 재시작으로 작업 상태가 종료되었습니다.",
    "failed_commit_recovery": "재시작 후 결과 저장을 복구하지 못했습니다.",
}


def safe_private(args, kwargs) -> dict[str, JsonValue]:
    return {"args": [str(value) for value in args], "kwargs": {str(key): str(value) for key, value in kwargs.items()}}


def worker_projection(result) -> dict[str, str | int | bool | None]:
    if not isinstance(result, dict):
        return {}
    allowed = {
        "count",
        "generatedAt",
        "incremental",
        "sqlite",
        "added",
        "total",
        "failed",
        "ok",
        "adapter",
        "proposalId",
        "reportId",
        "id",
        "date",
        "title",
        "artifactId",
        "savedCount",
        "snapshotId",
        # 건너뛴 이유는 결과에 남아야 한다. 떨어뜨리면 화면이 "수집 완료. 신규 0개"로
        # 그려서 조용한 건너뛰기가 된다(§6 절대 규칙 2).
        "skipped",
    }
    projected = {
        key: value
        for key, value in result.items()
        if key in allowed and (value is None or isinstance(value, (str, int, bool)))
    }
    generated_at = projected.get("generatedAt")
    if isinstance(generated_at, str):
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            if parsed.tzinfo is not None:
                projected["generatedAt"] = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    proposal = result.get("proposal")
    if isinstance(proposal, dict) and isinstance(proposal.get("id"), str):
        projected["proposalId"] = proposal["id"]
    return projected


def terminal_live_detail(job: SharedJob, result) -> dict[str, str | list[str] | None]:
    reply = None
    notice = None
    proposal_id = job.proposalId
    if job.taskType == TaskType.COMPANION and isinstance(result, dict):
        raw_reply = result.get("reply")
        raw_notice = result.get("notice")
        reply = raw_reply[:12_000] if isinstance(raw_reply, str) else None
        notice = "agent_notice" if isinstance(raw_notice, str) and raw_notice else None
        proposal = result.get("proposal")
        if isinstance(proposal, dict) and isinstance(proposal.get("id"), str):
            proposal_id = proposal["id"]
    return {"noticeCode": notice, "optionCodes": [], "reply": reply, "proposalId": proposal_id}


def compatibility_job(job: SharedJob, live_detail: TerminalLiveDetail | None = None) -> dict[str, JsonValue]:
    result = job.resultProjection.model_dump(mode="json") if job.resultProjection is not None else None
    if live_detail is not None and isinstance(result, dict):
        result = {**result, **live_detail.model_dump(mode="json")}
    return {
        "id": job.id,
        "kind": job.kind.value,
        "taskType": job.taskType.value,
        "label": LABELS[job.labelCode.value],
        "status": job.status.value,
        "progress": job.progress,
        "message": MESSAGES[job.status.value],
        "error": job.errorCode.value if job.errorCode is not None else None,
        "createdAt": job.createdAt,
        "updatedAt": job.updatedAt,
        "finishedAt": job.finishedAt,
        "result": result,
        "generationMode": job.generationMode.value,
        "engine": job.engine.value,
        "adapter": job.adapter.value,
        "requestedMode": job.requestedMode.value if job.requestedMode is not None else None,
        "mode": job.mode.value,
        "attemptedEngine": job.attemptedEngine.value if job.attemptedEngine is not None else None,
        "finalEngine": job.finalEngine.value if job.finalEngine is not None else None,
        "fallbackReason": job.fallbackReason.value if job.fallbackReason is not None else None,
        # 실패 이유를 코드로만 노출한다. 없으면 키를 만들지 않는다.
        **({"failureDetail": job.failureDetail} if getattr(job, "failureDetail", None) else {}),
    }


def job_identity(kind: str, fn_name: str, args, adapter_value: str | None):
    parsed_kind = JobKind(kind)
    if parsed_kind == JobKind.AGENT_BRIDGE:
        if args and isinstance(args[0], str) and args[0] in {task.value for task in TaskType}:
            task = TaskType(args[0])
        elif "market_memory_update" in fn_name:
            task = TaskType.MARKET_MEMORY_UPDATE
        else:
            task = TaskType.COMPANION
        adapter = Adapter(adapter_value or Adapter.AUTO.value)
        mode = JobMode.ANSWER if task == TaskType.COMPANION else JobMode.GENERATE
        return parsed_kind, task, GenerationMode.LLM_CLI, adapter, mode, Engine.CLI
    if parsed_kind == JobKind.TOPIC_REPORT:
        return (
            parsed_kind,
            TaskType.TOPIC_REPORT,
            GenerationMode.LLM_API,
            Adapter.AUTO,
            JobMode.GENERATE,
            Engine.API,
        )
    task_map = {
        JobKind.INDEX: (TaskType.INDEX, JobMode.INDEX),
        JobKind.RSS: (TaskType.RSS, JobMode.COLLECT),
        JobKind.SETUP: (TaskType.SETUP, JobMode.INSTALL),
        JobKind.AGENT_CLI_INSTALL: (TaskType.SETUP, JobMode.INSTALL),
        JobKind.BRIEFING: (TaskType.BRIEFING, JobMode.GENERATE),
        JobKind.COMPANY_ANALYSIS: (TaskType.COMPANY_ANALYSIS, JobMode.GENERATE),
        JobKind.MARKET_STATE_SNAPSHOT: (TaskType.MARKET_STATE_SNAPSHOT, JobMode.GENERATE),
    }
    task, mode = task_map[parsed_kind]
    return parsed_kind, task, GenerationMode.NONE, Adapter.NONE, mode, None
