# Research Cockpit

Dashboard는 `cockpit` 하나입니다(0.5에서 Legacy 모드 삭제). Cockpit payload는 시장 일정 ref, provider health, native symbol과 기존 로컬 투자 맥락을 집계하며 upstream network나 chart series를 포함하지 않습니다. 기존 `/api/dashboard` 호환 응답에는 저장된 Change Intelligence 이벤트와 집계 필드가 남아 있을 수 있지만, 현재 Cockpit 화면은 이를 표시하지 않습니다.

**Legacy 모드는 0.5에서 삭제했습니다.** 0.4에서 한 릴리즈 동안만 두기로 한 rollback 경로였고, Cockpit이 자리를 잡아 같은 화면을 두 벌 유지할 이유가 없습니다. 저장된 `dashboardMode: legacy`는 `cockpit`으로 승격됩니다. 사용자 설정 파일 `data/market-widget-settings.json`은 계약대로 **삭제하지 않고**, 집중 종목 fallback(`source: legacy_setting`)으로 계속 read-only로 읽습니다. 설정/Watchlist가 없으면 미국 `SPY`, 한국 `^KS11`을 사용합니다.

대시보드에는 브리핑 내용 변화 피드와 오늘의 변화 요약을 표시하지 않습니다. 저장된 과거 보고서의 Change Intelligence 필드는 기존 데이터 호환을 위해 읽을 수 있지만, 새 브리핑 생성에서는 해당 비교·판정·이벤트를 만들지 않습니다.

`오늘의 이야기 비중`은 브리핑과 독립적으로 수집된 뉴스의 동인별 보도량을 보여줍니다. 비중 이동은 내용 변화가 아니라는 안내를 함께 표시하며, 시장별 탭에서 US/KR/EUROPE/JP를 선택합니다.

`POST /api/dashboard/settings`는 기존 저장값과 merge 후 정규화합니다(부분 갱신이 다른 키를 초기화하지 않음). 저장 키: `dashboardMode`, `calendarView`, `calendarKinds`, `calendarMarkets`, `calendarWatchlistOnly`, `calendarMinImportance`(1=전부·2=중간 이상·3=최상위만), `chartRange`, `chartStyle`, `chartSymbol`.

차트 기간은 0.5에서 `1d/1m/3m/1y/5y`로 바뀌었다(`1d`는 5분봉). `6m`을 쓰던 저장값은 정규화 때 조용히 `3m`으로 떨어진다 — `legacy → cockpit`처럼 옮겨 주는 승격 경로는 두지 않았다.

Toss Open API가 켜져 있으면 KR/US 주식의 1D 차트는 REST 1분봉 bootstrap 뒤 equity WebSocket
체결 overlay를 사용한다. KOSPI/KOSDAQ은 공식 시장지표 candle endpoint의 1분봉을 5분봉으로
집계하지만 equity WebSocket은 열지 않아 상태를 `Toss 1분봉`으로 표시한다. 그 밖의 지수·환율은
yfinance 차트를 유지하고 `Toss 분봉 미지원`이라고 범위를 명시한다.

API: `GET /api/dashboard/cockpit`, `GET|POST /api/dashboard/settings`, `GET /api/dashboard/story-share?market=us|kr|europe|jp`. 기존 `GET /api/dashboard`는 그대로 유지합니다.

## 이야기 비중의 비교 기준

**하루가 아니라 직전 5거래일 합산이다**(`PREVIOUS_SESSION_WINDOW`). 하루끼리 비교하면 그날 수집량이 흔들리는 것만으로 비중이 수십 %p 움직인다 — 유럽·일본은 하루 수집이 열몇 건이라 기사 두 건이 그 폭을 만든다.

