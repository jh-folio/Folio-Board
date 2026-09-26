"""The sixteen approved indicators (seventeen provider series). No economic verdicts."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Series:
    id: str
    label: str
    market: str
    axis: str
    frequency: str
    unit: str
    adjustment: str
    provider: str
    code: str
    items: tuple[str, ...] = ()
    stage: str = 'coincident'
    transform: str = 'level'
    max_age_days: int = 60
    visible: bool = True

    @property
    def timezone(self):
        return 'America/Chicago' if self.market == 'US' else 'Asia/Seoul'

    @property
    def source_url(self):
        return f'https://fred.stlouisfed.org/series/{self.code}' if self.provider == 'fred' else 'https://ecos.bok.or.kr/'

    def public(self):
        return {**asdict(self), 'sourceUrl': self.source_url, 'timezone': self.timezone,
                'methodVersion': 'macro-1', 'replaySupported': self.market == 'US'}


SERIES = (
    Series('GDPC1','실질 GDP','US','growth','Q','Billions of Chained 2017 Dollars','SAAR','fred','GDPC1',transform='qoq',max_age_days=150),
    Series('INDPRO','산업생산','US','growth','M','Index 2017=100','SA','fred','INDPRO',transform='mom'),
    Series('UNRATE','실업률','US','growth','M','Percent','SA','fred','UNRATE',stage='lagging',transform='difference'),
    Series('CPIAUCSL','소비자물가지수 (CPI)','US','inflation','M','Index 1982-1984=100','SA','fred','CPIAUCSL',transform='yoy'),
    Series('PCEPILFE','근원 PCE 물가지수','US','inflation','M','Index 2017=100','SA','fred','PCEPILFE',transform='yoy'),
    Series('DFF','실효 연방기금금리','US','financial_conditions','D','Percent','NSA','fred','DFF',transform='difference',max_age_days=7),
    Series('NFCI','Chicago Fed 금융여건','US','financial_conditions','W','Index','NSA','fred','NFCI',max_age_days=21),
    Series('STLFSI4','St. Louis Fed 금융스트레스','US','stress_vulnerability','W','Index','NSA','fred','STLFSI4',max_age_days=21),
    Series('KR_GDP','실질 GDP','KR','growth','Q','십억원','SA','ecos','200Y104',('1400',),transform='qoq',max_age_days=150),
    Series('KR_IP','전산업생산 (농림어업 제외)','KR','growth','M','2020=100','SA','ecos','901Y033',('A00','2'),transform='mom'),
    Series('KR_UNRATE','실업률','KR','growth','M','%','SA','ecos','901Y027',('I61BC','I28B'),stage='lagging',transform='difference'),
    Series('KR_CPI','소비자물가지수 (CPI)','KR','inflation','M','2020=100','unknown','ecos','901Y009',('0',),transform='yoy'),
    Series('KR_RATE','한국은행 기준금리','KR','financial_conditions','D','연%','NSA','ecos','722Y001',('0101000',),transform='difference',max_age_days=7),
    Series('KR_USDKRW','원/달러 매매기준율','KR','financial_conditions','D','원','NSA','ecos','731Y001',('0000001',),max_age_days=7),
    Series('KR_CORP','회사채 3년 AA-','KR','stress_vulnerability','D','연%','NSA','ecos','817Y002',('010300000',),max_age_days=7,visible=False),
    Series('KR_GOV','국고채 3년','KR','stress_vulnerability','D','연%','NSA','ecos','817Y002',('010200000',),max_age_days=7,visible=False),
    Series('KR_CREDIT','가계신용','KR','stress_vulnerability','Q','십억원','NSA','ecos','151Y001',('1000000',),stage='structural',transform='yoy',max_age_days=180),
)
BY_ID = {s.id:s for s in SERIES}
AXES = {'growth':'경기','inflation':'물가','financial_conditions':'금융여건','stress_vulnerability':'위험'}


def series(series_id: str) -> Series:
    try:
        return BY_ID[series_id]
    except KeyError:
        raise ValueError('unknown_macro_series') from None


def indicators(market: str):
    if market not in {'US','KR'}:
        raise ValueError('unsupported_macro_market')
    result=[s.public() for s in SERIES if s.market==market and s.visible]
    if market=='KR':
        result.insert(-1,{**BY_ID['KR_CORP'].public(),'id':'KR_SPREAD','label':'회사채 AA- − 국고채 3년','unit':'%p','transform':'spread','visible':True,'inputs':['KR_CORP','KR_GOV']})
    return result
