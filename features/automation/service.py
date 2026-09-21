from __future__ import annotations

import datetime as dt
import threading
import time
from contextlib import nullcontext
from pathlib import Path

from features.automation.schema import normalize_settings
from features.automation.schema import (
    DEFAULT_CATCH_UP_HOURS,
    default_schedule,
    MARKET_CALENDAR_INTERVAL_MINUTES,
    MAX_ATTEMPTS_PER_DAY,
    ON_TIME_WINDOW_MINUTES,
    RETRY_DELAY_MINUTES,
    WEEKDAYS,
)
from features.agent_mode.bridge import submit_agent_task
from features.agent_mode.generation_mode import llm_override_for_mode
from features.common.jobs import (
    diagnostic_stage_failure,
    finish_direct_diagnostic,
    finish_direct_diagnostic_run,
    get_job,
    start_direct_diagnostic,
)
from features.common.diagnostics.support import bind_context, bind_failure_cache, current_context
from features.common.research_library.rss.service import import_rssarchive
from features.common.research_library.signals.runtime import promote_kr_rss_leads
from features.common.utils import kst_date, now_iso, read_json, write_json
from features.common.market_scope import load_market_scope
from features.daily_briefing.builder import build_briefing
from features.daily_briefing.schema import market_selection_scope, normalize_briefing_kind, normalize_market_selection
from features.llm_settings.client import default_generation_mode
from features.agent_mode.generation_mode import normalize_generation_mode
from features.llm_settings.task_runtime import (
    bind_task_policy,
    generation_mode as task_generation_mode,
    task_snapshot,
)
from features.market_memory.digest import run_rss_market_memory_update
from features.market_calendar.service import refresh_calendar
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
SETTINGS_PATH = DATA_DIR / "automation-settings.json"
RUNS_PATH = DATA_DIR / "automation-runs.json"
_LOOP_STARTED = False


def _automation_task_snapshot(task_key: str) -> dict:
    """Resolve a task once, retaining the legacy mode seam for callers/tests."""
    snapshot = task_snapshot(task_key)
    # Existing automation callers can inject the process-wide mode through
    # ``default_generation_mode``.  Preserve that seam only for global-source
    # rows; an explicit task override must always win.
    if snapshot.get("source") == "global":
        legacy_mode = normalize_generation_mode(default_generation_mode())
        if legacy_mode != task_generation_mode(snapshot):
            snapshot = {
                **snapshot,
                "enabled": legacy_mode != "rules",
                "mode": "cli" if legacy_mode == "llm_cli" else "",
            }
    return snapshot


def read_settings() -> dict:
    return normalize_settings(read_json(SETTINGS_PATH, {}))


def save_settings(raw: dict) -> dict:
    settings = normalize_settings(raw)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(SETTINGS_PATH, settings)
    return settings


# 실패 원인은 예외 **원문이 아니라 분류**로 남긴다. `run_automation_once`의 반환값은
# HTTP로 나가고 실행 기록도 `/api/automation/runs`로 나가는데, 예외 메시지에는 요청 URL,
# 헤더, 프롬프트 조각, 파일 경로가 그대로 실릴 수 있다. 키 패턴만 지우는 방식으로는
# 모르는 형태를 막지 못한다(`tests/test_security_alert_regressions.py`가 그 경계를 지킨다).
#
# 그렇다고 예전처럼 `automation_failed` 한 마디만 남기면 왜 실패했는지 알 수 없다.
# 예외 **종류**는 코드 식별자라 사용자 자료가 아니므로, 그것만 읽어 한국어 원인으로 옮긴다.
FAILURE_REASONS = {
    "TimeoutError": "시간이 초과되었습니다",
    "ConnectionError": "네트워크에 연결하지 못했습니다",
    "ConnectionResetError": "네트워크에 연결하지 못했습니다",
    "HTTPError": "외부 서비스가 오류를 돌려줬습니다",
    "URLError": "네트워크에 연결하지 못했습니다",
    "PermissionError": "파일에 접근하지 못했습니다",
    "FileNotFoundError": "필요한 파일을 찾지 못했습니다",
    "OSError": "파일이나 네트워크 접근에 실패했습니다",
    "JSONDecodeError": "응답을 해석하지 못했습니다",
    "ValueError": "값이 올바르지 않습니다",
    "MemoryError": "메모리가 부족합니다",
}
UNKNOWN_FAILURE_REASON = "알 수 없는 오류입니다"


