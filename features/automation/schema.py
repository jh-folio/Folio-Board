from __future__ import annotations

from features.common.research_library.rss.retention import (
    DEFAULT_RETENTION_DAYS,
    RETENTION_CHOICES,
    normalize_days as normalize_retention_days,
)

# 자동화 기본값은 네 시장(`all`)이다. 저장된 `both` 설정은 그대로 두 시장으로 남긴다.
VALID_MARKET_SCOPES = {"us", "kr", "europe", "jp", "all", "both"}
VALID_BRIEFING_TYPES = {"default", "market_focused", "concise"}
# 브리핑 **종류**. `briefingType`(편집 강조점)과 직교한다 — 그쪽 세 값은 모두 "기존 섹션
# 구성을 유지하라"고 지시하므로 골격이 다른 주간을 그 enum에 넣으면 계약이 자기 자신과
# 모순된다. 이 항목이 없는 저장된 예약은 일간으로 읽는다(판올림 호환).
VALID_BRIEFING_KINDS = {"daily", "weekly"}
VALID_QUALITY_MODES = {"diagnose_only", "llm_section_improve", "strict"}

# 시장 계약의 순서. 같은 집합이 늘 같은 순서로 저장돼야 화면과 파일 이름이 흔들리지 않는다.
ALL_MARKETS = ("us", "kr", "europe", "jp")
LEGACY_SCOPE_MARKETS = {
    "all": ALL_MARKETS,
    "both": ("us", "kr"),
    "us": ("us",),
    "kr": ("kr",),
    "europe": ("europe",),
    "jp": ("jp",),
}
# 상한이 없으면 24개를 만들어 하루 종일 LLM을 돌릴 수 있다. 시장 4개 + 종합 1개면 충분하고,
# 늘리는 것은 나중에 쉽다.
MAX_BRIEFING_SCHEDULES = 5

# 예약이 도는 요일. `datetime.weekday()`와 같은 0=월 … 6=일이다.
#
# **거래일 판정으로 대신하지 않는다.** 그러면 "장이 열리는 날"이 곧 발행일이 되어 주말
# 브리핑을 만들 길이 막힌다 — 주간 요약과 다음주 프리뷰는 토·일에 내는 것이 맞다.
# 게다가 판정 대상이 당일이 아니라 직전 세션이라 공휴일이 끼면 꼬일 여지가 크다.
# 언제 낼지는 사용자가 고르고, 코드는 그 선택을 지킨다(2026-08-10 사용자 결정).
WEEKDAYS = (0, 1, 2, 3, 4, 5, 6)
WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")


def _bool(value) -> bool:
    return bool(value)


