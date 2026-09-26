"""Bank of Korea calendar events.

Korea had a normalizer here but no collector, and nothing in ``service.py`` ever
called it — so the calendar carried zero Korean central-bank and macro entries
while the US side had FOMC and, with a key, FRED releases.

ECOS publishes the statistics themselves, not a release-date calendar, so the
schedule is derived from what has actually been published: the latest observation
month of a series shows the cadence and where the next one falls. Those derived
dates are marked ``estimated``, never ``confirmed`` — the project reserves
``confirmed`` for dates an official operator published as a schedule.

A figure is published *after* the month it measures. The first version dated each
observed month's value on the 15th of that same month, so July CPI read as
"released July 15" — two weeks before July ended. Results now land on the
customary release day of the following month, as an all-day entry because no
official timestamp backs the day. The base-rate decision is not derived here:
its dates come from the Bank of Korea's published meeting schedule
(``central_banks.py``).
"""
from __future__ import annotations

import datetime as dt
import json as _json
import urllib.parse
import urllib.request

from features.market_calendar.schema import normalize_event

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

# ECOS 통계표 → (표시명, 주기, item1, 중요도, 다음 달 관행 발표일).
# 발표일은 공식 일정이 아니라 관행이다 — 소비자물가동향(국가데이터처)은 다음 달 초,
# 생산자물가지수(한국은행)는 다음 달 셋째 주. 2026-08 기준 실제 발표는 9/2, 9/18.
# 기준금리는 여기서 만들지 않는다. ECOS 월별 값은 매달 있어 연 8회 회의가 12회로 보였다.
BOK_RELEASES: dict[str, tuple[str, str, str, int, int]] = {
    "901Y009": ("한국 소비자물가지수 (CPI)", "M", "0", 3, 2),
    # 예전 코드 901Y014는 ECOS에 없는 표라 PPI가 한 번도 들어오지 않았다.
    "404Y014": ("한국 생산자물가지수 (PPI)", "M", "*AA", 2, 18),
}
# 사람이 읽는 통계 포털. 예전 값은 API 엔드포인트라 클릭하면 개발자 문서가 열렸다.
_ECOS_DOC = "https://ecos.bok.or.kr/"


def normalize_bok_events(rows: list[dict]) -> list[dict]:
    return [
        normalize_event({
            **row,
            "kind": row.get("kind") or "central_bank",
            "provider": "bok",
            "source": row.get("source") or "Bank of Korea",
            "status": row.get("status") or "confirmed",
        })
        for row in rows
        if isinstance(row, dict)
    ]


def _parse_ecos_month(raw: str) -> dt.date | None:
    text = str(raw or "").strip()
    if len(text) != 6 or not text.isdigit():
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:]), 1)
    except ValueError:
        return None


def _add_months(day: dt.date, months: int) -> dt.date:
    total = day.year * 12 + (day.month - 1) + months
    return dt.date(total // 12, total % 12 + 1, 1)


def release_date(observed_month: dt.date, release_day: int) -> dt.date:
    """관측월의 수치가 나오는 관행일. 언제나 관측월이 끝난 **다음 달**이다."""
    return _add_months(observed_month, 1).replace(day=release_day)


def fetch_bok_macro_events(api_key: str, *, start: str, end: str, timeout: float = 8.0) -> list[dict]:
    """Project upcoming Korean release dates from ECOS publication history.

    Returns ``[]`` without a key, matching the FRED adapter — a missing key is a
    reported coverage gap, not an error.
    """
    if not str(api_key or "").strip():
        return []
    try:
        start_date = dt.date.fromisoformat(start)
        end_date = dt.date.fromisoformat(end)
    except ValueError:
        return []

    lookback = _add_months(start_date, -6).strftime("%Y%m")
    horizon = _add_months(end_date, 1).strftime("%Y%m")
    rows: list[dict] = []

    for stat_code, (title, cycle, item1, importance, release_day) in BOK_RELEASES.items():
        parts = [api_key, "json", "kr", "1", "20", stat_code, cycle, lookback, horizon]
        if item1:
            parts.append(item1)
        path = "/".join(urllib.parse.quote(str(part), safe="") for part in parts)
        try:
            with urllib.request.urlopen(f"{ECOS_BASE}/{path}", timeout=timeout) as response:
                payload = _json.loads(response.read().decode("utf-8"))
        except Exception:
            continue

        observations = (payload.get("StatisticSearch") or {}).get("row") or []
        by_month = {m: o for o, m in ((o, _parse_ecos_month(o.get("TIME"))) for o in observations) if m}
        months = sorted(by_month)
        if not months:
            continue

        def _row(month: dt.date, **extra) -> dict:
            return {
                "title": title,
                "market": "KR",
                "country": "KR",
                "kind": "macro",
                "startsAt": release_date(month, release_day).isoformat(),
                "timezone": "Asia/Seoul",
                "allDay": True,
                "importance": importance,
                "source": "Bank of Korea ECOS",
                "sourceUrl": _ECOS_DOC,
                **extra,
            }

        # 값이 존재해도 이 행의 날짜는 관행일 추정이다. 값과 날짜의 확실성을 섞지 않는다.
        for index, month in enumerate(months):
            if not (start_date <= release_date(month, release_day) <= end_date):
                continue
            observation = by_month[month]
            previous = by_month.get(months[index - 1]) if index else None
            rows.append(_row(
                month,
                status="estimated",
                actualValue=observation.get("DATA_VALUE"),
                previousValue=(previous or {}).get("DATA_VALUE"),
                unit=observation.get("UNIT_NAME"),
                observedAt=str(observation.get("TIME") or ""),
            ))

        # 마지막 관측월 다음 달부터 투영한다. ECOS가 공표 일정을 주지 않으므로
        # 관행 발표일에 두고 estimated로 표시한다.
        cursor = _add_months(months[-1], 1)
        while release_date(cursor, release_day) <= end_date:
            if start_date <= release_date(cursor, release_day):
                rows.append(_row(cursor, status="estimated"))
            cursor = _add_months(cursor, 1)

    return normalize_bok_events(rows)