def _run_briefing_rss_prerequisite() -> dict:
    """Give a manual briefing's RSS collection its own concrete child run."""
    parent = current_context()
    if parent is None:
        return import_rssarchive(run_collection=True)
    recorder = start_direct_diagnostic(
        feature_code="rss",
        route_code="rss_collect",
        authority_kind="direct",
        parent_run_id=parent.run_id,
    )
    if recorder is None:
        return import_rssarchive(run_collection=True)
    try:
        with bind_context(recorder.context):
            # A child run must never reuse the parent's Failure object/stage.
            with bind_failure_cache():
                result = import_rssarchive(run_collection=True)
        finish_direct_diagnostic(
            recorder,
            "succeeded" if isinstance(result, dict) and result.get("ok") is True else "unknown",
        )
        return result
    except Exception as error:
        diagnostic_stage_failure(
            recorder,
            error,
            stage_id=None,
            stage_code="collect",
            boundary="generic",
            terminal=True,
        )
        finish_direct_diagnostic(recorder, "failed")
        raise


def failure_reason(exc: BaseException) -> str:
    """Map an exception class to a cause a person can act on.

    상속을 따라 올라가며 아는 종류를 찾는다. `requests`·`urllib` 계열은 이름이 제각각이라
    정확히 맞지 않아도 부모 클래스(`OSError`)에서 걸린다.
    """
    for klass in type(exc).__mro__:
        reason = FAILURE_REASONS.get(klass.__name__)
        if reason:
            return reason
    return UNKNOWN_FAILURE_REASON


# 실행 기록은 로그가 아니라 스케줄 상태다(schedule_due가 읽는다). append와 reconcile이
# 둘 다 read-modify-write인데 스케줄러 데몬 스레드와 API 수동 실행(FastAPI 스레드풀)이
# 병렬로 겹치므로, 잠금 없이는 그 사이에 끼어든 행이 통째로 사라져 브리핑이 중복 생성된다.
_RUNS_LOCK = threading.Lock()


def _append_run(row: dict) -> None:
    with _RUNS_LOCK:
        runs = read_json(RUNS_PATH, [])
        if not isinstance(runs, list):
            runs = []
        runs.insert(0, row)
        write_json(RUNS_PATH, runs[:50])


def list_runs(limit: int = 20) -> list[dict]:
    runs = read_json(RUNS_PATH, [])
    return runs[: int(limit or 20)] if isinstance(runs, list) else []


def diagnostic_authority_for_run(run_id: str) -> dict[str, str] | None:
    """Read-only authority lookup for an automation diagnostic parent.

    Automation has no SharedJob for rules paths, so its persisted row—not an
    inferred child result—is the only authority available to detail projection.
    """
    if not isinstance(run_id, str):
        return None
    for row in list_runs(50):
        if not isinstance(row, dict) or row.get("diagnosticRunId") != run_id:
            continue
        status = str(row.get("status") or "").strip()
        if status == "submitted":
            return {"status": "running"}
        if status == "done":
            return {"status": "done"}
        if status == "failed":
            return {"status": "failed"}
        return None
    return None


def _parse_iso(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed(now: dt.datetime, finished: dt.datetime) -> dt.timedelta:
    """Compare timestamps without mixing local wall time and UTC wall time."""
    if now.tzinfo is None and finished.tzinfo is None:
        return now - finished
    if now.tzinfo is None:
        now = now.replace(tzinfo=finished.tzinfo)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=now.tzinfo)
    return now.astimezone(dt.timezone.utc) - finished.astimezone(dt.timezone.utc)


def _date_in_reference_timezone(value: dt.datetime, reference: dt.datetime) -> dt.date:
    if value.tzinfo is not None and reference.tzinfo is not None:
        return value.astimezone(reference.tzinfo).date()
    if value.tzinfo is not None:
        return value.astimezone().date()
    return value.date()


def _last_run_for(kind: str, runs: list[dict] | None = None) -> dict | None:
    for row in runs if runs is not None else list_runs(100):
        if row.get("kind") == kind:
            return row
    return None


def _row_failed(row: dict) -> bool:
    """Only an explicit `failed` counts as a failure.

    옛 기록과 테스트 fixture에는 `status`가 없는 행이 있다. 그것까지 실패로 보면
    이미 만든 브리핑을 다시 만든다.
    """
    return str(row.get("status") or "").strip() == "failed"


def _runs_on_date(
    kind: str, runs: list[dict], now: dt.datetime, *, schedule_id: str = ""
) -> list[tuple[dt.datetime, dict]]:
    """That day's attempts for one automation, newest first.

    `schedule_id`를 주면 그 스케줄의 시도만 센다. 하루 3회 상한이 스케줄별이어야
    아침 브리핑이 세 번 실패했다고 저녁 브리핑까지 막히지 않는다. 스케줄 id가 없는
    옛 기록은 승격된 첫 스케줄의 것으로 본다.
    """
    rows = []
    for row in runs:
        if row.get("kind") != kind:
            continue
        if schedule_id:
            row_id = str(row.get("scheduleId") or "").strip()
            if row_id and row_id != schedule_id:
                continue
        finished = _parse_iso(row.get("finishedAt", ""))
        if finished is not None and _date_in_reference_timezone(finished, now) == now.date():
            rows.append((finished, row))
    return sorted(rows, key=lambda pair: pair[0], reverse=True)


