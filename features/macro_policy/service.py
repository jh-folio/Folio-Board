"""Manual/Agent drafts are never policy decisions until explicitly confirmed."""
import datetime as dt
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from features.common.macro_data.schema import canonical, digest
from features.common.macro_data.store import backup_database, _SCHEMA_LOCK

POLICY_TYPES = {'central_bank_rate', 'central_bank_balance_sheet', 'fiscal_spending',
                'tax', 'tariff', 'subsidy', 'regulation', 'export_control'}
STATUSES = {'proposed', 'announced', 'enacted', 'effective', 'suspended', 'withdrawn'}
CHANNELS = {'demand_revenue', 'input_cost', 'financing_cost', 'capex_incentive',
            'market_access', 'compliance_cost', 'fx'}
SOURCE_KINDS = {'central_bank', 'government', 'gazette', 'legislation', 'company_filing'}


def text(value, field, limit=6000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('policy_invalid_' + field)
    return value.strip()


def source(value):
    if not isinstance(value, dict) or set(value) != {'url', 'title', 'kind', 'quote'}:
        raise ValueError('policy_official_source_required')
    result = {k: text(v, 'source_' + k) for k, v in value.items()}
    url = urlsplit(result['url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        raise ValueError('policy_official_source_required')
    if result['kind'] not in SOURCE_KINDS:
        raise ValueError('policy_official_source_required')
    # Source provenance is explicitly checked by the user at confirmation;
    # a URL or an Agent's assertion alone cannot prove an official decision.
    return result


def normalize(draft):
    required = {'title', 'policyType', 'jurisdiction', 'status', 'sourceRef',
                'counterConditions', 'nextCheckpoint'}
    optional = {'announcedAt', 'effectiveFrom', 'effectiveTo', 'channels'}
    if not isinstance(draft, dict) or not required <= draft.keys() or draft.keys() - required - optional:
        raise ValueError('policy_invalid_fields')
    result = {k: draft[k] for k in ('policyType', 'jurisdiction', 'status')}
    if result['policyType'] not in POLICY_TYPES or result['jurisdiction'] not in {'US', 'KR'} or result['status'] not in STATUSES:
        raise ValueError('policy_invalid_enum')
    result['title'] = text(draft['title'], 'title', 300)
    result['sourceRef'] = source(draft['sourceRef'])
    for field in ('counterConditions', 'nextCheckpoint'):
        result[field] = text(draft[field], field)
    for field in ('announcedAt', 'effectiveFrom', 'effectiveTo'):
        value = draft.get(field) or None
        if value is not None:
            try:
                if dt.date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError('policy_invalid_date') from None
        result[field] = value
    if result['effectiveFrom'] and result['effectiveTo'] and result['effectiveFrom'] > result['effectiveTo']:
        raise ValueError('policy_invalid_date_range')
    channels = draft.get('channels', [])
    if not isinstance(channels, list) or len(channels) > 30:
        raise ValueError('policy_invalid_channels')
    result['channels'] = []
    for entry in channels:
        if not isinstance(entry, dict) or set(entry) != {'channel', 'explanation', 'sourceRef'} or entry['channel'] not in CHANNELS:
            raise ValueError('policy_invalid_channel')
        result['channels'].append({'channel': entry['channel'],
                                   'explanation': text(entry['explanation'], 'explanation'),
                                   'sourceRef': source(entry['sourceRef'])})
    return result


def preview(draft):
    body = normalize(draft)
    return {'draft': body, 'previewId': digest({'version': 'policy-event-1', 'draft': body}),
            'requiresConfirmation': True,
            'notice': '공식 원문의 내용·날짜·진행 단계를 확인한 뒤 저장하세요. 전달 경로는 조건부 설명이며 예측이나 투자 지시가 아닙니다.'}


class PolicyStore:
    def __init__(self, data_root):
        self.path = Path(data_root).resolve() / 'market-memory.sqlite3'

    def list(self):
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='macro_policy_events'").fetchone():
                return []
            return [json.loads(row[0]) for row in conn.execute('SELECT body FROM macro_policy_events ORDER BY seq DESC')]

    def ensure(self):
        with _SCHEMA_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True) as conn:
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='macro_policy_events'").fetchone():
                        return
            backup_database(self.path, 'before-macro-policy-v1')
            with sqlite3.connect(self.path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('CREATE TABLE macro_policy_events(seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, body TEXT NOT NULL)')
                for operation in ('UPDATE', 'DELETE'):
                    conn.execute(f"CREATE TRIGGER macro_policy_no_{operation.lower()} BEFORE {operation} ON macro_policy_events BEGIN SELECT RAISE(ABORT,'immutable_policy_event'); END")

    def confirm(self, draft, *, preview_id, user_confirmed, official_source_confirmed):
        checked = preview(draft)
        if user_confirmed is not True or official_source_confirmed is not True:
            raise ValueError('policy_explicit_confirmation_required')
        if checked['previewId'] != preview_id:
            raise ValueError('policy_preview_changed')
        ident = 'policy-' + preview_id
        body = dict(checked['draft'], id=ident, schemaVersion='policy-event-1',
                    confirmedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                    layer='source-grounded', reuseAsEvidence=False)
        self.ensure()
        with sqlite3.connect(self.path, timeout=30) as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT body FROM macro_policy_events WHERE id=?', (ident,)).fetchone()
            if old:
                return json.loads(old[0])
            conn.execute('INSERT INTO macro_policy_events(id,body) VALUES(?,?)', (ident, canonical(body)))
        return body
