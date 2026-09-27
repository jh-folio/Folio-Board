# features/common

여러 화면과 기능이 공유하는 자료 기반, 품질/근거성 레이어, 시장 데이터, Python 유틸리티 모음입니다.

## 주요 모듈

| 파일 | 역할 |
| --- | --- |
| `workspace.py` | 사용자 자료(`data`/`research-inbox`/`config`)가 어디 있는지 결정하는 단일 출처 |
| `workspace_service.py` | 자료 위치 payload와 옮기기(복사·검증·표지) |
| `taxonomy.py` | 태그 canonical 어휘 단일 정의 |
| `markets.py` | `US | KR | EUROPE | JP | GLOBAL | UNKNOWN` 시장·브리핑 scope 단일 계약 |
| `instruments/` | 거래소·suffix·공식 식별자를 보존하는 cross-market instrument identity 계약 |
| `company_lookup.py` | 기업명/티커 정규화, SEC CIK 조회, 마스터 데이터 |
| `sector_cache.py` | 섹터를 담지 않는 출처(SEC `company_tickers.json`, 일본·유럽 구성종목)로 해석된 회사의 섹터를 yfinance로 채우고 `data/sector-cache.json`에 90일 캐시 |
| `utils.py` | 텍스트 정규화, JSON 읽기/쓰기, 날짜 유틸 |
| `dataframe_ops.py` | Polars 기반 필터링, 정렬, 집계 |
| `market_calendar.py` | 브리핑 날짜 계산, 시장별 세션 기술자(`marketSessions`) |
| `exchange_holidays.py` | LSE/Xetra/Euronext/Borsa Italiana/BME/JPX 연간 휴장일 표와 거래소별 개장 판정 |
| `market_data/providers.py` | provider 기반 시장 데이터 인터페이스와 한국장 수치 조회 |
| `macro_data/` | 공식 거시 시계열 registry·FRED/ECOS 수집·수정판 원장·보수적 과거 조회. [계약](macro_data/README.md) |
| `market_data/europe_core_universe.py` | FTSE 100+DAX+CAC 40+AEX 합성 유럽 히트맵 universe와 EUR 환산 |
| `market_data/nikkei225_universe.py` | 닛케이 225 히트맵 universe |
| `research_library/` | 자료 폴더 계약, RSS 수집, 증분 인덱싱, 하이브리드 검색 |
| `research_schema/` | checkpoint/evidence/sourceLedger/dataGap 공통 스키마 |
| `research_quality/` | 저장 산출물의 source grounding, hallucination risk, personal bias risk 평가 |
| `quality_generation/` | 생성 전 품질 목표, preflight, 약한 섹션 1회 보강, telemetry |
| `data_reliability/` | 공식자료 우선순위, provider 상태, 한국 수동 데이터 보강 경로 |
| `diagnostics/` | 실행별 bounded privacy-safe diagnostic record, OS writer lease, SharedJob/direct producer observer와 headless safe projection (0.6 L1a/L1b/L1c; UI 없음) |
| `execution_result.py` | provider 본문/response ID를 메모리에만 두는 additive structured execution facts; 기존 tuple/string API는 변경하지 않음 |
| `self_reference.py` | `generated_by` 자기참조 마커(`GENERATED_BY_MARKER`)와 신·구 이름 별칭 집합(`SELF_GENERATED_MARKER_ALIASES`) 단일 출처. Obsidian/Notion export writer가 값을 쓸 때 쓴다 |

## workspace.py / workspace_service.py

사용자 자료가 어디 있는지 한 곳에서 정합니다. `ROOT / "data"`를 새로 쓰지 말고 `data_dir()`, `research_inbox_dir()`, `config_dir()`를 부릅니다.

배포 zip은 `FolioOS-v0.5.0/`처럼 **버전이 박힌 폴더**로 풀리고 `data/`는 빈 채로 나옵니다. 그래서 새 버전을 받으면 새 폴더에 빈 워크스페이스가 생기고 이전 자료는 옛 폴더에 남습니다(실측 22,715개·914MB). 코드와 자료가 한 폴더에 섞여 있는 것이 원인입니다.

찾는 순서:

