"""Official-provider readers. Every page is validated before entering the ledger."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from features.common.data_reliability.fetch_runtime import FetchPolicy, ProviderFetchRuntime
from .registry import Series
from .schema import digest


class ProviderError(RuntimeError):
    pass


def fred_vintage_pattern(series_id=None):
    # `output_type=3` 응답의 열 이름. `GDPC1_20260625`처럼 시리즈와 보관판 날짜가 붙는다.
    return re.compile((re.escape(series_id) if series_id else '.+') + r'_(\d{4})(\d{2})(\d{2})')


def get_json(url: str):
    # 429·5xx만 짧게 두 번 다시 시도한다. 나머지는 즉시 원천 실패로 올린다.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=40) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(attempt + 1)
                continue
            raise ProviderError('provider_http_' + str(exc.code)) from None
        except (OSError, ValueError):
            raise ProviderError('provider_unavailable') from None
    raise ProviderError('provider_unavailable')


def parse_fred_vintages(payload: dict, series_id: str):
    """All periods and revisions. Calendar chooses a headline only after this parser."""
    rows = payload.get('observations')
    if not isinstance(rows, list):
        raise ProviderError('invalid_fred_payload')
    pattern = fred_vintage_pattern(series_id)
    for point in rows:
        if not isinstance(point, dict):
            raise ProviderError('invalid_fred_row')
        period = dt.date.fromisoformat(str(point.get('date', ''))).isoformat()
        for key, value in point.items():
            match = pattern.fullmatch(key)
            if match:
                vintage = dt.date.fromisoformat('-'.join(match.groups())).isoformat()
                yield {'period': period, 'vintageDate': vintage, 'value': None if value in (None, '.', '') else str(value)}


def ecos_period(raw: str, frequency: str):
    # ECOS 기간 표기(2024Q1 / 202401 / 20240102)를 관측기간 시작일로 바꾼다.
    if frequency == 'Q' and re.fullmatch(r'\d{4}Q[1-4]', raw):
        return dt.date(int(raw[:4]), 1 + (int(raw[-1]) - 1) * 3, 1).isoformat()
    if frequency == 'M' and re.fullmatch(r'\d{6}', raw):
        return dt.date(int(raw[:4]), int(raw[4:]), 1).isoformat()
    if frequency == 'D' and re.fullmatch(r'\d{8}', raw):
        return dt.datetime.strptime(raw, '%Y%m%d').date().isoformat()
    raise ProviderError('invalid_ecos_period')


def fred_metadata(row):
    # 제목·설명이 바뀌면 definitionVersion이 달라져 변화율 계산이 정의 변경을 넘지 않는다.
    return {
        'unit': row['units'],
        'frequency': row['frequency_short'],
        'adjustment': row['seasonal_adjustment_short'],
        'definitionVersion': digest([row.get('title'), row.get('notes')]),
        'providerSeries': row['id'],
    }


class OfficialReader:
    def __init__(self, runtime: ProviderFetchRuntime, *, fred_key='', ecos_key='', transport=get_json):
        self.runtime = runtime
        self.keys = {'fred': fred_key, 'ecos': ecos_key}
        self.transport = transport
        self.metadata_versions = {}

    def _fetch(self, provider, operation, params, url, required):
        def retrieve():
            result = self.transport(url)
            if not isinstance(result, dict) or required not in result:
                raise ProviderError('invalid_provider_payload')
            return result

        # cache 키에는 인증정보가 든 URL이 아니라 요청 매개변수만 들어간다.
        result = self.runtime.fetch(
            provider,
            'macro_' + operation,
            {**params, 'parserVersion': 'macro-1'},
            retrieve,
            policy=FetchPolicy(ttl_seconds=3600, timeout_seconds=60, stale_while_revalidate_seconds=0),
            background_refresh=False,
        )
        if result['status'] not in {'fresh', 'cached'}:
            raise ProviderError('provider_failed')
        return result['value'], result['fetchedAt']

    def fred(self, endpoint, params, required):
        if not self.keys['fred']:
            raise ProviderError('not_connected')
        url = 'https://api.stlouisfed.org/fred/' + endpoint + '?' + urllib.parse.urlencode({**params, 'api_key': self.keys['fred'], 'file_type': 'json'})
        cache_params = {**params}
        if endpoint == 'series/observations':
            # 메타데이터가 바뀌면 같은 관측 요청이라도 옛 cache를 다시 쓰지 않는다.
            cache_params['metadataVersion'] = self.metadata_versions.get(params['series_id'], 'unknown')
        return self._fetch('fred', endpoint, cache_params, url, required)

    def fred_pages(self, spec: Series, start: str, *, cursor=None, cancel=lambda: None):
        # 모든 FRED 보관판을 `(points, next_cursor, fetchedAt)` 페이지로 내보낸다.
        cursor = cursor or {}
        end = cursor.get('end') or dt.datetime.now(ZoneInfo(spec.timezone)).date().isoformat()
        since = cursor.get('since') or start

        # 1) 보관판별 메타데이터. 단위·주기·조정이 registry와 다르면 수집하지 않는다.
        metadata, _ = self.fred('series', dict(series_id=spec.code, realtime_start=start, realtime_end=end), 'seriess')
        meta_rows = metadata['seriess']
        if not isinstance(meta_rows, list) or not meta_rows:
            raise ProviderError('vintage_metadata_missing')
        for meta in meta_rows:
            if (
                not isinstance(meta, dict)
                or meta.get('id') != spec.code
                or meta.get('frequency_short') != spec.frequency
                or not meta.get('units')
                or not meta.get('seasonal_adjustment_short')
            ):
                raise ProviderError('invalid_fred_metadata')
            if dt.date.fromisoformat(meta['realtime_start']) > dt.date.fromisoformat(meta['realtime_end']):
                raise ProviderError('invalid_fred_metadata')
        self.metadata_versions[spec.code] = digest(meta_rows)

        # 2) 보관판 날짜 전체 목록. 페이지가 빠지면 부분 성공을 완료로 치지 않는다.
        dates = []
        offset = 0
        while True:
            cancel()
            # Some empty recent windows return a provider 500 instead of an empty list.
            # Enumerate the stable full range, then select the incremental window locally.
            payload, _ = self.fred(
                'series/vintagedates',
                dict(series_id=spec.code, realtime_start=start, realtime_end=end, limit=1000, offset=offset),
                'vintage_dates',
            )
            page = payload['vintage_dates']
            if not isinstance(page, list):
                raise ProviderError('invalid_vintage_dates')
            dates.extend(page)
            offset += len(page)
            if offset >= int(payload.get('count', len(dates))):
                break
            if not page:
                raise ProviderError('incomplete_vintage_page')
        if any(not isinstance(d, str) for d in dates) or dates != sorted(set(dates)):
            raise ProviderError('invalid_vintage_dates')
        if any(not start <= dt.date.fromisoformat(d).isoformat() <= end for d in dates):
            raise ProviderError('invalid_vintage_dates')
        if not dates:
            raise ProviderError('vintage_unavailable')
        first_vintage = dates[0]
        metadata_dates = sorted({
            m['realtime_start']
            for m in meta_rows
            if max(start, since) <= m['realtime_start'] <= end and m['realtime_start'] > first_vintage
        })
        dates = [day for day in dates if day >= since]

        # 3) 일간·주간 계열은 보관판 열이 너무 넓어져 기간 단위 장형 조회로 읽는다.
        if spec.frequency in {'D', 'W'}:
            yield from self._fred_interval_pages(spec, start, end, since, sorted(set(dates + metadata_dates)), meta_rows, cursor, cancel)
            return

        # 4) 월·분기 계열은 보관판 100개씩 신규·개정분(output_type=3)을 읽는다.
        chunk = len(dates) if cursor.get('phase') == 'fred_metadata' else int(cursor.get('chunk', 0))
        offset = int(cursor.get('offset', 0)) if cursor.get('phase') != 'fred_metadata' else 0
        batch_size = 100
        while chunk < len(dates):
            cancel()
            batch = dates[chunk:chunk + batch_size]
            params = dict(series_id=spec.code, observation_start=start, output_type=3, vintage_dates=','.join(batch), limit=10000, offset=offset)
            payload, fetched = self.fred('series/observations', params, 'observations')
            points = []
            for row in parse_fred_vintages(payload, spec.code):
                if row['vintageDate'] not in batch or row['period'] < start:
                    raise ProviderError('fred_range_mismatch')
                meta = next((m for m in meta_rows if m['realtime_start'] <= row['vintageDate'] <= m['realtime_end']), None)
                if meta is None:
                    raise ProviderError('vintage_metadata_missing')
                points.append({**row, 'seriesId': spec.id, 'availabilityBasis': 'provider_vintage', 'fetchedAt': fetched, 'metadata': fred_metadata(meta)})
            size = len(payload['observations'])
            total = int(payload['count'])
            if total < 0 or offset + size > total:
                raise ProviderError('invalid_observation_count')
            if not size and offset < total:
                raise ProviderError('incomplete_observation_page')
            offset += size
            if offset >= total:
                chunk += batch_size
                offset = 0
            yield points, {'phase': 'fred', 'end': end, 'since': since, 'chunk': chunk, 'offset': offset}, fetched

        # Metadata can change without a value changing. Ask for that day's official
        # snapshot so an unchanged number is never assigned a later definition early.
        index = int(cursor.get('metadataIndex', 0))
        offset = int(cursor.get('offset', 0)) if cursor.get('phase') == 'fred_metadata' else 0
        while index < len(metadata_dates):
            cancel()
            day = metadata_dates[index]
            payload, fetched = self.fred(
                'series/observations',
                dict(series_id=spec.code, observation_start=start, output_type=1, realtime_start=day, realtime_end=day, limit=10000, offset=offset),
                'observations',
            )
            meta = next(m for m in meta_rows if m['realtime_start'] <= day <= m['realtime_end'])
            points = []
            for row in payload['observations']:
                if row['realtime_start'] != day or row['date'] < start:
                    raise ProviderError('fred_range_mismatch')
                points.append({
                    'seriesId': spec.id,
                    'period': row['date'],
                    'value': row['value'],
                    'vintageDate': day,
                    'availabilityBasis': 'provider_vintage',
                    'fetchedAt': fetched,
                    'metadata': fred_metadata(meta),
                })
            size = len(payload['observations'])
            total = int(payload['count'])
            if offset + size > total or (not size and offset < total):
                raise ProviderError('incomplete_observation_page')
            offset += size
            if offset >= total:
                index += 1
                offset = 0
            yield points, {'phase': 'fred_metadata', 'end': end, 'since': since, 'metadataIndex': index, 'offset': offset}, fetched

    def _fred_interval_pages(self, spec, start, end, since, dates, meta_rows, cursor, cancel):
        # Daily/weekly long-form intervals avoid a large sparse vintage-column expansion.
        # Two-year windows stay below FRED's 2,000 JSON vintage limit.
        if not dates:
            return
        window = cursor.get('window') or max(since, dates[0])
        offset = int(cursor.get('offset', 0))
        while window <= end:
            upper = min(end, f'{int(window[:4]) + 1}-12-31')
            # 창 안에서 메타데이터가 바뀌면 그 전날에서 창을 끊어 한 창에 정의가 섞이지 않게 한다.
            boundaries = [m['realtime_start'] for m in meta_rows if window < m['realtime_start'] <= upper]
            if boundaries:
                upper = (dt.date.fromisoformat(min(boundaries)) - dt.timedelta(days=1)).isoformat()
            cancel()
            params = dict(series_id=spec.code, observation_start=start, output_type=1, realtime_start=window, realtime_end=upper, limit=10000, offset=offset)
            payload, fetched = self.fred('series/observations', params, 'observations')
            points = []
            for r in payload['observations']:
                vintage = dt.date.fromisoformat(r['realtime_start']).isoformat()
                period = dt.date.fromisoformat(r['date']).isoformat()
                if not window <= vintage <= upper or period < start:
                    raise ProviderError('fred_range_mismatch')
                meta = next((m for m in meta_rows if m['realtime_start'] <= vintage <= m['realtime_end']), None)
                if meta is None:
                    raise ProviderError('vintage_metadata_missing')
                points.append({
                    'seriesId': spec.id,
                    'period': period,
                    'value': r['value'],
                    'vintageDate': vintage,
                    'availabilityBasis': 'provider_vintage',
                    'fetchedAt': fetched,
                    'metadata': fred_metadata(meta),
                })
            size = len(payload['observations'])
            total = int(payload['count'])
            if total < 0 or offset + size > total:
                raise ProviderError('invalid_observation_count')
            if not size and offset < total:
                raise ProviderError('incomplete_observation_page')
            offset += size
            if offset >= total:
                window = (dt.date.fromisoformat(upper) + dt.timedelta(days=1)).isoformat()
                offset = 0
            yield points, {'phase': 'fred', 'end': end, 'since': since, 'window': window, 'offset': offset}, fetched

    def ecos_pages(self, spec: Series, start: str, *, cursor=None, cancel=lambda: None):
        # ECOS는 과거 발표판을 주지 않는다. 받을 때마다 현재 값을 local_observed로 기록한다.
        if not self.keys['ecos']:
            raise ProviderError('not_connected')
        cursor = cursor or {}
        end = cursor.get('end') or dt.datetime.now(ZoneInfo(spec.timezone)).date().isoformat()

        def provider_date(day):
            date = dt.date.fromisoformat(day)
            return f'{date.year}Q{(date.month - 1) // 3 + 1}' if spec.frequency == 'Q' else date.strftime('%Y%m' if spec.frequency == 'M' else '%Y%m%d')

        offset = int(cursor.get('offset', 1))
        total = cursor.get('total')
        # 마지막 페이지 값과 전체 개수를 함께 저장한다. 완료 상태를 쓰기 직전에
        # 중단되어도 범위 밖 페이지를 요청하지 않고 수집을 마무리할 수 있다.
        if total is not None and offset > int(total):
            return
        if total is None and offset > 1:
            # 이전 버전 cursor에는 전체 개수가 없다. 첫 페이지부터 멱등 재수집한다.
            offset = 1
        while True:
            cancel()
            params = {
                'series': spec.id,
                'table': spec.code,
                'frequency': spec.frequency,
                'items': spec.items,
                'start': start,
                'end': end,
                'offset': offset,
                'limit': 1000,
                'metadataVersion': digest(spec.public()),
            }
            parts = [self.keys['ecos'], 'json', 'kr', str(offset), str(offset + 999), spec.code, spec.frequency, provider_date(start), provider_date(end), *spec.items]
            url = 'https://ecos.bok.or.kr/api/StatisticSearch/' + '/'.join(urllib.parse.quote(str(p), safe='') for p in parts)
            payload, fetched = self._fetch('ecos', 'observations', params, url, 'StatisticSearch')
            body = payload['StatisticSearch']
            page = body.get('row')
            total = int(body.get('list_total_count', 0))
            if not isinstance(page, list) or not page:
                raise ProviderError('empty_ecos_page')
            if offset + len(page) - 1 > total:
                raise ProviderError('invalid_ecos_count')
            points = []
            for r in page:
                # 통계표·항목 코드가 요청과 정확히 같아야 한다. 다른 차원 값은 섞지 않는다.
                if r.get('STAT_CODE') != spec.code or any(str(r.get(f'ITEM_CODE{i + 1}', '')) != item for i, item in enumerate(spec.items)):
                    raise ProviderError('ecos_dimension_mismatch')
                if any(r.get(f'ITEM_CODE{i}') not in (None, '', '?') for i in range(len(spec.items) + 1, 5)):
                    raise ProviderError('ecos_dimension_mismatch')
                period = ecos_period(r['TIME'], spec.frequency)
                if not start <= period <= end:
                    raise ProviderError('ecos_range_mismatch')
                meta = {
                    'unit': r['UNIT_NAME'],
                    'frequency': spec.frequency,
                    'adjustment': spec.adjustment,
                    'providerSeries': spec.code,
                    'dimensions': list(spec.items),
                    'definitionVersion': 'ecos-' + spec.code,
                }
                points.append({'seriesId': spec.id, 'period': period, 'value': r['DATA_VALUE'], 'availabilityBasis': 'local_observed', 'fetchedAt': fetched, 'metadata': meta})
            offset += len(page)
            yield points, {'phase': 'ecos', 'end': end, 'offset': offset, 'total': total}, fetched
            if offset > total:
                break
