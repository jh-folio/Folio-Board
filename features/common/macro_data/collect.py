from __future__ import annotations

import datetime as dt
from pathlib import Path

from features.common.data_reliability.fetch_runtime import ProviderFetchRuntime
from features.llm_settings.client import bok_api_key,fred_api_key
from .providers import OfficialReader,ProviderError
from .registry import SERIES
from .store import MacroStore
from .cache_policy import prune_owned_cache


def collect(data_root:Path,*,start='2000-01-01',cancel=lambda:None,reader=None,selected=None):
    dt.date.fromisoformat(start)
    store=MacroStore(Path(data_root)/'market-memory.sqlite3')
    runtime=None
    if reader is None:
        runtime=ProviderFetchRuntime(Path(data_root)/'macro-cache')
        reader=OfficialReader(runtime,fred_key=fred_api_key(),ecos_key=bok_api_key())
    results=[]
    try:
        for spec in SERIES:
            if selected is not None and spec.id not in selected:continue
            cancel();state=store.state(spec.id);saved=state.get('cursor',{})
            cursor=saved if saved.get('phase') in {'fred','fred_metadata','ecos'} else {}
            if saved.get('start',start)!=start:cursor={}
            if not cursor and saved.get('start')==start and spec.provider=='fred' and state.get('last_success'):
                # Re-read a small vintage overlap. Same-vintage corrections become visible conflicts.
                cursor={'since':max(start,(dt.date.fromisoformat(state['last_success'][:10])-dt.timedelta(days=7)).isoformat())}
            count=0
            try:
                pages=reader.fred_pages(spec,start,cursor=cursor,cancel=cancel) if spec.provider=='fred' else reader.ecos_pages(spec,start,cursor=cursor,cancel=cancel)
                for rows,next_cursor,at in pages:
                    cancel()
                    count+=store.ingest(spec.id,rows,cursor={**next_cursor,'start':start},at=at)
                cancel()
                store.set_state(spec.id,'ok',cursor={'phase':'complete','start':start})
                results.append({'seriesId':spec.id,'status':'ok','inserted':count})
            except (ProviderError, ValueError, KeyError, TypeError) as exc:
                code=str(exc) if str(exc) in {'not_connected','vintage_metadata_missing','ecos_dimension_mismatch','empty_ecos_page'} else 'provider_failed'
                store.set_state(spec.id,'not_connected' if code=='not_connected' else 'provider_failed',error=code)
                results.append({'seriesId':spec.id,'status':code,'inserted':count})
        return {'ok':all(r['status']=='ok' for r in results),'series':results,'agentCalled':False}
    finally:
        if runtime:
            runtime.pool.shutdown(wait=True,cancel_futures=True)
            prune_owned_cache(Path(data_root)/'macro-cache')
