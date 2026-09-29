"""Deterministic sample selection, frozen before an independent blind reading."""
import hashlib
import json
import copy
from decimal import Decimal as D
from .engine import calculate
from .inputs import Inputs
from .rules import shift_months


def select_samples(records, minimum=12):
    valid = [r for r in records if all(r['proposal'][f] != 'unknown' for f in ('level', 'direction'))]
    chosen = {}
    # Cover every computed enum pair, conflict and state change before filling
    # chronological quantiles. Selection is fixed; no replacement after reading.
    groups = {}
    prior = None
    for record in valid:
        value = record['proposal']
        categories = [('enum', value['level'], value['direction']),
                      ('conflict', bool(value['conflicts']))]
        if prior and any(prior['proposal'][f] != value[f] for f in ('level', 'direction')):
            categories.append(('transition', value['level'], value['direction']))
        for key in categories:
            groups.setdefault(key, []).append(record)
        prior = record
    for group in groups.values():
        candidate = group[len(group) // 2]
        chosen[candidate['asOf']] = candidate
    if valid:
        for i in range(minimum):
            candidate = valid[round(i * (len(valid) - 1) / max(1, minimum - 1))]
            chosen[candidate['asOf']] = candidate
    return [chosen[key] for key in sorted(chosen)]


def blind_packet(report, replay):
    selected = select_samples(report['records'])
    # Also fix the two nearest observed boundaries per axis, using only values
    # available on that date. The independent reader still sees no verdicts.
    margins = []
    for record in report['records']:
        result = record['proposal']
        if any(result[f] == 'unknown' for f in ('level', 'direction')): continue
        b = Inputs(replay.select(record['asOf']), record['asOf'], replay.facts_at(record['asOf']))
        distances = []
        if report['axis'] == 'inflation':
            m = b.latest('PCEPILFE')
            value = b.growth('PCEPILFE', m, 12)
            if value is not None: distances = [abs(value - n) for n in (D('1.5'), D('2.5'), D('4'))]
        elif report['axis'] == 'financial_conditions':
            value = b.value('NFCI', b.latest('NFCI'))
            if value is not None: distances = [abs(value - n) for n in (D('-.25'), D('.25'))]
        else:
            q = result['observationSelection'].get('latest:GDPC1')
            if q:
                value, trend = b.growth('GDPC1', q, 3), b.trend('GDPC1', q, 3, 12)
                if value is not None and trend is not None:
                    distances = [abs(value - trend - n) for n in (D('-.25'), D('.25'))]
        if distances: margins.append((min(distances), record['asOf'], record))
    chosen = {r['asOf']: r for r in selected}
    for _, cutoff, record in sorted(margins, key=lambda x: (x[0], x[1]))[:2]: chosen[cutoff] = record
    selected = [chosen[k] for k in sorted(chosen)]
    cards, expected = [], []
    for record in selected:
        result = record['proposal']
        # Cycle is reviewed against dated events separately. This packet reads
        # growth level/direction, not claims-based cycle labels.
        excluded = {'ICSA', 'CFNAIMA3'} if report['axis'] == 'growth' else set()
        allowed = {(r['seriesId'], r['period']) for r in result['sourceRefs']
                   if r.get('rowKind') == 'observation' and r['seriesId'] not in excluded}
        rows = replay.select(record['asOf'], allowed=allowed)
        card = {'sampleId': f"{report['stage']}:{report['axis']}:{record['month']}",
                'asOf': record['asOf'], 'market': 'US', 'axis': report['axis'],
                'observationSelection': {k: v for k, v in result['observationSelection'].items()
                                         if not any(key in k for key in excluded)},
                'sourceRows': rows, 'publicationFacts': replay.facts_at(record['asOf'])}
        cards.append(card)
        expected.append({'sampleId': card['sampleId'], 'level': result['level'], 'direction': result['direction'],
                         'conflicts': result['conflicts'], 'confidence': result['confidence']})
    valid_count = len(cards)
    if cards:
        original = cards[len(cards) // 2]
        primary = {'growth': 'GDPC1', 'inflation': 'PCEPILFE', 'financial_conditions': 'NFCI'}[report['axis']]
        for kind in ('missing', 'integrity_conflict', 'stale'):
            fixture = copy.deepcopy(original)
            fixture['sampleId'] = f"fixture:{report['stage']}:{report['axis']}:{kind}"
            fixture['syntheticFixture'] = True
            if kind == 'missing':
                fixture['sourceRows'] = [r for r in fixture['sourceRows'] if r['seriesId'] != primary]
            elif kind == 'integrity_conflict':
                for row in fixture['sourceRows']:
                    if row['seriesId'] == primary: row['conflict'] = True
            else:
                fixture['asOf'] = shift_months(fixture['asOf'][:10], 12) + fixture['asOf'][10:]
            # Dates for fixtures must be selected from the mutated input, not the
            # original historical card. These are not revision comparisons.
            fixture.pop('observationSelection', None)
            result = calculate('US', report['axis'], fixture['sourceRows'], fixture['asOf'], facts=fixture['publicationFacts'])
            cards.append(fixture)
            expected.append({'sampleId': fixture['sampleId'], 'level': result['level'], 'direction': result['direction'],
                             'conflicts': result['conflicts'], 'confidence': result['confidence']})
    manifest = [{'sampleId': c['sampleId'], 'asOf': c['asOf']} for c in cards]
    fingerprint = hashlib.sha256(json.dumps(cards, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    return {'sampleHash': fingerprint, 'manifest': manifest, 'validCount': valid_count,
            'minimumMet': valid_count >= 12, 'cards': cards}, expected
