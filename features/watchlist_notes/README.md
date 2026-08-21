# 워치리스트/메모

이 기능은 사용자가 관심 기업/섹터를 저장하고, 관련 뉴스와 태그를 확인하며, 투자 아이디어 메모를 남기는 보조 기능입니다.

상세 화면은 차트와 수집 뉴스만 보여줍니다. 0.4.x에 있던 `빠른 시장 신호`와 `확인된 변화 기록` 두 레일은 0.4.8에서 뺐습니다.

빠른 시장 신호는 승인 provider가 한국 RSS 하나만 남으면서(0.4.5) 교차 확인이 구조적으로 불가능해졌고, lead에 붙는 티커가 워치리스트 종목과 맞는 경우가 없어 항상 비어 있었습니다. 내용도 RSS 피드와 종목별 뉴스에 이미 있는 같은 기사입니다. 확인된 변화 기록은 변화 이벤트를 티커로 거르는데 브리핑 lineage가 시장 단위라 역시 걸리는 것이 없었고, 대시보드 `무엇이 달라졌나`가 같은 이벤트를 더 읽을 수 있는 형태로 보여줍니다.

수집 자체는 그대로 둡니다. lead 승격은 RSS 수집 경로에 남아 있고 변화 이벤트는 생성 커밋에서 계속 쌓입니다. 사라진 것은 워치리스트 상세의 표시 레일과 그 화면이 60초마다 돌던 `/api/signals` polling입니다.

## 다음 실적 일정 (0.5.4)

백엔드는 예전부터 다 있었다 — 시장 캘린더가 워치리스트 티커의 earnings를 수집하고(`market_calendar/service.py::_calendar_target_tickers`) `/api/market-calendar`가 `kind`/`ticker` 필터를 지원한다. 없던 것은 화면뿐이다.

- 카드에 `실적 D-3` 배지, 상세에는 TradingView 위젯과 뉴스 사이에 날짜 블록.
- **`estimated`를 확정과 구분해 보여준다.** 실적·배당은 yfinance 예정치라 날짜가 움직인다. 배지에는 `*`를, 상세에는 "제3자 예정치입니다. 회사 IR 공지로 다시 확인하세요"를 붙인다. 확정 일정과 같은 무게로 보이면 사용자가 달력에 적어 둘 근거가 없다.
- **카드마다 부르지 않는다.** 티커를 한 번에 넘겨 한 번만 묻고 티커별로 나눈다(`watchlistEarnings.ts::fetchNextEarnings`) — 종목 20개짜리 워치리스트가 20개의 요청을 만들면 목록이 그만큼 늦게 뜬다. 조회 실패는 배지가 없는 것일 뿐 목록을 막지 않는다.
- **지난 일정은 "다음 실적"이 아니다.** D-day가 음수면 배지를 만들지 않고, 티커별로 가장 가까운 다가올 일정만 남긴다.
- 날짜 판정은 **보는 사람의 하루** 기준이다. 미국장 실적은 KST로 다음 날 새벽이라, UTC 날짜로 세면 D-day가 하루씩 어긋난다.

## 담당 범위

- 관심 기업/섹터 목록 저장
- 워치리스트 기반 관련 뉴스 표시 및 태그 집계
- 워치리스트 항목 상세 모달(TradingView 차트/심볼 정보 + 수집 뉴스)
- 관심 ticker의 body-free checkpoint projection
- 투자 메모 추가
- 최근 메모 표시

## 저장 위치

```text
data/watchlist.json
data/notes/notes.json
```

## 태그 품질 설계

`watchlist_overview()`는 워치리스트 항목별 관련 기사를 검색해 태그를 집계합니다. 탭의 카드에는 요약만 표시하고, 사용자가 항목을 클릭하면 `watchlist_detail()` 결과를 팝업으로 열어 회사 정보, TradingView 위젯, 수집 뉴스를 함께 보여줍니다. 태그 노이즈를 줄이기 위해 여러 단계의 필터를 적용합니다.

TradingView 심볼은 `tradingview_symbol_for_query()`가 만든다. 6자리 숫자는 `KRX:`, 거래소 접미사가 붙은 티커는 그 거래소(`7203.T` → `TSE:7203`, `ASML.AS` → `EURONEXT:ASML`, `SHEL.L` → `LSE:SHEL`), 나머지는 `NASDAQ:`을 붙인다. 예전에는 접미사도 미국 종류주처럼 다뤄 `NASDAQ:ASML-AS` 같은 없는 심볼을 만들었고, 위젯이 아무 설명 없이 비어 보였다.