def _minutes_from_time(value: str) -> int:
    hour, minute = str(value or "08:00").split(":")[:2]
    return int(hour) * 60 + int(minute)


def automation_due(kind: str, settings: dict | None = None, now: dt.datetime | None = None, runs: list[dict] | None = None) -> bool:
    settings = normalize_settings(settings or read_settings())
    now = now or dt.datetime.now().astimezone()
    runs = list_runs(100) if runs is None else runs
    if kind == "rss":
        cfg = settings["rss"]
        if not cfg.get("enabled"):
            return False
        last = _last_run_for("rss", runs)
        finished = _parse_iso((last or {}).get("finishedAt", ""))
        return finished is None or _elapsed(now, finished) >= dt.timedelta(minutes=int(cfg["intervalMinutes"]))
    if kind == "marketCalendar":
        # 설정 없이 항상 도는 유일한 자동화다(schema.MARKET_CALENDAR_INTERVAL_MINUTES).
        last = _last_run_for("marketCalendar", runs)
        finished = _parse_iso((last or {}).get("finishedAt", ""))
        return finished is None or _elapsed(now, finished) >= dt.timedelta(
            minutes=MARKET_CALENDAR_INTERVAL_MINUTES
        )
    if kind == "marketMemory":
        cfg = settings["marketMemory"]
        if not cfg.get("enabled"):
            return False
        last = _last_run_for("marketMemory", runs)
        finished = _parse_iso((last or {}).get("finishedAt", ""))
        return finished is None or _elapsed(now, finished) >= dt.timedelta(minutes=int(cfg["intervalMinutes"]))
    if kind == "briefing":
        schedules = settings.get("briefingSchedules") or []
        return any(
            schedule_due(schedule, settings=settings, now=now, runs=runs)
            for schedule in schedules
        )
    return False


def schedule_due(schedule: dict, *, settings: dict, now: dt.datetime, runs: list[dict]) -> bool:
    """Whether one briefing schedule should run right now."""
    if not schedule.get("enabled"):
        return False
    # 만들 시장도 돌 날도 없으면 성립하지 않는 예약이다. `normalize_schedule()`이 이미
    # 꺼 두지만, 저장을 거치지 않고 들어온 값에도 같은 판정이 걸려야 한다.
    if not schedule.get("markets") or not schedule.get("days"):
        return False
    # 고른 요일에만. 예전에는 요일을 보지 않아 08:00 예약이 토·일에도 돌았고, 장이
    # 열리지 않은 날 금요일 자료로 만든 브리핑이 매주 두 건씩 쌓였다.
    if now.weekday() not in set(schedule.get("days") or ()):
        return False
    target = _minutes_from_time(schedule.get("time", "08:00"))
    current = now.hour * 60 + now.minute
    if current < target:
        return False
    catch_up = int(settings.get("missedRuns", {}).get("catchUpHours", DEFAULT_CATCH_UP_HOURS))
    if current - target > max(ON_TIME_WINDOW_MINUTES, catch_up * 60):
        return False
    today = _runs_on_date("briefing", runs, now, schedule_id=str(schedule.get("id") or ""))
    # 성공한 실행만 "오늘 했다"로 친다. 예전에는 상태를 보지 않아서, LLM이 한 번
    # 타임아웃 나면 그날 브리핑이 아예 없었고 실패했다는 사실도 화면에 없었다.
    if any(not _row_failed(row) for _, row in today):
        return False
    if len(today) >= MAX_ATTEMPTS_PER_DAY:
        return False
    if today and _elapsed(now, today[0][0]) < dt.timedelta(minutes=RETRY_DELAY_MINUTES):
        return False
    return True


def market_memory_recently_run(*, now: dt.datetime | None = None, max_age_hours: int = 12, runs: list[dict] | None = None) -> bool:
    now = now or dt.datetime.now().astimezone()
    last = _last_run_for("marketMemory", list_runs(100) if runs is None else runs)
    if (last or {}).get("status") not in {"done", "ok", ""}:
        return False
    finished = _parse_iso((last or {}).get("finishedAt", ""))
    if finished is None:
        return False
    return _elapsed(now, finished) < dt.timedelta(hours=max(1, int(max_age_hours or 12)))


# 사전작업 스냅샷은 **전체 해석**이다. 예약이 고른 시장 집합과 무관하게 GLOBAL scope로
# 만든다 — 화면의 시장 내러티브는 시장별 보고서가 아니라 하나의 해석이고, 그 안에서
# `marketViews`로 미국장·한국장을 나눈다.
PREREQUISITE_SNAPSHOT_SCOPE = "GLOBAL"


