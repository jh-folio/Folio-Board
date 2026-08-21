# Research Cockpit

Dashboard는 `cockpit` 하나입니다(0.5에서 Legacy 모드 삭제). initial payload는 로컬 change projection, 시장 일정 ref, provider health, native symbol과 기존 로컬 투자 맥락만 집계하며 upstream network나 chart series를 포함하지 않습니다.

**Legacy 모드는 0.5에서 삭제했습니다.** 0.4에서 한 릴리즈 동안만 두기로 한 rollback 경로였고, Cockpit이 자리를 잡아 같은 화면을 두 벌 유지할 이유가 없습니다. 저장된 `dashboardMode: legacy`는 `cockpit`으로 승격됩니다. 사용자 설정 파일 `data/market-widget-settings.json`은 계약대로 **삭제하지 않고**, 집중 종목 fallback(`source: legacy_setting`)으로 계속 read-only로 읽습니다. 설정/Watchlist가 없으면 미국 `SPY`, 한국 `^KS11`을 사용합니다.

cockpit payload의 변화 이벤트는 `major_change | developing_signal | conflicting_uncertain`만 `changes`로 노출하고, 나머지(기준선·근거부족·변화없음)는 `quietChanges`(최대 8건)와 `changeCounts.quiet`로 분리합니다. `changeCounts`는 요약 스트립용 상태별 카운트입니다. **`quietChanges`는 0.5.0에서 화면에 없습니다** — `무엇이 달라졌나`는 의미 판정이 끝난 건(`new_information|reversal|trend_development`)만 본문에 두고 나머지는 감춥니다. 다만 판정 자체를 못 한 경우(LLM 없이 생성하면 전부 `not_evaluated`)에는 빈 상태 문구가 `변화가 없다`가 아니라 `판정하지 못한 기록이 N건`이라고 말합니다. 판정 실패를 변화 없음으로 바꿔 말하지 않기 위해서입니다. implications는 포트폴리오와 워치리스트 티커(`sec_ticker_for_name` 이름 해석 포함)를 모두 매칭하고 `source: portfolio|watchlist`를 표기합니다.

`POST /api/dashboard/settings`는 기존 저장값과 merge 후 정규화합니다(부분 갱신이 다른 키를 초기화하지 않음). 저장 키: `dashboardMode`, `calendarView`, `calendarKinds`, `calendarMarkets`, `calendarWatchlistOnly`, `calendarMinImportance`(1=전부·2=중간 이상·3=최상위만), `chartRange`, `chartStyle`, `chartSymbol`.

차트 기간은 0.5에서 `1d/1m/3m/1y/5y`로 바뀌었다(`1d`는 5분봉). `6m`을 쓰던 저장값은 정규화 때 조용히 `3m`으로 떨어진다 — `legacy → cockpit`처럼 옮겨 주는 승격 경로는 두지 않았다.

API: `GET /api/dashboard/cockpit`, `GET|POST /api/dashboard/settings`, `GET /api/dashboard/story-share?market=us|kr|europe|jp`. 기존 `GET /api/dashboard`는 그대로 유지합니다.

## 이야기 비중의 비교 기준 (0.5.4)

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

## 내용 변화 판정 (0.5.4)

`무엇이 달라졌나`의 카드는 의미 판정(`semanticVerdict`)이 끝난 변화만 보여준다. 예전에는 그 판정이 두 겹으로 막혀 있었다:

1. **Agent CLI 브리핑은 판정이 아예 돌지 않았다.** `decorate_candidate`가 `generation.mode == "llm"`일 때만 평가를 불렀는데 Agent 산출물의 mode는 `agent`다(`agent_mode/schema.py::agent_generation`). `SEMANTIC_GENERATION_MODES`로 둘 다 통과시킨다.
2. **`semantic.py`가 API 키만 봤다.** CLI 모드에서는 키가 없는 것이 정상이라 이중으로 막혔다. 키가 없으면 Agent bridge로 같은 판정 프롬프트를 보낸다.
   - **그 호출은 `serialize=False`다.** `bridge._RUN_SEMAPHORE`는 `threading.Semaphore(1)`이라 재진입이 안 되고 acquire에 타임아웃도 없다 — 브리핑 생성 잡은 커밋까지 통째로 그 세마포어 안에서 도는데, 판정이 그것을 다시 잡으면 그 잡이 영원히 멈춘다.
   - 판정 실패는 `not_evaluated`일 뿐 커밋을 무너뜨리지 않는다(기존 계약).

