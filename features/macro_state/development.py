"""Development-only, explicitly labelled revised-claims threshold selection."""
from decimal import Decimal as D

from .cycle import claims, diagnostic_available_at, us_cycle
from .inputs import Inputs, utc
from .metrics import cycle_events, timeliness, choose_threshold, usable
from .replay import evaluation_cutoffs
from .evaluation import local_month


FIXED_CLAIMS_CUTOFF = '2026-09-29T04:59:59.999999Z'  # Chicago 2026-09-28 end
FIXED_CLAIMS_VINTAGE = '2026-09-24'


def diagnostic_rows(rows, fixed_rows, cutoff, *, force_revised=False):
    book = Inputs(rows, cutoff)
    complete = all(v is not None for v in claims(book).values())
    if complete and not force_revised:
        return rows, 'as-of'
    revised = []
    for source in fixed_rows:
        available = diagnostic_available_at(source['period'])
        if available <= utc(cutoff):
            revised.append({**source, 'availableAt': available,
                            'actualSourceAvailableAt': source['availableAt'], 'diagnosticAvailability': True})
    return [r for r in rows if r['seriesId'] != 'ICSA'] + revised, 'revised'


def threshold_development(replay, *, cancel=None, progress=None):
    fixed = [r for r in replay.select(FIXED_CLAIMS_CUTOFF) if r['seriesId'] == 'ICSA']
    if not fixed or max(r['vintageDate'] or '' for r in fixed) != FIXED_CLAIMS_VINTAGE:
        raise ValueError('development_fixed_claims_vintage_mismatch')
    prepared = []
    revisions = []
    # Non-evaluation preparation months establish left-censoring only.
    for cutoff in evaluation_cutoffs('2000-02', '2012-12'):
        if cancel: cancel()
        original = replay.select(cutoff)
        rows, basis = diagnostic_rows(original, fixed, cutoff)
        prepared.append((cutoff, rows, basis, replay.facts_at(cutoff)))
        if local_month(cutoff) >= '2009-06':
            current = claims(Inputs(original, cutoff))
            revised_rows, _ = diagnostic_rows(original, fixed, cutoff, force_revised=True)
            revised = claims(Inputs(revised_rows, cutoff))
            revisions.append({'month': local_month(cutoff), 'asOf': {k: str(v) if v is not None else None for k, v in current.items()},
                              'fixedRevised': {k: str(v) if v is not None else None for k, v in revised.items()},
                              'differencePercent': {k: str((revised[k] / v - 1) * 100) if v and revised[k] is not None else None
                                                    for k, v in current.items()}})

    def candidate(theta_c, theta_r, kind):
        points = []
        for cutoff, rows, basis, facts in prepared:
            if cancel: cancel()
            book = Inputs(rows, cutoff, facts)
            result = us_cycle(book, theta_c=theta_c, theta_r=theta_r, diagnostic=True)
            points.append({'month': local_month(cutoff), 'signal': result['cycleSignal'], 'claimsBasis': basis})
        events = cycle_events([(p['month'], p['signal']) for p in points])
        for items in events.values():
            for event in items:
                bases = {p['claimsBasis'] for p in points if event['start'] <= p['month'] <= event['end']}
                event['claimsBasis'] = 'mixed' if len(bases) > 1 else next(iter(bases))
        turning = ['2001-03', '2007-12'] if kind == 'warnings' else ['2001-11', '2009-06']
        return {'theta': theta_c if kind == 'warnings' else theta_r,
                'timeliness': timeliness(events, kind, turning),
                'falseEvents': sum(e['falseSignal'] and usable(e) for e in events[kind]),
                'events': events, 'points': points}

    warnings = [candidate(D(n) / 100, D('.15'), 'warnings') for n in (10, 15, 20, 25, 30)]
    theta_c, empty_c = choose_threshold(warnings, D('.20'))
    if progress: progress(message='개발 구간의 수축 경고 후보 집계를 마쳤습니다.')
    recoveries = [candidate(theta_c, D(n) / 100, 'recoveries') for n in (10, 15, 20, 25)]
    theta_r, empty_r = choose_threshold(recoveries, D('.15'))
    for candidate_result in warnings + recoveries:
        candidate_result['theta'] = str(candidate_result['theta'])
    return {'diagnosticOnly': True, 'fixedClaimsCutoff': FIXED_CLAIMS_CUTOFF,
            'fixedClaimsVintage': FIXED_CLAIMS_VINTAGE,
            'parameters': {'thetaC': str(theta_c), 'thetaR': str(theta_r)},
            'emptyEligibleSet': {'thetaC': empty_c, 'thetaR': empty_r},
            'claimsRevisionComparison': revisions,
            'warningCandidates': warnings, 'recoveryCandidates': recoveries}