def market_state_snapshot_recently_run(*, now: dt.datetime | None = None, max_age_hours: int = 12) -> bool:
    """화면 스냅샷이 최근에 만들어졌는지 — **메모리 갱신 신선도와 따로 본다.**

    예전에는 둘을 한 덩어리로 봤다. 규칙 갱신이 12시간 안에 돌았으면 스냅샷 갱신까지
    통째로 건너뛰어서, 규칙 갱신은 신선한데 화면 해석만 며칠 전인 상태가 커버되지
    않았다. 스냅샷은 자기 `as_of`로 신선도를 말할 수 있으므로 그것을 직접 읽는다.
    """
    from features.market_memory.snapshot import latest_market_state_snapshot_as_of

    now = now or dt.datetime.now().astimezone()
    try:
        as_of = latest_market_state_snapshot_as_of(DATA_DIR / "market-memory.sqlite3")
    except Exception:  # noqa: BLE001 - 못 읽으면 오래된 것으로 본다(다시 만드는 쪽이 안전하다)
        return False
    saved = _parse_iso(as_of or "")
    if saved is None:
        return False
    return _elapsed(now, saved) < dt.timedelta(hours=max(1, int(max_age_hours or 12)))


# 스냅샷 생성이 실패한 뒤 다시 시도하기까지 기다리는 시간. 없으면 어댑터가 죽어 있는
# 동안 예약이 돌 때마다 수십 초짜리 CLI가 무한히 재시도된다 — 신선도 가드가 아끼려던
# 비용을 실패 경로가 그대로 되돌려 놓는다.
SNAPSHOT_RETRY_BACKOFF_HOURS = 6


def market_state_snapshot_recently_failed(*, now: dt.datetime | None = None, runs: list[dict] | None = None) -> bool:
    """마지막 스냅샷 시도가 최근에 **실패**했는지."""
    now = now or dt.datetime.now().astimezone()
    last = _last_run_for("marketStateSnapshot", list_runs(100) if runs is None else runs)
    if not last or not _row_failed(last):
        return False
    finished = _parse_iso(str(last.get("finishedAt") or ""))
    if finished is None:
        return False
    return _elapsed(now, finished) < dt.timedelta(hours=SNAPSHOT_RETRY_BACKOFF_HOURS)


def _refresh_market_state_snapshot(*, memory_is_fresh: bool = False) -> dict:
    """화면용 시장 상태 스냅샷을 다시 만든다.

    **실패해도 올리지 않는다.** 브리핑이 오늘의 결과물이고 스냅샷은 그 앞의 준비다.
    스냅샷을 못 만들었다고 브리핑까지 없어지면 손해가 더 크다 — 왜 못 만들었는지만
    남기고 넘어간다.

    엔진이 없으면(규칙 모드) 만들 수 없다. LLM이 시장 해석 문장을 쓰는 산출물이라
    규칙으로 대신할 수 있는 것이 아니다.
    """
    mode = "rules"
    try:
        task_policy = _automation_task_snapshot("market_memory")
        mode = task_generation_mode(task_policy)
        if mode == "rules":
            return {"ok": False, "skipped": True, "reason": "rules_mode"}
        if mode == "llm_cli":
            # Prerequisites own the medium-memory step.  This function is
            # snapshot-only so a failed memory call cannot suppress the second
            # step (and stale/fresh API and CLI take the same sequence).
            from features.agent_mode.bridge import run_agent_task

            result = run_agent_task(
                "market_state_snapshot",
                {"date": kst_date(), "_task_policy_snapshot": task_policy},
                adapter=str(task_policy.get("provider") or ""),
            )
            snapshot_id = str((result or {}).get("snapshotId") or "")
            return {"ok": True, "mode": mode, "scope": PREREQUISITE_SNAPSHOT_SCOPE, "snapshotId": snapshot_id}
        return {"ok": False, "reason": "unsupported_generation_mode"}
    except Exception as exc:  # noqa: BLE001 - 브리핑을 막지 않는다
        return {"ok": False, "mode": mode, "scope": PREREQUISITE_SNAPSHOT_SCOPE, "errorType": type(exc).__name__}


def _refresh_medium_memory() -> dict:
    """Run the configured medium-memory writer without blocking a snapshot."""
    try:
        task_policy = _automation_task_snapshot("market_memory")
        mode = task_generation_mode(task_policy)
        if mode == "llm_cli":
            from features.agent_mode.bridge import run_agent_task

            return run_agent_task(
                "market_memory_llm",
                {"date": kst_date(), "_task_policy_snapshot": task_policy},
                adapter=str(task_policy.get("provider") or ""),
            )
        return run_rss_market_memory_update()
    except Exception as exc:  # noqa: BLE001 - snapshot and briefing still run
        return {"ok": False, "errorType": type(exc).__name__}


