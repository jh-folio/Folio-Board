# Investment Review — Portfolio 투자 리뷰 (v2)

`data/investment-review/{date}.json`은 Portfolio 하위 탭이 읽는 날짜별 Personal
Overlay snapshot이다. 새 `portfolio_report`나 Canonical `ReportKind`는 만들지 않는다.
구조화 필드가 권위이며 `markdown`은 이를 읽기 좋게 표현한 파생 필드다.

## v2 저장·상태 계약

- v2는 `schemaVersion=2`, `sourceSchemaVersion=2`, 같은 날짜에서 단조 증가하는
  `reviewRevision`, `reviewState=draft|reviewed|stale|due`, `reviewedAt`,
  `previousReviewedAt`을 저장한다. 재생성은 `draft`로 돌아가고 이전 확인 시각만 넘긴다.
- `inputBasis`는 Portfolio revision, Thesis/Delta identity, 현재 Market State lineage,
  checkpoint watermark, 실제 사용한 Canonical identity, analytics/backtest method를
  fingerprint로 묶는다. quote/FX provider 관측 시각은 권위가 없으므로
  `marketData.status=partial`로 남긴다.
- `positionReviews`는 **현재 보유**만 다룬다. Watchlist를 합치지 않으며 내러티브
  노출은 Thesis `linked_regimes` 또는 manual regime-thesis link만 쓴다. evidence-derived
  `linkedCompanies`는 절대 연결 근거가 아니다.
- correlation/volatility contribution은 현재 holdings·통화·method/window와 맞는
  **저장된** backtest가 있을 때만 참조한다. 다시 돌리거나 수치를 꾸미지 않는다.
- 이전 비교는 같은 날 revision이 아니라 가장 최근 `date < current.date` snapshot 하나다.
  비교 불가한 legacy/identity/method 차이는 `uncertainties`로 남긴다.

v1 파일은 열 때만 `sourceSchemaVersion=1`, revision 0, legacy input basis와 stale
상태로 메모리 정규화한다. GET은 파일을 다시 쓰거나 생성하지 않는다. 명시적 `오늘 리뷰
갱신`만 v2 revision 1을 저장한다. `검토 완료`는
`POST /api/investment-review/{date}/reviewed {expectedReviewRevision}`의 CAS write이며,
상태·확인시각만 바꾼다.

직접 rules 생성은 shared artifact lock 안에서 마지막 input fingerprint를 다시 읽는다.
생성 중 입력이 바뀌면 같은 날짜의 candidate를 `stale`과
`input_changed_during_generation`으로 저장해 사용자가 원인을 볼 수 있다. 반대로 CLI Job은
staging과 promotion 사이에 오래 멈출 수 있어, promotion 직전 authority fingerprint가 다르면
`investment_review_external_input_changed_reopen_generation` conflict로 **아무 리뷰 파일도
쓰지 않고** 재생성을 요구한다. recovery도 같은 검사를 하므로 stale staged artifact를 승격하지
않는다. immutable stage manifest/journal 재설계는 이 Stage E 범위 밖이다.

Agent 반박은 `{kind: investment_review, id: date, revision: reviewRevision,
intent: challenge}`의 별도 scope다. 매 turn 정확한 파일·revision을 다시 읽고 불일치하면
`review_changed_reopen_challenge` gap만 반환한다. 일반 Portfolio 대화로 폴백하지 않는다.

## U.5 입력 범위와 표시 계약

- 새 명시적 생성은 `inputBasis.reportSelectionVersion=u5-v1`을 저장한다. 버전 없는
  기존 v2는 읽기·검토 완료·직접 저장·CLI 승격·복구 모두 기존 자료 선택과 fingerprint를
  유지한다. GET으로 옛 파일을 다시 쓰지 않는다.
- 종목 직접 기업분석/테마 자료를 시장 배경보다 먼저 선별한다. 포지션당 자료 8개,
  합집합 24개가 상한이며 `inputBasis.canonicalReports`는 실제 상세가 소비한 합집합이다.
  제목·자료 종류 같은 표시 정보는 fingerprint에 넣지 않는다.
- 상세는 최대 24포지션, 최소 목록 `positionRoster`는 최대 100포지션이다. `coverage`는
  전체·포함·제외 수를 분리한다. 상세 선별은 시계가 흘렀다는 이유만으로 fingerprint가
  바뀌지 않아야 하며, 화면의 기한 경과 우선순위는 저장 권위를 바꾸지 않는다.
- `thesisPresent`와 `latestReviewPresent`로 투자 논리 미작성, 최신 검토 미작성,
  검토 후 자료 부족을 구분한다. 읽기 실패와 옛 저장본의 미확인 상태는 false로 추정하지 않는다.
- 새 생성의 요약은 보유·상세 범위와 준비 상태·위험 판정의 규칙 집계다. 입력이 없는데
  검토 완료처럼 설명하지 않으며, 옛 저장 요약은 읽기에서 재작성하지 않는다.
