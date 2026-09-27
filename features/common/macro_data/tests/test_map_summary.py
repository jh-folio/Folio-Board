"""거시 지도 개요(요약 응답)·설명·한국 일정 연결."""
import datetime as dt

from features.common.macro_data.registry import SERIES, indicators
from features.common.macro_data.store import MacroStore
from features.macro_map.guides import GUIDES, guide
from features.macro_map.service import map_snapshot
from features.macro_map.summary import headline
from features.market_calendar.service import upsert_events
from .test_ledger import point, write

NOW = dt.datetime(2026, 9, 27, 3, tzinfo=dt.timezone.utc)


def _item(transform, values, *, series_id='CPIAUCSL', frequency='M', unit='Index'):
    history = [{'period': f'2024-{m:02d}-01', 'value': v, 'displayValue': v} for m, v in enumerate(values, start=1)]
    return {'series': {'id': series_id, 'transform': transform, 'frequency': frequency, 'unit': unit}, 'history': history}


def test_difference_indicators_lead_with_the_level_not_the_change():
    # 실업률은 "0%p"가 아니라 "4.1%"가 머리 숫자다.
    item = _item('difference', [4.0, 4.1, 4.1], series_id='UNRATE', unit='Percent')
    item['history'] = [{**p, 'displayValue': 0.0} for p in item['history']]
    h = headline(item)
    assert (h['value'], h['unit'], h['digits'], h['measure']) == (4.1, '%', 1, '수준')
    assert h['previous'] == 4.1 and h['delta'] == 0 and h['tone'] == 'flat'


def test_tone_is_direction_only_and_uses_display_precision():
    h = headline(_item('yoy', [3.30, 3.353]))
    assert h['tone'] == 'up' and h['delta'] == 0.05 and h['deltaUnit'] == '%p'
    # 표시 자릿수에서 같으면 변화 없음이다.
    assert headline(_item('yoy', [3.3441, 3.3439]))['tone'] == 'flat'
    assert headline(_item('level', [1384.0, 1360.0], series_id='KR_USDKRW', frequency='D'))['tone'] == 'down'


def test_period_changes_are_bars_and_rates_are_lines():
    assert headline(_item('qoq', [0.5, 0.4], frequency='Q'))['shape'] == 'bars'
    assert headline(_item('yoy', [2.0, 2.1]))['shape'] == 'line'
    assert headline(_item('level', [])) is None


def test_daily_spark_is_sampled_monthly_before_it_is_cut():
    # 일간 자료를 먼저 자르면 두 달치만 남아 흐름이 거꾸로 보였다(시안 실측).
    history = []
    day = dt.date(2023, 1, 2)
    while day <= dt.date(2026, 9, 24):
        history.append({'period': day.isoformat(), 'value': 5.33 if day.year < 2025 else 3.88, 'displayValue': 0.0})
        day += dt.timedelta(days=1)
    h = headline({'series': {'id': 'DFF', 'transform': 'difference', 'frequency': 'D', 'unit': 'Percent'}, 'history': history})
    assert len(h['spark']) == 36
    assert h['spark'][0][1] == 5.33 and h['spark'][-1][1] == 3.88


def test_industrial_production_reads_year_over_year():
    by_id = {s.id: s for s in SERIES}
    assert by_id['INDPRO'].transform == 'yoy' and by_id['KR_IP'].transform == 'yoy'
    assert all(s['methodVersion'] == 'macro-2' for s in indicators('US'))


def test_summary_view_is_small_and_carries_overview(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    write(store, point('2023-08-01', '300', '2023-09-12'), point('2024-07-01', '308', '2024-08-14'), point('2024-08-01', '310', '2024-09-11'))
    full = map_snapshot(tmp_path, now=NOW)
    summary = map_snapshot(tmp_path, now=NOW, view='summary')
    cpi = next(i for i in summary['items'] if i['series']['id'] == 'CPIAUCSL')
    assert summary['view'] == 'summary' and cpi['history'] == [] and cpi['headline']['measure'] == '전년 대비'
    assert summary['overview']['recent'][0]['seriesId'] == 'CPIAUCSL'
    assert summary['overview']['collection']['total'] == 8
    assert full['view'] == 'full' and full['overview'] is None
    # 상세(series 지정)는 요약을 요청해도 전체 이력과 설명을 준다.
    detail = map_snapshot(tmp_path, now=NOW, view='summary', series_id='CPIAUCSL')
    assert detail['view'] == 'full' and detail['items'][0]['history'] and detail['items'][0]['guide']


def test_every_visible_indicator_has_a_four_part_guide_without_advice():
    visible = [s['id'] for market in ('US', 'KR') for s in indicators(market)]
    assert len(visible) == 16 and set(visible) <= set(GUIDES)
    for series_id in visible:
        parts = guide(series_id)
        assert [p['heading'] for p in parts] == ['무엇을 재나요', '여기 숫자는', '어떻게 읽나요', '알아 둘 점']
        text = ' '.join(p['body'] for p in parts)
        assert not any(word in text for word in ('매수', '매도', '사야', '팔아', '추천'))


def test_korean_schedule_comes_from_calendar_without_legacy_rows(tmp_path):
    db = tmp_path / 'market-memory.sqlite3'
    upsert_events(db, [
        {'kind': 'central_bank', 'provider': 'bank_of_korea', 'title': '한국은행 기준금리 결정 (통화정책방향 결정회의)',
         'market': 'KR', 'startsAt': '2026-10-22', 'allDay': True, 'timezone': 'Asia/Seoul', 'status': 'confirmed', 'sourceUrl': 'https://www.bok.or.kr/'},
        {'kind': 'macro', 'provider': 'bok', 'title': '한국 소비자물가지수 (CPI)', 'market': 'KR',
         'startsAt': '2026-10-02', 'allDay': True, 'timezone': 'Asia/Seoul', 'status': 'estimated'},
        # 날짜가 틀린 옛 행(관측월 15일 08:00). 다음 발표로 읽으면 안 된다.
        {'kind': 'macro', 'provider': 'bok', 'title': '한국 소비자물가지수 (CPI)', 'market': 'KR',
         'startsAt': '2026-09-30T08:00:00', 'timezone': 'Asia/Seoul', 'status': 'estimated'},
        # 관행일보다 먼저 발표돼 값이 실린 행. 이미 나온 발표라 다음 발표가 아니다.
        {'kind': 'macro', 'provider': 'bok', 'title': '한국 소비자물가지수 (CPI)', 'market': 'KR',
         'startsAt': '2026-09-28', 'allDay': True, 'timezone': 'Asia/Seoul', 'status': 'estimated', 'actualValue': '120.4', 'observedAt': '202608'},
    ])
    items = {i['series']['id']: i for i in map_snapshot(tmp_path, market='KR', now=NOW, view='summary')['items']}
    assert items['KR_RATE']['nextRelease']['date'] == '2026-10-22'
    assert items['KR_RATE']['nextRelease']['basis'] == 'official_schedule'
    assert items['KR_CPI']['nextRelease']['date'] == '2026-10-02'
    assert items['KR_CPI']['nextRelease']['basis'] == 'customary_estimate'
