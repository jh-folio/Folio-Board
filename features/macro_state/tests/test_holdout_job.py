import datetime as dt
import json
from types import SimpleNamespace

from features.macro_state.evaluation_gate import write_json, code_hash
from features.macro_state.evaluation_jobs import run_holdout, file_hash
from features.macro_state.tests.test_evaluation import SyntheticReplay
from features.macro_state.tests.test_inputs import row


def test_holdout_job_finishes_all_outputs_before_terminal_completion(tmp_path, monkeypatch):
    import features.macro_state.evaluation as evaluation
    import features.macro_state.evaluation_jobs as worker
    from features.common import jobs
    db, spec = tmp_path/'source.db', tmp_path/'spec.md'
    db.write_text('synthetic'); spec.write_text('synthetic')
    source = SyntheticReplay([row('NFCI','2025-12-26','.3'),row('NFCI','2025-11-28','.1'),
                              row('DFF','2025-12-31','4'),row('DFF','2025-09-30','3')])
    monkeypatch.setattr(worker, 'Replay', lambda *a: source)
    monkeypatch.setattr(jobs, 'get_shared_job', lambda _: SimpleNamespace(status=SimpleNamespace(value='running')))
    monkeypatch.setitem(evaluation.PERIODS, 'validation', {k: ('2026-01','2026-01') for k in ('growth','inflation','financial_conditions')})
    identity={'codeHash': code_hash(worker.Path(worker.__file__).parent), 'specHash':file_hash(spec),
              'databaseHash':file_hash(db),'evaluationNow':'2026-06-01T00:00:00Z',
              'parameters':{'thetaC':'.20','thetaR':'.10'}}
    write_json(tmp_path/'execution/freeze.json', {'identity':identity,'commit':'synthetic'})
    write_json(tmp_path/'execution/development.json', {'status':'completed','identity':identity})
    write_json(tmp_path/'development-growth.json', {'records':[]})
    result=run_holdout(db,tmp_path,spec,'validation',job_id='synthetic')
    assert result['savedCount']==11
    assert json.loads((tmp_path/'execution/validation.json').read_text())['status']=='completed'
    assert len(list(tmp_path.glob('validation-*.json')))==11
    packet=json.loads((tmp_path/'validation-financial_conditions-blind.json').read_text())
    assert packet['validCount']==1 and not packet['minimumMet']
    assert len(packet['cards'])==4
    assert all('level' not in c and 'direction' not in c for c in packet['cards'])