def _run_market_state_snapshot_step(*, memory_is_fresh: bool = False) -> dict:
    """스냅샷 갱신을 실행하고 **결과를 실행 기록에 남긴다.**

    기록이 없으면 실패가 어디에도 남지 않는다. 규칙 갱신을 건너뛴 경로는 `_append_run`을
    부르지 않아서, 스냅샷이 며칠째 실패해도 자동화 화면에는 아무 흔적이 없었다 —
    사용자는 사전작업이 도는 줄 알고 옛 해석을 계속 본다. 재시도 유예도 이 기록을 읽는다.
    """
    started = now_iso()
    result = _refresh_market_state_snapshot(memory_is_fresh=memory_is_fresh)
    if not result.get("skipped"):
        _append_run({
            "kind": "marketStateSnapshot",
            "status": "done" if result.get("ok") else "failed",
            "startedAt": started,
            "finishedAt": now_iso(),
            "result": result,
        })
    return result


def run_briefing_prerequisites(
    *,
    now: dt.datetime | None = None,
    memory_max_age_hours: int = 12,
    force: bool = False,
) -> dict:
    prerequisites = {"rss": _run_briefing_rss_prerequisite()}
    # `force`는 사용자가 직접 "지금 실행"을 누른 경우다. 신선도 때문에 건너뛰면
    # 눌러도 아무 일이 없는 버튼이 된다. 예약 경로는 계속 신선도를 본다.
    if not force and market_memory_recently_run(now=now, max_age_hours=memory_max_age_hours):
        # 규칙 갱신은 건너뛰지만 **화면 스냅샷은 따로 본다.** 한 덩어리로 스킵하면
        # 규칙 갱신이 신선한 날에도 시장 내러티브 탭은 며칠 전 해석 그대로 남는다.
        skipped = {
            "ok": True,
            "skipped": True,
            "reason": "recent",
            "maxAgeHours": int(memory_max_age_hours or 12),
        }
        if market_state_snapshot_recently_run(now=now, max_age_hours=memory_max_age_hours):
            skipped["stateSnapshot"] = {
                "ok": True,
                "skipped": True,
                "reason": "recent",
                "maxAgeHours": int(memory_max_age_hours or 12),
            }
        elif not force and market_state_snapshot_recently_failed(now=now):
            # 방금 실패한 것을 예약마다 다시 시도하지 않는다. 조용히 건너뛰지도 않는다 —
            # 건너뛴 사실이 결과에 남아야 왜 화면이 안 바뀌는지 알 수 있다.
            skipped["stateSnapshot"] = {
                "ok": False,
                "skipped": True,
                "reason": "recent_failure",
                "retryAfterHours": SNAPSHOT_RETRY_BACKOFF_HOURS,
            }
        else:
            skipped["stateSnapshot"] = _run_market_state_snapshot_step(memory_is_fresh=True)
        prerequisites["marketMemory"] = skipped
    else:
        started = now_iso()
        try:
            memory = _refresh_medium_memory()
            status = "failed" if isinstance(memory, dict) and memory.get("ok") is False else "done"
            # 규칙 기반 갱신만으로는 **화면이 보여주는 내러티브가 바뀌지 않는다.**
            # 시장 내러티브 탭은 `market_state_snapshots`를 읽는데 위 함수는 그것을
            # 만들지 않는다 — `market_memory` 행과 regime 카운트만 갱신한다. 그래서
            # 사전작업이 도는 날에도 화면은 며칠 전 해석 그대로였다(실측: 스냅샷 이력이
            # 08-12, 08-07, 08-06으로 띄엄띄엄하고 그 시각에 자동화 기록이 없다 —
            # 전부 사용자가 버튼을 누른 것이었다).
            # Always attempt the snapshot even when the medium-memory writer
            # failed. Existing durable state is still useful snapshot input.
            # The attempt backoff is independent from memory freshness: a
            # stale memory pass may run, while a snapshot adapter that just
            # failed must not be invoked again on every scheduled briefing.
            if not force and market_state_snapshot_recently_failed(now=now):
                snapshot = {
                    "ok": False,
                    "skipped": True,
                    "reason": "recent_failure",
                    "retryAfterHours": SNAPSHOT_RETRY_BACKOFF_HOURS,
                }
            else:
                snapshot = _run_market_state_snapshot_step()
            memory = {**memory, "stateSnapshot": snapshot} if isinstance(memory, dict) else memory
            _append_run({
                "kind": "marketMemory",
                "status": status,
                "startedAt": started,
                "finishedAt": now_iso(),
                "result": memory,
            })
            prerequisites["marketMemory"] = memory
        except Exception:
            _append_run({
                "kind": "marketMemory",
                "status": "failed",
                "startedAt": started,
                "finishedAt": now_iso(),
                "error": "market_memory_prerequisite_failed",
            })
            raise
    return prerequisites


