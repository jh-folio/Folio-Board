"""Explicit evaluation primitives. Importing this module never reads user data."""
import datetime as dt
from zoneinfo import ZoneInfo

from .baselines import single_series
from .engine import calculate
from .inputs import utc
from .metrics import stability
from .replay import evaluation_cutoffs, revision_cutoff
from .rules import shift_months


PERIODS = {
    'development': {'growth': ('2000-08', '2012-12'), 'inflation': ('2000-08', '2012-12'),
                    'financial_conditions': ('2011-06', '2017-12')},
    'validation': {'growth': ('2013-01', '2019-12'), 'inflation': ('2013-01', '2019-12'),
                   'financial_conditions': ('2018-01', '2021-12')},
    'final': {'growth': ('2020-01', None), 'inflation': ('2020-01', None),
              'financial_conditions': ('2022-01', None)},
}


def local_month(cutoff, market='US'):
    timezone = 'America/Chicago' if market == 'US' else 'Asia/Seoul'
    return dt.datetime.fromisoformat(utc(cutoff).replace('Z', '+00:00')).astimezone(ZoneInfo(timezone)).strftime('%Y-%m')


def observed_periods(result):
    """Include missing requested periods, but never a newly published next period."""
    refs = result['sourceRefs'] + result['unknownReason']
    if 'cycleSignalBasis' in result:
        refs += result['cycleSignalBasis']['unknownReason']
    return {(r['seriesId'], r['period']) for r in refs if r.get('period') and r.get('rowKind') != 'fact'}


def pair(replay, axis, cutoff, revised_cutoff, *, market='US', parameters=None):
    facts = replay.facts_at(cutoff)
    rows = replay.select(cutoff)
    parameters = parameters or {}
    initial = calculate(market, axis, rows, cutoff, facts=facts, **parameters)
    baseline = single_series(market, axis, rows, cutoff, facts=facts)
    if calculate(market, axis, list(reversed(rows)), cutoff, facts=facts, **parameters) != initial:
        raise ValueError('evaluation_non_reproducible_proposal')
    if single_series(market, axis, list(reversed(rows)), cutoff, facts=facts) != baseline:
        raise ValueError('evaluation_non_reproducible_baseline')
    result = {}
    for name, original, function, options in (
        ('proposal', initial, calculate, parameters), ('B1', baseline, single_series, {}),
    ):
        allowed = observed_periods(original)
        revised_rows = replay.select(revised_cutoff, allowed=allowed)
        revised = function(market, axis, revised_rows, cutoff, facts=facts,
                           selection=original['observationSelection'], selection_cutoff=revised_cutoff, **options)
        if any((r['seriesId'], r['period']) not in allowed for r in revised['sourceRefs'] if r.get('rowKind') == 'observation'):
            raise ValueError('revision_observation_leak')
        if any(utc(r['availableAt']) > utc(cutoff) for r in original['sourceRefs']):
            raise ValueError('original_availability_leak')
        if any(utc(r['availableAt']) > utc(revised_cutoff) for r in revised['sourceRefs']):
            raise ValueError('revision_availability_leak')
        result[name] = original
        result[name + 'Revised'] = revised
    return result


def evaluate(replay, axis, stage, now, *, parameters=None, weekly=False, progress=None, cancel=None):
    """Caller must acquire the durable run gate before calling this function."""
    start, end = PERIODS[stage][axis]
    last_complete = shift_months(local_month(now) + '-01', -1)[:7]
    end = min(end or last_complete, last_complete)
    cutoffs = list(evaluation_cutoffs(start, end, weekly=weekly))
    prior_start = shift_months(start + '-01', -1)[:7]
    previous = list(evaluation_cutoffs(prior_start, prior_start, weekly=weekly))[-1]
    records = []
    for index, cutoff in enumerate(cutoffs):
        if cancel:
            cancel()
        revised = revision_cutoff(cutoff, weekly=weekly)
        immature = utc(revised) > utc(now)
        # Immature rows remain in scheduled/unknown counts, without future selection.
        reference = cutoff if immature else revised
        current = pair(replay, axis, cutoff, reference, parameters=parameters)
        # B0 means the preceding scheduled judgement; its reference uses CURRENT t+3.
        preceding = pair(replay, axis, previous, reference, parameters=parameters)
        current.update(asOf=cutoff, referenceCutoff=revised, month=local_month(cutoff),
                       immatureReference=immature, B0=preceding['proposal'], B0Revised=preceding['proposalRevised'])
        if stage == 'development' and index == 0:
            current['B0'] = current['B0Revised'] = {'level': 'unknown', 'direction': 'unknown', 'cycleSignal': 'unknown'}
        records.append(current)
        previous = cutoff
        if progress:
            progress(index + 1, len(cutoffs))
    fields = ['level', 'direction'] + (['cycleSignal'] if axis == 'growth' else [])
    return {'stage': stage, 'axis': axis, 'weekly': weekly, 'records': records,
            'invariants': {'reproducedInputOrderPermutations': len(records) * 2,
                           'availabilityAndObservationSetChecked': True},
            'stability': {field: stability([r for r in records if not (
                stage == 'development' and axis == 'inflation' and field == 'level' and r['month'] < '2012-01')], field)
                for field in fields}}
