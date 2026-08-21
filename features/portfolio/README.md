# Portfolio

포트폴리오 기능은 현재 보유 포지션을 입력해 평가 손익과 비중을 확인하고, 목표 포트폴리오 프리셋과 리서치용 백테스트를 관리한다.

## 프리셋이 1급 시민이다 (0.5.4)

`목표 비중` 탭을 **프리셋**으로 바꿨다. 목표 비중은 프리셋으로 할 수 있는 **여러 일 중 하나**다 — 백테스트의 입력도, 비교 백테스트의 입력도 같은 프리셋이라, 탭 이름이 그 셋 중 하나만 가리키면 나머지 둘을 어디서 하는지 알 수 없다.

- 프리셋 목록·만들기·지우기가 위에 오고, "현재 보유와의 차이"(`analytics?presetId=`)는 프리셋을 고른 뒤의 한 가지 보기가 된다.
- **프리셋 비교 화면을 신설했다.** `POST /api/portfolio/backtests/compare`는 예전부터 있었고 프리셋 2개 이상을 받아 부분 실패까지 허용하며 돌리는데, **부르는 화면이 없었다.** 지표 표(수익률·CAGR·최대 낙폭·변동성·샤프)와 한 좌표계에 겹친 시계열을 함께 보여준다.
- **지표마다 나은 쪽 하나만 굵게 하고 동점이면 아무도 강조하지 않는다.** 비교가 성립하지 않는데 우열을 표시하면 없는 판단을 만든다.
- **최대 낙폭은 `nearZero`로 비교한다.** 실측 값이 음수로 온다(-0.1346). "작을수록 좋다"로 두면 **더 깊은** 낙폭을 최선으로 강조하게 되고, "클수록 좋다"로 두면 provider가 양수 크기로 바꾸는 날 정반대가 된다. 낙폭은 0에 가까울수록 낫다는 말을 그대로 적는다.
- 부분 실패를 숨기지 않는다. 실패한 프리셋 이름을 경고로 남긴다 — 몇 개를 골랐는데 몇 개가 돌았는지 보여야 한다.
- 리서치용 경계는 그대로다. 세금·수수료·체결오차·배당 처리 한계와 "매수·매도 지시가 아니다"를 결과 옆에 둔다.
- 비교 결과 저장은 기존 `POST /backtests/save`가 이미 `type: "comparison"`을 받는다.

## 담당 기능

- 현재 보유 포지션 입력
- `revision`/`expectedRevision` 기반 동시 편집 충돌 방지(불일치 시 409와 최신본 반환)
- 티커 기반 종목명, 시장, 통화, 섹터, 자산군 자동 매칭
- `yfinance` 현재가 기반 평가금액, 손익, 비중 계산
- 여러 통화(USD/KRW/EUR/GBP/JPY)가 섞인 포트폴리오의 USD 기준 환산 비중 계산
- 종목, 섹터, 시장/통화, 자산군, 손익 기여도 Plotly 시각화
- 목표 포트폴리오 프리셋 생성, 저장, 삭제
- 현재 포트폴리오를 프리셋 초안으로 불러와 비중/종목 수정
- 현재 포트폴리오와 목표 프리셋 비교
- 목표 대비 비중 차이, 금액 차이, 매수/매도 필요 수량 표시
- 프리셋 기반 리서치용 백테스트 실행, 선택 저장, 열기, 삭제
- 여러 포트폴리오 초안 간 비교 백테스트
- 백테스트 결과의 수익률, 위험/변동성, 위험조정 성과, 시장 민감도 지표 분류 표시
- 수익률 기여도, 변동성 기여도, 베타 기여도 분석
- 누적 성과, Drawdown, Rolling 12M Return, Rolling Volatility, Rolling Beta 시각화

Plotly 차트는 포트폴리오 뷰 또는 하위 탭이 활성화된 뒤 `public/app.js::schedulePortfolioChartResize()`로 다시 치수를 계산한다. 숨겨진 탭에서 먼저 렌더된 차트는 폭을 잘못 잡을 수 있으므로, 새 차트 추가 시 렌더 직후와 탭 전환 후 resize 경로를 유지한다.

## 화면 구조

포트폴리오 탭은 세 개의 하위 탭으로 나뉜다.

```text
보유·평가     보유 종목 입력 + 평가 요약 + 구성/집중도/살펴볼 점
목표 비중     목표 프리셋 저장·삭제 + 선택한 목표와의 차이
백테스트      목표 비중으로 과거 성과 계산·저장
```

