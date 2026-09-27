import datetime as dt
import json as _json
import urllib.parse
import urllib.request

from features.market_calendar.schema import normalize_event
from features.common.macro_data.providers import fred_vintage_pattern, parse_fred_vintages

_VINTAGE_KEY = fred_vintage_pattern()  # Legacy import compatibility; shared parser owns the pattern.

# FRED release id → (표시명, 중요도). 발표 시각은 BLS/BEA/Census 공식 고정 시각 08:30 ET.
# https://fred.stlouisfed.org/docs/api/fred/release_dates.html
# 릴리즈 하나에는 시리즈가 여럿 들어 있다. 헤드라인 숫자로 읽히는 대표 시리즈를
# 하나씩만 지정해 발표 결과를 채운다. 없는 릴리즈는 일정만 남는다.
FRED_HEADLINE_SERIES: dict[int, tuple[str, str]] = {
    10: ("CPIAUCSL", "지수"),
    50: ("PAYEMS", "천 명"),
    53: ("GDPC1", "십억 달러"),
    54: ("PCEPI", "지수"),
    46: ("PPIACO", "지수"),
    9: ("RSAFS", "백만 달러"),
    192: ("JTSJOL", "천 건"),
    13: ("INDPRO", "지수"),
    51: ("BOPGSTB", "백만 달러"),
}

FRED_RELEASES = {
    10: ("미국 CPI", 3),
    50: ("미국 고용보고서", 3),
    53: ("미국 GDP", 2),
    54: ("미국 개인소득·지출 (PCE)", 3),
    46: ("미국 PPI", 2),
    # `8`은 FRED 릴리즈 목록에 없는 번호라 소매판매가 한 번도 들어온 적이 없다.
    # 실제 번호는 9(Advance Monthly Sales for Retail and Food Services)다.
    9: ("미국 소매판매", 2),
    192: ("미국 JOLTS 구인·이직", 2),
    13: ("미국 산업생산", 2),
    51: ("미국 무역수지", 2),
}
_FRED_API = "https://api.stlouisfed.org/fred/release/dates"


def normalize_fred_releases(rows: list[dict]) -> list[dict]:
    return [normalize_event({**row, "kind": "macro", "provider": "fred", "source": row.get("source") or "FRED", "status": row.get("status") or "confirmed"}) for row in rows if isinstance(row, dict)]


def fetch_fred_macro_events(api_key: str, *, start: str, end: str, timeout: float = 8.0) -> list[dict]:
    """Fetch scheduled release dates for the allowlisted FRED releases. Returns [] without a key."""
    if not str(api_key or "").strip():
        return []
    rows = []
    for release_id, (title, importance) in FRED_RELEASES.items():
        params = urllib.parse.urlencode({
            "release_id": release_id, "api_key": api_key, "file_type": "json",
            "include_release_dates_with_no_data": "true", "sort_order": "asc",
            "realtime_start": start, "realtime_end": end, "limit": 30,
        })
        try:
            with urllib.request.urlopen(f"{_FRED_API}?{params}", timeout=timeout) as response:
                payload = _json.loads(response.read().decode("utf-8"))
        except Exception:
            continue
        for entry in payload.get("release_dates", []):
            date = str(entry.get("date") or "")
            if not (start <= date <= end):
                continue
            rows.append({
                "_releaseId": release_id,
                "title": title, "market": "US", "startsAt": f"{date}T08:30:00",
                "timezone": "America/New_York", "importance": importance,
                "sourceUrl": f"https://fred.stlouisfed.org/release?rid={release_id}",
            })
    _attach_observations(rows, api_key, timeout=timeout)
    return normalize_fred_releases(rows)


_FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"