- **날짜별 비중을 평균 내지 않는다.** 창 전체의 문서를 모아 하나의 분포로 센다. 평균을 내면 수집이 적은 날이 많은 날과 같은 무게를 갖게 되어, 줄이려던 흔들림이 그대로 돌아온다.
- **문서는 한 번만 센다.** `select_briefing_docs`가 돌려주는 것은 그 날짜 하나가 아니라 세션 창(보통 이틀)이라 이웃한 기준일들의 창이 겹친다. 그대로 더하면 같은 기사가 두세 번 세어지고, 겹치는 자리의 문서만 무게가 커진다. 같은 문서 판정은 경로·URL·제목·날짜가 **모두** 같을 때다 — 경로 하나로 묶으면 서로 다른 기사가 한 건으로 접힌다.
- 공휴일이 끼면 거래일 5개를 채우느라 달력으로는 5일보다 길어진다. 그것이 맞다 — 휴장일을 분모에 넣으면 수집이 거의 없는 날이 기준이 된다.
- **표본 부족 임계는 창 길이에 비례한다**(`MIN_CONFIDENT_SAMPLE × 창 길이`). 하루 12건 기준을 5일 합산에 그대로 쓰면 하루 두세 건씩만 모여도 "충분한 표본"이 되어 이 경고가 사실상 꺼진다.
- 페이로드는 `schemaVersion: 2`이고 `previousDates`/`previousSessionCount`를 싣는다. 단일 날짜 필드(`previousDate`)는 창의 시작일로 남긴다 — 없애면 판올림 중인 화면이 비교 기준을 아예 못 읽는다.
- 화면 문구는 `comparisonLabel()`이 만든다. "직전 거래일 대비"는 창이 하루일 때만 맞는 말이다.
- **예열 비용은 창 길이에 비례한다**(실측 18,928건 기준): 창 1일이면 네 시장 0.23초, 창 5일이면 4.27초(첫 시장 2.05초, 이후 0.74초/시장). 늘어난 시간은 문서 스캔이 아니라 **동인 추론**이다 — 날짜별로 문서를 미리 묶어 봐도 빨라지지 않았고(오히려 5.09초) 선별 규칙만 두 벌이 되어 되돌렸다. 예열은 시작 직후 배경 스레드에서 돌고 결과는 10분 캐시되므로 사용자가 기다리는 시간은 아니다.

## 동인은 고정 어휘표다 (0.5.4)

비중 산정의 주제는 `daily_briefing/selection.py::DRIVER_TERMS`이고 추론은 단순 부분일치다. **표에 없는 주제는 아무리 크게 보도돼도 이 막대에 나타나지 않는다** — 화면이 `driverBasis`로 그 사실을 밝힌다. 동적 토픽 발견(LLM/클러스터)은 범위 밖이다.

이 표는 **브리핑 동인 선정과 공유**하므로 측정 없이 손대지 않는다. 0.5.4에서 실측으로 고친 것:

- **`금` 한 글자를 뺐다.** 한글 토큰은 단어 경계 없이 부분일치라(영문·숫자만 경계를 갖는다) `금`이 금리·금융·자금·세금·연금·임금을 전부 물었다. 실측으로 문서의 24.5%가 걸렸고 그중 `금` 하나로만 원자재/유가에 들어온 2,808건(14.8%)의 실제 매칭은 금리 2,712 · 금융 1,052 · 기준금리 320이었다 — 금값 기사는 사실상 없었다. 금값을 가리키는 표기(`금값`·`금 가격`·`금시세`·`귀금속`)만 남겼고, 원자재/유가 비중이 35.0% → 20.4%로 내려갔다. **한 글자 한글 어휘를 새로 넣지 않는다.**
- **`크립토`를 넣었다.** 2026 시장 보도에서 독립된 이야기인데 표에 없었다. 실측 334건(1.8%)이 걸리고 그중 어느 동인에도 속하지 못하던 80건이 7건으로 줄었다.

## 오늘의 이야기 비중 (story_share.py)

얇은 누적 막대와 범례로 그날 수집된 articles/rss 시장 관련 문서 전체를 `infer_drivers()`로 묶어 상위 4개 + "그 외 이야기"의 언급 비중을 계산하고, 직전 거래일과의 %p 델타(`▲ +13%p`)를 붙입니다. 규칙 계산 전용이며 LLM을 호출하지 않습니다.

- 브리핑과 독립: 브리핑을 생성하지 않아도 계산되고, 브리핑용 상한 잘린 선별본이 아니라 그날 문서 전체(`select_briefing_docs(strict=True)`)를 씁니다. strict를 쓰는 이유는 두 날짜를 같은 잣대로 비교하기 위해서입니다(비-strict는 pool을 오늘까지 확장해 직전 거래일 계산을 오염시킴).
- 비중 이동은 보도량 변화일 뿐 내용 변화가 아니라는 경고 문장을 UI에 고정합니다.
- 네 시장(US/KR/EUROPE/JP)을 지원하며 시장 목록은 `PRODUCT_MARKETS`에서 파생합니다.
- 표본이 작으면 비중과 %p 델타가 기사 몇 건에 좌우되므로, 문서가 `MIN_CONFIDENT_SAMPLE`(12건) 미만이면 `smallSample` 경고를 붙여 화면에 표본 수를 함께 표시합니다. 유럽·일본은 수집량이 미국·한국보다 적어 이 경로에 자주 들어갑니다.
- 응답은 (date, market) 키로 10분 캐시하고 RSS 수집 완료 시 `invalidate_story_share_cache()`로 비웁니다.