def markets_in_scope(requested) -> tuple[list[str], list[str]]:
    """Intersect a schedule's markets with the ones the user still watches.

    관심 시장은 제품의 바깥 테두리다(CLAUDE.md). 자동화는 그 테두리를 몰라서, KR을 꺼도
    KR 브리핑이 계속 만들어졌다. 선택 자체를 막지 않고 실행할 때 교집합을 쓰는 이유는
    시장을 잠깐 껐다 켜는 동안 스케줄이 파괴되지 않아야 하기 때문이다.

    범위를 못 읽으면 요청한 그대로 돌린다. 설정 파일 하나가 안 읽힌다고 브리핑이
    통째로 멈추는 쪽이 더 나쁘다.
    """
    markets = list(normalize_market_selection(requested))
    try:
        selected = {str(code).strip().upper() for code in load_market_scope()["selected"]}
    except Exception:  # noqa: BLE001 - 범위를 못 읽는다고 생성을 막지 않는다
        return markets, []
    # 시장 계약은 소문자(`us`), 관심 시장 저장값은 대문자(`US`)다. 비교만 맞추고
    # 돌려주는 값은 생성기가 기대하는 표기 그대로 둔다.
    kept = [code for code in markets if code.upper() in selected]
    return kept, [code for code in markets if code.upper() not in selected]


def _first_schedule(settings: dict) -> dict:
    schedules = settings.get("briefingSchedules") or []
    return schedules[0] if schedules else default_schedule(enabled=True)


def _run_briefing(settings: dict | None = None, schedule: dict | None = None) -> dict:
    settings = normalize_settings(settings or read_settings())
    cfg = schedule if isinstance(schedule, dict) else _first_schedule(settings)
    requested = cfg.get("markets") or []
    markets, dropped = markets_in_scope(requested)
    if not markets:
        # 고른 시장을 전부 꺼둔 상태다. 조용히 넘기지 않고 왜 건너뛰었는지 남긴다.
        return {
            "skipped": True,
            "reason": "markets_out_of_scope",
            "scheduleId": cfg.get("id", ""),
            "requestedMarkets": list(normalize_market_selection(requested)),
            "droppedMarkets": dropped,
        }
    date = kst_date()
    kind = normalize_briefing_kind(str(cfg.get("kind") or "daily").strip().lower())
    from features.daily_briefing.news_selection_runtime import pin_selection_context
    selection_context = pin_selection_context(date, markets, kind)
    prerequisites = {}
    # 값이 없으면 켠 것으로 읽는다(§10 계약, schema 기본값과 동일). 결측을 끔으로
    # 읽으면 이 키가 생기기 전의 예약이 조용히 사전작업을 잃는다.
    if cfg.get("runPrerequisites", True):
        prerequisites = run_briefing_prerequisites()
    task_policy = _automation_task_snapshot("daily_briefing")
    generation_mode = task_generation_mode(task_policy)
    scope_label = market_selection_scope(markets)
    kind = str(cfg.get("kind") or "daily").strip().lower()
    kind = normalize_briefing_kind(kind)
    if generation_mode == "llm_cli":
        briefing = submit_agent_task("briefing", {
            "date": date,
            "strict_date": False,
            "quality_mode": cfg.get("qualityMode", "diagnose_only"),
            "market_scope": scope_label,
            "markets": markets,
            "briefing_type": cfg.get("briefingType", "default"),
            "kind": kind,
            "selection_context": selection_context,
            "_task_policy_snapshot": task_policy,
            })
    else:
        with bind_task_policy(task_policy):
            briefing = build_briefing(
                date=date,
                strict_date=False,
                llm_override=llm_override_for_mode(generation_mode),
                quality_mode=cfg.get("qualityMode", "diagnose_only"),
                markets=markets,
                briefing_type=cfg.get("briefingType", "default"),
                kind=kind,
                selection_context=selection_context,
            )
    return {
        "date": date,
        "generationMode": generation_mode,
        "scheduleId": cfg.get("id", ""),
        "marketScope": scope_label,
        "markets": markets,
        "kind": kind,
        "droppedMarkets": dropped,
        "prerequisites": prerequisites,
        "briefing": briefing,
    }