1. `FOLIO_HOME` 환경변수 — 화면에 노출하지 않는 탈출구. 이 값이 있으면 설정 화면의 옮기기를 막습니다(표지를 써도 다음 시작에서 환경변수가 이기므로, 옮겼다고 말하면 거짓말이 됩니다).
2. 앱 폴더의 `workspace.json` 표지 — 옮기기가 성공했을 때만 생깁니다. 배포 zip에는 없습니다.
3. 앱 폴더 `data/`에 **파일이 있으면** 앱 폴더.
4. `~/Documents/FolioBoard`(새 이름) 또는 `~/Documents/FolioOS`(구 이름, 새 이름에 자료가 없을 때만)에 자료가 있으면 거기. 옮기기의 목적지는 새 이름 하나뿐이지만, 이 탐색만은 구 이름을 계속 본다 — 옮겨 둔 사용자가 새 버전을 풀었을 때 자료를 잃지 않기 위해서다.
5. 아니면 앱 폴더 — 기본값.

**기본값은 앱 폴더입니다.** 옮기는 것은 선택이며 아무것도 새로 만들지 않습니다.

- 폴더 존재가 아니라 **파일 유무**로 판정합니다. 배포 zip이 빈 폴더를 만들어 두기 때문에, 존재만 보면 갓 푼 설치도 "쓰던 워크스페이스"로 오인합니다.
- 표지(2번)가 필요한 이유는 옮기기가 **원본을 지우지 않기** 때문입니다. 표지가 없으면 3번이 걸려 방금 옮긴 곳이 아니라 옛 자료를 계속 씁니다.
- 판정은 프로세스당 1회 캐시합니다. 모듈 상수 수십 곳이 import 시점에 읽으므로, 캐시가 없으면 매번 디렉터리를 훑고 import 도중 `data/`가 생기면 앞뒤 모듈이 서로 다른 워크스페이스를 가리킵니다. 옮긴 뒤에는 재시작이 필요하며 화면이 그렇게 안내합니다.
- 문서 폴더는 Windows에서 레지스트리(`User Shell Folders\Personal`)로 읽습니다. OneDrive로 리디렉션되면 `~/Documents`가 실제 문서 폴더가 아닙니다. 목적지가 OneDrive 아래면 막지 않고 경고만 합니다(700MB 인덱스가 저장마다 업로드되고 두 PC에서 충돌 사본이 생깁니다).
- 옮기기는 복사 → 파일별 크기 검증 → 표지 순입니다. 검증에 실패하면 표지를 쓰지 않아 앱이 계속 원본을 씁니다. 목적지에 이미 자료가 있으면 `merge` 없이 진행하지 않습니다 — 합치기라서 목적지에만 있던 파일이 남고, 앱 폴더로 되돌릴 때 예전에 지운 보고서가 되살아납니다.
- 목적지는 `documents`/`app` 둘뿐입니다. 임의 경로를 받지 않습니다.
- API: `GET /api/workspace`, `POST /api/workspace/move`, `POST /api/workspace/reveal`.

## market_calendar.py / exchange_holidays.py

`briefing_market_windows()`는 기존 `us*`/`kr*` 키를 그대로 두고, 시장별 세션을 `marketSessions.{us,kr,europe,jp}`에 따로 담습니다. 기존 소비자가 읽는 모양을 바꾸지 않기 위해서입니다.

시장마다 한국시간 기준 성격이 달라 세션 기준일 규칙이 다릅니다.

- **미국·유럽**: 한국시간 자정 이후에 마감하므로 브리핑일 `D`의 세션은 `D` 아침에 아직 끝나지 않았습니다. 항상 직전 완료 세션을 씁니다.
- **한국·일본**: JST가 KST와 같은 시간대라 두 장이 나란히 흐릅니다. 생성 시각(`as_of`)으로 `pre_open | intraday | closed`를 가르고, 마감 후에만 브리핑일을 세션일로 씁니다.

`exchange_holidays.py`는 각 거래소가 공시한 연간 휴장일을 전사한 표입니다(NYSE·KRX·FOMC와 같은 방식).

