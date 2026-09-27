# 시장 캘린더 (Market Calendar)

0.7 보존 계약: BOK ECOS 관행일은 값이 있어도 `estimated`이며 UI에 `값 확인 · 발표일 미확인`을 표시한다. 날짜가 틀린 옛 BOK 행(parser `0.4.0`, 관측월 15일 08:00 KST 합성 시각)은 삭제하지 않고 `LEGACY_BOK_ROW_SQL`로 읽을 때 뺀다. 캘린더 API·주간 브리핑·대시보드가 같은 조건을 쓴다. 대체 행이 확인된 경우에만 지우면 기준금리·옛 예정일·창 밖 과거 값이 화면에 남는다. FRED의 공통 vintage parser는 모든 개정을 보존하고 Calendar가 헤드라인 하나를 고른다. 거시 원장은 Calendar의 시각을 공식 공표 근거로 쓰지 않는다.

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 시장 캘린더 (Market Calendar)

- 로직은 `features/market_calendar/`에 둔다. `features/common/market_calendar.py`(거래일 helper)와는 별개 모듈이다.
- event kind는 `macro | central_bank | holiday | earnings | filing | dividend` 6종만 허용하고 `market-memory.sqlite3::market_calendar_events`에 upsert한다.
- `confirmed | estimated | tentative | actual`을 source tier로 결정한다. 회사 IR/공식 일정이 우선이고 yfinance/Nasdaq 등 제3자 예정치는 `estimated`로만 표시한다.
- NYSE/KRX 휴장일과 FOMC·ECB·BoE·BOJ·한국은행 금통위는 공식 발표 연간 일정을 adapter에 전사해 등재한다(confirmed + 공식 sourceUrl, 새 연도 공시 시 표만 갱신). 브리핑 세션 기준일은 코드가 결정하며, Toss Open API 거래소 캘린더가 연결되어 유효한 응답을 주면 해당 응답을 정적 휴장일 표보다 우선하고 미연결·실패·응답 불일치 시 정적 표로 fallback한다. 미국 지표 발표일은 `FRED_API_KEY`가 있을 때만 수집하고 없으면 `fred_key_required`를 남긴다. 실적/배당은 포트폴리오+워치리스트 티커 대상 yfinance estimated이며, 워치리스트 표시명은 SEC company_tickers 기반 `sec_ticker_for_name()`으로 해석한다.
- **FRED 발표 결과는 vintage로 맞춘다.** 최신 관측치를 지나간 모든 발표일에 붙이면 지난 발표가 전부 오늘의 숫자를 말한다 — 실측으로 8/12 CPI 행에 6월 관측치가, 7/2 고용 행에 7월치가 붙어 있었다. `output_type=3`(신규·개정분)의 `SERIES_YYYYMMDD` 열이 공표일이며, 발표일과 정확히 맞은 값만 붙인다. 그날 공표된 값이 없으면 비워 두고 `confirmed`로 남긴다 — 지난 값을 오늘 발표라고 말하지 않는다.
- **한국 지표는 관측월이 끝난 뒤에 놓는다.** ECOS는 발표일을 주지 않으므로 다음 달 관행일(CPI 2일, PPI 18일)에 종일 행으로 두고 시각을 지어내지 않는다. 관측월 15일에 두면 발표가 관측기간보다 앞선다. 기준금리 결정은 ECOS 월별 값에서 만들지 않고 한국은행 회의 일정표에서만 등재한다(월별 값에서 만들면 연 8회 회의가 12회가 된다).
- **지표 수집 창은 과거 45일부터 연다.** 오늘부터 시작하면 결과가 실린 발표가 하나도 안 들어와 지난달 지표가 캘린더에 없다. 게다가 집계가 최근 날짜부터 내려주므로 한 창으로 과거까지 물으면 앞쪽 페이지가 전부 미래 일정으로 차서 과거에 닿지 못한다 — **과거 구간과 미래 구간을 따로 요청한다**(실측: 26건 전부 미래 → 83건 중 과거 57건 전부 결과 포함).
- yfinance 경제 캘린더에 `Expected`(컨센서스) 열은 있으나 값이 오지 않는다(과거·미래 네 구간 600여 건 전부 결측). 그래서 화면의 결과 비교는 예상치가 아니라 **직전 값** 기준으로 읽는다. `forecastValue` 필드는 다른 provider가 컨센서스를 주면 실리도록 남긴다.
- 실적·배당 추정은 매 수집마다 티커 목록에서 통째로 다시 만들어지므로, 이번 수집에 안 나온 `estimated` 행은 갱신 실패가 아니라 **더는 성립하지 않는 행**이다(`prune_stale_estimates`). 날짜로 자르지 않는다 — 시장 판정을 고쳤을 때 `8316.T` 실적이 도쿄와 뉴욕 두 줄로 남았고 둘 다 과거 날짜였다. 공식 일정(휴장·FOMC·지표)과 확정 행은 건드리지 않는다.
- 실적·배당 행은 `companyName`을 함께 싣는다(`_company_name.py`). 일본 구성종목은 `englishName`을 우선해 `三井住友フィナンシャルグループ` 대신 읽히는 이름을 쓰고, KOSPI 구성종목은 `373220`으로 저장되므로 `.KS`/`.KQ` 형태도 함께 색인한다.
- raw page/PDF를 장기 보존하지 않고 normalized event와 source URL만 저장한다. refresh는 automation job이며 Agent를 호출하지 않는다.

