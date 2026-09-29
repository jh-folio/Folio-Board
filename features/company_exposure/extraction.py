"""Conservative extraction from the existing company's scored official passages.

No keyword co-mention is used to infer another company's exposure. Direction is
unclear unless the cited sentence itself explicitly states the signed effect.
"""
import re

from features.common.macro_data.schema import digest

FACTORS = {
    'interest_rate': r'interest rates?|금리|이자율',
    'fx': r'foreign currency(?! controls)|foreign exchange (?:rates?|risks?|fluctuations)|exchange rates?|환율|외환위험',
    'commodity_input': r'raw material|commodity (?:prices?|costs?)|원자재|원재료 가격',
    'freight': r'freight|shipping costs?|운임|운송비',
    'regional_demand': r'regional demand|geographic(?:al)? (?:revenue|sales)|지역별 매출|지역 수요',
    'customer_capex': r'customers?.{0,25}capital expenditur|고객.{0,15}설비투자',
    'inventory_cycle': r'inventory|재고',
    'credit_access': r'access to (?:credit|capital)|credit availability|자금조달|신용공여',
    'policy_specific': r'export controls?|tariffs?|수출통제|관세',
}
DIRECTIONS = {'benefits_from_rise', 'hurt_by_rise', 'two_sided', 'unclear'}
LIMITATIONS = ['공시가 밝힌 노출이며 기업 전체의 순효과가 아닙니다.',
               '헤지 규모·전달 시차·상쇄 경로를 확인하지 못한 항목은 별도로 판단할 수 없습니다.',
               '선별 공시 문단 밖의 노출은 누락될 수 있습니다.']


def direction(quote, factor):
    # Only narrow, explicit effect statements. Negation or multiple factors
    # requires human interpretation, so never infer a signed net effect.
    if re.search(r'\b(?:not|no|insignificant|immaterial)\b|않|없', quote, re.I):
        return 'unclear'
    if sum(bool(re.search(pattern, quote, re.I)) for pattern in FACTORS.values()) != 1:
        return 'unclear'
    phrase = FACTORS[factor]
    rise = rf'(?:higher|rising|increases? in)\s+(?:market\s+)?(?:{phrase})'
    negative = bool(re.search(rf'{rise}.{{0,240}}(?:increase|raise)\s+(?:(?:our|the company.s|the corporation.s|the group.s|the)\s+)?(?:interest expense|borrowing costs|costs?|cost of capital)', quote, re.I))
    positive = bool(re.search(rf'{rise}.{{0,240}}(?:increase|improve)\s+(?:our\s+)?(?:net interest income|revenue|revenues)', quote, re.I))
    if negative and positive:
        return 'two_sided'
    if negative:
        return 'hurt_by_rise'
    if positive:
        return 'benefits_from_rise'
    if re.search(rf'(?:{phrase}).{{0,12}}상승.{{0,30}}(?:이자비용|조달비용).{{0,12}}증가', quote):
        return 'hurt_by_rise'
    return 'unclear'


def sentences(original):
    start = 0
    for boundary in re.finditer(r'[.!?]\s+(?=[A-Za-z0-9가-힣])', original):
        end = boundary.start() + 1
        prefix = original[:end]
        if re.search(r'(?:\b[A-Z]\.){2,}$|\b(?:Inc|Corp|Co|Ltd|Mr|Ms|Dr)\.$', prefix, re.I):
            continue
        yield original[start:end].strip()
        start = boundary.end()
    if start < len(original):
        yield original[start:].strip()


def explicit_exposure(quote, factor):
    # Accounting inventory balances, trading inventory and generic third-party
    # access to capital are not the issuer's inventory-cycle/credit exposure.
    if not re.search(r'\b(?:our|we|company|corporation|group|firm)\b|당사|회사|연결기업|그룹', quote, re.I):
        return False
    if factor == 'fx':
        # A named tax rule is not an exchange-rate exposure. Remove its name
        # before requiring an actual FX risk/effect relationship in a clause.
        if re.search(r'effective tax rate|실효세율', quote, re.I) and not re.search(
                r'(?:exchange rates?|환율).{0,40}(?:fluctuat|strengthen|weaken|변동|상승|하락)|'
                r'(?:fluctuat|strengthen|weaken).{0,40}(?:exchange rates?|currenc)', quote, re.I):
            return False
        exposure_text = re.sub(r'foreign currency (?:loss |gain )?(?:regulations?|rules?)', '', quote, flags=re.I)
        return any(
            re.search(FACTORS['fx'], clause, re.I)
            and re.search(r'risk|expos|sensitiv|hedg|derivative|fluctuat|affect|impact|cost|expense|income|revenue|위험|노출|영향|변동|비용|매출', clause, re.I)
            for clause in re.split(r';|\bbut\b|\bwhereas\b', exposure_text, flags=re.I)
        )
    if factor == 'inventory_cycle':
        return bool(re.search(r'demand|product transitions|고객|수요|재고.{0,20}(?:폐기|평가손실)', quote, re.I))
    if factor == 'commodity_input':
        return bool(re.search(r'raw materials?|fuel|purchase|cost fluctuations|원재료|원자재.{0,20}비용', quote, re.I))
    if factor == 'policy_specific':
        # Utility rate schedules are also called tariffs; they are not import
        # duties. A bare tariff mention does not establish trade exposure.
        return bool(re.search(r'export controls?|수출통제|관세|\b(?:trade|imports?|exports?|customs|duties)\b', quote, re.I))
    return bool(re.search(r'risk|expos|sensitiv|hedg|derivative|cost|expense|income|revenue|impact|affect|rely|depend|uncertain|위험|노출|영향|비용|금리|환율', quote, re.I))


