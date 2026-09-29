from pathlib import Path

import pytest

from features.common.macro_data.store import MacroStore
from features.common.macro_data.tests.test_ledger import point,write
from features.macro_state.replay import Replay, evaluation_cutoffs, revision_cutoff


def test_vintage_collision_and_same_period_revision(tmp_path):
    store=MacroStore(tmp_path/'market-memory.sqlite3')
    write(store,point(),point(value='110',vintage='2024-03-01'))
    replay=Replay(store.path,['CPIAUCSL'])
    first=replay.select('2024-02-15T23:59:59Z')
    second=replay.select('2024-03-15T23:59:59Z')
    assert first[0]['rawValue']=='100' and second[0]['rawValue']=='110'
    write(store,point(value='111',vintage='2024-03-01'))
    collided=Replay(store.path,['CPIAUCSL']).select('2024-03-15T23:59:59Z')[0]
    assert collided['conflict'] and collided['value'] is None


def test_month_end_and_friday_cutoffs_respect_dst():
    assert list(evaluation_cutoffs('2024-02','2024-03'))==['2024-03-01T05:59:59.999999Z','2024-04-01T04:59:59.999999Z']
    assert revision_cutoff('2024-03-01T05:59:59.999999Z')=='2024-06-01T04:59:59.999999Z'
    assert revision_cutoff('2024-03-30T04:59:59.999999Z',weekly=True)=='2024-06-30T04:59:59.999999Z'
    assert revision_cutoff('2024-11-30T05:59:59.999999Z',weekly=True)=='2025-03-01T05:59:59.999999Z'
