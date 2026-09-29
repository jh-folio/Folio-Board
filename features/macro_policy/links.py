"""Resolve explicit immutable company/condition references, never co-mentions."""
import sqlite3
from pathlib import Path

from features.company_exposure.service import ticker_value
from features.company_exposure.store import ExposureStore
from features.thesis_tracking.reason_history import latest


def targets(root, ticker):
    ticker = ticker_value(ticker)
    profile = ExposureStore(root).get(ticker)
    reason = None
    path = Path(root) / 'market-memory.sqlite3'
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            conn.row_factory = sqlite3.Row
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='reason_revision'").fetchone():
                reason = latest(conn, ticker)
    return {'profile': profile, 'reason': {'revisionId': reason['revisionId'],
            'conditions': reason['content'].get('falsification_triggers', []),
            'layer': 'hypothesis'} if reason else None}


def resolve(root, link, explanation):
    if not isinstance(link, dict) or not {'ticker', 'profileId', 'exposureId'} <= link.keys():
        raise ValueError('policy_invalid_company_link')
    if link.keys() - {'ticker', 'profileId', 'exposureId', 'condition'}:
        raise ValueError('policy_invalid_company_link')
    current = targets(root, link['ticker'])
    profile = current['profile']
    if not profile or profile['profileId'] != link['profileId']:
        raise ValueError('policy_stale_exposure')
    exposure = next((r for r in profile['items'] if r['id'] == link['exposureId']), None)
    if not exposure:
        raise ValueError('policy_missing_exposure')
    result = {key: link[key] for key in ('ticker', 'profileId', 'exposureId')}
    result.update(sourceRef=exposure['sourceRef'], quote=exposure['quote'], layer='source-grounded')
    condition = link.get('condition')
    if condition is not None:
        if not isinstance(condition, dict) or set(condition) != {'revisionId', 'index', 'overlapQuote'}:
            raise ValueError('policy_invalid_condition')
        reason = current['reason']
        index = condition['index']
        if not reason or reason['revisionId'] != condition['revisionId']:
            raise ValueError('policy_stale_reason')
        if type(index) is not int or index < 0 or index >= len(reason['conditions']):
            raise ValueError('policy_missing_condition')
        quote = reason['conditions'][index]
        overlap = condition['overlapQuote']
        if not isinstance(quote, str) or not isinstance(overlap, str) or len(overlap.strip()) < 2 or overlap not in quote or overlap not in explanation:
            raise ValueError('policy_condition_not_explicitly_overlapping')
        result['condition'] = {**condition, 'quote': quote, 'layer': 'hypothesis',
                               'sourceRef': {'reasonRevisionId': reason['revisionId'], 'conditionIndex': index}}
    return result