- **유럽은 하나의 캘린더가 아닙니다.** 영국 은행휴일은 LSE만 닫고 Euronext·Xetra는 열립니다. 주현절은 반대로 마드리드만 닫습니다. 이런 날이 연 십여 일 있어 `divergent`/`openVenues`/`closedVenues`로 갈린 상태를 그대로 보고하고, 지역 `isOpen`은 한 곳이라도 열리면 참입니다.
- **표가 없는 연도는 추측하지 않습니다.** `coverage_expired`를 반환하고 개장으로 간주하지 않습니다. 새 연도 공시가 나오면 `EXCHANGE_HOLIDAYS` 표만 갱신합니다.
- **그래도 세션 기준일이 주말이 되지는 않습니다.** 표가 없으면 `previous_trading_day()`/`next_trading_day()`의 최종 폴백이 매번 도달하는데, 예전에는 달력상 하루를 그대로 돌려줘 2027-03-08 브리핑의 유럽·일본 세션일이 일요일(2027-03-07)이었습니다. 주말은 표 없이도 아는 사실이라 건너뛰고, 공휴일까지 맞히려는 추측은 하지 않습니다. 개장 여부는 계속 `coverage_expired`로 보고합니다.
- **미국 휴장일은 주말에 걸리면 인접 평일로 옮깁니다.** 신정만 예외로 토요일 보정이 없습니다(NYSE는 전년 12/31에 휴장하지 않습니다). 성탄절은 양방향입니다.
- **한국 대체공휴일은 `KR_LUNAR_MARKET_HOLIDAYS` 표에 함께 적습니다.** 고정 공휴일이 주말에 걸리면 다음 첫 비공휴일이 휴장일입니다. 빠지면 열리지 않은 장이 정규 거래일로 판정되어 브리핑이 없는 마감을 서술합니다. 같은 표가 `features/market_calendar/adapters/exchange.py::KRX_HOLIDAYS`에도 있어 **한쪽만 고치면 갈라집니다** — 실제로 2026-09-28·2026-10-05가 그렇게 갈라져 있었습니다.

## 히트맵 universe (S&P 500 / KOSPI 200 / 유럽 / 닛케이 225)

네 시장 모두 같은 방식입니다. **구성종목 명단은 위키백과**에서 받아 `config/*_constituents.json`에 커밋하고, 런타임에는 일봉 시세만 조회합니다. 새 연도/분기 갱신은 각 모듈의 `__main__` 진입점으로 실행합니다.

```bash
py -3 -m features.common.market_data.europe_core_universe
py -3 -m features.common.market_data.nikkei225_universe
```

