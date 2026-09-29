"""Maintainer-only, preview/confirm registration of official non-publication facts.

Collection and GET paths never invoke this writer. A null observation is not a fact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from .schema import canonical, digest, timestamp
from .store import MacroStore


def preview_fact(payload: dict) -> dict:
    if payload.get('seriesId') != 'UNRATE':
        raise ValueError('publication_fact_requires_unrate')
    month = payload.get('observationMonth', '')
    try:
        date = dt.date.fromisoformat(month + '-01')
    except (TypeError, ValueError):
        raise ValueError('invalid_observation_month') from None
    if date.strftime('%Y-%m') != month:
        raise ValueError('invalid_observation_month')
    url = payload.get('sourceUrl', '')
    source = urlsplit(url)
    if source.scheme != 'https' or source.hostname not in {'bls.gov', 'www.bls.gov'} or source.username or source.password or source.port not in {None, 443} or not source.path.strip('/'):
        raise ValueError('publication_fact_requires_official_bls_url')
    available = timestamp(payload.get('availableAt', ''))
    if available[:10] < date.isoformat():
        raise ValueError('publication_fact_precedes_observation')
    body = {'rowKind': 'fact', 'factType': 'officiallyNotPublished', 'seriesId': 'UNRATE',
            'observationMonth': month, 'sourceUrl': url, 'availableAt': available}
    return {**body, 'confirmationToken': digest(body)}


def record_fact(store: MacroStore, payload: dict, *, confirmation_token: str) -> dict:
    preview = preview_fact(payload)
    token = preview.pop('confirmationToken')
    if confirmation_token != token:
        raise ValueError('publication_fact_confirmation_required')
    body = {**preview, 'recordedAt': dt.datetime.now(dt.timezone.utc).isoformat()}
    store.ensure()
    with sqlite3.connect(store.path, timeout=30) as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('INSERT OR IGNORE INTO macro_publication_facts VALUES(?,?,?,?,?)',
                     (token, body['seriesId'], body['observationMonth'], body['availableAt'], canonical(body)))
        saved = conn.execute('SELECT body FROM macro_publication_facts WHERE identity=?', (token,)).fetchone()
    return json.loads(saved[0])


def publication_facts(store: MacroStore, *, cutoff: str) -> list[dict]:
    cutoff = timestamp(cutoff)
    with store.read() as conn:
        if conn is None or not conn.execute("SELECT 1 FROM sqlite_master WHERE name='macro_publication_facts' AND type='table'").fetchone():
            return []
        return [json.loads(row[0]) for row in conn.execute(
            'SELECT body FROM macro_publication_facts WHERE available_at<=? ORDER BY series_id,period,available_at,identity', (cutoff,))]


def main():
    parser = argparse.ArgumentParser(description='공식 미발표 사실 미리보기 및 명시 등록 (수집기가 호출하지 않음)')
    parser.add_argument('--input', type=Path, required=True, help='공식 원문을 확인한 사실 JSON')
    parser.add_argument('--database', type=Path, help='명시 등록 대상 market-memory.sqlite3')
    parser.add_argument('--confirm', help='미리보기 confirmationToken과 일치해야 저장')
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding='utf-8'))
    if args.confirm:
        if args.database is None or args.database.name != 'market-memory.sqlite3':
            parser.error('--database must name market-memory.sqlite3')
        result = record_fact(MacroStore(args.database), payload, confirmation_token=args.confirm)
    else:
        result = preview_fact(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
