from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from decimal import Decimal
from zoneinfo import ZoneInfo

from .registry import series


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def timestamp(value: str) -> str:
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('macro_timestamp_requires_timezone')
    return parsed.astimezone(dt.timezone.utc).isoformat()


def day_end(day: str, timezone: str) -> str:
    date=dt.date.fromisoformat(day)
    return dt.datetime.combine(date,dt.time.max,ZoneInfo(timezone)).astimezone(dt.timezone.utc).isoformat()


def normalize_observation(row: dict) -> dict:
    spec=series(row['seriesId'])
    period=dt.date.fromisoformat(row['period']).isoformat()
    value=row.get('value')
    if value in (None,'','.'): value=None
    else:
        if isinstance(value,bool) or not math.isfinite(float(value)):raise ValueError('invalid_macro_value')
        number=Decimal(str(value))
        value='0' if number==0 else format(number.normalize(),'f')
    basis=row.get('availabilityBasis')
    if basis not in {'official_release','provider_vintage','local_observed'}:raise ValueError('invalid_availability_basis')
    if spec.market=='KR' and basis!='local_observed':raise ValueError('korean_historical_replay_unsupported')
    fetched=timestamp(row['fetchedAt'])
    vintage=row.get('vintageDate')
    released=row.get('releasedAt')
    if basis=='provider_vintage':
        vintage=dt.date.fromisoformat(vintage).isoformat()
        available=day_end(vintage,spec.timezone)
        precision='date'
        released=None
    elif basis=='official_release':
        if not row.get('releaseEvidenceUrl'):raise ValueError('release_evidence_required')
        available=timestamp(released)
        precision='timestamp'
        vintage=dt.date.fromisoformat(vintage or available[:10]).isoformat()
    else:
        available=fetched
        precision='timestamp'
        vintage=None
        released=None
    metadata=row.get('metadata')
    if not isinstance(metadata,dict) or not metadata.get('unit') or metadata.get('frequency')!=spec.frequency:
        raise ValueError('invalid_macro_metadata')
    return {'seriesId':spec.id,'period':period,'value':value,'vintageDate':vintage,
            'releasedAt':released,'availableAt':available,'availabilityBasis':basis,'precision':precision,
            'fetchedAt':fetched,'metadata':metadata,'releaseEvidenceUrl':row.get('releaseEvidenceUrl') if released else None}