- **유럽에는 재배포 가능한 광역 구성종목 명단이 없습니다.** 그래서 계획이 허용한 국가지수 합성으로 만듭니다: FTSE 100 + DAX + CAC 40 + AEX(총 203종목, 에어버스·아르셀로미탈은 두 지수에 중복 등재되어 한 번만 남습니다). 유럽 선 차트와 같은 네 지수입니다.
- **스위스는 이 네 지수에 없어서 유럽 universe 밖입니다.** Nestlé·Novartis·Roche는 해석되지 않고, 유럽장 보고서가 이들을 주도 기업으로 꼽으면 차트 자리가 빕니다. 이건 결함이 아니라 범위이며(2026-08-19 사용자 결정: 지금 상태를 유지), 넓히려면 구성종목·선 차트·히트맵을 함께 옮겨야 합니다 — 차트에 없는 종목이 히트맵에만 나오면 안 됩니다. 그래서 지금 효과가 없어 보이는 두 곳을 **지우지 마세요**: `config/foreign_company_aliases.json`의 `NESN.SW`·`NOVN.SW`·`ROG.SW` 별칭(오버레이는 구성종목 행에만 붙으므로 대상이 없습니다)과 `market_calendar/adapters/_ticker_market.py`의 `.SW` 접미사(일정만 다루므로 넓어도 무해합니다). 둘 다 나중에 SIX를 넣을 때 쓰는 자리입니다.
- **시가총액을 통화 섞어 더하지 않습니다.** 런던 종목은 GBP, 나머지는 EUR로 오므로 빌드 시점에 EUR로 환산하고 사용한 환율을 파일에 기록합니다(`fxRates`). 환율을 모르면 1.0으로 가정하지 않고 그 종목을 뺍니다(`missingFx`). 산출물은 `weightBasis: market_cap_eur`를 달고 다니며, 히트맵 스냅샷도 이 값을 그대로 들고 갑니다.
- **섹터는 지수별 분류 대신 시세 provider의 분류를 씁니다.** 네 유럽 지수가 ICB·Prime Standard·GICS 하위산업을 제각각 쓰기 때문입니다. 네 어휘로 동시에 묶은 히트맵은 묶음이 아닙니다.
- **일본 증권코드는 영숫자입니다.** 2024년부터 `285A`(키오시아) 같은 코드가 쓰여 숫자 4자리만 받으면 신규 편입 종목이 조용히 빠집니다.
- provider 실패는 마지막 정상 스냅샷으로 되돌아가고 `stale`로 표시합니다. 캐시도 없으면 `unavailable`입니다 — 빈 히트맵과 무변동 장세는 화면에서 구분되지 않기 때문입니다.
- 히트맵 일봉 bulk가 일부 종목만 돌려주면 성공한 종목은 유지하고, 현재 세션 종가·유효한 전일 종가가 없는 종목만 작은 batch와 제한된 순차 모드로 재시도합니다. 끝까지 빠진 종목이 있으면 `coverage.status=partial|unavailable`, `missingCount`, `missingSymbols`, warning을 남기며 전체 히트맵으로 표시하지 않습니다. 완전한 동일 세션·동일 universe 캐시만 재사용하고, partial 결과로 last-good을 덮어쓰지 않습니다.
- **last-good 캐시 저장 실패는 스냅샷을 죽이지 않습니다.** `save_last_good_snapshot()`은 `atomic_replace`로 쓰고 실패 시 `False`를 돌려줍니다. 여기 오면 시세를 이미 다 받은 뒤라, 캐시 저장 하나 때문에 예외를 올리면 그 시장 히트맵이 통째로 비고 브리핑 사이드카는 immutable이라 영구히 `unavailable`로 남습니다.

## market_data/providers.py

브리핑이 기사 표현에만 의존하지 않도록 시장 데이터 provider 경계를 둡니다.

- `MarketDataProvider`: 날짜별 시장 수치를 가져오는 인터페이스입니다.
- `TossOpenApiKoreaMarketProvider`: 현재 집계 보고서 경로에서는 준비 상태만 확인하고 yfinance로 넘기는 내부 adapter입니다. Toss 지수 분봉은 별도 native chart 경로에서 사용합니다. 이 공급원 구분은 운영 메타데이터이며 브리핑 작성용 본문에 경고로 전달하지 않습니다.
- `YFinanceKoreaMarketProvider`: KOSPI/KOSDAQ/KOSPI200 지수 종가·등락률과 원·달러 환율을 조회합니다.
- `PyKrxKoreaMarketProvider`는 2026-08-12에 제거했습니다. pykrx 1.2.x부터 지수 조회에 KRX 계정(`KRX_ID`/`KRX_PW`)이 필요해 자격증명 없는 설치에서는 항상 실패했고, 거래대금·투자자별 수급·업종 등락률은 그래서 실제로 채워진 적이 없습니다.
- `fetch_korea_market_data(date)`: provider chain을 실행하고, 별도 FX 보조 경로로 원·달러 환율(`USDKRW=X`)을 붙입니다.
- `YFinanceKoreaMarketProvider`의 KOSPI·KOSDAQ·KOSPI200 등락률은 요청 세션의 정확한 직전 KRX 세션 봉을 찾을 때만 채웁니다. 직전 봉이 없으면 종가·기준일은 보존하되 `changePct`는 비우고 비교일·사유를 함께 남깁니다.
- **환율도 지수와 같은 세션일로 부릅니다.** Toss 경로가 켜져 있으면 `fetch_usdkrw_exchange_rate(date_time=<세션일>)`로 요청하고, 응답 `asOfDate`가 세션일보다 미래면 그 세션의 값이 아니므로 버리고 yfinance로 폴백합니다. 예전에는 무인자 호출이라 지난 세션 브리핑에 오늘 환율이 섞였습니다(yfinance 경로는 원래 `as_of <= date`로 잘라 왔습니다).

provider가 실패해도 호출자는 빈 payload와 warning을 받아야 하며, 보고서 생성 경로는 수치를 추정하지 않고 한계를 명시해야 합니다.

