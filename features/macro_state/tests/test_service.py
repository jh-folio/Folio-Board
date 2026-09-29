import datetime as dt

from features.macro_state.service import summary, previous_month_snapshot, METHOD
from features.macro_state.store import StateStore
from .test_store import snapshot


def test_empty_read_never_creates_db_and_frozen_parameters(tmp_path):
    result = summary(tmp_path, now=dt.datetime(2026, 3, 2, tzinfo=dt.timezone.utc))
    assert all(card['snapshot'] is None for card in result['cards'])
    assert not (tmp_path/'market-memory.sqlite3').exists()
    assert METHOD['parameters']['thetaR'] == '0.1'


def test_comparison_only_stored_month_close_before_day(tmp_path):
    store = StateStore(tmp_path/'market-memory.sqlite3')
    item = snapshot(); item['asOf'] = '2026-02-28T12:00:00Z'
    store.save(item, reason='intraday')
    assert previous_month_snapshot(store, 'US', 'stress_vulnerability', dt.date(2026,3,2)) is None
    item['asOf'] = '2026-03-01T05:59:59.999999Z'
    saved = store.save(item, reason='month_end')
    assert previous_month_snapshot(store, 'US', 'stress_vulnerability', dt.date(2026,3,2))['snapshotId'] == saved['snapshotId']
    assert previous_month_snapshot(store, 'US', 'stress_vulnerability', dt.date(2026,2,28)) is None