def passages(materials, market):
    for key in ('rankedFiling', 'rankedQuarterlyFiling'):
        filing = materials.get(key) or {}
        if not filing.get('ok'):
            continue
        meta = filing.get('metadata') or {}
        form = filing.get('form') or meta.get('form') or ''
        for row in filing.get('paragraphs') or []:
            if not isinstance(row, dict):
                continue
            item = str(row.get('item') or '')
            body = str(row.get('text') or '')
            row_form = row.get('form') or form
            if market == 'US' and not (row_form == '10-Q' or row_form == '10-K' and item in {'1A', '7A', '8'}):
                continue
            if market == 'KR' and not re.search(r'재무\s*위험|금융\s*위험|시장\s*위험|위험\s*관리|financial risk management|market risk', body, re.I):
                continue
            own_source = str(row.get('source') or '')
            ref = {'url': row.get('url') or (own_source if own_source.startswith('https://') else '') or (meta.get('url') if not own_source else '') or '',
                   'path': row.get('path') or (own_source if own_source and not own_source.startswith('https://') else '') or (meta.get('path') if not own_source else '') or '',
                   'form': row_form, 'section': item,
                   'date': row.get('date') or meta.get('filingDate') or ''}
            if body and (ref['url'] or ref['path']):
                yield body, ref


def validate_item(item, original):
    if item.get('factor') not in FACTORS or item.get('direction') not in DIRECTIONS:
        raise ValueError('invalid_exposure_enum')
    if item.get('layer') != 'canonical' or item.get('magnitudeBasis') not in {'qualitative_only', 'company_quantified'}:
        raise ValueError('invalid_exposure_layer_or_magnitude')
    quote = item.get('quote')
    if not isinstance(quote, str) or not quote.strip() or quote not in original:
        raise ValueError('exposure_quote_not_in_source')
    if not item.get('sourceRef') or not (item['sourceRef'].get('url') or item['sourceRef'].get('path')):
        raise ValueError('exposure_source_required')
    quantified = item.get('magnitudeQuote')
    if item['magnitudeBasis'] == 'company_quantified':
        if not isinstance(quantified, str) or quantified not in quote or not re.search(r'\d', quantified):
            raise ValueError('exposure_quantification_not_in_quote')
    elif quantified:
        raise ValueError('qualitative_exposure_cannot_quantify')
    return item


def extract(company, materials, *, personal_reason=None):
    # personal_reason intentionally never participates in selection or output.
    market = company.get('market', 'US')
    if market not in {'US', 'KR'}:
        raise ValueError('unsupported_exposure_market')
    ticker = str(company.get('ticker') or '').strip().upper()
    if not ticker:
        raise ValueError('exposure_ticker_required')
    items = {}
    source_count = 0
    omitted_fragments = 0
    for original, ref in passages(materials, market):
        source_count += 1
        # Keep exact source text; do not rewrite or synthesize financial numbers.
        for quote in sentences(original):
            if len(quote) < 30 or len(quote) > 1200 or quote[-1:] not in '.!?' or (quote and quote[0].isascii() and not quote[0].isupper()):
                omitted_fragments += 1
                continue
            for factor, pattern in FACTORS.items():
                if not re.search(pattern, quote, re.I):
                    continue
                if not explicit_exposure(quote, factor):
                    continue
                item = {'factor': factor, 'direction': direction(quote, factor),
                        'magnitudeBasis': 'qualitative_only', 'quote': quote,
                        'sourceRef': ref, 'sourceRefs': [ref], 'layer': 'canonical'}
                # Do not turn arbitrary figures (dates, debt balance, segment
                # revenue) into a quantified sensitivity. Only explicitly
                # supplied and reviewed quantified items can use that basis.
                validate_item(item, original)
                # Only identical source sentences merge; similar wording must
                # not hide a changed hedge, period, qualifier or numerical value.
                key = (factor, item['direction'], quote)
                if key not in items:
                    items[key] = item
                elif ref not in items[key]['sourceRefs']:
                    items[key]['sourceRefs'].append(ref)
    for item in items.values():
        item['id'] = 'exposure-' + digest(item)
    result = {'schemaVersion': 'company-exposure-1', 'extractionVersion': 'company-exposure-rules-2', 'ticker': ticker, 'market': market,
              'layer': 'canonical', 'promotion': 'shadow',
              'items': sorted(items.values(), key=lambda x: x['id']),
              'coverage': {'scoredPassages': source_count, 'exposures': len(items), 'omittedFragments': omitted_fragments},
              'limitations': LIMITATIONS,
              'dataGaps': (['scored_passage_extraction_not_exhaustive'] if source_count else ['official_filing_passages_unavailable']) + (['incomplete_source_fragments_omitted'] if omitted_fragments else [])}
    result['inputFingerprint'] = digest(result)
    result['profileId'] = 'exposure-profile-' + result['inputFingerprint']
    return result
