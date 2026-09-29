"""Explicit refresh reuses company-analysis sources. Reads never collect."""
import datetime as dt
import re
from pathlib import Path

from features.common.macro_data.store import MacroStore
from features.macro_state.replay import Replay
from .extraction import extract
from .interpretation import interpret
from .store import ExposureStore


def ticker_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9.^-]{1,20}', value):
        raise ValueError('invalid_exposure_ticker')
    return value.upper()


def read(root, ticker, *, now=None):
    ticker = ticker_value(ticker)
    profile = ExposureStore(root).get(ticker)
    if profile is None:
        return {'profile': None, 'interpretation': None, 'status': 'not_collected'}
    as_of = (now or dt.datetime.now(dt.timezone.utc)).isoformat()
    keys = ['DFF', 'NFCI'] if profile['market'] == 'US' else ['KR_RATE', 'KR_USDKRW']
    path = Path(root) / 'market-memory.sqlite3'
    with MacroStore(path).read() as conn:
        exists = conn is not None
    rows = Replay(path, keys).select(as_of, observation_end=as_of[:10]) if exists else []
    return {'profile': profile, 'interpretation': interpret(profile, rows, as_of), 'status': 'saved'}


def collect_materials(root, company, *, cancel=lambda: None):
    from features.company_analysis.sec_filings import ranked_annual_report_paragraphs, ranked_quarterly_report_paragraphs
    from features.company_analysis.service import build_filing_item_context, company_analysis_doc_score, company_direct_relevance, is_sec_filing_doc
    from features.common.research_library.indexing.research_index import load_documents_from_db

    cancel()
    annual = {}; quarterly = {}
    if company['market'] == 'US':
        annual = ranked_annual_report_paragraphs(company, Path(root) / 'sec-cache', max_paragraphs=14)
        cancel()
        quarterly = ranked_quarterly_report_paragraphs(company, Path(root) / 'sec-cache', max_paragraphs=8)
    if not annual.get('ok'):
        path = Path(root) / 'research-index.sqlite3'
        docs = load_documents_from_db(path) if path.exists() else []
        scored = [company_analysis_doc_score(d, company, company['ticker']) for d in docs
                  if not d.get('generated_by') and d.get('reuseAsEvidence') is not False
                  and d.get('source_layer') not in {'hypothesis', 'primary_processed'}
                  and is_sec_filing_doc(d) and company_direct_relevance(d, company, company['ticker'])[0] >= 15]
        scored.sort(key=lambda d: (d.get('analysisScore', 0), d.get('date', '')), reverse=True)
        _, _, paragraphs = build_filing_item_context(scored, financial_risk_only=company['market'] == 'KR')
        annual = {'ok': bool(paragraphs), 'paragraphs': paragraphs, 'metadata': {}}
    cancel()
    return {'rankedFiling': annual, 'rankedQuarterlyFiling': quarterly}


def refresh(root, ticker, *, job_id=None, progress=None):
    from features.common.company_lookup import infer_requested_company
    from features.common.jobs import get_shared_job

    def cancel():
        if job_id:
            job = get_shared_job(job_id)
            if job is None or job.status.value in {'cancel_requested', 'cancelled', 'failed_restart'}:
                raise RuntimeError('exposure_cancelled')

    ticker = ticker_value(ticker)
    cancel()
    company = infer_requested_company(ticker, [])
    if not company or ticker_value(company.get('ticker', '')) != ticker:
        raise ValueError('exposure_company_unresolved')
    company['market'] = 'KR' if re.fullmatch(r'\d{6}', ticker) else 'US'
    if progress:
        progress(message='공식 공시의 노출 근거를 확인하고 있습니다.')
    materials = collect_materials(root, company, cancel=cancel)
    profile = extract(company, materials)
    cancel()
    if job_id:
        from features.common.macro_job_commit import commit
        from features.common.macro_data.schema import digest
        commit(root, job_id, [{'type': 'company_exposure', 'id': profile['profileId'], 'hash': digest(profile)}],
               lambda: ExposureStore(root).save(profile, materials=materials), saved_count=1)
    else:
        ExposureStore(root).save(profile, materials=materials)
    return {'profileId': profile['profileId'], 'ticker': ticker, 'savedCount': 1,
            'exposureCount': len(profile['items']), 'dataGaps': profile['dataGaps']}