### 저장 브리핑의 정규장 가격 계열

`market_data/price_history.py::build_price_history()`는 저장 보고서용 5분봉·1시간봉·일봉을 같은 yfinance 정규장·비수정 가격 기준으로 받습니다(`prepost=False`, `auto_adjust=False`). Toss의 최근 200개 1분봉과 장후까지 포함하는 일봉을 혼합하지 않습니다. 요청한 날짜·봉 간격을 유지하고 없는 구간을 만들지 않습니다. `chart_service.py`의 실시간 Toss bootstrap·분봉 집계·WebSocket 및 공급원 설정은 이 변경과 별개로 유지합니다.

### market_data/snapshot.py 수익률 기준

`fetch_market_snapshot()`은 기존 `last`, `asOfDate`, `oneDayPct`, `fiveDayPct`, `periodPct` 필드를 유지합니다. 주식·지수·ETF의 1일·5일 값은 미국 거래소 캘린더의 정확한 비교 세션을 사용하며, 해당 봉이 없으면 수치를 만들지 않고 `oneDayReason`/`fiveDayReason`과 비교일을 함께 남깁니다. 정렬되지 않은 행·중복일·비유한 값·미래 봉·휴장일 봉은 계산에서 제외합니다. 과거 `as_of_date` 조회는 요청 기간에 비교용 warmup만 더하고 `periodStartDate`/`periodPct`는 원래 `period` 경계에서 계산하므로, 짧은 기간이 조용히 장기 수익률로 늘어나지 않습니다.

FX·선물·금리에는 주식 캘린더가 없으므로 1일·5일 비교율을 만들지 않고 사유만 남깁니다. 24시간 암호화폐는 정확한 달력일이 있는 경우에만 비교합니다. 캘린더 범위를 확인할 수 없는 경우 평일을 거래일로 추측하지 않습니다. yfinance 스냅샷은 `oneDayComparisonValue`/`fiveDayComparisonValue`와 비교일, `comparisonSource`, `priceUnit`, `priceBasis`를 함께 남기며, 선물처럼 단위를 확정할 수 없는 값은 `unknown`으로 표시합니다. Toss/custom 행은 선언하지 않은 조정 기준을 새로 만들지 않습니다. 이 순수 계산 경로는 연결 provider를 호출하지 않으며, provider·Market Tape·차트 전달은 각 기능의 계약을 따릅니다.

## taxonomy.py

모든 태그 어휘의 단일 출처(single source of truth)입니다.

```python
from features.common.taxonomy import normalize_tag, canonical_tag, canonical_industry
from features.common.taxonomy import TAG_ALIASES, CANONICAL_TAGS
```

### CANONICAL_TAGS

섹터 태그와 영향 태그 두 그룹으로 구성됩니다.

```python
CANONICAL_SECTOR_TAGS = [
    "Semiconductors", "AI", "Data Centers", "Battery",
    "Energy", "Defense", "Financials", "Automobiles",
]
CANONICAL_IMPACT_TAGS = [
    "규제", "금리", "환율", "공급망", "수급", "매출 성장", "마진",
]
```

### TAG_ALIASES

alias → canonical label 매핑입니다. 키는 소문자+언더스코어 형식을 권장합니다.

```python
TAG_ALIASES = {
    "semiconductor": "Semiconductors",
    "반도체": "Semiconductors",
    "tariff": "규제",
    "rate": "금리",
    ...
}
```

### normalize_tag()

태그 문자열을 canonical label로 정규화합니다. exact match → lowercase → lowercase+underscore 순으로 시도하고, 매칭되지 않으면 원래 값을 반환합니다.

```python
normalize_tag("semiconductor")  # → "Semiconductors"
normalize_tag("tariffs")        # → "규제"
normalize_tag("unknown")        # → "unknown"
```

### 태그 어휘 수정 규칙

- 새 canonical 태그: `CANONICAL_TAGS` 리스트에 추가
- 새 alias: `TAG_ALIASES`에 추가
- `research_library/indexing/service.py`의 `SECTOR_TERMS`/`IMPACT_TERMS` 키워드와 taxonomy canonical label이 일치하도록 유지할 것