빈도가 다르기 때문에 나눈다. 보유·평가는 열 때마다 보고, 목표는 가끔 정하고, 백테스트는 드물게 돌린다. 한 화면에 세로로 쌓으면 매번 보는 것이 거의 안 쓰는 것에 밀린다.

저장하면 `revision`이 오르고, 그 값을 하위 컴포넌트에 내려보내 시세·비중·목표 차이를 다시 받는다.

### 현재 포트폴리오

티커, 수량, 평균단가만 입력한다. 종목명, 시장, 통화, 섹터, 자산군은 가능한 경우 `yfinance`에서 자동 조회한다.

한국 상장 종목은 `005930`, `442580`처럼 6자리 숫자를 입력하면 `.KS` 또는 `.KQ` 후보를 자동으로 시도한다. ETF나 일부 종목은 거래소 구분에 따라 조회 실패가 날 수 있다.

유럽·일본 상장 종목은 거래소 접미사를 붙여 입력한다(`7203.T`, `ASML.AS`, `SAP.DE`, `SHEL.L`, `ENI.MI`, `SAN.MC`). 시장과 통화는 접미사에서 정하고 평가금액은 USD로 환산한다.

접미사가 붙은 티커와 미국 종류주(`BRK.B`)는 표기가 같아 보이지만 다르게 다룬다. 종류주는 `BRK-B`로 바꿔 조회하고, 접미사는 점을 그대로 둔다. `.L`, `.T`처럼 양쪽으로 읽힐 수 있는 경우는 두 형태를 모두 시도한다.

런던 시세는 파운드가 아니라 펜스(`GBp`)로 들어온다. 100으로 나눠 파운드로 저장하므로 화면 금액은 파운드 기준이다.

### 프리셋 · 백테스트

프리셋은 티커와 목표 비중만 입력해 저장한다. 저장 시 각 티커를 자동 매칭하고, 비중 합계가 100%에 가까운지 확인한다.

`현재 포트폴리오 불러오기`를 누르면 현재 평가 비중을 기준으로 프리셋 초안이 채워진다. 이후 사용자가 종목을 삭제하거나 비중을 수정한 뒤 새 프리셋으로 저장할 수 있다.

저장한 프리셋은 다음 용도로 쓴다.

- 현재 포트폴리오와 목표 비중 비교
- 매수/매도 필요 수량 계산
- 백테스트 입력 포트폴리오

백테스트는 과거 가격과 일자별 환율을 사용해 리서치용 성과를 계산한다. 기준 통화는 USD 또는 KRW이며, 그 외 통화 종목은 일자별 USD 환율을 거쳐 기준 통화로 환산한다. 환율을 못 가져온 통화는 환산하지 않은 값을 쓰는 대신 해당 종목 계산을 중단한다. 실행 결과는 자동 저장하지 않는다. 화면에 표시된 결과가 보관할 만하다고 판단될 때 `결과 저장` 버튼을 눌러 저장한다. 비교 초안을 2개 이상 만든 경우에도 같은 방식으로 사용자가 선택한 비교 결과만 저장한다.

## 데이터 저장 위치

```text
data/portfolio.json
data/portfolio-presets.json
data/portfolio-backtests/
data/portfolio-price-cache/
data/portfolio-fx-cache.json
```

이 경로들은 사용자의 직접 입력값, 저장 결과, 가격 캐시를 포함한다. 명시 요청 없이 삭제하거나 초기화하지 않는다.

## API

```text
GET    /api/portfolio
POST   /api/portfolio
GET    /api/portfolio/summary
GET    /api/portfolio/analytics          # ?presetId= 를 주면 그 목표와의 차이를 함께 계산
GET    /api/portfolio/resolve?ticker=...

GET    /api/portfolio/presets
POST   /api/portfolio/presets
POST   /api/portfolio/presets/from-current
DELETE /api/portfolio/presets/{preset_id}

GET    /api/portfolio/backtests
POST   /api/portfolio/backtests          # 실행만 수행, 자동 저장하지 않음
POST   /api/portfolio/backtests/compare  # 비교 실행만 수행, 자동 저장하지 않음
POST   /api/portfolio/backtests/save     # 화면에 표시된 결과를 사용자가 선택 저장
GET    /api/portfolio/backtests/{backtest_id}
DELETE /api/portfolio/backtests/{backtest_id}
```

`POST /api/portfolio`는 선택적으로 `expectedRevision`을 받는다. 현재 revision과 다르면 저장하지 않고 409를 반환한다. 과거 `portfolio.json`은 revision 0으로 읽고 첫 저장부터 additive schema v2로 승격한다.

## ETF 섹터 분류

ETF는 `yfinance`가 종목 유형을 정확히 반환하지 못하는 경우가 많아 별도 분류 테이블을 사용합니다.

