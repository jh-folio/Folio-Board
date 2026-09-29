"""Maintainer-triggered evaluation SharedJob; no GET or scheduler invokes it."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from features.common.macro_data.registry import SERIES
from .development import threshold_development
from .evaluation import evaluate
from .evaluation_gate import EvaluationGate, code_hash, write_json
from .replay import Replay
from .evaluation_report import summarize_growth
from .cycle import us_cycle
from .inputs import Inputs
from .interpretation_samples import blind_packet


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run_development(database, output, spec, now, *, job_id, progress=None):
    from features.common.jobs import get_shared_job

    def cancel():
        job = get_shared_job(job_id)
        if job is None or job.status.value in {'cancel_requested', 'cancelled', 'failed_restart'}:
            raise RuntimeError('macro_evaluation_cancelled')

    database, output, spec = Path(database), Path(output), Path(spec)
    identity = {'specHash': file_hash(spec), 'codeHash': code_hash(Path(__file__).parent),
                'databaseHash': file_hash(database), 'evaluationNow': now, 'methodVersion': 'macro-state-1'}
    gate = EvaluationGate(output / 'execution')
    gate.begin('development', identity)
    cancel()
    if progress: progress(message='개발 구간의 과거 판본을 읽고 있습니다.')
    replay = Replay(database, [s.id for s in SERIES if s.market == 'US' and s.axis != 'stress_vulnerability'])
    tuning = threshold_development(replay, cancel=cancel, progress=progress)
    write_json(output / 'development-thresholds.json', tuning)
    parameters = {'theta_c': Decimal(tuning['parameters']['thetaC']), 'theta_r': Decimal(tuning['parameters']['thetaR'])}
    summaries = {}
    for axis in ('growth', 'inflation', 'financial_conditions'):
        if progress: progress(message=f'개발 구간 {axis}의 수정 안정성을 계산하고 있습니다.')
        report = evaluate(replay, axis, 'development', now, parameters=parameters, cancel=cancel)
        write_json(output / f'development-{axis}.json', report)
        summaries[axis] = report['stability']
        if axis == 'financial_conditions':
            weekly = evaluate(replay, axis, 'development', now, parameters=parameters, weekly=True, cancel=cancel)
            write_json(output / 'development-financial_conditions-weekly.json', weekly)
    report_path = output / 'development-summary.json'
    write_json(report_path, {'identity': identity, 'parameters': tuning['parameters'], 'stability': summaries,
                             'promotion': 'shadow', 'holdoutsExecuted': False})
    if file_hash(database) != identity['databaseHash']:
        raise ValueError('evaluation_database_changed_during_run')
    cancel()
    gate.finish('development', identity, report_path)
    return {'ok': True, 'savedCount': 6}


def submit_development(database, output, spec, now):
    from features.common.jobs import submit_job
    return submit_job('macro_evaluate', '거시 규칙 개발 검증', run_development,
                      str(database), str(output), str(spec), now,
                      pass_job_id=True, dedicated_thread=True)


def run_holdout(database, output, spec, stage, *, job_id, progress=None):
    """One frozen batch includes sensitivity tables; it does not tune parameters."""
    from features.common.jobs import get_shared_job
    if stage not in {'validation', 'final'}:
        raise ValueError('invalid_holdout_stage')
    database, output, spec = Path(database), Path(output), Path(spec)
    frozen = json.loads((output / 'execution/freeze.json').read_text(encoding='utf-8'))
    identity = frozen['identity']
    actual = {**identity, 'specHash': file_hash(spec), 'databaseHash': file_hash(database),
              'codeHash': code_hash(Path(__file__).parent)}
    gate = EvaluationGate(output / 'execution')
    gate.begin(stage, actual)

    def cancel():
        job = get_shared_job(job_id)
        if job is None or job.status.value in {'cancel_requested', 'cancelled', 'failed_restart'}:
            raise RuntimeError('macro_evaluation_cancelled')

    parameters = {'theta_c': Decimal(identity['parameters']['thetaC']),
                  'theta_r': Decimal(identity['parameters']['thetaR'])}
    replay = Replay(database, [s.id for s in SERIES if s.market == 'US' and s.axis != 'stress_vulnerability'])
    summaries = {}
    for axis in ('growth', 'inflation', 'financial_conditions'):
        cancel()
        if progress: progress(message=f'{stage}: {axis} 고정 규칙을 평가하고 있습니다.')
        report = evaluate(replay, axis, stage, identity['evaluationNow'], parameters=parameters, cancel=cancel)
        if axis == 'growth':
            prefix = []
            for earlier in (['development'] if stage == 'validation' else ['development', 'validation']):
                prefix += json.loads((output / f'{earlier}-growth.json').read_text(encoding='utf-8'))['records']
            report['events'] = summarize_growth(report['records'], prefix=prefix)
            # Predeclared full grid, evaluated in this same attempt. No parameter selection.
            sensitivity = []
            prepared = [(r['asOf'], replay.select(r['asOf']), replay.facts_at(r['asOf'])) for r in report['records']]
            for c in (10, 15, 20, 25, 30):
                for r in (10, 15, 20, 25):
                    points = []
                    for cutoff, rows, facts in prepared:
                        cancel()
                        result = us_cycle(Inputs(rows, cutoff, facts), theta_c=Decimal(c) / 100, theta_r=Decimal(r) / 100)
                        points.append({'asOf': cutoff, 'cycleSignal': result['cycleSignal']})
                    sensitivity.append({'thetaC': str(Decimal(c) / 100), 'thetaR': str(Decimal(r) / 100), 'points': points})
            report['sensitivity'] = sensitivity
        write_json(output / f'{stage}-{axis}.json', report)
        packet, expected = blind_packet(report, replay)
        write_json(output / f'{stage}-{axis}-blind.json', packet)
        write_json(output / f'{stage}-{axis}-expected.json', expected)
        summaries[axis] = report['stability']
        if axis == 'financial_conditions':
            weekly = evaluate(replay, axis, stage, identity['evaluationNow'], parameters=parameters, weekly=True, cancel=cancel)
            write_json(output / f'{stage}-{axis}-weekly.json', weekly)
    report_path = output / f'{stage}-summary.json'
    write_json(report_path, {'identity': identity, 'stability': summaries, 'promotion': 'shadow',
                            'interpretationReview': 'pending', 'userAcceptance': 'pending'})
    if file_hash(database) != identity['databaseHash']:
        raise ValueError('evaluation_database_changed_during_run')
    cancel()
    gate.finish(stage, identity, report_path)
    return {'ok': True, 'savedCount': 11}


def run_shadow(database, output, now, *, job_id, progress=None):
    from features.common.jobs import get_shared_job
    from .shadow_evaluation import korea_diagnostic, stress_diagnostic
    def cancel():
        job = get_shared_job(job_id)
        if job is None or job.status.value in {'cancel_requested', 'cancelled', 'failed_restart'}:
            raise RuntimeError('macro_evaluation_cancelled')
    replay = Replay(Path(database), [s.id for s in SERIES if s.market == 'KR' or s.id == 'STLFSI4'])
    if progress: progress(message='한국 현재 수정치와 미국 빠른 스트레스의 시험 표시를 점검합니다.')
    output = Path(output)
    write_json(output / 'shadow-KR-current-revised.json', korea_diagnostic(replay, now, cancel=cancel))
    for weekly in (False, True):
        write_json(output / f'shadow-US-stress-{weekly}.json', stress_diagnostic(replay, now, weekly=weekly, cancel=cancel))
    return {'ok': True, 'savedCount': 3}


def submit_shadow(database, output, now):
    from features.common.jobs import submit_job
    return submit_job('macro_evaluate', '거시 시험 표시 진단', run_shadow, str(database), str(output), now,
                      pass_job_id=True, dedicated_thread=True)


def submit_holdout(database, output, spec, stage):
    from features.common.jobs import submit_job
    return submit_job('macro_evaluate', '거시 규칙 고정 검증', run_holdout,
                      str(database), str(output), str(spec), stage,
                      pass_job_id=True, dedicated_thread=True)