def run_automation_once(kind: str, schedule: dict | None = None) -> dict:
    kind = str(kind or "").strip()
    if kind not in {"rss", "marketCalendar", "marketMemory", "briefingPrerequisites", "briefing"}:
        return {"ok": False, "error": f"Unsupported automation: {kind}"}
    started = now_iso()
    schedule_id = str((schedule or {}).get("id") or "").strip()
    recorder = start_direct_diagnostic(
        feature_code="automation", route_code="automation_run", authority_kind="automation",
    )
    diagnostic_run_id = recorder.context.run_id if recorder is not None else ""
    try:
        with bind_context(recorder.context) if recorder is not None else nullcontext():
            if kind == "rss":
                result = import_rssarchive(run_collection=True)
                # 한국 lead 표시는 이미 수집한 행을 다시 읽을 뿐이라 네트워크도 자격증명도 쓰지 않는다.
                # 별도 자동화 없이 RSS 수집에 함께 실린다.
                try:
                    result = {**result, "krFastOriginLeads": promote_kr_rss_leads(DATA_DIR)}
                except Exception:
                    pass
            elif kind == "marketCalendar":
                result = refresh_calendar(DATA_DIR)
            elif kind == "marketMemory":
                result = run_rss_market_memory_update()
            elif kind == "briefingPrerequisites":
                # 사전작업의 정의는 한 곳이다. 여기서 따로 조립하면 예약 경로만 화면
                # 스냅샷을 만들고 이 경로는 안 만드는 식으로 갈라진다. 다만 이쪽은 사용자가
                # 직접 부르는 경로라 신선도로 건너뛰지 않는다.
                result = run_briefing_prerequisites(force=True)
            elif kind == "briefing":
                result = _run_briefing(schedule=schedule)
            else:
                raise AssertionError("validated automation kind")
            status = "done"
            job_id = ""
            if kind == "rss" and isinstance(result, dict) and result.get("collection", {}).get("ok") is False:
                # 수집이 실패했는데 done으로 적으면 자동 수집이 도는 줄 알고 며칠을 보낸다 —
                # 실제로 매시 실행이 300초에서 잘리는 동안 실행 기록은 열흘 내내 done이었다.
                status = "failed"
            if kind == "briefing" and isinstance(result, dict) and result.get("generationMode") == "llm_cli":
                # submit_agent_task는 job을 전용 스레드로 띄우고 바로 돌아온다. 이 시점은
                # 완료가 아니라 제출이다 — done으로 적으면 job이 실패해도 그날 '성공'이
                # 남아 30분 재시도가 한 번도 돌지 않고 화면도 성공으로 말한다.
                briefing_job = result.get("briefing") if isinstance(result.get("briefing"), dict) else {}
                job_id = str(briefing_job.get("id") or "").strip()
                if job_id:
                    status = "submitted"
            row = {"kind": kind, "status": status, "startedAt": started, "finishedAt": now_iso(), "result": result}
        if job_id:
            row["jobId"] = job_id
        if schedule_id:
            row["scheduleId"] = schedule_id
        if diagnostic_run_id:
            row["diagnosticRunId"] = diagnostic_run_id
        _append_run(row)
        if status != "submitted":
            finish_direct_diagnostic(recorder, "succeeded" if status == "done" else "failed")
        return {"ok": True, **row}
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 기록으로 남기고 다음 주기로 넘긴다
        diagnostic_stage_failure(
            recorder, exc, stage_id=None, stage_code="generate", boundary="generic",
        )
        row = {
            "kind": kind,
            "status": "failed",
            "startedAt": started,
            "finishedAt": now_iso(),
            # 실패도 스케줄을 남긴다. 아침 브리핑이 세 번 실패했다고 저녁 브리핑까지
            # 막히면 안 되므로 재시도 상한을 스케줄별로 세야 한다.
            **({"scheduleId": schedule_id} if schedule_id else {}),
            "error": "automation_failed",
            # 예외 종류는 코드 식별자라 사용자 자료가 아니다. 원문 메시지는 담지 않는다.
            "errorType": type(exc).__name__,
            "errorReason": failure_reason(exc),
        }
        if diagnostic_run_id:
            row["diagnosticRunId"] = diagnostic_run_id
        _append_run(row)
        finish_direct_diagnostic(recorder, "failed")
        return {"ok": False, **row}


def _reconcile_submitted_briefings() -> None:
    """CLI 제출 브리핑 행에 job 종결 상태를 되돌려 적는다.

    submitted 행은 job이 도는 동안 성공처럼 취급되어 중복 제출을 막고, job이
    실패로 끝나면 여기서 failed로 바뀌어 README의 재시도 계약(30분 뒤, 하루 3회)이
    되살아난다. 화면의 실행 기록도 이 파일을 읽으므로 함께 진실이 된다.
    """
    with _RUNS_LOCK:
        _reconcile_submitted_briefings_locked()


