import json

import pytest

from features.macro_state.evaluation import pair, evaluate
from features.macro_state.evaluation_gate import EvaluationGate, write_json
from features.macro_state.inputs import utc
from .test_inputs import row


class SyntheticReplay:
    def __init__(self, rows):
        self.rows = rows

    def facts_at(self, cutoff):
        return []

    def select(self, cutoff, *, allowed=None):
        chosen = {}
        for r in self.rows:
            key = (r['seriesId'], r['period'])
            if utc(r['availableAt']) <= utc(cutoff) and (allowed is None or key in allowed):
                chosen[key] = r
        return list(chosen.values())


def test_revision_changes_old_values_without_importing_new_period():
    source = SyntheticReplay([
        row('NFCI', '2025-12-26', '.3'), row('NFCI', '2025-11-28', '.1'),
        row('DFF', '2025-12-31', '4'), row('DFF', '2025-09-30', '3'),
        row('NFCI', '2025-12-26', '-.3', availableAt='2026-02-15T00:00:00Z'),
        row('NFCI', '2026-02-13', '5', availableAt='2026-02-15T00:00:00Z'),
    ])
    result = pair(source, 'financial_conditions', '2026-02-01T05:59:59Z', '2026-05-01T04:59:59Z')
    assert result['proposal']['level'] == 'tight'
    assert result['proposalRevised']['level'] == 'loose'
    assert result['proposalRevised']['observationSelection'] == result['proposal']['observationSelection']
    assert all(r['period'] != '2026-02-13' for r in result['proposalRevised']['sourceRefs'])


def test_immature_references_are_not_compared_and_b0_uses_prior_schedule(monkeypatch):
    import features.macro_state.evaluation as module
    monkeypatch.setitem(module.PERIODS, 'development', {'financial_conditions': ('2026-01', '2026-02')})
    source = SyntheticReplay([row('NFCI', '2025-12-26', '.3')])
    result = evaluate(source, 'financial_conditions', 'development', '2026-03-02T00:00:00Z')
    assert len(result['records']) == 2
    assert result['records'][1]['B0'] == result['records'][0]['proposal']
    assert result['stability']['level']['immatureReference'] == 2
    assert result['stability']['level']['commonCount'] == 0


def test_holdout_requires_freeze_prerequisite_and_cannot_repeat(tmp_path):
    gate = EvaluationGate(tmp_path)
    identity = {'specHash': 'spec', 'codeHash': 'code', 'parameters': {'thetaC': '.20'}}
    gate.begin('development', identity)
    with pytest.raises(FileNotFoundError):
        gate.begin('validation', identity)
    gate.finish('development', identity, 'dev.json')
    write_json(tmp_path / 'freeze.json', {'identity': identity, 'commit': 'abc123'})
    gate.begin('validation', identity)
    with pytest.raises(ValueError, match='incomplete'):
        gate.begin('final', identity)
    gate.finish('validation', identity, 'validation.json')
    gate.begin('final', identity)
    with pytest.raises(FileExistsError):
        gate.begin('final', identity)
    assert json.loads((tmp_path / 'final.json').read_text())['status'] == 'started'
    gate.finish('final', identity, 'final.json')
    with pytest.raises(FileExistsError):
        gate.begin('final', identity)


def test_code_or_input_change_rejects_frozen_holdout(tmp_path):
    gate = EvaluationGate(tmp_path)
    write_json(tmp_path / 'freeze.json', {'identity': {'codeHash': 'original'}, 'commit': 'abc123'})
    with pytest.raises(ValueError, match='freeze_mismatch'):
        gate.begin('validation', {'codeHash': 'changed'})
    assert not (tmp_path / 'validation.claim').exists()


def test_revised_trend_minimum_counts_only_frozen_window():
    from features.macro_state.rules import shift_months
    rows=[row('GDPC1',shift_months('2026-07-01',3*i),100+i,
              metadata={'unit':'index','frequency':'Q','adjustment':'SA','definitionVersion':'A' if i==0 else 'B'},
              availableAt='2030-01-01T00:00:00Z') for i in range(15)]
    revised={**rows[1], 'metadata':rows[0]['metadata'], 'availableAt':'2030-03-01T00:00:00Z'}
    result=pair(SyntheticReplay(rows+[revised]),'growth','2030-01-31T23:59:59Z','2030-04-30T23:59:59Z')
    assert result['B1']['level']=='moderate'
    assert result['B1Revised']['level']=='unknown'


def test_final_cannot_use_validation_from_different_frozen_version(tmp_path):
    gate=EvaluationGate(tmp_path)
    write_json(tmp_path/'freeze.json',{'identity':{'codeHash':'B'},'commit':'commit-B'})
    write_json(tmp_path/'validation.json',{'status':'completed','identity':{'codeHash':'A'}})
    with pytest.raises(ValueError,match='prerequisite_identity_mismatch'):
        gate.begin('final',{'codeHash':'B'})
    assert not (tmp_path/'final.claim').exists()
