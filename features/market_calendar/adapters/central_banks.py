"""ECB, Bank of England, Bank of Japan, and Bank of Korea rate decision dates.

Same approach as the FOMC adapter: each bank publishes its year ahead, so the
schedule is transcribed rather than scraped. These are `confirmed` because the
bank itself published them, and they expire the same way — a year with no table
produces nothing instead of a guess.

Every date below was checked against the issuing bank's own publication:
  ECB  — the 2026 reserve maintenance calendar, which is built around the
         Governing Council meeting dates.
  BoE  — the published 2026 MPC announcement dates, all at 12:00 London.
  BoJ  — the published 2026 Monetary Policy Meeting schedule; the decision
         lands on the second day.
  BOK  — the 2026 통화정책방향 결정회의 list on the bank's own schedule page.
         Before this table the base rate came from ECOS monthly observations,
         which put a "decision" on the 15th of every month — twelve a year for a
         committee that meets eight times, one of them on Liberation Day.
"""
from __future__ import annotations

from features.market_calendar.schema import normalize_event

# 결정 발표는 2일차다. 성명 14:15 CET, 기자회견 14:45 CET.
# https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html
ECB_DECISIONS = {
    2026: (
        "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-11",
        "2026-07-23", "2026-09-10", "2026-10-29", "2026-12-17",
    ),
}
# 발표 12:00 London. 2·4·7·11월 회의에는 통화정책보고서와 기자회견이 따른다.
# https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates
BOE_DECISIONS = {
    2026: (
        ("2026-02-05", True), ("2026-03-19", False), ("2026-04-30", True), ("2026-06-18", False),
        ("2026-07-30", True), ("2026-09-17", False), ("2026-11-05", True), ("2026-12-17", False),
    ),
}
# 2일 회의이고 결정은 2일차 정오 무렵 공표된다. 정확한 시각은 회의마다 달라
# 시간을 확정하지 않고 종일 일정으로 둔다.
# https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm
BOJ_MEETINGS = {
    2026: (
        ("2026-01-22", "2026-01-23"), ("2026-03-18", "2026-03-19"),
        ("2026-04-27", "2026-04-28"), ("2026-06-15", "2026-06-16"),
        ("2026-07-30", "2026-07-31"), ("2026-09-17", "2026-09-18"),
        ("2026-10-29", "2026-10-30"), ("2026-12-17", "2026-12-18"),
    ),
}

# 통화정책방향 결정회의는 연 8회다. 결정문 공표 시각이 공식 일정표에 없어 종일 일정으로 둔다.
# https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755
BOK_DECISIONS = {
    2026: (
        "2026-01-15", "2026-02-26", "2026-04-10", "2026-05-28",
        "2026-07-16", "2026-08-27", "2026-10-22", "2026-11-26",
    ),
}

_URLS = {
    "ecb": "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
    "bank_of_england": "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates",
    "bank_of_japan": "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm",
    "bank_of_korea": "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755",
}
_SOURCES = {
    "ecb": "European Central Bank", "bank_of_england": "Bank of England",
    "bank_of_japan": "Bank of Japan", "bank_of_korea": "Bank of Korea",
}


def normalize_central_bank_events(rows: list[dict], *, provider: str) -> list[dict]:
    if provider not in _URLS:
        raise ValueError("calendar_central_bank_provider_invalid")
    return [
        normalize_event({
            **row,
            "kind": "central_bank",
            "provider": provider,
            "source": row.get("source") or _SOURCES[provider],
            "status": row.get("status") or "confirmed",
            "sourceUrl": row.get("sourceUrl") or _URLS[provider],
        })
        for row in rows
        if isinstance(row, dict)
    ]


def _ecb_rows(years: list[int]) -> list[dict]:
    rows = []
    for year in years:
        for date in ECB_DECISIONS.get(year, ()):
            rows.append({
                "title": "ECB 금리 결정 (성명 14:15 CET, 기자회견 14:45)",
                "market": "EUROPE", "country": "EU",
                "startsAt": f"{date}T14:15:00", "endsAt": f"{date}T15:45:00",
                # ECB는 프랑크푸르트에 있지만 IANA 표준 zone은 Europe/Berlin이다.
                "timezone": "Europe/Berlin", "importance": 3,
            })
    return rows


def _boe_rows(years: list[int]) -> list[dict]:
    rows = []
    for year in years:
        for date, with_report in BOE_DECISIONS.get(year, ()):
            suffix = " · 통화정책보고서" if with_report else ""
            rows.append({
                "title": f"BoE 기준금리 결정 (12:00 London){suffix}",
                "market": "EUROPE", "country": "GB",
                "startsAt": f"{date}T12:00:00", "endsAt": f"{date}T12:30:00",
                "timezone": "Europe/London", "importance": 3,
            })
    return rows


def _boj_rows(years: list[int]) -> list[dict]:
    rows = []
    for year in years:
        for start, end in BOJ_MEETINGS.get(year, ()):
            rows.append({
                "title": "BOJ 금융정책결정회합 결과 발표",
                "market": "JP", "country": "JP",
                "startsAt": f"{end}T00:00:00", "timezone": "Asia/Tokyo",
                "allDay": True, "importance": 3,
            })
            rows.append({
                "title": "BOJ 금융정책결정회합 1일차",
                "market": "JP", "country": "JP",
                "startsAt": f"{start}T00:00:00", "timezone": "Asia/Tokyo",
                "allDay": True, "importance": 2,
            })
    return rows


def _bok_rows(years: list[int]) -> list[dict]:
    rows = []
    for year in years:
        for date in BOK_DECISIONS.get(year, ()):
            rows.append({
                "title": "한국은행 기준금리 결정 (통화정책방향 결정회의)",
                "market": "KR", "country": "KR",
                "startsAt": date, "timezone": "Asia/Seoul",
                "allDay": True, "importance": 3,
            })
    return rows


def official_central_bank_events(years: list[int]) -> list[dict]:
    """ECB/BoE/BoJ/BOK decision dates for the requested years.

    A year with no transcribed table simply contributes nothing — the calendar
    shows a gap rather than an invented meeting.
    """
    events = []
    for provider, builder in (("ecb", _ecb_rows), ("bank_of_england", _boe_rows), ("bank_of_japan", _boj_rows), ("bank_of_korea", _bok_rows)):
        events.extend(normalize_central_bank_events(builder(years), provider=provider))
    return events
