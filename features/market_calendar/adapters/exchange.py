from features.common.exchange_holidays import (
    EXCHANGE_LABELS,
    MARKET_EXCHANGES,
    exchange_holiday_rows,
    has_coverage,
)
from features.market_calendar.schema import normalize_event

# 공식 발표 연간 휴장일 전사. 새 연도 일정이 공시되면 아래 표만 갱신한다.
# NYSE: https://www.nyse.com/markets/hours-calendars
# KRX:  https://open.krx.co.kr (연간 휴장일 안내)
NYSE_HOLIDAYS = {
    2026: [
        ("2026-01-01", "New Year's Day"), ("2026-01-19", "Martin Luther King Jr. Day"),
        ("2026-02-16", "Washington's Birthday"), ("2026-04-03", "Good Friday"),
        ("2026-05-25", "Memorial Day"), ("2026-06-19", "Juneteenth"),
        ("2026-07-03", "Independence Day (observed)"), ("2026-09-07", "Labor Day"),
        ("2026-11-26", "Thanksgiving Day"), ("2026-12-25", "Christmas Day"),
    ],
}
KRX_HOLIDAYS = {
    2026: [
        ("2026-01-01", "신정"), ("2026-02-16", "설 연휴"), ("2026-02-17", "설날"), ("2026-02-18", "설 연휴"),
        ("2026-03-02", "삼일절 대체휴일"), ("2026-05-05", "어린이날"), ("2026-05-25", "부처님오신날 대체휴일"),
        # 공직선거법 제34조의 임기만료 지방선거일이자 `관공서의 공휴일에 관한 규정`
        # 제2조 제10호의 법정 공휴일이라 KRX가 휴장한다.
        ("2026-06-03", "제9회 전국동시지방선거"),
        ("2026-08-17", "광복절 대체휴일"), ("2026-09-24", "추석 연휴"), ("2026-09-25", "추석"),
        # 추석 연휴가 토요일(9/26)까지만 걸치고 일요일과 겹치지 않아 대체휴일이 없다.
        # features/common/market_calendar.py::KR_LUNAR_MARKET_HOLIDAYS의 같은 주석 참고.
        ("2026-10-05", "개천절 대체휴일"), ("2026-10-09", "한글날"),
        ("2026-12-25", "성탄절"), ("2026-12-31", "연말 휴장"),
    ],
}
_SOURCE_URLS = {"nyse": "https://www.nyse.com/markets/hours-calendars", "krx": "https://open.krx.co.kr"}

# 유럽·일본 휴장일은 `features/common/exchange_holidays.py` 표 하나를 세션 판정과
# 캘린더가 함께 읽는다. 두 곳에 적으면 반드시 갈라진다.
_OVERSEAS_PROVIDERS = {
    "LSE": ("lse", "https://www.londonstockexchange.com/trade/trading-access/business-days"),
    "XETRA": ("xetra", "https://www.xetra.com/xetra-en/trading/trading-calendar-and-trading-hours"),
    "EURONEXT": ("euronext", "https://www.euronext.com/en/trade/trading-hours-holidays"),
    "BORSA_ITALIANA": ("borsa_italiana", "https://www.borsaitaliana.it/borsaitaliana/calendario-e-orari-di-negoziazione/calendario-borsa-orari-di-negoziazione.en.htm"),
    "BME": ("bme", "https://www.bolsasymercados.es/en/bme-exchange/trading/trading-calendar.html"),
    "JPX": ("jpx", "https://www.jpx.co.jp/english/corporate/about-jpx/calendar/"),
}
_OVERSEAS_TIMEZONES = {
    "LSE": "Europe/London", "XETRA": "Europe/Berlin", "EURONEXT": "Europe/Paris",
    "BORSA_ITALIANA": "Europe/Rome", "BME": "Europe/Madrid", "JPX": "Asia/Tokyo",
}
_OVERSEAS_COUNTRIES = {
    "LSE": "GB", "XETRA": "DE", "EURONEXT": "FR",
    "BORSA_ITALIANA": "IT", "BME": "ES", "JPX": "JP",
}


_VALID_PROVIDERS = {"nyse", "krx", *(code for code, _ in _OVERSEAS_PROVIDERS.values())}


def normalize_exchange_holidays(rows: list[dict], *, provider: str) -> list[dict]:
    if provider not in _VALID_PROVIDERS:
        raise ValueError("calendar_exchange_provider_invalid")
    return [normalize_event({**row, "kind": "holiday", "provider": provider, "source": row.get("source") or provider.upper(), "status": row.get("status") or "confirmed", "allDay": True}) for row in rows if isinstance(row, dict)]


def official_holiday_events(years: list[int]) -> list[dict]:
    events = []
    for provider, table, market, tz in (("nyse", NYSE_HOLIDAYS, "US", "America/New_York"), ("krx", KRX_HOLIDAYS, "KR", "Asia/Seoul")):
        rows = []
        for year in years:
            for date, title in table.get(year, []):
                rows.append({
                    "title": f"{'NYSE' if provider == 'nyse' else 'KRX'} 휴장 — {title}",
                    "market": market, "startsAt": f"{date}T00:00:00", "timezone": tz,
                    "importance": 1, "sourceUrl": _SOURCE_URLS[provider],
                })
        events.extend(normalize_exchange_holidays(rows, provider=provider))
    events.extend(overseas_holiday_events(years))
    return events


def overseas_holiday_events(years: list[int]) -> list[dict]:
    """Europe and Japan venue closures.

    Europe emits one event per venue rather than one per region: London can be
    shut while Frankfurt trades, and a single "Europe closed" entry would tell
    the reader something that is not true on those days.
    """
    events = []
    for market, exchanges in MARKET_EXCHANGES.items():
        for exchange in exchanges:
            provider, source_url = _OVERSEAS_PROVIDERS[exchange]
            label = EXCHANGE_LABELS.get(exchange, exchange)
            rows = [
                {
                    "title": f"{label} 휴장 — {title}",
                    "market": market,
                    "country": _OVERSEAS_COUNTRIES[exchange],
                    "startsAt": f"{day.isoformat()}T00:00:00",
                    "timezone": _OVERSEAS_TIMEZONES[exchange],
                    "importance": 1,
                    "sourceUrl": source_url,
                }
                for year in years if has_coverage(exchange, year)
                for day, title in exchange_holiday_rows(exchange, year)
            ]
            events.extend(normalize_exchange_holidays(rows, provider=provider))
    return events