관심 종목 관리는 카드 한 곳에서 한다. 키워드를 추가하면 즉시 저장되고 카드가 나타나며, 삭제는 카드 우상단의 삭제 버튼으로 한다(별도 키워드 칩 목록은 두지 않는다). 카드 좌측 강조색과 밝은 표면은 브리핑 목록 카드와 같은 시각 규격을 공유한다.

## Investment Context와 checkpoint (0.2.3)

`watchlist_checkpoint_context()`는 워치리스트 ticker에 연결된 native
`noteType=checkpoint`만 읽어 최대 개수와 상태를 제한한 projection을 반환한다.
본문·원문 생각·수량·가격은 반환하지 않으며 `reuseAsEvidence=false`를 유지한다.
projection 조회는 `watchlist.json`을 다시 쓰지 않는다.

포트폴리오에도 같은 ticker가 있으면 공통 Investment Context의 source는 `both`가 된다.
이 연결은 저장 항목의 존재만 나타내며 보유량, 비중, 매수/매도 판단을 뜻하지 않는다.
화면의 checkpoint 생성·확인은 native investment note 저장소에만 반영한다.

### 관련 뉴스와 `N건`

카드의 건수와 목록, 상세 모달의 목록은 모두 `watchlist_news()` 한 곳에서 나옵니다. 건수는 **색인 전체에서 그 회사가 언급된 뉴스 문서 수**이며 목록 길이가 아닙니다.

- 예전에는 검색 상위 200건 안에서만 세어 AMD가 실제 295건인데 카드에 69건으로 나왔습니다.
- 매칭이 0건이면 **검색 결과 개수를 그대로** 건수로 썼습니다. Howmet Aerospace는 색인에 한 건도 없는데 카드가 107건이라고 했고, 같은 항목의 상세 화면은 0건이라고 했습니다. 종목은 그 종목이 실제로 언급된 문서만 뉴스이며, 없으면 없다고 말합니다.
- 테마 키워드(`AI`, `ETF` 등 `WATCHLIST_THEME_TERMS`)는 매칭할 회사가 없으므로 검색 결과가 곧 답입니다.
- 목록은 관련도 순위가 아니라 **최신순**입니다. 카드가 보여줄 것은 최신 소식입니다.

**연결 열쇠는 종목 코드입니다.** 워치리스트는 해석된 정식명(`ADVANCED MICRO DEVICES INC`)을 저장하는데 기사에 붙은 회사는 `AMD`라, 이름끼리는 한 글자도 겹치지 않습니다. 그래서 회사를 먼저 해석해 코드를 얻고, 코드가 없거나 표기가 다를 때(도쿄 `6501.T` vs 미국 ADR `HTHIY`) 이름이 받습니다.

뉴스 문서를 가리고 회사 이름을 정규화하는 준비는 항목과 무관하므로 `news_company_index()`가 한 번만 만듭니다. 항목마다 다시 하면 실측으로 5개에 0.98초가 쌓입니다.

### 주요 기업 필터 (Fix 2)
문서의 `companies` 목록 상위 2개에 해당 기업이 있을 때만 태그를 수집합니다. 주변 언급 기업의 태그가 섞이는 것을 방지합니다.

### 동반 기업 섹터 오염 방지 (Fix 6)
같은 문서에서 다른 기업(예: 애널리스트 언급 투자은행)에 귀속된 섹터 태그는 제외합니다. Alphabet 기사에 Goldman Sachs가 언급돼도 "Financials" 태그가 붙지 않습니다. `impactTags`(규제, 금리 등)는 기업 귀속이 없으므로 필터 없이 수집합니다.

### 빈도 기반 필터 (Fix 3)
2회 이상 등장한 태그를 우선합니다. 미달 시 상위 4개로 fallback합니다.

### 기업 자체 섹터 고정 (Fix 4)
검색 결과에서 해당 기업의 `sector` 값을 기본 태그로 수집해 태그 목록에 없으면 맨 앞에 고정합니다. 관련 기사가 적어 빈도 기준에 미달해도 Lam Research → Technology, Visa → Financials 같은 기본 태그가 항상 표시됩니다.