- `ETF_SECTOR_MAP`: 티커 → ETF 섹터 레이블 매핑. 주식(ETF), 채권(ETF), 금/원자재(ETF), 배당(ETF), 부동산(ETF), 레버리지/인버스(ETF), 통화(ETF) 분류를 사용합니다.
- `_ETF_NAME_KEYWORDS`: `yfinance` 종목명 기반 fallback 분류.
- 분류 우선순위: `ETF_SECTOR_MAP` → `yfinance` quoteType → 종목명 키워드 → 기존 저장값.
- 한국 숫자코드 ETF(예: 442580, 161510)는 `yfinance`가 `EQUITY`로 잘못 반환하는 경우가 있어 `ETF_SECTOR_MAP` 조회가 반드시 `infer_portfolio_asset_class()` 이전에 실행됩니다.
- 새 ETF를 추가하려면 `features/portfolio/service.py`의 `ETF_SECTOR_MAP`에 티커를 추가하세요.

## 계산 기준

- 현재가와 과거 가격은 `yfinance`를 사용한다.
- 가격 조회 실패 시 해당 행은 `확인 필요`로 표시하고 전체 화면은 계속 렌더링되어야 한다.
- 달러가 아닌 자산은 환율을 반영해 USD 기준 평가금액과 비중을 계산한다. 환율은 Yahoo `XXX=X`(달러당 해당 통화)를 쓴다.
- 목표 포트폴리오 비교의 매매 수량은 `목표금액 - 현재금액`을 현재가로 나누어 추정한다.
- 백테스트는 리서치용이며 실제 세금, 수수료, 슬리피지, 체결오차를 반영하지 않는다.
- 변동성 기여도는 일별 수익률 공분산을 활용한 대략적인 리스크 기여도이며, 베타 기여도는 벤치마크와의 일별 수익률 공분산을 기준으로 계산한다.

## Investment Context 연결 (0.2.3)

현재 포트폴리오의 ticker는 읽기 전용 Investment Context에서 Market Memory,
thesis, checkpoint, 보고서, Smart Collection과 연결할 수 있다. 연결 projection에는
`source=portfolio|watchlist|both`와 정규화된 stance만 들어가며 수량, 평균단가,
평가금액, 손익, 비중은 포함하지 않는다.

이 projection은 Home, Market Memory, Smart Collection, Deep Research의 개인 맥락
카드와 0.4.3의 Portfolio route에서 사용한다. 연결 결과는 리서치 점검을 돕는
hypothesis metadata일 뿐 자동 리밸런싱·매수/매도/보유 권고가 아니다.

이미지 가져오기는 **0.5.0 화면에 없다**(아래 "사진 가져오기" 절). 보유 종목은 직접
입력하며, 이름으로 적어도 `features/common/company_resolution.py`가 티커로 바꾼다. 원본 이미지, crop 이미지, raw OCR text와 bbox는 저장하지 않는다. 외부 Vision은
매 요청의 명시적 동의가 있을 때만 crop/redaction 미리보기를 전송하며 결과를 즉시 저장하지
않고 사용자가 편집표를 확인한 뒤 revision-safe 저장을 별도로 실행한다.

## 아직 범위 밖인 기능

- 거래 내역 기반 평균단가 자동 계산
- 배당과 현금흐름 반영
- 세금, 수수료, 슬리피지 반영
- 자동 리밸런싱 제안
- 실제 주문/자동매매

현재 앱은 투자 실행 도구가 아니라 리서치와 점검용 도구다.

## 종목 입력 — 0.5

보유 표의 종목 칸은 이름으로 적어도 된다. 입력을 벗어날 때 `features/common/company_resolution.py`가 한 번 해석해 티커로 바꾸고, **비어 있을 때만** 시장 칸을 채운다. 사용자가 적어 둔 값은 덮지 않는다.

- 표 안이라 글자마다 부르지 않는다. 행이 여럿일 때 호출이 곱절로 늘어난다.
- 해석된 회사명은 화면 확인용이며 저장 payload에 넣지 않는다.
- 행을 지우면 아래 행 번호가 당겨지므로 표시용 이름도 함께 옮긴다.

## 사진 가져오기 — 0.5.0에서 뺐다

0.5.0에는 `사진에서 가져오기` 버튼도 다이얼로그도 없다. 실제로 써 보니 시간이 걸리는 데 비해 인식 결과가 만족스럽지 않았고(2026-08-07 사용자), 무엇보다 **첫 설정에 한 번 쓰는 도구**라 손으로 치는 것 대비 이득이 크지 않았다.

