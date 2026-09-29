"""Descriptive evaluation tables; these never change snapshot promotion."""
from .metrics import NBER, distance, month_shift, false_contractions, cycle_events, timeliness, usable


def transitions(points):
    pairs = [(a, b) for a, b in zip(points, points[1:]) if a[1] != 'unknown' and b[1] != 'unknown']
    by_year = {}
    for a, b in pairs:
        if a[1] != b[1]:
            by_year[b[0][:4]] = by_year.get(b[0][:4], 0) + 1
    return {'comparableAdjacentPairs': len(pairs), 'changes': sum(by_year.values()), 'byYear': by_year}


def detections(points, confirmed='contraction'):
    if not points: return []
    result = []
    for peak, trough in NBER:
        if not points[0][0] <= peak <= points[-1][0]: continue
        found = next((m for m, s in points if s == confirmed and month_shift(peak, -3) <= m <= month_shift(trough, 3)), None)
        result.append({'peak': peak, 'trough': trough, 'detected': found,
                       'delayMonths': max(0, distance(peak, found)) if found else None,
                       'earlyMonths': max(0, distance(found, peak)) if found else None})
    return result


def summarize_growth(records, *, prefix=()):
    result = {}
    start, end = records[0]['month'], records[-1]['month']
    for method in ('proposal', 'B0', 'B1'):
        level = [(r['month'], r[method]['level']) for r in records]
        cycle = [(r['month'], r[method].get('cycleSignal', 'unknown')) for r in [*prefix, *records]]
        events = cycle_events(cycle)
        for key in events:
            events[key] = [e for e in events[key] if start <= e['start'] <= end]
        peaks = [p for p, _ in NBER if start <= p <= end]
        troughs = [t for _, t in NBER if start <= t <= end]
        confirmation = []
        for trough in troughs:
            dates = [e['firstConfirmation'] for e in events['recoveries'] if usable(e) and e['firstConfirmation']
                     and trough <= e['firstConfirmation'] <= month_shift(trough, 9)]
            first = min(dates) if dates else None
            confirmation.append({'trough': trough, 'firstConfirmation': first,
                                 'delayMonths': distance(trough, first) if first else None})
        cycle_current = [(m, s) for m, s in cycle if start <= m <= end]
        result[method] = {'levelDetection': detections(level), 'levelFalseContractions': false_contractions(level),
                          'cycleFalseConfirmations': false_contractions(cycle_current, confirmed='contraction_confirmed'),
                          'cycleDetection': detections(cycle_current, confirmed='contraction_confirmed'),
                          'events': events, 'warningTimeliness': timeliness(events, 'warnings', peaks),
                          'recoveryTimeliness': timeliness(events, 'recoveries', troughs),
                          'recoveryConfirmation': confirmation,
                          'falseWarnings': sum(usable(e) and e['falseSignal'] for e in events['warnings']),
                          'falseRecoveries': sum(usable(e) and e['falseSignal'] for e in events['recoveries']),
                          'returnToContraction': [b[0] for a, b in zip(cycle, cycle[1:])
                                                  if a[1] in {'recovery_signal', 'recovery_confirmed'}
                                                  and b[1] == 'contraction_confirmed' and start <= b[0] <= end],
                          'changes': {field: transitions([(r['month'], r[method].get(field, 'unknown')) for r in records])
                                      for field in ('level', 'direction', 'cycleSignal')}}
    return result
