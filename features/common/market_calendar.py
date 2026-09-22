"""Market trading calendar and briefing date window helpers."""
import datetime as dt
import json
import re
import time
from functools import lru_cache
from features.common.config_bootstrap import resolve_config
from features.common.markets import PRODUCT_MARKETS
from features.common.exchange_holidays import MARKET_EXCHANGES, market_exchange_status
from features.common.markets import MarketCode, normalize_market_code
from features.common.utils import normalize

# 한국 기사 관행: 종목명 뒤 6자리 종목코드 대괄호 표기(예: 셀트리온[068270]).
_KR_STOCK_CODE_RE = re.compile(r"\[\d{6}\]")
_KST = dt.timezone(dt.timedelta(hours=9))
# 한국시간 자정 이후에 마감하는 시장. 이 시장의 세션 S는 발행일 S+1에 실린다.
OVERNIGHT_CLOSE_MARKETS = ("us", "europe")
_KR_REGULAR_OPEN = dt.time(9, 0)
_KR_REGULAR_CLOSE = dt.time(15, 30)
# JST는 KST와 같은 시간대(UTC+9)라 한국 기준 생성 시각을 그대로 비교할 수 있다.
# JPX는 2024-11-05 종가 연장 이후 09:00~15:30이다(11:30~12:30 점심 휴장은 세션 안이다).
_JP_REGULAR_OPEN = dt.time(9, 0)
_JP_REGULAR_CLOSE = dt.time(15, 30)


def previous_calendar_date(date):
    try:
        return (dt.datetime.strptime(date, "%Y-%m-%d").date() - dt.timedelta(days=1)).isoformat()
    except Exception:
        return date


def parse_iso_date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except Exception:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def parse_kst_datetime(value):
    """Parse an ISO timestamp and normalize it to Korea Standard Time."""
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_KST)
    return parsed.astimezone(_KST)


def _dt_now_kst():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))


def kr_session_phase(briefing_day, is_open_on_date, as_of=None):
    """Return holiday/pre_open/intraday/closed for a Korean trading date.

    ``as_of=None`` preserves the historical date-only behavior for callers that
    intentionally inspect a calendar fixture without a generation timestamp.
    Runtime briefing generation always supplies its KST-aware creation time.

    A caller that omits ``as_of`` is inspecting the calendar, not generating a
    briefing, so the legacy answer stands. Everything that decides what a
    reader sees — session mode, title, stored windows — resolves the phase from
    a real timestamp instead.
    """
    if not is_open_on_date:
        return "holiday"
    timestamp = parse_kst_datetime(as_of)
    if timestamp is None:
        return "intraday"
    if briefing_day < timestamp.date():
        return "closed"
    if briefing_day > timestamp.date():
        return "pre_open"
    current_time = timestamp.timetz().replace(tzinfo=None)
    if current_time < _KR_REGULAR_OPEN:
        return "pre_open"
    if current_time < _KR_REGULAR_CLOSE:
        return "intraday"
    return "closed"


def jp_session_phase(briefing_day, is_open_on_date, as_of=None):
    """Return holiday/pre_open/intraday/closed for a Japanese trading date.

    Tokyo runs alongside Seoul rather than overnight, so the briefing-day session
    can still be in progress when the briefing is generated — the same problem
    ``kr_session_phase`` solves. ``as_of=None`` keeps the date-only behavior for
    callers inspecting a calendar without a generation timestamp.
    """
    if not is_open_on_date:
        return "holiday"
    timestamp = parse_kst_datetime(as_of)
    if timestamp is None:
        return "intraday"
    if briefing_day < timestamp.date():
        return "closed"
    if briefing_day > timestamp.date():
        return "pre_open"
    current_time = timestamp.timetz().replace(tzinfo=None)
    if current_time < _JP_REGULAR_OPEN:
        return "pre_open"
    if current_time < _JP_REGULAR_CLOSE:
        return "intraday"
    return "closed"


def align_briefing_market_windows_to_as_of(market_windows, as_of):
    """Apply a generation timestamp to legacy date-only market windows.

    This is used when reading reports saved before session phases were stored.
    It returns a copy and never rewrites the canonical report.
    """
    windows = dict(market_windows or {})
    briefing_day = parse_iso_date(windows.get("briefingDate"))
    scheduled_open = bool(
        windows.get("krMarketOpenOnDate", windows.get("krCurrentSessionOpen"))
    )
    phase = kr_session_phase(briefing_day, scheduled_open, as_of)
    windows["krMarketOpenOnDate"] = scheduled_open
    windows["krSessionPhase"] = phase
    windows["krCurrentSessionActive"] = phase == "intraday"
    if phase in {"intraday", "closed"}:
        windows["krCurrentSessionDate"] = briefing_day.isoformat()
    else:
        windows["krCurrentSessionDate"] = ""
    windows["krLatestCompletedSessionDate"] = (
        briefing_day.isoformat()
        if phase == "closed"
        else str(windows.get("krPreviousSessionDate") or "")[:10]
    )
    return windows


def observed_date(day):
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def sunday_observed_date(day):
    """일요일이면 다음 월요일. 토요일 보정은 하지 않는다.

    NYSE Rule 7.2는 토요일에 걸친 휴일을 직전 금요일로 당기되 **신정만은 예외**로
    두어 전년 12/31을 휴장하지 않는다(2021-12-31 실제 개장). 신정에 양방향 보정을
    쓰면 있지도 않은 휴장일을 만들고, 반환값이 그 해 집합을 벗어나기까지 한다.
    """
    return day + dt.timedelta(days=1) if day.weekday() == 6 else day


def nth_weekday(year, month, weekday, n):
    day = dt.date(year, month, 1)
    offset = (weekday - day.weekday()) % 7
    return day + dt.timedelta(days=offset + 7 * (n - 1))


def last_weekday(year, month, weekday):
    if month == 12:
        day = dt.date(year, 12, 31)
    else:
        day = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return day - dt.timedelta(days=(day.weekday() - weekday) % 7)