한 가지는 인식이 아니라 우리 코드 문제였다는 것을 남겨 둔다. 한국 증권사 화면은 미국 종목도 한글 이름으로 보여주고 티커 칸이 없는 경우가 많은데, `normalize_draft()`가 티커 모양 문자열만 받아 **이름만 읽힌 행을 전부 `unresolved`로 버렸다**. 모델은 제대로 읽었는데 우리가 버린 것이다 — `알파벳`→GOOGL, `브로드컴`→AVGO, `히타치`→6501.T 모두 `company_resolution`이 confident로 답한다. 다시 만들 때 여기부터 붙인다.

**남은 코드는 죽은 코드가 아니다.** `import_image.py`(임시 파일 수명·`validate_image` 가드·`import_preview` 정규화), `agent_import.py`(CLI 추출), `vision_import.py`(API 추출), `import_schema.py`(초안 정규화)는 0.5.X가 그대로 쓴다. 지우기 전에 `roadmap/release/0.5_PLAN.md`를 본다.

## 다시 만들 때 — Agent 도크로 통일 (0.5.X)

전용 진입점을 만들지 않는다. **사용자가 도크에 사진을 붙이고 포지션 입력을 요청할 때만** 인식한다(2026-08-07 사용자 결정).

- 엔진 선택을 따로 두지 않는다. 도크가 설정의 CLI/API 모드를 따르므로 그 선택이 곧 인식 엔진이다. 로컬 Tesseract는 도크에 자리가 없어 함께 사라진다(`local_ocr.py`, `import_image.py`의 `local` 모드).
- **막힌 지점**: 도크 API 모드는 지금 이미지를 못 읽는다. `chat.py::_run_with_images`가 `bridge.run_agent_prompt`(CLI 전용)를 부르고, CLI가 없으면 "이미지를 열 수 없습니다"라고 답한다. `vision_import.py`가 하는 base64 vision 입력을 그 경로에 붙여야 "도크 하나로 통일"이 성립한다.
- crop 슬라이더 5개는 없앤다. CLI/모델이 전체 화면을 읽고 합계·예수금 행을 알아서 거른다. 계좌번호를 가리는 용도의 상단 가리기 하나만 남길지는 다시 만들 때 정한다.
- **리뷰 표는 없애지 못한다.** 저장 전 확인이 안전 계약이다. 다만 별도 표를 만들지 말고 읽은 행을 Portfolio 편집표에 얹고(화면 상단 배너로 알림) 기존 `Portfolio 저장` 버튼이 커밋하게 하면, 다이얼로그·crop·모드 라디오·preflight가 모두 사라져 남는 UI가 오히려 줄어든다.
- 기존 제안(proposal) 배관은 쓸 수 없다. markdown 보고서 전용이라 diff·섹션 검증·base revision이 전제이고 `ReportKind`도 셋뿐이다. 포트폴리오는 JSON 포지션이라 짧은 별도 경로가 필요하다.

## 화면 재연결 (0.5.1 완료)

React 전환 때 화면만 안 옮겨와서 백엔드 API 16개 중 화면이 쓰는 것이 2개(`/api/portfolio` 읽기·쓰기)뿐이었다. 0.5.1에서 `/summary`·`/analytics`·`/presets`·`/backtests`를 다시 붙였다. `/resolve`와 `/suggest`는 `HoldingsTable`이 이미 쓰는 공용 해석기로 대체돼 있어 그대로 둔다.

붙이면서 드러난 두 가지를 함께 고쳤다. 둘 다 **화면이 없어서 아무도 못 밟고 있던 버그**다.

- `POST /presets/from-current`는 `targetWeight`가 이미 있는 포지션만 담았다. 그 값을 넣을 칸이 화면에 없어서 결과가 **항상 빈 프리셋**이었다(실측: 보유 3종목 → `positions: []`). 지금 평가액 비중을 그대로 목표로 삼는다.
- `analytics.targetWeights`는 포지션의 `targetWeight`만 봤고 프리셋과 서로 몰랐다. 프리셋을 아무리 만들어도 `hasTargets`가 False라 **목표와의 차이 표가 한 번도 뜨지 않았다**. `GET /analytics?presetId=`로 어느 목표와 비교할지 받는다. 프리셋에만 있고 아직 안 산 종목도 한 줄로 낸다 — 조정에서 가장 중요한 정보다.

남은 CSS 정리: 초기 공개 릴리즈에 실려 온 `.portfolio-donut-grid`·`.portfolio-analysis-grid` 등 46개 클래스는 D1 프리미티브 이전 디자인(테두리 있는 카드)이라 되살리지 않았다. 0.5.1 디자인 정리에서 걷어낸다.