- `freshness.dueCount`는 이전 검토/생성 이후 새로 도래한 항목이라는 기존 뜻을 유지한다.
  `overdueUnresolvedCount`는 저장 snapshot의 고유한 비종결 체크포인트 중 기한 경과 수다.
  날짜만 있는 기한은 한국 시간 해당 날짜가 끝난 뒤, 시각이 있는 기한은 평가 시각 이하일 때
  경과로 센다. 시차 없는 시각은 한국 시간이다. `evaluatedAt`은 서버 평가 시각이며
  기한 경과 0건이 현재 전체 미완료 0건을 뜻하지 않는다.
- Agent 반박은 정확한 날짜/revision의 최소 종목 목록·coverage·핵심 반증을 우선 보존한다.
  일반 시장/화면 보고서 맥락으로 넓히지 않으며, 입력 상한에 따른 생략은 data gap으로 밝힌다.

## 화면과 API

화면은 판단 요약·지난 리뷰 이후 변화와 핵심 반증/불확실성을 먼저 읽고 행동하는 순서다.
중요 위험은 접지 않으며 상세 포지션·연결 자료·이력은 필요할 때 펼친다. 생성·검토 완료·
정확한 날짜/revision 반박은 서로 실행 잠금을 공유한다. 빈 상태의 보유 화면 바로가기는
탭 이동만 하고 생성하거나 저장하지 않는다. 저장된 리뷰는 현재 보유가 비어 있어도 읽을 수 있다.

```text
GET  /api/investment-review            # 저장본 + read-time freshness, 생성 없음
GET  /api/investment-review/history    # 날짜별 snapshot 메타데이터
GET  /api/investment-review/{date}     # 정확한 날짜, 없으면 empty response
POST /api/investment-review/generate   # 명시적 rules-based 갱신
POST /api/investment-review/{date}/reviewed
```

# 이전 Investment Review 설명 (역사 기록 — 현재 계약 아님)

> 이 아래는 v1의 홈·캐시·API를 보존한 역사 기록이다. 현재 동작은 이 문서 맨 앞의 v2 저장·상태 계약과 5개 Investment Review API를 따른다. v1 저장본은 재작성하지 않고 읽을 때만 legacy/stale로 해석한다. Investment Context는 현재 Investment Review와 별개인 읽기 전용 projection이다.

여러 기능을 하나의 **투자 리뷰 홈**으로 집계한다.

> 최근 시장 변화가 내 투자 논리를 강화했나 약화했나? 이번 주 무엇을 확인해야 하나?

설계: 로컬 계획문서 `folio_os_roadmap_post_v1.md` §8 ·
추적: 로컬 계획문서 `IMPLEMENTATION_PLAN_POSTV1.md`

## 계층

**Personal Overlay 계층**이다. Canonical 보고서(브리핑/기업분석/테마)를 **수정하지 않고**,
사용자 데이터·기존 산출물을 연결한 개인용 리뷰를 별도 객체/화면으로만 만든다.
포트폴리오 영향은 투자 판단 보조이며 **매수/매도 지시가 아니다**.

## 집계 소스

| 섹션 | 소스 |
|---|---|
| 오늘의 시장 상태 | `market_memory.list_states`(regime_v2 momentum/confidence) |
| 내 Thesis 변화 | `thesis_tracking`(thesis + 최신 thesis_delta verdict) |
| 포트폴리오 영향 | `portfolio` + `watchlist_notes` ↔ regime/thesis 연결 |
| 이번 주 체크포인트 | Step 6 `research_schema.checkpoints`(thesis_delta + regime nextCheckpoints) |
| 연결된 내 노트 | `features/obsidian/importer/note_index.py`(importable hypothesis 노트) |

## 동작

- **LLM 없이 규칙 기반**으로 생성한다. 데이터가 없으면 빈 섹션 + warning(원문 불변).
- 집계는 주입식 순수 함수(`build_market_state`, `build_thesis_changes`,
  `build_portfolio_impacts`, `aggregate_checkpoints`, `build_linked_notes`)로 분리 — DB 없이 테스트 가능.
- **체크포인트 dedupe 키는 `(티커, 문구)`다.** thesis delta의 기본 체크포인트 문구는 모든 종목이
  같아서 문구만으로 접으면 첫 종목만 살아남고, 종목별 Investment Context 필터를 거친 나머지
  종목은 근거 없이 "확인할 체크포인트 없음"이 된다.
- **캐싱**: 일 1회 생성 후 `data/investment-review/{date}.json`. 저장본이 있으면 재사용,
  강제 재생성(`forceRefresh`) 가능, 해당 날짜 저장본이 없으면 최신 저장본 + `stale` 표시.