def _attach_observations(rows: list[dict], api_key: str, *, timeout: float) -> None:
    """각 발표일에 **그 발표가 공표한** 수치를 붙인다.

    예정만 보여주면 발표 뒤에 캘린더를 다시 열 이유가 없다. 다만 붙이는 값은 반드시
    그 발표의 것이어야 한다.

    **최신 관측치를 지나간 모든 발표일에 붙이면 안 된다.** 예전 구현이 그랬다
    (`sort_order=desc, limit=2`). 그래서 7월 CPI를 발표하는 8월 12일 행에 6월 관측치가
    붙었고, 6월 25일 GDP 행에는 7월 30일에야 공표된 값이 붙었다. 지난 발표가 전부
    "오늘의 최신 숫자"를 말하고 있었다 — 캘린더를 되짚어 볼 수 없다는 뜻이다.

    FRED는 vintage(실시간) 조회로 **어느 날 무엇이 처음 공표됐는지**를 알려준다.
    `output_type=4`(초판만)를 쓰면 관측치마다 `realtime_start`가 최초 공표일이다:

        관측월 2026-05-01  값 333.979  최초공표 2026-06-10
        관측월 2026-06-01  값 332.568  최초공표 2026-07-14

    발표일과 최초 공표일을 정확히 맞춰야 그 발표의 숫자가 된다. 시리즈마다 공표 지연이
    다르므로(JOLTS는 두 달, GDP는 분기) "발표 달 - 1"* 같은 고정 오프셋으로는 맞출 수
    없다. 이 방식은 시리즈를 가리지 않는다.

    **그날 공표된 값이 없으면 아무것도 붙이지 않는다.** 발표일이 지났어도 FRED에 아직
    안 들어왔을 수 있다(실측 2026-08-12 CPI). 그때 지난 값을 대신 보여주면 틀린 숫자를
    오늘 발표라고 말하는 것이다 — 비워 두는 편이 맞다.
    """
    today = dt.date.today().isoformat()
    dated = [
        (row, str(row.get("startsAt") or "")[:10], FRED_HEADLINE_SERIES.get(row.get("_releaseId") or 0))
        for row in rows
    ]
    pending = [(row, day, series) for row, day, series in dated if series and day and day <= today]
    if not pending:
        return

    earliest = min(day for _row, day, _series in pending)
    cache: dict[str, dict] = {}
    for _row, _day, series in pending:
        series_id = series[0]
        if series_id not in cache:
            cache[series_id] = _first_releases(series_id, api_key, earliest, today, timeout=timeout)

    for row, day, series in pending:
        series_id, unit = series
        published = cache.get(series_id) or {}
        point = published.get(day)
        if not point:
            continue
        row["status"] = "actual"
        row["actualValue"] = point["value"]
        row["unit"] = unit
        row["observedAt"] = point["date"]
        # 직전 값은 **그 이전 발표가 공표한 값**이다. 최신 관측치의 바로 앞이 아니다.
        earlier = [d for d in published if d < day]
        row["previousValue"] = published[max(earlier)]["value"] if earlier else ""


def _first_releases(series_id: str, api_key: str, start: str, end: str, *, timeout: float) -> dict:
    """`{공표일: {"date": 관측기간, "value": 값}}`.

    `output_type=3`(신규·개정분)은 관측기간마다 **vintage 날짜별 값**을 한 줄로 준다:

        {"date": "2026-01-01", "GDPC1_20260528": "24152.656", "GDPC1_20260625": "24180.419"}
        {"date": "2026-04-01", "GDPC1_20260730": "24270.599"}

    키의 `_YYYYMMDD`가 그 값이 공표된 날이다. **개정 발표까지 잡힌다** — GDP는 잠정·수정·
    확정으로 세 번 발표하는데, 초판만 보는 `output_type=4`로는 6월 25일 확정치 발표가
    빈칸으로 남았다.

    한 시리즈에 한 번만 호출한다. 창을 앞으로 넉넉히 여는 이유는 범위 첫 발표에도
    직전 비교값이 있어야 하기 때문이다.
    """
    try:
        window_start = (dt.date.fromisoformat(start) - dt.timedelta(days=400)).isoformat()
    except ValueError:
        window_start = start
    params = urllib.parse.urlencode({
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "output_type": 3, "realtime_start": window_start, "realtime_end": end,
        "sort_order": "asc",
    })
    try:
        with urllib.request.urlopen(f"{_FRED_OBSERVATIONS}?{params}", timeout=timeout) as response:
            payload = _json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}
    published: dict[str, dict] = {}
    try:
        points = list(parse_fred_vintages(payload, series_id))
    except (ValueError, TypeError, RuntimeError):
        return {}
    for point in points:
        observed, day, value = point['period'], point['vintageDate'], point['value']
        if value is None:
            continue
        # Calendar alone selects a headline; the shared parser preserves every revision.
        current = published.get(day)
        if not current or observed > current['date']:
            published[day] = {'date': observed, 'value': value}
    return published