**화면은 "판정됨"과 "미판정"을 가른다**(`summarizeChangeEvents`). 예전에는 confirmed가 아닌 것을 전부 미판정으로 세서, `coverage_shift_only`·`no_new_information`처럼 **정상적으로 판정이 끝난** 날에도 "판정하지 못했다"고 말하고 이미 연결된 AI Agent를 연결하라고 안내했다. 의미 비교는 브리핑 변화 단위에만 걸리므로 다른 아티팩트는 verdict가 없는 것이 정상이고 미판정으로 세지 않는다. Agent가 연결돼 있으면 연결 안내 대신 다음 생성에서 판정된다고 말한다.

## 오늘의 이야기 비중 (story_share.py)

"무엇이 달라졌나" 패널 상단의 얇은 누적 막대와 범례입니다. 그날 수집된 articles/rss 시장 관련 문서 전체를 `infer_drivers()`로 묶어 상위 4개 + "그 외 이야기"의 언급 비중을 계산하고, 직전 거래일과의 %p 델타(`▲ +13%p`)를 붙입니다. 규칙 계산 전용이며 LLM을 호출하지 않습니다.

- 브리핑과 독립: 브리핑을 생성하지 않아도 계산되고, 브리핑용 상한 잘린 선별본이 아니라 그날 문서 전체(`select_briefing_docs(strict=True)`)를 씁니다. strict를 쓰는 이유는 두 날짜를 같은 잣대로 비교하기 위해서입니다(비-strict는 pool을 오늘까지 확장해 직전 거래일 계산을 오염시킴).
- 비중 이동은 보도량 변화일 뿐 내용 변화가 아니라는 경고 문장을 UI에 고정합니다. 내용 판정은 Change Intelligence의 의미 비교가 담당합니다.
- 네 시장(US/KR/EUROPE/JP)을 지원하며 시장 목록은 `PRODUCT_MARKETS`에서 파생합니다.
- 표본이 작으면 비중과 %p 델타가 기사 몇 건에 좌우되므로, 문서가 `MIN_CONFIDENT_SAMPLE`(12건) 미만이면 `smallSample` 경고를 붙여 화면에 표본 수를 함께 표시합니다. 유럽·일본은 수집량이 미국·한국보다 적어 이 경로에 자주 들어갑니다.
- 응답은 (date, market) 키로 10분 캐시하고 RSS 수집 완료 시 `invalidate_story_share_cache()`로 비웁니다.

## 내용의 변화 카드

변화 피드는 최근 14일(`CHANGE_FEED_WINDOW_DAYS`) 안의 이벤트만 보여준다. 더 오래된 행과 권위 저장소는 그대로 두고 피드 projection만 좁힌다. 같은 날짜에 구형 통합 id(`2026-08-05`)와 시장별 id(`2026-08-05.us`)가 함께 있으면 통합 행을 피드에서 숨긴다 — 0.4→0.5 id 전환으로 남은 행이라 시장별 행이 그 날짜의 현재 세대다.

변화 피드는 `semanticVerdict` 칩(새 정보/방향 전환/흐름 진전/보도량 이동/변화 없음/내용 미평가)이 붙은 카드로 렌더링합니다. 카드 본문의 `펼치기`는 항목별 직전/현재 대조(순위·비중, 대표 기사 제목 양쪽)를 인라인으로 보여주고, `Agent에게 묻기`는 카드가 아는 사실(전/후 값·분류·근거 제목·기준 id)을 질문으로 만들어 우측 Agent dock을 엽니다(`openReactAgentDock`, 자동 제출 없음). 상세 데이터는 change 이벤트 payload(`changedItems[].contextDocs/previousContextDocs/semanticNote`)에 이미 실려 있어 별도 상세 API가 없습니다.