def _reconcile_submitted_briefings_locked() -> None:
    runs = read_json(RUNS_PATH, [])
    if not isinstance(runs, list):
        return
    changed = False
    terminal_diagnostics: list[tuple[str, str]] = []
    for row in runs:
        if not isinstance(row, dict) or row.get("kind") != "briefing" or row.get("status") != "submitted":
            continue
        job_id = str(row.get("jobId") or "").strip()
        if not job_id:
            row["status"] = "failed"
            row["error"] = "briefing_job_id_missing"
            changed = True
            diagnostic_run_id = row.get("diagnosticRunId")
            if isinstance(diagnostic_run_id, str):
                terminal_diagnostics.append((diagnostic_run_id, "failed"))
            continue
        try:
            job = get_job(job_id)
        except Exception:  # noqa: BLE001 - job 저장소를 못 읽으면 다음 주기에 다시 본다
            continue
        if job is None:
            # 재시작 복구(load_jobs)가 미완 job을 failed로 남기므로 없는 job은 기록 유실이다.
            row["status"] = "failed"
            row["error"] = "briefing_job_not_found"
            changed = True
            diagnostic_run_id = row.get("diagnosticRunId")
            if isinstance(diagnostic_run_id, str):
                terminal_diagnostics.append((diagnostic_run_id, "failed"))
            continue
        job_status = str(job.get("status") or "").strip()
        # committing도 아직 도는 상태다(JobStatus에 있다). 커밋 구간에 reconcile 주기가
        # 걸리면 여기서 failed로 못박혀 뒤이은 done이 영원히 반영되지 않고, 30분 뒤
        # 같은 브리핑이 한 번 더 만들어진다.
        if job_status in {"queued", "running", "cancel_requested", "committing"}:
            continue
        row["status"] = "done" if job_status == "done" else "failed"
        if row["status"] == "failed":
            # 원문 메시지는 담지 않는다 — 실행 기록은 코드 식별자만 갖는다.
            row["error"] = "briefing_job_failed"
        finished = str(job.get("finishedAt") or "").strip()
        if finished:
            # 재시도 30분 간격은 제출 시각이 아니라 실제 실패 시각부터 센다.
            row["finishedAt"] = finished
        changed = True
        diagnostic_run_id = row.get("diagnosticRunId")
        if isinstance(diagnostic_run_id, str):
            terminal_diagnostics.append((diagnostic_run_id, "succeeded" if row["status"] == "done" else "failed"))
    if changed:
        write_json(RUNS_PATH, runs)
        # The automation row is the authority parent.  Its persisted terminal
        # status precedes this observational close; a missing child remains a
        # parent failure with no invented provider cause.
        for run_id, observed_status in terminal_diagnostics:
            finish_direct_diagnostic_run(run_id, observed_status)


def run_due_automations(now: dt.datetime | None = None) -> dict:
    _reconcile_submitted_briefings()
    settings = read_settings()
    runs = list_runs(100)
    executed = []
    rss_ran = False
    if automation_due("marketCalendar", settings=settings, now=now, runs=runs):
        executed.append(run_automation_once("marketCalendar"))
    if automation_due("rss", settings=settings, now=now, runs=runs):
        executed.append(run_automation_once("rss"))
        rss_ran = True
    memory_cfg = settings.get("marketMemory", {})
    if memory_cfg.get("enabled") and ((rss_ran and memory_cfg.get("runAfterRss")) or automation_due("marketMemory", settings=settings, now=now, runs=runs)):
        executed.append(run_automation_once("marketMemory"))
    # 스케줄마다 독립된 job이다. 같은 날 같은 시장 집합을 두 번 만들지 않도록,
    # 이번 주기에 이미 돈 집합은 건너뛴다(시각이 가까운 스케줄 둘이 같은 시장을 볼 때).
    #
    # **종류가 키에 들어간다.** 같은 시장의 일간 예약과 주간 예약이 한 주기에 걸리면
    # (일요일 아침이 정확히 그 경우다) 뒤에 오는 쪽이 조용히 스킵돼, 사용자는 주간
    # 예약을 켜 두고도 아무것도 받지 못한다.
    now_at = now or dt.datetime.now().astimezone()
    produced: set[tuple[str, ...]] = set()
    for schedule in settings.get("briefingSchedules") or []:
        if not schedule_due(schedule, settings=settings, now=now_at, runs=runs):
            continue
        markets, _ = markets_in_scope(schedule.get("markets") or [])
        key = (str(schedule.get("kind") or "daily"), *markets)
        if markets and key in produced:
            continue
        outcome = run_automation_once("briefing", schedule=schedule)
        executed.append(outcome)
        if markets and outcome.get("ok"):
            produced.add(key)
    return {"ok": True, "executed": executed}


def schedule_automation_loop(interval_seconds: int = 60) -> bool:
    global _LOOP_STARTED
    if _LOOP_STARTED:
        return False
    _LOOP_STARTED = True

    def _worker() -> None:
        while True:
            try:
                run_due_automations()
            except Exception:
                _append_run({
                    "kind": "scheduler",
                    "status": "failed",
                    "startedAt": now_iso(),
                    "finishedAt": now_iso(),
                    "error": "scheduler_iteration_failed",
                })
            time.sleep(max(10, int(interval_seconds)))

    threading.Thread(target=_worker, name="folio-automation", daemon=True).start()
    return True