### `Unclassified`는 분류가 아니다
`Unclassified`는 "모른다"는 자리표시자이므로 태그로 올리지 않는다(`_real_sector()`). **회사를 알아낸 출처가 섹터를 갖고 있지 않을 때가 많다** — SEC `company_tickers.json`은 `cik`/`ticker`/`title` 셋뿐이고 일본·유럽 구성종목 파일도 섹터를 담지 않아, 그 출처로 해석된 회사는 전부 이 값을 받는다. 섹터를 들고 있는 것은 수동 사전(`curated`)뿐이라 실측으로 종목 넷 중 셋(LRCX·8306.T·6501.T)이 `UNCLASSIFIED` 칩을 달고 있었다. 회사를 못 찾은 것이 아니라 티커는 아는데 섹터만 없는 상태다.

빈 섹터는 `features/common/sector_cache.py`가 그 티커로 yfinance에 물어 채운다(`_fill_missing_sectors()`). 조회는 종목당 한 번이고 `data/sector-cache.json`에 90일 캐시되므로 화면을 열 때마다 치르는 값이 아니다(실측 콜드 5종목 2.4초, 이후 0초). 답이 없는 항목도 7일 캐시해 상장폐지 종목이 매번 네트워크를 태우지 않게 한다. 티커가 없는 관심 주제는 아예 묻지 않는다.

**수동 사전이 조회 결과를 이긴다.** Howmet은 사전이 `Aerospace`, yfinance가 `Industrials`인데 앞엣것이 종목을 잘 설명한다. 그래서 섹터가 이미 있는 카드는 조회 대상에 넣지 않는다. 조회가 실패하거나 마감 시각(6초)을 넘기면 카드를 그대로 두고, 못 받은 값은 캐시에 적지 않는다 — 죽은 네트워크를 "이 회사는 섹터가 없다"로 굳히면 살아난 뒤에도 계속 빈 채로 남는다.

## 관련 코드

- `features/watchlist_notes/service.py`: `watchlist_overview()`, `watchlist_detail()`, `watchlist_checkpoint_context()`, `_item_matches_company()`, `normalize_watchlist_keyword()`
- `features/common/sector_cache.py`: `resolve_sectors()`, `cached_sector()`, `quote_symbols()` — 섹터를 모르는 출처로 해석된 회사의 섹터 캐시(`data/sector-cache.json`)
- `features/investment_notes/checkpoints.py`: controlled checkpoint normalization/projection
- `app.py`: 워치리스트/메모 API 엔드포인트
- `public/app.js`: `loadWatchlistNews()`, `openWatchlistDetail()`, `renderWatchlistDetailNews()`, `renderNotes()`
- `public/index.html`: `watchlist`, `notes` 탭

## 주의점

- 워치리스트 태그와 뉴스는 인덱스 기준이므로 인덱스를 새로 빌드하면 반영됩니다.
- 메모는 사용자의 직접 입력 데이터이므로 자동 삭제하지 마세요.

## 입력 기업 판단 — 0.5

이름으로 적은 기업도 정식 명칭 하나로 통일한다. 해석기는 `features/common/company_resolution.py`이며 규칙 기반이라 LLM을 쓰지 않는다.

- 예전에는 **티커 모양일 때만** 회사로 인식해서 "하우멧"과 "Howmet Aerospace"가 서로 다른 항목이 됐다.
- 워치리스트는 주제 키워드도 받는다. 못 알아본 입력은 오류가 아니라 키워드다.
- 이름 일부만 겹친 약한 후보(`strong: false`)에는 후보 목록을 띄우지 않는다. "반도체"에 한미반도체가 걸린다고 목록을 열면 주제어 입력을 방해한다.
- **자국 원주를 등록한다.** 워치리스트는 회사를 따라다니는 화면이라 도쿄에 상장된 도요타(`7203.T`)를 봐야 한다. 미국 ADR(`TM`)은 통화도 시간대도 가격도 다른 별개의 증권이다. 그래서 워치리스트만 `prefer_home`으로 해석한다(`/api/company/resolve?prefer=home`). 기업분석은 반대다 — SEC 등록분이라야 공시와 재무가 붙는다.
- 한글로 친 일본·유럽 기업도 잡힌다. 별칭은 `config/foreign_company_aliases.json`에 있고, 영문명은 구성종목 파일의 `englishName`에서 온다.
- 후보 목록은 입력 패널 위에 뜬다. 패널에 transform이 걸려 있어 패널이 자기 쌓임 맥락을 만들기 때문에, 목록의 `z-index`가 아니라 **패널**이 아래 카드를 이겨야 한다(`.watchlist-editor.input-panel { position: relative; z-index: 5 }`).
