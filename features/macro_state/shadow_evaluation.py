"""Non-promotable KR current-revision and US fast-stress diagnostics."""
from features.common.macro_data.registry import AXES
from .engine import calculate
from .baselines import single_series
from .evaluation import local_month, pair
from .replay import evaluation_cutoffs, revision_cutoff
from .rules import shift_months
from .inputs import utc, month_end
from .metrics import stability


def korea_diagnostic(replay, now, *, cancel=None):
    end = shift_months(local_month(now, 'KR') + '-01', -1)[:7]
    records = []
    for cutoff in evaluation_cutoffs('2000-08', end, 'KR'):
        if cancel: cancel()
        month = local_month(cutoff, 'KR')
        rows = replay.select(now, observation_end=month_end(month + '-01'))
        for axis in AXES:
            result = calculate('KR', axis, rows, cutoff, selection_cutoff=now, basis='current_revised', diagnostic=True)
            baseline = single_series('KR', axis, rows, cutoff, selection_cutoff=now)
            records.append({'asOf': cutoff, 'axis': axis, 'proposal': result, 'B1': baseline})
    return {'basis': 'current_revised', 'diagnosticOnly': True, 'promotion': 'shadow', 'referenceCutoff': now,
            'revisionStability': 'not_applicable_no_historical_vintages', 'records': records}


def stress_diagnostic(replay, now, *, weekly=False, cancel=None):
    dates = [r[2] for (key, _), rows in replay.history.items() if key == 'STLFSI4' for r in rows]
    if not dates: return {'promotion': 'shadow', 'records': [], 'reason': 'no_vintage'}
    start = local_month(min(dates))
    end = shift_months(local_month(now) + '-01', -1)[:7]
    records = []
    previous = None
    for cutoff in evaluation_cutoffs(start, end, weekly=weekly):
        if cancel: cancel()
        reference = revision_cutoff(cutoff, weekly=weekly)
        immature = utc(reference) > utc(now)
        target = cutoff if immature else reference
        current = pair(replay, 'stress_vulnerability', cutoff, target)
        if previous:
            prior = pair(replay, 'stress_vulnerability', previous, target)
            b0, revised = prior['proposal'], prior['proposalRevised']
        else:
            b0 = revised = {'level': 'unknown', 'direction': 'unknown'}
        current.update(asOf=cutoff, month=local_month(cutoff), referenceCutoff=reference,
                       immatureReference=immature, B0=b0, B0Revised=revised)
        records.append(current)
        previous = cutoff
    return {'promotion': 'shadow', 'weekly': weekly, 'records': records,
            'stability': {field: stability(records, field) for field in ('level', 'direction')}}
