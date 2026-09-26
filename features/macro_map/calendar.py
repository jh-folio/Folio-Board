"""Read existing schedule evidence without creating Calendar tables or upgrading vintages."""
import sqlite3
from pathlib import Path
from features.common.macro_data.schema import timestamp

# Release-family links are deliberately distinct from exact numeric-series links.
FRED_RELEASE_TITLES = {
    'GDPC1': '미국 GDP', 'INDPRO': '미국 산업생산', 'UNRATE': '미국 고용보고서',
    'CPIAUCSL': '미국 CPI', 'PCEPILFE': '미국 개인소득·지출 (PCE)',
}


def next_releases(path: Path, day: str, *, cutoff=None):
    """FRED release *dates* only. Calendar's legacy 08:30 is not time evidence.

    Schedules collected after an as-of cutoff cannot leak into that projection.
    No schedule here proves an observation's exact official publication time.
    """
    path=Path(path).resolve()
    if not path.exists():return {}
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='market_calendar_events'").fetchone():return {}
        columns={r[1] for r in conn.execute('PRAGMA table_info(market_calendar_events)')}
        required={'provider','title','starts_at','source_url','fetched_at','status','cancelled'}
        if not required<=columns:return {}
        rows=conn.execute("SELECT title,starts_at,source_url,fetched_at FROM market_calendar_events WHERE provider='fred' AND status IN ('confirmed','actual') AND cancelled=0 AND substr(starts_at,1,10)>=? ORDER BY starts_at",(day,)).fetchall()
    result={}
    for series_id,title in FRED_RELEASE_TITLES.items():
        match=None
        for row in rows:
            if row['title']!=title:continue
            if cutoff:
                try:
                    if timestamp(row['fetched_at'])>cutoff:continue
                except (ValueError,TypeError):continue
            match=row;break
        if match:
            result[series_id]={'date':match['starts_at'][:10],'timezone':'America/New_York','precision':'date',
                               'basis':'provider_schedule','sourceUrl':match['source_url'],'fetchedAt':match['fetched_at']}
    return result