def easter_date(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def us_market_holidays(year):
    # 달력일이 주말에 걸리면 NYSE는 인접 평일에 휴장한다. 신정만 토요일 보정이
    # 없다(sunday_observed_date 참고). 성탄절은 양방향이다 — 2021-12-24(토→금),
    # 2022-12-26(일→월) 모두 실제 휴장일이었다.
    fixed = [
        sunday_observed_date(dt.date(year, 1, 1)),
        observed_date(dt.date(year, 7, 4)),
        observed_date(dt.date(year, 12, 25)),
    ]
    # Juneteenth는 연방 공휴일 지정(2021-06-17)이 NYSE 휴장으로 이어진 것이 2022년
    # 부터다. 2021-06-18은 실제 정규 거래일이었으므로 그 전 연도에 적용하면 과거
    # 백테스트와 세션일 판정이 하루씩 틀린다.
    # 출처: NYSE Holidays & Trading Hours https://www.nyse.com/markets/hours-calendars
    if year >= 2022:
        fixed.append(observed_date(dt.date(year, 6, 19)))
    return set(fixed + [
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        easter_date(year) - dt.timedelta(days=2),
        last_weekday(year, 5, 0),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
    ])


# 음력 공휴일과 **대체공휴일**, 그리고 선거일·임시공휴일. 고정 공휴일이 주말에 걸리면 다음 첫 비공휴일이
# 휴장일이 되므로(2023년 개정으로 성탄절·부처님오신날까지 적용) 그 날짜도 여기 적는다.
# 대체공휴일이 빠지면 열리지 않은 장이 정규 거래일로 판정되어, 브리핑이 없는 마감을
# 서술하고 세션일과 어긋난 yfinance 수치가 통째로 폐기된다.
# 출처: KRX 연간 휴장일 안내 https://open.krx.co.kr
# 같은 표가 features/market_calendar/adapters/exchange.py::KRX_HOLIDAYS에도 있다.
# 한쪽만 고치면 갈라진다 — 실제로 2026-09-28·2026-10-05가 그렇게 갈라져 있었다.
KR_LUNAR_MARKET_HOLIDAYS = {
    2024: ["2024-02-09", "2024-02-12", "2024-04-10", "2024-05-15", "2024-09-16", "2024-09-17", "2024-09-18"],
    2025: ["2025-01-28", "2025-01-29", "2025-01-30", "2025-03-03", "2025-05-06", "2025-06-03", "2025-10-06", "2025-10-07", "2025-10-08"],
    2026: [
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-25",
        # 제9회 전국동시지방선거(2026-06-03 수). 공직선거법 제34조가 정한 임기만료
        # 지방선거일이며 `관공서의 공휴일에 관한 규정` 제2조 제10호의 법정 공휴일이라
        # KRX가 휴장한다(2025-06-03 대선과 같은 근거). 표에 없으면 열리지 않은 장이
        # 정규 거래일로 판정되어 브리핑이 없는 마감을 서술한다.
        # 출처: KRX 연간 휴장일 안내 https://open.krx.co.kr
        "2026-06-03",
        # 추석 연휴(9/24 목~9/26 토)는 토요일까지만 걸치고 일요일과 겹치지 않는다.
        # 설날·추석의 대체공휴일(관공서의 공휴일에 관한 규정 제3조 제1항 제2호)은
        # 일요일과 겹칠 때만 적용되므로(국경일·성탄절과 달리 토요일은 대상이 아니다)
        # 9/28은 대체휴일이 아니다 — 넣었다가 실제로 열린 장을 휴장으로 오판했다.
        "2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05",
    ],
    2027: [
        "2027-02-08", "2027-02-09", "2027-02-10", "2027-05-13",
        "2027-08-16", "2027-09-14", "2027-09-15", "2027-09-16",
        "2027-10-04", "2027-10-11", "2027-12-27",
    ],
}


def kr_market_holidays(year):
    holidays = {
        dt.date(year, 1, 1),
        dt.date(year, 3, 1),
        dt.date(year, 5, 1),
        dt.date(year, 5, 5),
        dt.date(year, 6, 6),
        dt.date(year, 8, 15),
        dt.date(year, 10, 3),
        dt.date(year, 10, 9),
        dt.date(year, 12, 25),
    }
    for text in KR_LUNAR_MARKET_HOLIDAYS.get(year, []):
        holidays.add(dt.date.fromisoformat(text))
    last_day = dt.date(year, 12, 31)
    while last_day.weekday() >= 5:
        last_day -= dt.timedelta(days=1)
    holidays.add(last_day)
    return holidays


_EXCHANGE_CALENDAR_CACHE = {}
_EXCHANGE_CALENDAR_ERROR_TTL_SECONDS = 60


def connected_exchange_calendar_status(day, market):
    """Return a connected exchange API status, or None for static fallback."""
    try:
        from features.common.market_data.toss_open_api import (
            fetch_toss_market_calendar,
            toss_credentials_available,
        )
        if not toss_credentials_available():
            return None
    except Exception:
        return None

    normalized_market = normalize_market_code(market).value
    if normalized_market == MarketCode.UNKNOWN.value:
        return None
    key = (normalized_market, day.isoformat())
    cached = _EXCHANGE_CALENDAR_CACHE.get(key)
    now = time.monotonic()
    if cached and (cached[1] is not None or now - cached[0] < _EXCHANGE_CALENDAR_ERROR_TTL_SECONDS):
        return cached[1]
    try:
        status = fetch_toss_market_calendar(normalized_market, date=day.isoformat())
    except Exception:
        status = None
    if not isinstance(status, dict) or status.get("date") != day.isoformat() or not isinstance(status.get("isOpen"), bool):
        status = None
    _EXCHANGE_CALENDAR_CACHE[key] = (now, status)
    return status


def _normalize_exchange_calendar_status(day, market, raw):
    if isinstance(raw, bool):
        return {
            "date": day.isoformat(),
            "market": market,
            "isOpen": raw,
            "provider": "exchange_api",
        }
    if not isinstance(raw, dict):
        return None
    if raw.get("date") != day.isoformat() or not isinstance(raw.get("isOpen"), bool):
        return None
    return {
        "date": day.isoformat(),
        "market": market,
        "isOpen": raw["isOpen"],
        "provider": str(raw.get("provider") or "exchange_api"),
        "previousBusinessDay": str(raw.get("previousBusinessDay") or "")[:10],
        "nextBusinessDay": str(raw.get("nextBusinessDay") or "")[:10],
    }


def market_open_status(day, market, exchange_calendar_fetcher=None):
    """Resolve one market date with exchange API priority and static fallback."""
    normalized_market = normalize_market_code(market).value
    fetcher = exchange_calendar_fetcher or connected_exchange_calendar_status
    try:
        api_status = _normalize_exchange_calendar_status(day, normalized_market, fetcher(day, normalized_market))
    except Exception:
        api_status = None
    if api_status is not None:
        api_status["source"] = "exchange_api"
        return api_status

    if normalized_market in MARKET_EXCHANGES:
        # 유럽·일본은 거래소별 표를 합쳐 판정한다. 유럽은 런던과 대륙이 갈리는 날이
        # 연 십여 일 있어 하나의 "유럽 휴장" 플래그로는 틀린다.
        status = market_exchange_status(normalized_market, day)
        return {
            "date": day.isoformat(),
            "market": normalized_market,
            "isOpen": status["isOpen"],
            "provider": "static_calendar" if status["coverage"] != "coverage_expired" else "coverage_expired",
            "source": "static" if status["coverage"] != "coverage_expired" else "unavailable",
            "coverage": status["coverage"],
            "divergent": status.get("divergent", False),
            "openVenues": status.get("openVenues", []),
            "closedVenues": status.get("closedVenues", []),
        }

    if day.weekday() >= 5:
        is_open = False
    elif normalized_market == "US":
        is_open = day not in us_market_holidays(day.year)
    elif normalized_market == "KR":
        is_open = day not in kr_market_holidays(day.year)
    else:
        is_open = False
    supported_static_market = normalized_market in {MarketCode.US.value, MarketCode.KR.value}
    return {
        "date": day.isoformat(),
        "market": normalized_market,
        "isOpen": is_open,
        "provider": "static_calendar" if supported_static_market else "unsupported_market",
        "source": "static" if supported_static_market else "unavailable",
    }


def is_market_open(day, market, exchange_calendar_fetcher=None):
    return market_open_status(day, market, exchange_calendar_fetcher)["isOpen"]


def _business_day_from_status(status, field, *, before=None, after=None):
    try:
        value = dt.date.fromisoformat(str(status.get(field) or "")[:10])
    except (TypeError, ValueError):
        return None
    if before is not None and value >= before:
        return None
    if after is not None and value <= after:
        return None
    return value


# 휴장일 표가 없는 연도(coverage_expired)에서는 어떤 날도 개장으로 판정되지 않아
# 아래 두 함수의 최종 폴백이 매번 도달한다. 그때 달력상 하루를 그대로 돌려주면
# 세션일이 토·일이 된다 — 실측으로 2027-03-08 브리핑의 유럽·일본 세션일이 일요일
# 2027-03-07이었다. 개장 여부는 계속 모른다고 보고하되(provider=coverage_expired),
# **주말은 표 없이도 아는 사실**이므로 세션일 후보에서 뺀다. 공휴일까지 맞히려는
# 추측은 하지 않는다.
def _nearest_weekday(day, step):
    cursor = day
    for _ in range(7):
        cursor += dt.timedelta(days=step)
        if cursor.weekday() < 5:
            return cursor
    return day + dt.timedelta(days=step)


def previous_trading_day(day, market, exchange_calendar_fetcher=None):
    status = market_open_status(day, market, exchange_calendar_fetcher)
    if status.get("source") == "exchange_api":
        api_previous = _business_day_from_status(status, "previousBusinessDay", before=day)
        if api_previous is not None:
            return api_previous
    cursor = day - dt.timedelta(days=1)
    for _ in range(14):
        if is_market_open(cursor, market, exchange_calendar_fetcher):
            return cursor
        cursor -= dt.timedelta(days=1)
    return _nearest_weekday(day, -1)


def next_trading_day(day, market, exchange_calendar_fetcher=None):
    cursor = day + dt.timedelta(days=1)
    for _ in range(14):
        if is_market_open(cursor, market, exchange_calendar_fetcher):
            return cursor
        cursor += dt.timedelta(days=1)
    return _nearest_weekday(day, 1)


def publication_date_for_session(session_date: str, market_scope: str) -> str:
    """사용자가 고른 시장 세션일을 저장·생성 기준인 발행일로 옮긴다.

    한 브리핑 안에서 두 시장의 세션일은 하루 어긋난다. 발행일 D에서 미국장은
    D-1 정규장을 복기하고 한국장은 D 장을 다룬다. 따라서 같은 세션일이라도
    어느 시장을 생성하느냐에 따라 발행일이 달라진다.

        미국장·유럽장 세션 S -> 발행일 = S 다음 거래일 (한국시간 자정 이후 마감)
        한국장·일본장 세션 S -> 발행일 = S           (KST와 같은 시간대)
        여러 시장 동시 선택   -> 밤샘 마감 시장 기준

    저장 키와 아카이브 정렬은 계속 발행일이다. 이 함수는 입력 해석만 바꾼다.
    """
    text = str(session_date or "").strip()[:10]
    try:
        day = dt.date.fromisoformat(text)
    except ValueError:
        return text
    from features.daily_briefing.schema import normalize_market_selection

    markets = normalize_market_selection(market_scope)
    overnight = [key for key in OVERNIGHT_CLOSE_MARKETS if key in markets]
    if not overnight:
        return day.isoformat()
    # 밤샘 마감 시장이 하나라도 있으면 그 기준으로 옮긴다. 여러 시장을 함께
    # 고르면 발행일 하나로 둘을 다 만족시킬 수 없다는 긴장이 그대로 남는다 —
    # 미국+한국에서 이미 그랬고(한국장은 그 다음 세션이 함께 담긴다), 시장이
    # 늘어도 규칙은 같다.
    return next_trading_day(day, overnight[0].upper()).isoformat()


def publication_date_groups(session_date: str, market_scope) -> list[tuple[str, list[str]]]:
    """고른 세션일 하나를 시장별 발행일로 나눈다.

    발행일 하나로 두 시장을 다 만족시킬 수 없다. 미국장 세션 S의 발행일은 S 다음
    거래일이고, 한국장 세션 S의 발행일은 S다. 예전에는 함께 고르면 밤샘 마감 시장
    기준 하나로 합쳤는데, 그러면 나머지 시장은 그 발행일을 **자기 세션일로** 읽는다 —
    금요일(08-07)을 고르고 미국장·한국장을 함께 만들면 미국장은 08-07 장을, 한국장은
    08-10 장을 다뤘다. 고르지 않은 날의 브리핑이 아무 경고 없이 나왔다.

    저장 파일은 이미 시장별이므로(`{발행일}.{시장}.json`) 그룹을 나눠 각각 만들면 둘 다
    사용자가 고른 세션을 다룬다. 미국·유럽은 한 그룹, 한국·일본은 다른 그룹이 되어
    시장이 넷으로 늘어도 그룹은 최대 둘이다.

    날짜를 읽을 수 없으면 나누지 않는다. 그 판단은 호출부(오늘 날짜 사용)가 갖는다.
    """
    from features.daily_briefing.schema import normalize_market_selection

    markets = list(normalize_market_selection(market_scope))
    groups: dict[str, list[str]] = {}
    for market in markets:
        groups.setdefault(publication_date_for_session(session_date, [market]), []).append(market)
    return [(date, groups[date]) for date in sorted(groups)]


def latest_trading_day_on_or_before(day, market, exchange_calendar_fetcher=None):
    status = market_open_status(day, market, exchange_calendar_fetcher)
    if status["isOpen"]:
        return day
    if status.get("source") == "exchange_api":
        api_previous = _business_day_from_status(status, "previousBusinessDay", before=day)
        if api_previous is not None:
            return api_previous
    cursor = day
    for _ in range(14):
        if is_market_open(cursor, market, exchange_calendar_fetcher):
            return cursor
        cursor -= dt.timedelta(days=1)
    return previous_trading_day(day, market, exchange_calendar_fetcher)


def _date_range(start_iso, end_iso):
    try:
        start = dt.date.fromisoformat(start_iso)
        end = dt.date.fromisoformat(end_iso)
    except Exception:
        return []
    out = []
    cursor = start
    while cursor <= end and len(out) < 31:
        out.append(cursor.isoformat())
        cursor += dt.timedelta(days=1)
    return out


# 분석 모드별 세션 역할(primary/secondary/background/off_session_news).
# doc_analysis_priority()가 자료의 세션 토큰을 이 표로 매핑한다.
_MODE_SESSION_ROLES = {
    "weekday_kr_preopen": {
        "US_PREV_REGULAR": "primary",
        "KR_PREV_REGULAR": "primary",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "weekday_kr_open": {
        "US_PREV_REGULAR": "primary",
        "KR_CURRENT_INTRADAY": "primary",
        "KR_PREV_REGULAR": "background",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "weekday_kr_closed": {
        "US_PREV_REGULAR": "primary",
        "KR_CURRENT_INTRADAY": "primary",
        "KR_PREV_REGULAR": "background",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "us_holiday_kr_preopen": {
        "KR_PREV_REGULAR": "primary",
        "US_PREV_REGULAR": "secondary",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "us_holiday_kr_open": {
        "KR_CURRENT_INTRADAY": "primary",
        "US_PREV_REGULAR": "secondary",
        "KR_PREV_REGULAR": "background",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "us_holiday_kr_closed": {
        "KR_CURRENT_INTRADAY": "primary",
        "US_PREV_REGULAR": "secondary",
        "KR_PREV_REGULAR": "background",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "kr_holiday": {
        "US_PREV_REGULAR": "primary",
        "KR_PREV_REGULAR": "background",
        "TODAY_LATEST_NEWS": "secondary",
        "GLOBAL_PREV": "background",
    },
    "weekend": {
        "US_PREV_REGULAR": "primary",
        "KR_PREV_REGULAR": "primary",
        "TODAY_LATEST_NEWS": "off_session_news",
        "GLOBAL_PREV": "background",
    },
    "both_holiday": {
        "US_PREV_REGULAR": "primary",
        "KR_PREV_REGULAR": "primary",
        "TODAY_LATEST_NEWS": "off_session_news",
        "GLOBAL_PREV": "background",
    },
}

_MODE_PRIORITY_RULE = {
    "weekday_kr_preopen": "한국장 개장 전: 최근 한국 정규장 마감과 미국 전일 정규장을 주 분석축으로 둡니다. 당일 한국장 가격 반응이나 수급을 만들지 않습니다.",
    "weekday_kr_open": "평일/한국장 개장일: 주 분석축은 ①미국 전일 정규장 ②한국 당일 개장 후/장중 흐름입니다. 한국 전일 정규장은 배경 맥락으로만 쓰고, 시장 흐름 섹션의 중심을 차지하지 않게 합니다.",
    "weekday_kr_closed": "한국장 마감 후: 당일 한국 정규장 마감 결과와 미국 전일 정규장을 주 분석축으로 둡니다. 장중 수치는 종가와 구분합니다.",
    "us_holiday_kr_preopen": "미국 휴장일/한국장 개장 전: 최근 한국 정규장 마감을 우선하고, 직전 미국 정규장은 보조로 둡니다. 당일 한국장 가격 반응을 만들지 않습니다.",
    "us_holiday_kr_open": "미국 휴장일/한국 개장일: 한국 당일 장중·정규장을 우선 분석하고, 직전 미국 정규장은 보조로 둡니다. 미국 정규장 결과를 새로 만들지 말고, 미국 휴장 중 선물·환율·뉴스는 다음 미국 정규장 반응 후보로 분리합니다.",
    "us_holiday_kr_closed": "미국 휴장일/한국장 마감 후: 당일 한국 정규장 마감을 우선하고, 직전 미국 정규장은 보조로 둡니다. 미국 정규장 결과를 새로 만들지 않습니다.",
    "kr_holiday": "한국 휴장일: 한국 당일 장중 시황을 만들지 않습니다. 최근 미국 정규장을 우선 분석하고, 휴장 전 한국 정규장과 휴장 중 한국 관련 뉴스가 다음 한국 거래일에 어떻게 반영될지 다음 거래일 확인 재료로 다룹니다.",
    "weekend": "주말: 정규장 가격 반응이 없으므로 최근 미국·한국 정규장을 간결히 복기하고, 주말 사이 나온 새 뉴스(정책·지정학·기업·중앙은행·원자재·환율·실적·M&A·규제)는 현재 가격 반응이 아니라 다음 거래일 반영 후보로 다룹니다. 장중 시황을 만들지 않습니다.",
    "both_holiday": "양시장 휴장일: 정규장 가격 반응이 없으므로 최근 미국·한국 정규장을 간결히 복기하고, 휴장 중 나온 새 뉴스는 다음 거래일 반영 후보로 다룹니다. 장중 시황을 만들지 않습니다.",
}


def briefing_market_windows(date, exchange_calendar_fetcher=None, as_of=None):
    briefing_day = parse_iso_date(date)
    resolved = {}

    def calendar_fetcher(day, market):
        key = (market, day.isoformat())
        if key not in resolved:
            fetcher = exchange_calendar_fetcher or connected_exchange_calendar_status
            resolved[key] = fetcher(day, market)
        return resolved[key]

    # Always use the previous completed US session (D-1), never the briefing day itself.
    # On a Korean Monday morning the US briefing-day session hasn't opened yet.
    us_status = market_open_status(briefing_day, "US", calendar_fetcher)
    kr_status = market_open_status(briefing_day, "KR", calendar_fetcher)
    us_previous = previous_trading_day(briefing_day, "US", calendar_fetcher)
    kr_current_open = kr_status["isOpen"]
    us_open = us_status["isOpen"]
    kr_previous = previous_trading_day(briefing_day, "KR", calendar_fetcher) if kr_current_open else latest_trading_day_on_or_before(briefing_day, "KR", calendar_fetcher)
    kr_phase = kr_session_phase(briefing_day, kr_current_open, as_of)
    kr_current_session_date = briefing_day.isoformat() if kr_phase in {"intraday", "closed"} else ""

    # 브리핑 대상일의 시장 개장 상태로 분석 모드를 정한다.
    if kr_current_open and us_open:
        analysis_mode = {
            "pre_open": "weekday_kr_preopen",
            "intraday": "weekday_kr_open",
            "closed": "weekday_kr_closed",
        }[kr_phase]
    elif kr_current_open and not us_open:
        analysis_mode = {
            "pre_open": "us_holiday_kr_preopen",
            "intraday": "us_holiday_kr_open",
            "closed": "us_holiday_kr_closed",
        }[kr_phase]
    elif not kr_current_open and us_open:
        analysis_mode = "kr_holiday"
    else:
        analysis_mode = "weekend" if briefing_day.weekday() >= 5 else "both_holiday"

    weekend_or_holiday_news = (
        analysis_mode in {"kr_holiday", "weekend", "both_holiday"}
        or analysis_mode.startswith("us_holiday_kr_")
    )
    # 휴장/주말 사이 새 뉴스 구간: 가장 최근 정규장 다음날부터 브리핑 대상일까지.
    last_regular = max(us_previous, kr_previous)
    if analysis_mode == "kr_holiday":
        off_start = kr_previous + dt.timedelta(days=1)
    elif analysis_mode.startswith("us_holiday_kr_"):
        off_start = us_previous + dt.timedelta(days=1)
    else:
        off_start = last_regular + dt.timedelta(days=1)
    off_start = min(off_start, briefing_day)
    off_window = {"start": off_start.isoformat(), "end": briefing_day.isoformat()}

    # 유럽·일본 세션. 두 시장은 한국시간 기준으로 성격이 정반대라 규칙을 따로 쓴다.
    #
    # 유럽은 미국과 같다. 런던 16:30 마감은 KST 00:30~01:30(다음 날)이라 브리핑일 D의
    # 유럽 세션은 D 아침에 아직 끝나지 않았다. 그래서 미국처럼 항상 직전 완료 세션을 쓴다.
    #
    # 일본은 한국과 같다. JST가 KST와 같은 시간대라 09:00~15:30 세션이 한국 장중과
    # 나란히 흐른다. 그래서 한국처럼 생성 시각으로 pre_open/intraday/closed를 가른다.
    europe_status = market_open_status(briefing_day, "EUROPE", calendar_fetcher)
    jp_status = market_open_status(briefing_day, "JP", calendar_fetcher)
    europe_session = previous_trading_day(briefing_day, "EUROPE", calendar_fetcher)
    jp_phase = jp_session_phase(briefing_day, jp_status["isOpen"], as_of)
    jp_session = (
        briefing_day
        if jp_phase == "closed"
        else previous_trading_day(briefing_day, "JP", calendar_fetcher)
        if jp_status["isOpen"]
        else latest_trading_day_on_or_before(briefing_day, "JP", calendar_fetcher)
    )
    market_sessions = {
        "us": {
            "market": "US", "timezone": "America/New_York",
            "sessionDate": us_previous.isoformat(),
            "openOnBriefingDate": us_open,
            "provider": us_status["provider"],
        },
        "kr": {
            "market": "KR", "timezone": "Asia/Seoul",
            "sessionDate": (briefing_day if kr_phase == "closed" else kr_previous).isoformat(),
            "openOnBriefingDate": kr_current_open,
            "phase": kr_phase,
            "provider": kr_status["provider"],
        },
        "europe": {
            "market": "EUROPE", "timezone": "Europe/London",
            "sessionDate": europe_session.isoformat(),
            "openOnBriefingDate": europe_status["isOpen"],
            "provider": europe_status["provider"],
            "coverage": europe_status.get("coverage", ""),
            # 런던과 대륙이 갈리는 날은 "유럽 휴장"으로 뭉뚱그리지 않는다.
            "venuesDiverge": europe_status.get("divergent", False),
            "openVenues": europe_status.get("openVenues", []),
            "closedVenues": europe_status.get("closedVenues", []),
        },
        "jp": {
            "market": "JP", "timezone": "Asia/Tokyo",
            "sessionDate": jp_session.isoformat(),
            "openOnBriefingDate": jp_status["isOpen"],
            "phase": jp_phase,
            "provider": jp_status["provider"],
            "coverage": jp_status.get("coverage", ""),
        },
    }

    session_roles = _MODE_SESSION_ROLES[analysis_mode]
    primary_sessions = [t for t, r in session_roles.items() if r == "primary"]
    secondary_sessions = [t for t, r in session_roles.items() if r == "secondary"]
    if weekend_or_holiday_news:
        secondary_sessions = secondary_sessions + ["OFF_SESSION_NEWS"]

    source_dates = {us_previous.isoformat(), kr_previous.isoformat()}
    if kr_current_open:
        source_dates.add(briefing_day.isoformat())
    if weekend_or_holiday_news:
        # 주말/휴장 사이 새 뉴스가 누락되지 않도록 off-session 구간 날짜를 명시 포함.
        source_dates.update(_date_range(off_window["start"], off_window["end"]))

    closed_notes = []
    if not kr_current_open:
        closed_notes.append(f"한국장 {briefing_day.isoformat()}은 주말/공휴일 가능성이 높아 당일 장중 시황으로 해석하지 않습니다.")
    if not us_open:
        closed_notes.append(f"미국장 {briefing_day.isoformat()}은 휴장일 가능성이 높아 당일 미국 정규장 결과를 새로 만들지 않습니다.")
    if briefing_day.weekday() >= 5:
        closed_notes.append(f"브리핑 대상일 {briefing_day.isoformat()}은 주말입니다.")

    if kr_phase == "pre_open":
        kr_rule = (
            f"한국장은 가장 최근 마감한 {kr_previous.isoformat()} 정규장 결과를 중심으로 해석합니다. "
            f"{briefing_day.isoformat()} 정규장은 아직 개장 전이므로 당일 가격 반응을 만들지 않습니다."
        )
    elif kr_phase == "intraday":
        kr_rule = (
            f"한국장은 직전 한국 거래일인 {kr_previous.isoformat()} 정규장 결과와 "
            f"{briefing_day.isoformat()} 개장 후/장중 시황 자료를 구분해 해석합니다."
        )
    elif kr_phase == "closed":
        kr_rule = f"한국장은 {briefing_day.isoformat()} 정규장 마감 결과를 중심으로 해석합니다."
    else:
        kr_rule = f"한국장은 가장 최근 한국 거래일인 {kr_previous.isoformat()} 정규장 결과를 중심으로 해석합니다. 당일 한국장이 휴장일이면 장중 반영 여부를 단정하지 않습니다."
    return {
        "briefingDate": date,
        "analysisMode": analysis_mode,
        "usRegularSessionDate": us_previous.isoformat(),
        "krPreviousSessionDate": kr_previous.isoformat(),
        "krCurrentSessionDate": kr_current_session_date,
        "krCurrentSessionOpen": kr_current_open,
        "krMarketOpenOnDate": kr_current_open,
        "krCurrentSessionActive": kr_phase == "intraday",
        "krSessionPhase": kr_phase,
        "krLatestCompletedSessionDate": briefing_day.isoformat() if kr_phase == "closed" else kr_previous.isoformat(),
        "usMarketOpenOnDate": us_open,
        "calendarProviders": {
            "US": us_status["provider"],
            "KR": kr_status["provider"],
            "EUROPE": europe_status["provider"],
            "JP": jp_status["provider"],
        },
        # 0.5 시장별 세션 기술자. 기존 us*/kr* 키는 호환을 위해 그대로 두고,
        # 새 시장은 여기에만 담는다 — 기존 소비자가 읽는 모양을 바꾸지 않기 위해서다.
        "marketSessions": market_sessions,
        "primarySessions": primary_sessions,
        "secondarySessions": secondary_sessions,
        "sessionRoles": session_roles,
        "weekendOrHolidayNewsMode": weekend_or_holiday_news,
        "offSessionNewsWindow": off_window,
        "sourceDates": sorted(source_dates),
        "closedNotes": closed_notes,
        "sessionPriorityRule": _MODE_PRIORITY_RULE[analysis_mode],
        "rule": f"한국시간 브리핑일 {date} 기준: 미국장은 최근 미국 거래일인 {us_previous.isoformat()} 정규장 마감 결과를 우선 해석하고, {kr_rule}",
    }


# 자료의 세션 버킷 → 분석 우선순위(primary/secondary/background/off_session_news).
_BUCKET_SESSION_TOKEN = {
    "US 전일 정규장": "US_PREV_REGULAR",
    "KR 전일 정규장": "KR_PREV_REGULAR",
    "KR 당일 개장/장중": "KR_CURRENT_INTRADAY",
    "당일 최신 자료": "TODAY_LATEST_NEWS",
    "전일 글로벌 자료": "GLOBAL_PREV",
}


def doc_analysis_priority(doc, windows):
    """브리핑 분석 모드 기준으로 자료의 우선순위를 반환한다.

    primary / secondary / background / off_session_news 중 하나.
    """
    roles = windows.get("sessionRoles", {})
    token = _BUCKET_SESSION_TOKEN.get(doc_market_bucket(doc, windows))
    if token and token in roles:
        return roles[token]
    # 정규장 버킷이 아니면 주말/휴장 사이 새 뉴스인지 확인한다.
    if windows.get("weekendOrHolidayNewsMode"):
        win = windows.get("offSessionNewsWindow") or {}
        session = doc.get("marketSessionDate") or doc.get("date", "")
        if win.get("start") and win.get("end") and win["start"] <= session <= win["end"]:
            return "off_session_news"
    return "background"


@lru_cache(maxsize=1)
def _company_market_matchers():
    """Compile (matcher, market) pairs from ``config/company_master.json``.

    회사명/별칭/티커가 기사 텍스트에 등장하면 그 회사의 시장을 시장 태그 신호로
    쓴다. ASCII 별칭은 단어 경계로, 한글 별칭은 부분 문자열로 매칭한다.
    """
    try:
        data = json.loads(resolve_config("company_master.json").read_text(encoding="utf-8"))
    except Exception:
        return ()
    matchers = []
    for company in data.get("companies", []) or []:
        market = str(company.get("market") or "").strip().upper()
        if market not in _PRODUCT_MARKET_VALUES:
            continue
        names = [company.get("name", ""), company.get("ticker", "")] + list(company.get("aliases", []) or [])
        for name in names:
            token = str(name or "").strip().lower()
            if len(token) < 2:
                continue
            if re.fullmatch(r"[\x00-\x7f]+", token):
                if len(token) < 3:
                    # 두 글자 ASCII 티커(GM 등)는 일반 단어와 충돌 위험이 커서 제외.
                    continue
                pattern = re.compile(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])")
                matchers.append((lambda text, _p=pattern: len(_p.findall(text)), market))
            else:
                matchers.append((lambda text, _t=token: text.count(_t), market))
    return tuple(matchers)


def _text_has_token(text, token):
    """Substring for Korean/symbol tokens, word-boundary for ASCII words.

    단순 부분 문자열 매칭은 "dow"→"downgrade", "oil"→"turmoil" 같은 오탐으로
    잘못된 시장 태그를 만들었다. ASCII 단어 토큰은 앞뒤 영숫자를 차단하되
    복수형(s)과 뒤따르는 숫자(S&P500, Dow30)는 허용한다.
    """
    if not token.isascii() or not token[0].isalnum():
        return token in text
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}s?(?![a-z])", text) is not None


_EXPLICIT_MARKETS = {"US", "KR", "EUROPE", "JP", "GLOBAL", "EU"}
# 회사 마스터 matcher가 다루는 시장. 시장 계약에서 파생한다.
_PRODUCT_MARKET_VALUES = frozenset(market.value for market in PRODUCT_MARKETS)


def _canonical_market(token: str) -> str:
    """`EU`는 경계에서만 받아주고 저장값은 `EUROPE`다(영국을 포함하므로)."""
    return "EUROPE" if token == "EU" else token


# 거래소·지수·통화·중앙은행처럼 그 시장을 특정하는 말만 넣는다. 국가명 단독은
# 넣지 않는다 — "이탈리아 총선"이 시장 기사로 승격되기 때문이다.
EUROPE_TOKENS = (
    "유럽증시", "유럽 증시", "유로존", "유로화", "ecb", "유럽중앙은행", "european central bank",
    "ftse", "dax", "cac 40", "aex", "ibex", "ftse mib", "stoxx", "euro stoxx",
    "런던증시", "런던 증시", "프랑크푸르트", "유로스톡스",
    "bank of england", "영란은행", "boe", "gilt", "bund", "분트",
    "euronext", "xetra", "lse", "borsa italiana", "bolsa de madrid",
    # 현지어: 각국 지수·중앙은행·거래소
    "dax-index", "leitzins", "bundesbank", "aktienmarkt",
    "bourse de paris", "banque de france", "cac40",
    "beurs", "amsterdamse beurs", "aandelenmarkt",
    "borsa", "piazza affari", "spread btp",
    "bolsa", "ibex 35", "banco de españa", "banco de espana",
)
JAPAN_TOKENS = (
    "일본증시", "일본 증시", "도쿄증시", "도쿄 증시", "닛케이", "nikkei", "topix", "토픽스",
    "일본은행", "bank of japan", "boj", "엔화", "엔달러", "엔·달러", "yen",
    "도쿄증권거래소", "tokyo stock exchange", "jpx",
    # 일본어: 지수·중앙은행·거래소·통화
    "日経平均", "日経", "東証", "東京証券取引所", "日銀", "円安", "円高",
    "プライム市場", "topix", "国債利回り",
)


# 아래 세 표는 EUROPE/JAPAN과 달리 오랫동안 **한국어와 영어만** 담고 있었다. 그래서
# 현지어 기사는 자기 시장만 말할 수 있고 남의 시장은 가리키지 못했다 — 실측(2026-08-09)에서
# 제목이 미국을 가리키는 일본어 기사 17건 중 16건(94.1%)이 US 태그를 못 받았고,
# `NYダウ 3日連続最高値`가 일본장 레인에 들어갔다. 유럽어는 25.0%였는데 그나마 나은 건
# 라틴 문자라 `Trump`·`Dollar`·`Nasdaq`가 우연히 그대로 쓰이기 때문이지 설계가 맞아서가 아니다.
#
# 추가 원칙은 EUROPE_TOKENS와 같다 — 그 시장을 특정하는 말만 넣는다. 그리고 두 가지를 주의한다.
#   1. 한자·가나는 `_text_has_token()`에서 부분 문자열로 매칭된다. 다른 말 안에 우연히
#      박히지 않는지 본다. `ダウ`는 넣지 않는다 — `ダウン`(down)에 걸린다. `米` 단독도
#      넣지 않는다 — 쌀이다(`米価格`).
#   2. 라틴 문자는 단어 경계로 매칭되어 뒤에 글자가 붙으면 안 걸린다. 로망스어 굴절형은
#      형태를 직접 적는다(`americano/a/i/e`). 악센트가 있으면 비ASCII라 부분 일치가 되어
#      한 형태로 충분하다(`américain` → `américaine(s)`).
KR_TOKENS = (
    "한국", "서울증시", "코스피", "코스닥", "kospi", "kosdaq", "krx",
    "원달러", "원·달러", "원화", "외국인 순매", "기관 순매", ".ks", ".kq",
    "korea chip", "korean semiconductor", "korean exporter", "korean chip",
    "국내 증시", "국내증시", "유가증권시장", "한국은행", "금융감독원",
    "실적 시즌", "실적발표", "잠정실적",
    # 일본어
    "韓国株", "韓国市場", "韓国銀行", "コスピ", "ソウル株式市場",
    # 유럽어 — 한국 시장을 특정하는 말만. 국가명 단독은 넣지 않는다.
    "kospi", "borsa di seoul", "bolsa de seúl", "bourse de séoul",
)
US_TOKENS = (
    "미국", "뉴욕증시", "뉴욕 증시", "월스트리트", "나스닥", "nasdaq", "s&p", "dow",
    "다우", "nyse", "wall street", "federal reserve", "연준", "treasury",
    "fed", "fomc", "earnings", "earnings season", "월가", "미 증시", "미국채", "russell", "잭슨홀",
    # 일본어 — `ダウ` 단독은 `ダウン`에 걸리므로 반드시 앞말을 붙인다.
    "米国", "米株", "米市場", "米経済", "米金利", "米長期金利", "米利上げ", "米利下げ",
    # 비교 대상 텍스트는 `.lower()`를 거치므로 라틴 문자가 섞인 토큰은 소문자로 적는다
    # (`NYダウ`로 적으면 `token in text`가 영원히 거짓이다).
    "米国債", "米連邦準備", "frb", "ナスダック", "nyダウ", "ダウ平均", "ny株",
    "ニューヨーク株式市場", "ニューヨーク市場", "ウォール街", "米関税",
    # 국적 형용사(americano·américain·estadounidense·amerikaans)는 넣지 않는다. 이 파일이
    # EUROPE_TOKENS에 세운 "국가명 단독은 넣지 않는다"에 해당하고, 실측에서 다른 말 안에
    # 박혔다 — `américain`이 `sud-américain`(남아메리카)에, `americana`가 브라질 유통사
    # `Americanas`에 걸려 둘 다 미국장 기사가 됐다. 나라 이름 명사구만 남긴다.
    # 독일어
    "us-notenbank", "us-börse", "us-aktien", "us-zinsen", "us-märkte", "wall-street",
    # 프랑스어
    "états-unis", "etats-unis", "réserve fédérale", "bourse de new york",
    # 이탈리아어
    "stati uniti", "riserva federale", "borsa americana", "borsa di new york",
    # 스페인어
    "estados unidos", "reserva federal", "bolsa de nueva york",
    # 네덜란드어
    "verenigde staten", "amerikaanse beurs",
)
GLOBAL_TOKENS = (
    "global", "international", "middle east", "oil", "crude", "dollar", "supply chain",
    "원자재", "국제", "중동", "유가", "달러", "공급망", "관세", "지정학",
    # 일본어
    "原油", "原油価格", "供給網", "サプライチェーン", "地政学", "資源価格", "中東情勢",
    # 독일어 — `zölle`는 움라우트 덕에 `Strafzölle`·`US-Zölle`까지 부분 일치로 잡힌다.
    "ölpreis", "rohöl", "lieferkette", "zölle", "geopolitik",
    # 프랑스어
    "pétrole", "chaîne d'approvisionnement", "droits de douane", "géopolitique",
    # 이탈리아어 — `crudo`는 넣지 않는다(생선·식품 기사와 충돌).
    "petrolio", "greggio", "catena di fornitura", "dazi", "geopolitica",
    # 스페인어
    "petróleo", "cadena de suministro", "aranceles", "geopolítica",
    # 네덜란드어 — `olie`는 단어 경계 때문에 `olieprijs`를 못 잡으므로 형태를 직접 적는다.
    "olieprijs", "ruwe olie", "toeleveringsketen", "invoerheffingen", "geopolitiek",
)
EUROPE_TOKENS = EUROPE_TOKENS + (
    # 일본어·한국어에서 유럽 시장을 가리키는 말. 유럽 피드가 아닌 곳에서 온 유럽 기사가
    # 자기 시장 어휘를 쓰지 않기 때문에 따로 붙인다.
    "欧州株", "欧州市場", "ユーロ圏", "欧州中央銀行", "英中銀", "独連銀",
)


# 위 다섯 표를 고치면 이 값을 올린다. RSS 캐시가 행마다 이 버전을 들고 있어서, 값이
# 달라지면 파일이 그대로여도 그 행을 다시 읽는다. 이게 없으면 표를 고쳐도 이미 저장된
# 자료는 영원히 옛 태그로 남는다 — 실제로 UNKNOWN 3,912건이 그렇게 쌓였다.
# `test_market_inference_multilingual.py`가 표의 해시를 함께 검사하므로, 표만 고치고
# 버전을 안 올리면 테스트가 잡는다.
MARKET_TAGGER_VERSION = 2


# 거래소 접미사는 자유 텍스트 토큰으로 두면 안 된다. `.t`는 URL·약어 어디에나
# 들어 있어 미국·한국 기사를 일본으로 태깅했다(실측 회귀). 앞에 실제 티커가 붙은
# 형태로만 인식한다: `7203.T`, `ASML.AS`, `SAP.DE`.
_EXCHANGE_SUFFIX_MARKETS = {
    "t": "JP",
    "l": "EUROPE", "de": "EUROPE", "pa": "EUROPE",
    "as": "EUROPE", "mi": "EUROPE", "mc": "EUROPE",
}
_EXCHANGE_TICKER_RE = re.compile(
    # 슬래시 뒤는 제외한다. 추론 텍스트에 URL이 포함되므로 `a.com/b.t` 같은 경로가
    # 티커로 읽히면 미국 기사가 일본으로 넘어간다.
    r"(?<![a-z0-9/])[a-z0-9]{1,6}\.(t|l|de|pa|as|mi|mc)(?![a-z0-9])"
)


def _exchange_suffix_markets(text: str) -> set[str]:
    return {
        _EXCHANGE_SUFFIX_MARKETS[match.group(1)]
        for match in _EXCHANGE_TICKER_RE.finditer(text)
    }


def infer_doc_markets(doc):
    """Infer all markets discussed by an article.

    Returns one or more of US, KR, GLOBAL, UNKNOWN. US/KR/GLOBAL can overlap.
    UNKNOWN is only used when no useful market signal is present; an explicit
    UNKNOWN tag is treated as "no signal" and re-inferred, not echoed back.
    """
    explicit = doc.get("markets")
    if isinstance(explicit, list):
        values = []
        for item in explicit:
            token = str(item or "").strip().upper()
            if token in _EXPLICIT_MARKETS and token not in values:
                values.append(_canonical_market(token))
        if values:
            return values
    explicit_text = str(doc.get("market") or "").strip().upper()
    if "," in explicit_text:
        values = []
        for item in explicit_text.split(","):
            token = item.strip()
            if token in _EXPLICIT_MARKETS and token not in values:
                values.append(_canonical_market(token))
        if values:
            return values
    if explicit_text in _EXPLICIT_MARKETS:
        return [_canonical_market(explicit_text)]
    if explicit_text == "BOTH":
        return ["US", "KR"]
    # feed가 선언한 시장은 키워드 추론보다 우선한다. 각국 경제면에서 온 항목은
    # 그 시장이 다루는 자료라는 것이 이미 확정돼 있고, 본문 키워드는 한국어/영어에
    # 맞춰져 있어 현지어 기사에서는 신호가 되지 못한다.
    feed_market = str(doc.get("defaultMarket") or doc.get("default_market") or "").strip().upper()
    if feed_market in _EXPLICIT_MARKETS:
        return [_canonical_market(feed_market)]

    """Infer the market discussed by an article without using publisher name.

    A Korean publisher can cover Wall Street and a foreign wire can cover Seoul.
    Treating the publisher itself as a market signal caused those articles to be
    promoted into the wrong session lane.
    """
    companies = doc.get("companies", []) or []
    company_markets = {str(c.get("market") or "").upper() for c in companies}
    text = normalize(" ".join([
        doc.get("title", "") or "",
        doc.get("summary", "") or "",
        (doc.get("content", "") or "")[:1600],
        doc.get("url", "") or "",
        " ".join(doc.get("sectors", []) or []),
        " ".join(doc.get("impactTags", []) or []),
    ])).lower()
    # **본문 깊은 곳의 한 번은 신호가 아니다.** 페이지 장식이 회사 이름을 흘린다 —
    # 실측으로 Handelsblatt 기사 본문에 섞여 들어온 "bei google bevorzugen"(공유 위젯)
    # 한 줄이 Alphabet을 붙였고, 그 종목의 시장이 독일 기사를 `US`로 만들었다.
    # 제목·요약에 나오거나 본문에서 두 번은 불려야 그 시장 신호로 본다.
    head = text[:400]
    for matcher, market in _company_market_matchers():
        if market in company_markets:
            continue
        if matcher(head) or matcher(text) >= 2:
            company_markets.add(market)
    if _KR_STOCK_CODE_RE.search(text):
        company_markets.add("KR")
    kr_tokens = KR_TOKENS
    us_tokens = US_TOKENS
    global_tokens = GLOBAL_TOKENS
    is_kr = "KR" in company_markets or any(_text_has_token(text, token) for token in kr_tokens)
    is_us = "US" in company_markets or any(_text_has_token(text, token) for token in us_tokens)
    suffix_markets = _exchange_suffix_markets(text)
    is_europe = (
        "EUROPE" in company_markets
        or "EUROPE" in suffix_markets
        or any(_text_has_token(text, token) for token in EUROPE_TOKENS)
    )
    is_jp = (
        "JP" in company_markets
        or "JP" in suffix_markets
        or any(_text_has_token(text, token) for token in JAPAN_TOKENS)
    )
    is_global = any(_text_has_token(text, token) for token in global_tokens)
    markets = []
    if is_us:
        markets.append("US")
    if is_kr:
        markets.append("KR")
    if is_europe:
        markets.append("EUROPE")
    if is_jp:
        markets.append("JP")
    # 둘 이상의 시장이 함께 걸리면 지역 간 사안으로 본다.
    if is_global or len(markets) > 1:
        markets.append("GLOBAL")
    return markets or ["UNKNOWN"]


def infer_doc_market(doc):
    """Backward-compatible primary market label for existing callers.

    `BOTH` keeps meaning US+KR, exactly as stored reports use it. A document that
    also touches Europe or Japan still collapses to whichever single label these
    callers can handle; multi-market consumers should read `infer_doc_markets`.
    """
    markets = infer_doc_markets(doc)
    if "US" in markets and "KR" in markets:
        return "BOTH"
    if "KR" in markets:
        return "KR"
    if "US" in markets:
        return "US"
    if "EUROPE" in markets:
        return "EUROPE"
    if "JP" in markets:
        return "JP"
    if "GLOBAL" in markets:
        return "GLOBAL"
    return "UNKNOWN"


def doc_market_bucket(doc, windows):
    # 자료가 실제로 다루는 시장 거래일(marketSessionDate)을 발행일(date)보다 우선한다.
    # 한국 언론의 뉴욕증시 마감 기사는 발행일이 미국 정규장 거래일보다 하루 앞설 수
    # 있어, 발행일로 분류하면 전 거래일 결과를 당일 결과로 오인한다.
    date = doc.get("marketSessionDate") or doc.get("date", "")
    markets = set(infer_doc_markets(doc))
    is_kr = "KR" in markets
    is_us = "US" in markets
    if date == windows["usRegularSessionDate"] and is_us:
        return "US 전일 정규장"
    if date == windows["krPreviousSessionDate"] and is_kr:
        return "KR 전일 정규장"
    if windows.get("krCurrentSessionDate") and date == windows["krCurrentSessionDate"] and is_kr:
        return "KR 당일 개장/장중"
    if date == windows["usRegularSessionDate"]:
        return "전일 글로벌 자료"
    if windows.get("krCurrentSessionDate") and date == windows["krCurrentSessionDate"]:
        return "당일 최신 자료"
    if date == windows.get("briefingDate"):
        return "당일 최신 자료"
    return "보조 자료"


def kr_session_is_open_now(market_windows) -> bool:
    """phase가 기록되지 않은 window를 현재 시각으로 판정한다.

    세션일이 오늘이고 정규장 시간 안일 때만 참이다. 지난 세션은 끝났고 아직
    오지 않은 세션은 시작하지 않았다.
    """
    session_date = str((market_windows or {}).get("krCurrentSessionDate") or "").strip()
    if not session_date:
        return False
    now = _dt_now_kst()
    if session_date != now.date().isoformat():
        return False
    return _KR_REGULAR_OPEN <= now.time() < _KR_REGULAR_CLOSE