def _int(value, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _time(value: str, default: str = "08:00") -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        return default
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return default
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return f"{hour:02d}:{minute:02d}"


# 시장 일정 갱신은 사용자 선택 항목이 아니다. 끄면 지표 발표일이 조용히 비어 있게 되고,
# 화면은 "이번 주에 일정이 없음"과 구분되지 않는다. 실제로 이 설정이 꺼진 채로 남아
# CPI·고용지표가 한 건도 등록되지 않은 상태가 지속됐다. Agent를 호출하지 않고 비용도
# 없으므로 항상 6시간마다 돈다.
MARKET_CALENDAR_INTERVAL_MINUTES = 360

# 예약 시각을 놓쳤을 때 몇 시간까지 따라잡을지. 예전에는 `skip`/`catch_up` 둘뿐이었고
# 둘 다 나빴다 — `skip`은 10분 창이 전부라 08:15에 PC를 켜면 그날 브리핑이 없었고,
# `catch_up`은 상한이 없어 23:50에 켜도 아침 브리핑을 만들었다. 데스크톱 앱이라
# 늘 켜져 있지 않다는 것이 전제다.
CATCH_UP_HOUR_CHOICES = (0, 1, 3, 6, 24)
DEFAULT_CATCH_UP_HOURS = 3
# 0시간을 골라도 정시에 딱 맞춰 켜져 있어야 하는 것은 아니다. 스케줄러가 1분마다 도므로
# 예전 `skip`이 주던 10분 창을 바닥으로 유지한다.
ON_TIME_WINDOW_MINUTES = 10
# 실패했을 때 다시 시도하기까지, 그리고 하루에 몇 번까지. 예전에는 실패한 실행도
# "오늘 실행함"으로 쳐서 LLM이 한 번 타임아웃 나면 그날 브리핑이 아예 없었다.
RETRY_DELAY_MINUTES = 30
MAX_ATTEMPTS_PER_DAY = 3


def default_settings() -> dict:
    return {
        "rss": {
            "enabled": False,
            "intervalMinutes": 60,
            "saveFullText": True,
            "retentionDays": DEFAULT_RETENTION_DAYS,
        },
        "marketMemory": {"enabled": False, "intervalMinutes": 1440, "runAfterRss": True},
        "briefingSchedules": [],
        "missedRuns": {"catchUpHours": DEFAULT_CATCH_UP_HOURS},
    }


def default_schedule(**overrides) -> dict:
    """A schedule with every field filled in, so callers never guess a default."""
    row = {
        "id": "",
        "enabled": False,
        "time": "08:00",
        # 네 시장이 기본이다. `both`(미국+한국)는 시장이 둘이던 시절의 값이라,
        # 유럽·일본만 보는 사용자가 자동화를 켜면 안 보는 시장 둘이 나왔다.
        "markets": list(ALL_MARKETS),
        "briefingType": "default",
        "kind": "daily",
        "qualityMode": "diagnose_only",
        "runPrerequisites": True,
        # 새 예약은 장이 서는 평일만. 주말 브리핑은 고르는 것이지 기본값이 아니다.
        "days": [0, 1, 2, 3, 4],
    }
    row.update(overrides)
    return row


def _markets(value, default: list[str]) -> list[str]:
    """Read a market set from a list or an old scope name, in contract order."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text in LEGACY_SCOPE_MARKETS:
            return list(LEGACY_SCOPE_MARKETS[text])
        value = [part for part in text.split(",") if part]
    if not isinstance(value, (list, tuple)):
        return list(default)
    # 빈 목록과 읽을 수 없는 값은 다르다. **빈 목록은 선택이다** — 마지막 시장을 끈
    # 것이므로 그대로 둔다(예전에는 기본값으로 되돌려서 끄겠다는 선택이 정반대로
    # 저장됐다). 반면 값이 있는데 하나도 알아볼 수 없으면(`marketScope: "bad"`) 그건
    # 선택이 아니라 고장이라 기본값으로 되돌린다. 만들 보고서가 없는 예약은
    # `normalize_schedule()`이 꺼 둔다.
    if not value:
        return []
    wanted = {str(item).strip().lower() for item in value}
    ordered = [market for market in ALL_MARKETS if market in wanted]
    return ordered or list(default)


def _days(raw: dict) -> list[int]:
    """이 예약이 도는 요일. 계약 순서(월→일)로 돌려준다.

    **이 항목이 없는 저장된 예약은 매일로 읽는다.** 요일을 고를 수 없던 시절에 만든
    예약이라 "매일"이 선택이 아니라 선택지가 없었던 것이지만, 판올림만으로 토·일
    브리핑이 사라지면 그것도 사용자가 정한 적 없는 변화다. 화면에 요일 칩이 보이므로
    한 번 눌러 정하면 된다. 새로 만드는 예약은 `default_schedule()`이 평일로 시작한다.

    빈 목록은 그대로 둔다. 돌 날이 없는 예약은 `normalize_schedule()`이 꺼 둔다.
    """
    if "days" not in raw:
        return list(WEEKDAYS)
    value = raw.get("days")
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
        return list(WEEKDAYS)
    # 시장과 같은 규칙이다. 빈 목록은 선택이고, 읽을 수 없는 값은 고장이다.
    if not value:
        return []
    chosen = set()
    for item in value:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if day in WEEKDAYS:
            chosen.add(day)
    return [day for day in WEEKDAYS if day in chosen] or list(WEEKDAYS)


def normalize_schedule(raw: dict | None, *, index: int = 0) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    row = default_schedule()
    # id는 클라이언트가 소유한다. 없으면 순서로 만들어 두는데, 이 값이 매번 달라지면
    # 실행 기록의 `scheduleId`가 스케줄과 이어지지 않아 재시도 횟수를 셀 수 없다.
    row["id"] = str(raw.get("id") or "").strip() or f"sched-{index + 1}"
    row["enabled"] = bool(raw.get("enabled", False))
    row["time"] = _time(raw.get("time"), row["time"])
    row["markets"] = _markets(raw.get("markets", raw.get("marketScope")), row["markets"])
    row["briefingType"] = _choice(raw.get("briefingType"), VALID_BRIEFING_TYPES, "default")
    row["kind"] = _choice(raw.get("kind"), VALID_BRIEFING_KINDS, "daily")
    row["qualityMode"] = _choice(raw.get("qualityMode"), VALID_QUALITY_MODES, "diagnose_only")
    row["runPrerequisites"] = bool(raw.get("runPrerequisites", True))
    row["days"] = _days(raw)
    # 만들 시장이 없거나 돌 날이 없으면 예약은 꺼진 것이다. 켠 채로 두면 화면은 켜졌다고
    # 말하는데 아무 일도 일어나지 않는다 — 켜고 끄는 것은 사용자가 정하고, 성립하지
    # 않는 예약은 그 사실을 화면이 바로 보여준다(2026-08-10 사용자 결정).
    if not row["markets"] or not row["days"]:
        row["enabled"] = False
    return row


def normalize_schedules(raw: dict) -> list[dict]:
    """Read the schedule list, promoting the old single-schedule setting.

    예전에는 브리핑 자동화를 **하나만** 등록할 수 있었다. 시장이 넷이 되면서 마감 시각이
    전부 달라져(유럽 01:30 · 미국 05~06 · 일본 15:00 · 한국 15:30 KST) 시각 하나짜리
    모델로는 구조적으로 안 된다. 저장된 싱글톤은 스케줄 하나로 승격해 동작을 보존한다.
    """
    rows = raw.get("briefingSchedules")
    if not isinstance(rows, list):
        legacy = raw.get("briefing")
        rows = [legacy] if isinstance(legacy, dict) else []
    normalized = [
        normalize_schedule(row, index=index)
        for index, row in enumerate(rows[:MAX_BRIEFING_SCHEDULES])
        if isinstance(row, dict)
    ]
    # id가 겹치면 재시도 횟수가 뒤섞인다. 나중 것을 밀어 고유하게 만든다.
    seen: set[str] = set()
    for position, row in enumerate(normalized):
        while row["id"] in seen:
            row["id"] = f"{row['id']}-{position + 1}"
        seen.add(row["id"])
    return normalized


def _catch_up_hours(raw: dict) -> int:
    """Read the grace window, migrating the old two-state setting in place.

    `skip`은 10분 창이 전부였으므로 0시간, `catch_up`은 그날 자정까지였으므로 24시간이
    같은 동작이다. 저장된 설정은 그대로 두고 읽을 때만 옮기므로 기존 사용자의 동작이
    바뀌지 않는다. 기본 3시간은 새로 켜는 사람에게만 적용된다.
    """
    if "catchUpHours" in raw:
        try:
            value = int(raw.get("catchUpHours"))
        except (TypeError, ValueError):
            return DEFAULT_CATCH_UP_HOURS
        return value if value in CATCH_UP_HOUR_CHOICES else DEFAULT_CATCH_UP_HOURS
    legacy = str(raw.get("onStartup") or "").strip()
    if legacy == "catch_up":
        return 24
    if legacy == "skip":
        return 0
    return DEFAULT_CATCH_UP_HOURS


def _choice(value, choices: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in choices else default


def _retention_for(raw: dict, rss: dict, default: int) -> int:
    """보관 기간. **판올림한 사람에게는 적용하지 않는다.**

    이 항목이 없는 설정 파일은 보관 기간이 생기기 전에 만들어진 것이다. 거기에 기본
    90일을 먹이면, 반년치를 모아 둔 사람이 새 버전을 받는 것만으로 다음 수집에서 석 달치를
    잃는다 — 지우겠다고 말한 적이 없는데 지워진다(§6 절대 규칙 2).

    그래서 쓰던 설정에는 `계속 보관`을 주고, 줄이는 것은 화면에서 고르게 한다. 고를 때
    몇 건이 지워지는지 먼저 보여주므로 그때는 알고 하는 선택이다. 설정 파일이 아예 없는
    새 설치만 기본 90일로 시작해 아카이브가 처음부터 묶인다.
    """
    if "retentionDays" in rss:
        return normalize_retention_days(rss["retentionDays"])
    return default if not raw else 0


def normalize_settings(raw: dict | None) -> dict:
    raw = raw or {}
    defaults = default_settings()
    rss = raw.get("rss") or {}
    memory = raw.get("marketMemory") or {}
    missed = raw.get("missedRuns") or {}
    return {
        "rss": {
            "enabled": _bool(rss.get("enabled", defaults["rss"]["enabled"])),
            "intervalMinutes": _int(rss.get("intervalMinutes"), defaults["rss"]["intervalMinutes"], 15),
            "saveFullText": _bool(rss.get("saveFullText", defaults["rss"]["saveFullText"])),
            "retentionDays": _retention_for(raw, rss, defaults["rss"]["retentionDays"]),
        },
        "marketMemory": {
            "enabled": _bool(memory.get("enabled", defaults["marketMemory"]["enabled"])),
            "intervalMinutes": _int(memory.get("intervalMinutes"), defaults["marketMemory"]["intervalMinutes"], 30),
            "runAfterRss": _bool(memory.get("runAfterRss", defaults["marketMemory"]["runAfterRss"])),
        },
        "briefingSchedules": normalize_schedules(raw),
        "missedRuns": {
            "catchUpHours": _catch_up_hours(missed),
        },
    }


def wants_prerequisites(settings: dict) -> bool:
    """Whether a manual briefing should collect first.

    스케줄마다 정할 수 있게 됐지만 손으로 만드는 브리핑은 어느 스케줄에도 속하지 않는다.
    켜 둔 스케줄 중 하나라도 원하면 수집한다 — 싱글톤이던 시절 동작과 같고, 여분으로
    한 번 더 수집하는 것은 해가 없다.
    """
    return any(row.get("runPrerequisites") for row in settings.get("briefingSchedules", []) if row.get("enabled"))