- **저장은 언제나 오늘 날짜다.** 집계 입력(regime·thesis·포트폴리오·워치리스트·노트)은 전부 현재
  시점 조회이며 as-of 질의 경로가 없다. `date`에 다른 날짜를 주면 결과에 "현재 데이터로 집계했다"는
  warning이 붙고, 저장은 오늘 파일로 한다 — 파일명이 곧 날짜라 다른 날짜로 저장하면 오늘의 판단이
  그 날짜의 판단으로 굳는다(미래 날짜 파일은 `_load_latest()`의 '최신 저장본' 자리까지 영구 선점한다).
  `persist=False` 렌더링(잡 준비)은 호출자가 날짜를 소유하므로 라벨을 바꾸지 않고 warning만 남긴다.
- `date` 형식은 `YYYY-MM-DD`만 받는다(`normalize_review_date`). 다른 값은 `ValueError`이며 API는 400이다.

## 홈 대시보드 구성 (UI)

투자 리뷰 뷰는 **대시보드 화면**으로 구성한다(위→아래). 별도 "오늘의 투자 리뷰" hero 카드는 두지 않고, 대시보드 본문은 현재 시장·리뷰 지표부터 바로 시작한다.

1. **바로가기 타일** — 브리핑 생성(primary)·기업분석·테마분석·RSS (각 view로 이동/실행)
2. **최근 보고서** — 최신 브리핑/기업분석/테마 카드(클릭 시 해당 탭 이동)
3. **Current Market 위젯 보드** — TradingView Market Overview/Advanced Chart 기반 사용자 위젯. 저장 브리핑 snapshot과 분리된 현재 시장 화면이며, 위젯 로드 실패 시 기존 `marketTape`를 fallback으로 표시
4. **요약 스탯 카드** — 시장 강화중·Thesis 강화/약화·포지션 긍정/주의·체크포인트 수 (`stats`)
5. **차트** — Thesis 분포·포지션 영향 도넛(SVG) + 내러티브 노출 막대 (`stats`/`exposure`)
6. **상세 카드(메인 3개만)** — 시장 상태(confidence 미터)·포트폴리오 영향·이번 주 체크포인트. 도넛과 중복되는 Thesis 변화/연결 노트는 홈에서 생략하고, 경고(`warnings`)는 있을 때만 노출.

> 차트는 외부 라이브러리 없이 인라인 SVG/CSS로 그리며 색은 팔레트 토큰(`--folio-green/gold/burgundy/ink-muted` 등)을 쓴다.
> `marketTape`는 `build_dashboard_tape()`가 계속 채운다 — US 지수/원자재는 yfinance 레벨(`^GSPC/^NDX/^DJI/^RUT/^TNX/^VIX/DX-Y.NYB/GC=F/CL=F`), 한국 수치(KOSPI·KOSDAQ·USD/KRW)는 `providers` 체인(yfinance). 현재 UI에서는 TradingView 위젯의 fallback으로만 사용하며, 위젯 데이터는 보고서 evidence나 snapshot에 저장하지 않는다.
> 포트폴리오 영향에서 한국 종목(6자리 코드)은 코드 대신 종목명으로 표시한다.
> 전역 hero(`header.hero`)는 기본 컴팩트 브랜드 바이며, 홈(대시보드)에서만 `.page.home-active`로 크게 키운다. 다른 화면은 섹션 제목이 소형 hero 역할을 한다.

## impact enum

`positive` / `watch` / `negative` / `neutral` — thesis verdict(at_risk/broken→watch,
strengthened→positive)와 regime momentum(strengthening→positive, fading/turning→watch)로 판정.

## 종목별 Investment Context (0.2.3)

`InvestmentContextService`는 포트폴리오와 워치리스트의 ticker를 기준으로 Market Memory
driver, thesis verdict, 예정 checkpoint, 연결 보고서와 Smart Collection 상태를 묶은
읽기 전용 projection을 만든다. 이 객체는 Personal Overlay/hypothesis 계층이며
Canonical 보고서나 외부 evidence를 수정하지 않는다.

- `GET /api/investment-context/summary`: 전체 ticker 수와 source/stance 집계, 점검할 context
- `GET /api/investment-context/{ticker}`: 한 ticker의 bounded context
- 포트폴리오 수량·비중·가격, native note 본문은 응답에 포함하지 않는다.
- 입력 저장소 watermark가 바뀐 경우에만 메모리 캐시를 다시 계산하며 별도 context 파일을 쓰지 않는다.
- Home, Market Memory, Smart Collection, Deep Research가 같은 projection과 route link를 재사용한다.

## 역사 기록: v1 API (현재 사용 금지)

```text
GET  /api/investment-review            # 오늘(또는 최신) 리뷰
POST /api/investment-review/generate   # 강제 재생성 (body: date, includePortfolio/Watchlist/Obsidian, useLlm, forceRefresh)
GET  /api/investment-review/{date}     # 특정 날짜 리뷰(없으면 최신 + stale)
GET  /api/investment-context/summary   # metadata-only 종목별 개인 맥락 집계
GET  /api/investment-context/{ticker}  # metadata-only 종목별 개인 맥락
```

## 테스트

```powershell
py -3 features\investment_review\tests\test_review_summary.py
py -3 features\investment_review\tests\test_portfolio_links.py
py -3 features\investment_review\tests\test_checkpoint_aggregation.py
```
