"""Read existing schedule evidence without creating Calendar tables or upgrading vintages."""
import sqlite3
from pathlib import Path
from features.common.macro_data.schema import timestamp

# Release-family links are deliberately distinct from exact numeric-series links.
FRED_RELEASE_TITLES = {
    'GDPC1': '미국 GDP', 'INDPRO': '미국 산업생산', 'UNRATE': '미국 고용보고서',
    'CPIAUCSL': '미국 CPI', 'PCEPILFE': '미국 개인소득·지출 (PCE)',
}

# (지표, 캘린더 provider, 제목, 근거). customary_estimate는 공식 일정이 아니라 관행일 추정이다.
KR_RELEASES = (
    ('KR_RATE', 'bank_of_korea', '한국은행 기준금리 결정 (통화정책방향 결정회의)', 'official_schedule'),
    ('KR_CPI', 'bok', '한국 소비자물가지수 (CPI)', 'customary_estimate'),
)


def next_releases(path: Path, day: str, *, cutoff=None):
    """FRED release *dates* only. Calendar's legacy 08:30 is not time evidence.

    Schedules collected after an as-of cutoff cannot leak into that projection.
    No schedule here proves an observation's exact official publication time.
    """
    path = Path(path).resolve()
    if not path.exists():
        return {}
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='market_calendar_events'").fetchone():
            return {}
        columns = {r[1] for r in conn.execute('PRAGMA table_info(market_calendar_events)')}
        required = {'provider', 'title', 'starts_at', 'source_url', 'fetched_at', 'status', 'cancelled'}
        if not required <= columns:
            return {}
        rows = conn.execute(
            "SELECT title,starts_at,source_url,fetched_at FROM market_calendar_events WHERE provider='fred' AND status IN ('confirmed','actual') AND cancelled=0 AND substr(starts_at,1,10)>=? ORDER BY starts_at",
            (day,),
        ).fetchall()
        # 한국: 금통위는 한국은행 공시 일정, CPI는 관행일 추정 행이다. 종일 행만 읽어
        # 날짜가 틀린 옛 ECOS 행(관측월 15일 08:00)은 들어오지 않는다. 값이 이미 실린 행은
        # 관행일보다 먼저 발표된 것이므로 다음 발표가 아니다.
        kr_rows = conn.execute(
            "SELECT provider,title,starts_at,source_url,fetched_at FROM market_calendar_events WHERE provider IN ('bok','bank_of_korea') AND all_day=1 AND cancelled=0 AND actual_value='' AND substr(starts_at,1,10)>=? ORDER BY starts_at",
            (day,),
        ).fetchall() if {'all_day', 'actual_value'} <= columns else []
    result = {}
    for series_id, title in FRED_RELEASE_TITLES.items():
        match = None
        for row in rows:
            if row['title'] != title:
                continue
            if cutoff:
                # 과거 시점 재현에서는 그 시점 뒤에 수집한 일정을 쓰지 않는다.
                try:
                    if timestamp(row['fetched_at']) > cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
            match = row
            break
        if match:
            result[series_id] = {
                'date': match['starts_at'][:10],
                'timezone': 'America/New_York',
                'precision': 'date',
                'basis': 'provider_schedule',
                'sourceUrl': match['source_url'],
                'fetchedAt': match['fetched_at'],
            }
    for series_id, provider, title, basis in KR_RELEASES:
        eligible = []
        for row in kr_rows:
            if row['provider'] != provider or row['title'] != title:
                continue
            if cutoff:
                try:
                    if timestamp(row['fetched_at']) > cutoff:
                        continue
                except (TypeError, ValueError):
                    continue
            eligible.append(row)
        match = next(iter(eligible), None)
        if match:
            result[series_id] = {
                'date': match['starts_at'][:10],
                'timezone': 'Asia/Seoul',
                'precision': 'date',
                'basis': basis,
                'sourceUrl': match['source_url'],
                'fetchedAt': match['fetched_at'],
            }
    return result
