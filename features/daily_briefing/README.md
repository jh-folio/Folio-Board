# 일일 브리핑

이 기능은 `research-inbox/articles`와 `research-inbox/rss`의 최신 뉴스 자료를 바탕으로 일일 시장 브리핑을 생성하고 날짜별로 저장합니다.

## 담당 범위

- 오늘 또는 선택 날짜의 브리핑 생성
- 과거 브리핑 조회
- LLM 브리핑과 규칙 기반 fallback
- 브리핑용 웹 검색 보완 ON/OFF
- 0.2 기본 시장 가격 스냅샷 보조(yfinance). Toss Open API 어댑터는 숨김 내부 경로로만 유지
- provider 기반 한국장 시장 수치 보조(yfinance)
- 최근 반복된 시장 흐름 참고

## 시장 범위와 출력 계약

생성 API는 `marketScope: us | kr | both`를 받습니다. 각 시장은 기존 `0~6 + 오늘의 결론`, 주도 기업 2개, 참고자료 구성을 그대로 유지하며, 모든 주요 섹션은 `한 줄 결론 + 가운뎃점 3~4개 + 줄글` 순서로 생성됩니다. 저장 JSON의 `briefings.us`와 `briefings.kr`에는 시장별 markdown·세션·기준일·출처와 `marketScope`, `briefingType`, `generatedAt`, `sessionDate`, `title`, `summary`, `tags`가 따로 남고, 기존 소비자는 결합 `markdown`을 계속 읽을 수 있습니다.

부분 시장 재생성은 같은 날짜의 반대편 시장 결과를 보존합니다. Canonical 본문이 바뀌면 기존 `personalOverlay`도 삭제하지 않고 `stale: true`로 표시합니다. 시장 내러티브 누적은 중복을 막기 위해 `both` 생성에서만 수행합니다.

## 이슈·출처 선별

`issue_selection.py`는 기사를 먼저 보수적으로 사건 단위로 묶고, 같은 매체의 반복 기사와 재전송본을 한 표로 계산합니다. 미국장은 Reuters·WSJ·FT·Bloomberg 등 해외 핵심 매체와 미국 시장 반응을 우선하고, 한국장은 국내 수급·환율·업종 전문성을 유지하면서 해외 핵심 매체의 독립 보도를 `internationalSalience`로 반영합니다.

LLM 입력과 표시 참고자료에는 같은 evidence lane·cluster dedupe·매체별 soft cap을 적용합니다. 시장 반응 자료가 없으면 영향 0으로 간주하지 않고 `marketImpactStatus: unavailable`과 `dataGaps`를 남깁니다. 공개 RSS에는 연합뉴스와 매일경제 공식 피드가 추가되었으며 유료 본문 우회 수집은 하지 않습니다.

## 브리핑 종류 — 일간과 주간 (0.5.4)

브리핑에는 **종류**(`kind`)가 있고 `daily`와 `weekly` 둘이다. 편집 강조점(`briefingType`)과 직교한다 — 그쪽 세 값은 모두 "기존 섹션 구성을 유지하라"고 지시하므로, 골격이 다른 주간을 그 enum에 넣으면 계약이 자기 자신과 모순된다. **저장된 예약과 보고서에 이 값이 없으면 일간이다**(판올림 호환).

- **저장 키가 갈린다.** 주간은 `{발행일}.{시장}.weekly.json`이다. 접미사가 없으면 일요일 실행에서 `_scope_session_date()`가 금요일을 돌려줘 그 주 금요일 일간 브리핑을 통째로 덮어쓴다 — 이번 릴리즈에서 가장 위험했던 충돌이다. 파일 이름 규칙은 `schema.py::_scoped_file_stem()`, 아카이브 정규식(`archive.py`), `canonical_identity.BRIEFING_KIND_SUFFIXES` 셋이 함께 알아야 한다. 마지막 것을 빼먹으면 저장이 정체성 검증에서만 조용히 막힌다.
- **주간에는 세션이 없다.** 발행일이 곧 저장 키이고 제목은 `{라벨} 주간 — {MM.DD}~{MM.DD}`다. `마감`/`장중`을 붙이지 않고, 세션 제목 정규화(`normalize_briefing_markdown_titles`)를 태우지 않는다 — 태우면 구간이 세션일로 바뀌어 보고서가 스스로를 잘못 소개한다.
- **자료 창은 달력 7일이다**(`weekly.py::WeeklyWindow`). 발행일 기준 `P-6 … P`이며, 시장마다 창을 다르게 잡지 않는다. **비어도 넓히지 않는다** — 일간의 세션 창은 비면 예전 풀로 되돌아가지만, 주간에서 창을 넓히면 "지난주"라는 말이 거짓이 된다.
- **다음주 프리뷰는 시장 캘린더에서 온다.** `weekly.calendar_preview()`가 그 시장 + `GLOBAL` 일정을 `macro/central_bank/holiday/earnings/dividend` 다섯 종으로 읽어 표로 싣고, `confirmed`/`estimated` 구분을 그대로 남긴다. 프롬프트와 컨텍스트 양쪽이 "표에 없는 일정을 기억으로 채우지 말라"고 못박는다 — 프롬프트에만 적으면 부탁이지 제한이 아니다.
- **주간은 시장 내러티브에 적재하지 않는다.** 같은 이슈를 일간이 이미 그 주에 넣었고, 다시 넣으면 한 사건이 두 번 세어져 regime 근거 카운트가 부푼다. `AGGREGATE_SCOPES` 게이트 앞에서 명시적으로 끊는다.
- **주간은 세션 시각자료를 만들지 않는다.** 시각자료는 하루 세션의 가격 계열과 히트맵이라, 한 주를 덮는 보고서에 붙이면 특정 하루가 그 주를 대표하는 것처럼 읽힌다. 주간 차트는 별도 설계가 필요하다.
- **프롬프트는 별도 파일 넷이다**(`prompt_weekly_{us,kr,europe,jp}.md`). 일간 프롬프트에 "이번엔 주간으로 써라"를 덧붙이는 방식은 두 지시가 충돌한다 — 일간은 제목에 세션 상태를 붙이라고, 오늘 하루를 하나의 이야기로 엮으라고 지시한다. 계약 검사도 갈린다(`contracts.py::weekly_prompt_contract_errors`, `briefing_contract.weekly_required_sections`).
- **규칙 fallback은 사실만 싣는다.** `weekly.build_weekly_rules_markdown()`은 자료 건수·동인 목록·이슈 묶음·내러티브 상태·다음주 일정 표를 담고, 해석 문장이 비어 있다는 사실을 본문에 적는다. 한 주의 이야기를 엮는 일은 LLM 산출물이고, 규칙이 흉내 내면 근거 없는 문장이 남는다(§5 원칙 3·4).
- **아카이브 카드가 갈린다.** dedup 키는 `(세션일, 시장, 종류)`다. 주간의 구간 끝은 그 시장의 세션일과 같은 날일 수 있어, 종류가 없으면 둘 중 하나가 조용히 사라진다. 화면 해시도 `#/briefing/{date}/{scope}/{kind}`로 종류를 싣는다 — 없으면 주간 카드를 눌러도 그날 일간 브리핑이 열린다.
- **삭제도 종류를 본다.** `DELETE /api/briefings/{date}?kind=weekly`는 주간 파일만 지운다. 종류를 무시하면 주간 카드의 삭제가 그날 일간 브리핑을 지운다.

## 개수 상한은 한 곳에서 나온다 (0.5.4)

`features/daily_briefing/limits.py`가 선별 파이프라인의 상한을 소유한다. 예전에는 `limit=14`가 기본 인자 여섯 곳과 호출부 전부에 흩어져 있어 어느 하나를 고쳐도 나머지가 그대로였다.

```text
이슈 ISSUE_COVERAGE_LIMIT(10)  →  다양성 선발 DIVERSE_SELECTION_LIMIT(18)
  →  컨텍스트 CONTEXT_DOC_LIMIT(24, 주간 40)
  →  참고자료 SOURCE_REF_LIMIT(= 컨텍스트와 같은 값)
  →  다시장 병합 = 시장 수 × 시장당 상한
```

- **참고자료는 프롬프트가 본 문서 전부다.** 예전에는 컨텍스트 24건 중 14건만 보여줘, 근거로 쓰였을 수 있는 열 건이 출처 목록에 없었다 — source-grounding 원칙과 어긋난다. 표시 개수 설정은 만들지 않는다(일치가 기본이면 설정할 것이 없다, 2026-08-20 사용자 결정).
- `source_lines()`의 기본값이 8이라 `build_prompt_markdown()`이 인자 없이 불러 **규칙 경로는 14건을 뽑아 놓고 8건만 출력했다.** 기본값을 `SOURCE_REF_LIMIT`으로 바꾸고 호출부도 명시한다.
- 병합 상한 28은 이미 잘라먹고 있었다. 네 시장이면 시장당 상한만 곱해도 그 두 배가 넘어 뒤에 오는 시장의 출처가 통째로 빠졌다. 시장 수에서 산출한다(`merged_source_limit`).

## 시장 범위와 저장

생성 대상은 **시장 집합**입니다. 화면에서 미국장·한국장·유럽장·일본장을 원하는 만큼 골라 생성하면 고른 시장이 각각 만들어집니다. 최소 한 개는 선택되어 있어야 합니다.

API는 `markets: ["us","jp"]`를 받고, 예전 `marketScope: us | kr | europe | jp | all | both`도 계속 받습니다(집합으로 풀어서 처리).

- **`all`은 네 시장, `both`는 미국·한국 두 시장**입니다. `both`로 저장된 예전 보고서는 유럽·일본을 담은 적이 없으므로 소급해서 넓히지 않습니다. 넓히면 생성된 적 없는 커버리지를 주장하게 됩니다.
- **이름 없는 조합은 `multi`** 입니다(예: 미국+일본). 조합마다 이름을 만들면 추측이 자리만 옮기므로, 레이블은 표시용이고 실제 커버리지는 저장된 시장 목록(`generationMarkets` / `includedMarkets`)이 말합니다.
- 알 수 없는 값은 `both`로 정규화합니다. 오타가 네 시장 생성으로 확대되지 않게 하기 위해서입니다.

저장 위치:

```text
data/briefings/{date}.us.json
data/briefings/{date}.kr.json
data/briefings/{date}.europe.json
data/briefings/{date}.jp.json
data/briefings/{date}.link.json      # 시장 간 연결 분석
data/briefings/{date}.json           # 통합 보고서(레거시 결합본 포함)
```

통합 보고서는 `includedMarkets`(실제로 생성된 시장)와 `expectedMarkets`(요청한 시장)를 함께 저장합니다. 범위 이름만으로 커버리지를 추측하지 않게 하기 위해서입니다. 예를 들어 유럽 생성이 실패한 `all` 요청은 범위는 그대로 `all`이지만 `includedMarkets`가 세 개이고 `coverageWarnings`가 빠진 시장을 밝힙니다.

아카이브 카드는 **항상 시장별 한 장**입니다. 다중 시장 생성이라도 접지 않습니다 — 접힌 카드는 모든 시장을 이어 붙인 합본으로 열려서, US+KR을 함께 예약하면 각 시장 보고서를 화면에서 읽을 수 없었습니다(2026-08-10 사용자 결정).

아카이브 질의의 `marketScope=all`은 **"시장 필터 없음"**이고 브리핑 범위의 `all`과 다른 말입니다. 다중 시장 카드만 보려면 `aggregate`를 씁니다.

## 시장별 프롬프트와 규칙 경로

현재 active prompt는 시장마다 하나씩입니다.

```text
features/daily_briefing/prompt_us.md
features/daily_briefing/prompt_kr.md
features/daily_briefing/prompt_europe.md
features/daily_briefing/prompt_jp.md
```

통합 범위는 해당 시장의 프롬프트를 이어 붙입니다(`both`는 미국·한국 둘, `all`은 넷). 네 프롬프트는 같은 섹션 골격(`0~6 + 오늘의 결론 + Source & Data Notes`), 같은 자료 우선순위, 같은 no-fabrication·data gap 규칙을 유지합니다.

**시장별로 다른 것은 그 시장의 실제 구조입니다.**

- **유럽**은 한 나라가 아닙니다. 영어 자료가 압도적으로 많아 아무 조정 없이 쓰면 브리핑이 조용히 "영국 뉴스 + 유로 단어 몇 개"가 됩니다. 프롬프트가 광역 지수와 국가 지수를 구분하게 하고, **통화가 둘(GBP·EUR)**, **정책 주체가 둘(ECB·BoE)**, 거래소 휴장이 갈리는 날이 있다는 것을 명시합니다.
- **일본**은 한국과 같은 시간대라 세션 단계(`pre_open | intraday | closed`)를 따릅니다. "아시아 증시" 광역 기사를 일본장 근거로 쓰지 않으며, 엔화가 수출 기업과 내수에 반대로 작용하는 두 경로를 함께 보게 합니다.

### 번역은 파생 텍스트이지 새 출처가 아닙니다

현지어(독·프·네·이·서·일) 자료를 근거로 쓰고 한국어로 옮겨 해설할 수 있습니다. 다만 번역에 근거해 수치·방향·인용을 주장하면 **그 주장이 기댄 원문 문장을 그대로** 함께 남깁니다(요약이 아니라 원문 조각). 규칙 기반 품질 게이트는 근거 개수와 섹션 존재를 셀 뿐 "이 한국어 문장이 저 일본어 문장을 옳게 옮겼는가"를 판정하지 못하므로, 검증을 사람이 할 수 있는 형태로 남기는 것입니다.

**LLM 키가 없으면 유럽·일본 브리핑은 한국어 해설이 생성되지 않습니다.** 규칙 경로는 번역을 하지 않기 때문에 번역되지 않은 헤드라인, 정규화된 수치, 구조화된 갭만 남습니다. 설계상 수용한 한계이며 미국·한국의 키 없는 동작은 지금과 같습니다.

### 규칙 경로의 시장별 문장

규칙 경로는 시장 간 유보 문장과 결론 문장을 시장별로 다르게 씁니다. 유럽·일본 브리핑에 "미국장과 한국장의 연결성은..." 문장이 그대로 나가면 그 보고서가 **다루지도 않은 두 시장에 대한 유보**를 다는 셈이기 때문입니다. 같은 이유로 한국장 수치 섹션은 한국장을 포함한 범위에서만 만듭니다.

### 마감/장중은 언제 정해지는가

제목의 `마감`/`장중`은 보고서에 저장된 값이 아니라 **읽을 때마다 다시 계산됩니다**. 그래서 판정 규칙이 한 곳에만 있어야 합니다.

- 생성 시각(`as_of`)이 권위입니다. 두 생성 경로(`builder`, Agent writeback) 모두 생성 시각을 `briefing_market_windows()`에 넘겨 `krSessionPhase`를 window에 새깁니다.
- Agent writeback은 `sessionModes`를 보고서에 함께 저장합니다. 저장하지 않으면 읽을 때마다 다시 추측하게 되고, 추측이 틀리면 브리핑이 스스로 어느 세션을 다뤘는지 잘못 말합니다.
- phase가 없는 예전 보고서는 `_effective_market_windows()`가 `generatedAt`으로 window를 재정렬합니다. 벽시계를 쓰면 11시에 만든 진짜 장중 브리핑이 저녁에 마감으로 바뀌어 그것도 사실과 어긋납니다.
- 그래도 phase를 알 수 없으면 **마감**입니다. `krCurrentSessionDate`가 있다는 것은 그날이 거래일이라는 뜻일 뿐 장이 열려 있다는 뜻이 아닙니다. 이 한 줄이 "거래일이니 장중"이었을 때, 한국장 브리핑은 날짜와 무관하게 열 때마다 `장중`으로 되살아났습니다.

`kr_session_phase(as_of=None)`은 달력 fixture 조회용으로 legacy 응답을 유지합니다. 사용자가 보는 값을 정하는 경로는 모두 실제 시각으로 phase를 해석하므로 이 기본값에 기대지 않습니다.

### 시장별 세션 기준일

브리핑이 다루는 거래일은 시장마다 다르게 정합니다.

| 시장 | 기준일 | 이유 |
| --- | --- | --- |
| 미국 | `usRegularSessionDate` (D-1) | 한국시간 자정 이후 마감 |
| 유럽 | `marketSessions.europe.sessionDate` (D-1) | 런던 16:30 = KST 다음날 00:30 |
| 한국 | `krCurrentSessionDate` 또는 직전 | 생성 시각으로 장중/마감 판정 |
| 일본 | `marketSessions.jp.sessionDate`, 장중이면 브리핑일 | JST가 KST와 같아 한국과 나란히 흐름 |

일본은 장중 예외가 하나 있습니다. `marketSessions.jp.sessionDate`는 장중일 때 직전
**완료** 세션을 담으므로 그 값을 그대로 쓰면 장중 생성분이 전날 세션 키로 저장돼 이미
저장된 그 세션의 마감 브리핑을 덮어씁니다(제목도 이미 끝난 세션을 `장중`이라고 말합니다).
한국장의 `krCurrentSessionDate`가 이미 "장중이면 당일"이므로 일본도 같이 흐릅니다.
유럽은 한국시간 자정 이후 마감이라 `phase` 키 자체가 없고 이 예외에 걸리지 않습니다.

유럽·일본이 한국의 window 키로 흘러가면 유럽 브리핑에 한국 세션일이 찍힙니다.

## 시장 간 연결 분석은 제거됐습니다

통합 생성이 만들던 `{date}.link.json`과 그 본문은 0.5에서 제거했습니다.

동인 분류가 7종(금리·환율/달러·반도체AI·원자재/유가·수급·정책/규제·실적/가이던스)뿐이라, 시장이 늘수록 **모든 시장이 모든 동인을 공유**하는 쪽으로 수렴했습니다. 네 시장 실측에서 "공통 흐름"에는 동인 4종이 전부 네 시장 이름을 달고 올라온 반면, 정작 정보인 "시장별 고유 동인"은 비었습니다. "네 시장이 다 반도체/AI로 움직였다"는 말은 맞지만 읽을 가치가 없습니다.

- 이미 저장된 `{date}.link.json`은 **지우지 않습니다**. 읽지 않을 뿐이며, 브리핑 날짜 전체를 삭제하면 함께 정리됩니다.
- `split_market_markdown`은 예전 연결 요약 제목을 계속 인식합니다. 못 알아보면 그 본문이 앞 시장 섹션에 딸려 들어갑니다.
- 시장 간 관계는 각 시장 프롬프트 안에서 "해석에 필요한 만큼만" 다루는 계약으로 남습니다.

## 생성 당시 시각 스냅샷

브리핑 생성 시 `visualRecommendations`와 `visualSnapshots`를 함께 만듭니다. 선택 지수와 주도 기업은 무료·무키 경로로 생성 세션의 5분봉과 최대 1년 일봉을 저장하며 반드시 `marketSessionDate` 이후 행을 제거합니다. 1D는 5분봉, 1M·3M·YTD·1Y는 저장된 일봉에서 화면이 파생합니다. provider, 실제 `asOf`, freshness, coverage, timezone, currency를 저장하고 기준일보다 데이터가 오래됐거나 일부 종목이 누락되면 상태와 경고를 표시합니다. 시각자료 수집 실패는 Canonical markdown 생성을 막지 않습니다.

당일 한국장 브리핑을 09:00 KST 전에 생성하면 분석 창의 `krCurrentSessionDate`는 당일을 유지하더라도 차트 snapshot은 아직 시작하지 않은 세션을 요청하지 않고 직전 한국 거래일을 사용합니다. 개장 후에는 당일 5분봉을 사용합니다.
일봉 provider 반영이 늦고 같은 세션의 5분봉이 있으면 해당 5분봉의 OHLCV를 집계해 마지막 일봉을 보완합니다. 이 파생 행은 provider에 `intraday_aggregate`를 명시합니다.

### 대표 지수와 통화

대표 지수는 `features/common/markets.py`의 `MARKET_REGISTRY`가 단일 출처입니다. `IndexDescriptor`가 티커·표시명·통화·시간대·국가를 함께 들고 있고, `INDEX_UNIVERSE`는 이 목록에서 파생합니다. 지수를 더하거나 빼려면 레지스트리만 고칩니다.

| 시장 | 기본 차트 지수 | 통화 |
| --- | --- | --- |
| 미국 | S&P 500, Nasdaq, Dow Jones | USD |
| 한국 | KOSPI, KOSDAQ | KRW |
| 유럽 | STOXX Europe 600, FTSE 100, DAX, CAC 40, AEX | EUR + **GBP** |
| 일본 | Nikkei 225, TOPIX 추종 ETF(1475) | JPY |

유럽은 통화가 하나가 아닙니다. FTSE 100은 GBP, 나머지는 EUR로 표시되므로 스냅샷 하나에 통화 하나를 붙이면 축의 숫자에 대해 거짓을 말하게 됩니다. 그래서 **통화는 시리즈마다** 저장하고, 스냅샷에는 `currencies` 목록을 둡니다. 스냅샷의 `currency`는 통화가 하나일 때만 그 값이고 섞이면 `MIXED`입니다. 실제로 그려진 시리즈만 통화를 주장하므로, GBP 지수가 빠지면 `currencies`에서도 GBP가 빠집니다.

FTSE MIB(이탈리아)와 IBEX 35(스페인)는 레지스트리에 대표 지수로 남지만 기본 선 차트에서는 뺍니다(`in_default_chart=False`). 선 7개는 읽히지 않습니다.

TOPIX는 yfinance에 지수 심볼이 없어(`^TPX`·`^TOPX` 모두 빈 응답) 추종 ETF로 대신 그립니다. 이 시리즈는 `proxyFor`와 경고로 ETF임을 밝히며, 지수라고 표기하지 않습니다.

지수 하나가 실패해도 브리핑은 실패하지 않습니다. 해당 심볼만 `coverage.missingSymbols`로 빠지고 나머지 지수는 그대로 그려집니다.

### 히트맵 universe

| 시장 | universe | 상자 크기 기준 |
| --- | --- | --- |
| 미국 | S&P 500 | `market_cap` (USD) |
| 한국 | KOSPI 200 | `market_cap` (KRW) |
| 유럽 | FTSE 100 + DAX + CAC 40 + AEX 합성 199종목 | `market_cap_eur` |
| 일본 | 닛케이 225 | `market_cap_jpy` |

유럽 상자는 **EUR로 환산한** 시가총액입니다. 런던 종목은 GBP로 오기 때문에 환산 없이 더하면 영국 기업이 환율만큼 부풀어 오릅니다. 스냅샷은 `weightBasis`와 그 기준 통화를 함께 저장하므로, 화면이 크기를 읽을 때 무엇으로 잰 크기인지도 함께 읽습니다. 시장 기본 통화를 쓰지 않는 이유도 같습니다 — 유럽의 기본 통화 하나를 붙이면 절반이 틀립니다.

에어버스(DAX·CAC 40)와 아르셀로미탈(CAC 40·AEX)처럼 두 지수에 든 기업, 셸·유니레버·RELX처럼 런던과 암스테르담에 이중상장된 기업은 한 상자로 접습니다. 접지 않으면 같은 기업이 두 번 그려져 섹터 비중까지 부풀어 오릅니다.

유럽 일봉은 마감 직후 provider 반영이 늦습니다(런던 16:30 마감 = KST 다음날 00:30). 세션일 종가가 아직 없으면 마지막 정상 스냅샷으로 되돌아가 `stale`로 표시하고, 그것도 없으면 `unavailable`로 둡니다. 전일 종가를 당일 세션 종가로 붙이지 않습니다.

가격 series는 보고서 JSON에 inline 저장합니다. 히트맵 상세 rows는 compact gzip `data/briefings/{date}.visuals.json.gz` 사이드카에 저장하고 보고서는 `sidecarRef`만 가집니다. 기존 `.visuals.json`은 읽기 호환합니다. 일부 시장만 재생성하면 반대편 시장의 snapshot과 사이드카 rows를 보존합니다. 따라서 과거 브리핑은 provider를 다시 호출하지 않고 생성 당시 데이터를 재현할 수 있습니다.

| 위치 | 분석 질문 | 차트 계약 | 핵심 필드 |
| --- | --- | --- | --- |
| 시장 요약 | 주요 지수의 세션 전 움직임은 어땠는가 | Focus price / line·candle | `intraday(5m)`, `daily(1d)`, `ticker` |
| 주도 기업 ①·② | 주도주의 최근 가격 경로는 어땠는가 | Focus price / line·candle | `time`, OHLCV, `subject` |
| 시장 히트맵 | 전체 시장의 상승·하락과 시가총액 집중은 어디였는가 | Sector→industry→ticker treemap. 단, `sector`와 `industry`가 같은 KR 행은 중복 산업 단계를 생략해 Sector→ticker로 표시 | `sector`, `industry`, `changePct`, `marketCap` |

좁은 화면(폭 520px 미만)에서는 히트맵을 한 층씩 봅니다. 375px 폰에서 재보면 전체 지도(637타일)의 92%가 라벨을 담을 수 없는 크기라 색만 남습니다. 섹터부터 보여주고 칸을 누르면 산업→종목으로 들어가며, 히트맵 위 경로(`전체 › Technology › Semiconductors`)로 되돌아옵니다. Plotly 자체 pathbar는 좁은 화면에서 18px짜리 빈 띠라 쓰지 않습니다. 층을 옮기면 글자 크기를 그 층의 형제 기준으로 다시 계산합니다 — 전체 기준 크기를 그대로 두면 섹터에 들어간 산업들이 화면을 가득 채우고도 6px 이름표를 들고 옵니다(`compactLevelText`).

미국 지수 차트는 **S&P 500 → Nasdaq → Dow Jones** 순서로 표시합니다. `Nasdaq`은 뉴스에서 일반적으로 말하는 Nasdaq Composite(`^IXIC`) 기준이며, Nasdaq 100(`^NDX`)이 아닙니다. 한국 지수는 KOSPI·KOSDAQ 종합(`^KQ11`)을 사용합니다. KOSPI 200은 KOSPI와 같은 선을 한 번 더 그리는 셈이라 두 번째 선을 코스닥으로 바꿔 두 시장이 갈리는 날을 보이게 했습니다(0.5). 히트맵은 **미국은 S&P 500 구성종목, 한국은 KOSPI 200 구성종목**으로 한정하며 KOSDAQ은 제외합니다. 미국 히트맵의 종목·섹터·산업 분류는 `config/sp500_constituents.json`에 내장한 **GICS Sector / Sub-Industry**(finviz와 동일한 익숙한 분류)를 사용하고, 시가총액(박스 크기)도 이 파일의 스냅샷을 씁니다. 한국 히트맵도 `config/kospi200_constituents.json`의 KOSPI 200 구성종목과 시가총액 스냅샷을 기본 universe로 사용합니다. KR 행에서 산업명이 섹터명과 같거나 비어 있으면 화면에서는 산업 단계를 만들지 않고 종목을 섹터 바로 아래에 배치해 중복 라벨 공간을 줄입니다. 0.2 기본 실행에서는 yfinance 일봉을 사용하고, 전일가·미지원/누락 종목은 저장된 마지막 정상 snapshot으로 보완합니다. 두 universe 파일은 각각 `py -3 -m features.common.market_data.sp500_universe`, `py -3 -m features.common.market_data.kospi200_universe`로 주기적으로 갱신합니다. Toss Open API 가격 보강은 `FOLIO_ENABLE_TOSS_OPEN_API=1`을 켠 내부 검증 경로로만 남겨둡니다.
미국 히트맵은 `GOOGL/GOOG`, `FOXA/FOX`, `NWS/NWSA`, `BRK.A/BRK.B`처럼 같은 기업의 복수 종류주식이 universe에 함께 있으면 한 기업 타일로 합쳐 표시합니다. 타일 크기는 중복 합산하지 않고 대표 회사 시가총액(max)을 쓰며, 등락률은 종류주식별 시가총액 가중 평균으로 계산합니다.

히트맵 글자 크기는 박스 면적(시가총액)에 비례해 조정되어, 대형주는 티커가 크게 보이고 소형주도 작게나마 티커가 노출됩니다(finviz 스타일).

## 사용 자료

브리핑은 뉴스 자료만 사용합니다.

```text
research-inbox/articles/
research-inbox/rss/
```

`filings`와 `reports`는 브리핑에 직접 사용하지 않습니다.

## 한미 시장 시차 기준

한국시간 아침/오전 브리핑은 단일 날짜 기사만 보지 않습니다. 브리핑 대상일이 `D`이면 앱은 기본적으로 `D-1`과 `D` 자료를 함께 후보로 봅니다.

- 미국장: `D-1` 미국 정규장 마감 결과를 우선 사용
- 한국장: `D-1` 한국 정규장 결과와 `D` 한국장 개장 후/장중 시황을 구분해서 사용
- `D-1` 미국장 마감 이후 나온 뉴스는 `D-1` 한국장에 이미 반영됐다고 쓰지 않음
- `D` 한국장 장중 기사, 수급, 업종 반응이 있을 때만 한국장이 반영하기 시작했다고 표현

LLM 컨텍스트에는 각 자료의 `시장시간대`가 붙고, provider가 성공하면 `## 한국장 시장 수치` 블록이 추가됩니다.

```text
US 전일 정규장
KR 전일 정규장
KR 당일 개장/장중
전일 글로벌 자료
당일 최신 자료
```

### 기사 발행일 vs 시장 거래일(`marketSessionDate`)

한국 언론의 `뉴욕증시 마감/브리핑` 기사는 한국시간 D일에 발행돼도 보통 미국 **D-1** 정규장 결과를 다룹니다. 발행일(`date`)을 그대로 미국장 거래일로 쓰면 전 거래일 결과를 당일 결과로 오인합니다(예: 6/9 발행 "나스닥 0.9%↑"는 실제 미국 6/8 장).

- `selection.py::infer_market_session_date(doc, market_windows)`가 선별 단계에서 각 자료의 실제 시장 거래일을 추론합니다. 한국 언론 뉴욕증시 마감 기사(`is_us_market_close_article`)는 발행일 직전 미국 거래일로 보정하고, 그 외는 발행일을 그대로 씁니다. `app.py::build_briefing()`이 docs에 `marketSessionDate`를 주입합니다.
- `doc_market_bucket()`은 `date`보다 `marketSessionDate`를 우선 사용합니다.
- `build_llm_context`는 미국 정규장 당일(`usRegularSessionDate`) 마감 시황 기사(`is_us_market_close_article` 기준)를 컨텍스트에 반드시 시드로 포함하고, 각 자료 줄에 `시장기준일(추정)`을 표기합니다. 프롬프트/지침은 "미국장 결과 수치는 `marketSessionDate == usRegularSessionDate`인 자료 또는 스냅샷 기준일이 일치할 때만 사용, 둘 다 없으면 확인되지 않는다고 명시"하도록 강제합니다.

## 브리핑 대상일별 분석 우선순위

`briefing_market_windows(date)`는 브리핑 대상일의 시장 개장 상태로 `analysisMode`를 정하고, 분석축 우선순위(`primarySessions`/`secondarySessions`/`sessionRoles`), 주말·휴장 새 뉴스 구간(`offSessionNewsWindow`, `weekendOrHolidayNewsMode`), 사람이 읽는 `sessionPriorityRule`을 함께 반환합니다. "가장 최근 마감한 시장"만 기계적으로 요약하지 않고, 모드에 맞는 주 분석축을 먼저 정합니다.

세션 기준일은 Agent/LLM이 정하지 않고 `features/common/market_calendar.py`가 결정합니다. Toss Open API가 활성화되고 자격증명이 연결된 환경에서는 `/api/v1/market-calendar/{KR|US}`의 해당 날짜 개장 여부와 직전 영업일을 정적 휴장일 표보다 우선합니다. API 미연결, 요청 실패, 날짜 불일치 또는 검증할 수 없는 응답이면 기존 정적 캘린더로 자동 복귀합니다. 판정에 사용한 provider는 `marketWindows.calendarProviders`에 남깁니다.

독자용 시장별 제목은 발행일이 아니라 **시장 세션일 + 상태**를 사용합니다. 예: `US Market Briefing — 2026.08.03 마감`. 한국장은 생성 시각(KST)을 함께 판정해 09:00 전에는 `Korea Market Briefing — 2026.08.03 마감`, 09:00~15:30에는 `Korea Market Briefing — 2026.08.04 장중`, 15:30 이후에는 `Korea Market Briefing — 2026.08.04 마감`으로 표시합니다. 보고서 생성일은 별도 `publicationDate`와 리더의 `2026.08.04 KST 발행` 보조 정보로 표시합니다. 저장 키와 기본 정렬은 발행일을 유지하고, 아카이브 텍스트·날짜 검색은 `reportDate`와 `sessionDate`를 모두 검색합니다. Agent CLI 출력 계약은 기대 제목을 정확히 검증하며 API LLM·규칙 fallback도 같은 제목 정규화를 거칩니다. 종합 브리핑의 상위 제목은 발행일을 유지하고 내부 미국장·한국장 제목에서 각 세션일을 구분합니다.

한국장 세션 단계는 `marketWindows.krSessionPhase`의 `pre_open | intraday | closed | holiday`로 저장합니다. 거래소 API가 연결되어 있으면 먼저 해당 날짜의 개장 여부를 확인하고, 개장일에만 KST 정규장 시각을 적용합니다. `pre_open`에서는 `krCurrentSessionDate`를 비워 당일 장중 자료를 만들지 않고 `krLatestCompletedSessionDate`를 제목·Market Tape·차트 기준으로 사용합니다.

| analysisMode | 주요 분석축(primary) | 보조/추가 | 비고 |
| --- | --- | --- | --- |
| `weekday_kr_preopen` | 최근 미국 정규장 + 최근 한국 정규장 마감 | D 개장 전 최신 뉴스 | 한국 D 장중 가격·수급을 만들지 않음 |
| `weekday_kr_open` | 미국 D-1 정규장 + 한국 D 장중 | 한국 D-1 정규장(배경), D 최신 뉴스 | 한국 D-1은 배경 맥락으로만 |
| `weekday_kr_closed` | 미국 D-1 정규장 + 한국 D 마감 | 한국 D-1 정규장(배경), D 최신 뉴스 | 한국 D 종가를 `마감`으로 표시 |
| `weekend` / `both_holiday` | 최근 미국 정규장 + 최근 한국 정규장 | 주말/휴장 사이 새 뉴스(off_session_news) | 장중 시황 안 만듦, 뉴스는 다음 거래일 반영 후보 |
| `kr_holiday` | 최근 미국 정규장 | 휴장 전 한국 정규장(배경), 휴장 중 한국 뉴스 | 한국 당일 장중 시황 안 만듦 |
| `us_holiday_kr_open` | 한국 D 장중/정규장 | 직전 미국 정규장, 미 휴장 중 선물·환율·뉴스 | 미국 정규장 결과 새로 만들지 않음 |

### 평일 / 한국장 개장일
- 주요 분석축: 미국 D-1 정규장 + 한국 D 장중 흐름
- 보조 맥락: 한국 D-1 정규장(시장 흐름 섹션의 중심을 차지하지 않게 함)

### 주말 / 양시장 휴장일
- 주요 분석축: 최근 미국 정규장 + 최근 한국 정규장(간결한 복기)
- 추가 분석축: 주말/휴장 사이 나온 새 뉴스와 다음 거래일 영향 후보
- 주말·휴장 뉴스는 현재 가격 반응으로 쓰지 않고 다음 거래일 확인점으로 다룸. `sourceDates`에 off-session 구간 날짜를 명시 포함해 주말 뉴스 누락을 막음

### 한국 휴장일
- 한국 당일 장중 시황은 만들지 않음
- 미국장 결과와 휴장 중 한국 관련 뉴스의 다음 한국 거래일 반영 여부를 다룸

### 미국 휴장일 / 한국 개장일
- 미국 정규장 결과를 새로 만들지 않음
- 한국장이 열렸다면 한국장 자체의 수급·업종·환율을 우선 분석

자료별 우선순위는 `doc_analysis_priority(doc, windows)`가 `primary / secondary / background / off_session_news`로 반환하고, `briefing_doc_score()`가 모드별 가중치(평일은 미국 전일/한국 당일 primary, 주말·휴장은 off_session_news 비중 ↑)를 적용합니다. LLM 컨텍스트에는 모드 요약과 각 자료의 `분석우선순위`가 표시됩니다. 위 "한미 시장 시차 기준"의 `시장시간대` 버킷은 이 분석 우선순위로 매핑됩니다.

`build_llm_context`는 미국 정규장 마감 시황 기사에 더해, **`weekday_kr_open` 모드에서 한국 D 개장/장중(`KR 당일 개장/장중`) 자료를 고정 슬롯으로 컨텍스트에 시드**합니다(driver/group 경쟁에서 밀려 한국 당일 분석축이 비는 것을 방지). 참고자료(`refTier`)에도 한국 D 장중 자료에 `kr_current_flow` 등급을 줘 상단 일부에 배치합니다. `후보 이슈 묶음`도 `briefing_doc_score` 기준으로 정렬해 KR D-1 정규장 자료가 계속 상단을 차지하지 않게 합니다.

`weekend` / `both_holiday` 모드에서는 `off_session_news` 자료를 핵심 변수와 주도 기업·섹터 후보에서 우선합니다. 직전 미국/한국 정규장 자료는 `시장 흐름` 섹션의 짧은 배경 복기에 쓰고, `시장을 움직인 핵심 변수`와 `시장을 주도한 기업` 섹션은 주말/휴장 사이 새로 나온 정책·지정학·기업 이벤트·실적/가이던스·M&A·규제·원자재/환율 뉴스를 다음 거래일 반영 후보로 다룹니다. 가격 반응은 단정하지 않고 다음 거래일 거래대금, 수급, 선물, 환율, 동종 기업 상대강도로 확인합니다.

이 세션 구분은 분석 안전장치이며 독자용 문구가 아닙니다. 최종 본문에는 “장이 열리지 않았다”, “현재 가격 반응으로 해석할 수 없다”, `off_session_news` 같은 운영 설명을 노출하지 않습니다. 뉴스의 경제적 전달 경로를 바로 분석하고, 필요한 검증 조건만 다음 장 체크포인트에 자연스럽게 배치합니다.

자료 가용성도 같은 원칙을 따릅니다. 유료 매체의 본문 수집 실패, 제목·공개 요약만 확보했다는 상태, 로컬/입력 자료에서 확인되지 않았다는 제작 과정은 Canonical Markdown에 노출하지 않습니다. 근거가 부족한 세부 주장은 생략하고 구조화된 `dataGaps`에만 남기며, 본문의 불확실성은 실적·정책·사업 조건의 구체적인 반대 시나리오로 표현합니다.

한국장 시장 수치는 `features/common/market_data/providers.py`의 provider 체인에서 가져옵니다. 체인은 `YFinanceKoreaMarketProvider` 하나이며 KOSPI/KOSDAQ/KOSPI200 지수 종가·등락률을 조회합니다. `PyKrxKoreaMarketProvider`는 2026-08-12에 제거했습니다 — pykrx 1.2.x부터 KRX 계정을 요구해 자격증명 없는 설치에서 항상 실패했고, 거래대금·투자자별 수급·업종 등락률은 실제로 채워진 적이 없습니다. 원·달러 환율은 `USDKRW=X` fallback으로 붙입니다. Toss Open API provider와 `/exchange-rate` 보조 경로는 0.2 사용자 표면에서 제외되며 `FOLIO_ENABLE_TOSS_OPEN_API=1`을 켠 내부 검증에서만 실행됩니다. provider가 실패하면 “입력 자료에서 한국장 종가 등락률은 확인되지 않는다”고 명시하고 수치를 추정하지 않습니다.

저장된 브리핑 `stats`에는 자료 부족/코드 문제를 구분하기 위한 세션 카운트가 포함됩니다: `krCurrentIntradayDocCount`, `usPrevRegularDocCount`, `krPrevRegularDocCount`(+ `analysisMode`). 한국 D 장중이 약한데 `krCurrentIntradayDocCount`가 0이면 자료 부족, 충분한데도 약하면 프롬프트/선별 문제로 진단합니다.

## 자료 선별과 시장 동인 그룹화

브리핑 자료 선별 로직은 `features/daily_briefing/selection.py`에 분리되어 있습니다. 인덱싱용 `marketRelevance`와 회사/섹터 기준 `group_docs()`는 그대로 두고, 브리핑 전용 로직만 담습니다.

- `briefing_doc_score(doc, market_windows)`: "이 자료가 오늘 브리핑에서 얼마나 쓸 만한가" 전용 점수. 출처 신뢰도, 시장 시간창 적합성, 시장 관련성, 본문 품질, 영향/섹터/회사 태그, **시장 반응 연결성**, **broad keyword 단발 기사 감점**, RSS 헤드라인 감점을 합산합니다.
- `market_connection_score(doc)`: 자료가 실제 시장 가격/지수/수급 반응과 직접 연결되는지(지수명·등락·수급 신호·회사+섹터)를 점수화합니다. driver 키워드(금리·채권·달러 등)만 스친 단발 기사(개별 채권 발행·펀드·trivia·거시 단신)는 0에 가깝게 나와 참고자료 상단에서 밀려납니다.
- `effective_market_relevance(doc)`: 직접 저장 article이 인덱싱 단계에서 `marketRelevance=100`으로 고정되는 과대평가를, 시장 신호(회사/섹터/영향 태그)가 거의 없으면 브리핑 선별 단계에서만 보수적으로 낮춥니다. 인덱싱은 건드리지 않습니다.
- 미국장 브리핑에서는 Reuters/WSJ/Financial Times/Bloomberg 같은 foreign core source를 우선합니다. 한국 source의 미국장 기사도 사용할 수 있지만 `source_profile()`에서 미국장 전문성 점수를 낮게 두어, foreign/core source나 시장 데이터로 확인되지 않은 한국 source 기사가 미국장 결과물을 주도하지 않게 합니다.
- `infer_drivers(doc)` / `DRIVER_TERMS`: 문서를 금리, 환율/달러, 반도체/AI, 원자재/유가, 수급, 정책/규제, 실적/가이던스, 중국/글로벌 경기, 지정학 동인으로 추론합니다.
- `derive_market_drivers(docs, market_windows, limit=4)`: 문서를 시장 동인 기준으로 묶습니다. 출처 다양성과 미국·한국 양쪽 시간대에 걸친 동인 여부를 가산합니다. 자료 수가 많은 동인이 곧 중요한 동인은 아니라는 점을 점수 설계에 반영합니다.
- `prioritize_briefing_groups(groups, market_windows)`: 주도 기업/섹터 그룹을 브리핑 모드에 맞게 재정렬합니다. 주말/휴장 모드에서는 `off_session_news`를 가진 그룹이 먼저 오도록 보정합니다.
- `briefing_doc_excerpt(doc, clean_fn, tier)`: `driver`(1200자) / `group`(850자) / `support`(450자) tier로 발췌 길이를 차등합니다.

LLM 컨텍스트(`build_llm_context`)에는 `## 후보 이슈 묶음`보다 앞에 `## 핵심 변수 후보` 섹션이 추가되고(사용자 노출 용어 '핵심 변수' = 코드의 `market_drivers`), `## 기사/자료 원문 요약`의 각 자료에는 `자료등급`(핵심 변수 / 주도 기업·섹터 / 보조)이 붙어 tier별로 길이가 차등됩니다. 그룹 상위 자료와 패딩 자료 모두 `briefing_doc_score` 기준으로 뽑아, 출처만 유명하고 본문은 시장과 무관한 기사가 끼지 않게 합니다.

참고자료(`usedDocs`)는 각 자료에 **우선순위 라벨 `refTier`**를 부여해 정렬합니다.

```text
us_close          # 미국 D-1 정규장 마감 시황
kr_current_flow   # 한국 D 장중/마감 흐름
korea_market_data # KOSPI/KOSDAQ/수급/환율 직접 자료
semiconductor     # 반도체·소부장 흐름
macro_market      # 유가·지정학·금리·환율 자료
core_driver       # 핵심 변수에 쓰인 자료
leading_company   # 주도 기업 분석에 쓰인 자료
market_flow       # 지수·수급 등 시장 가격 반응과 연결된 자료
support           # 나머지 보조 자료
```

`(refTier, briefing_doc_score, date)` 순으로 정렬하므로, 미국 마감→한국 당일 흐름/시장 수치→반도체→유가·지정학·금리 순서의 자료가 상단에 오고, driver keyword만 스친 단발 기사는 뒤로 밀립니다. 저장된 브리핑의 `sources`에도 `refTier`가 남습니다.

저장된 브리핑 JSON의 `stats`에는 `driverCount`, `topDrivers`, `sourceCount`가 기록됩니다.
Step 6 Data Foundation Lite 이후 저장 JSON에는 공통 구조화 필드 `checkpoints`, `dataGaps`, `marketTape`도 포함됩니다. 이 필드는 대시보드/품질 평가가 markdown 파싱 없이 읽기 위한 별도 필드이며, 기본 브리핑 markdown은 변경하지 않습니다.

**`checkpoints`는 시장별로 뽑습니다.** 각 시장의 markdown에서 그 시장의 섹션 제목
(`## 6. 다음 {시장 라벨} 체크포인트`)으로 따로 추출하며, 제목 목록은 `MARKET_LABELS`에서
파생합니다(`service.py::briefing_checkpoint_headings`). 통합 markdown에서 한 번에 뽑으면
어느 항목이 어느 시장 것인지 남지 않아 미국 보고서에 한국장 확인 조건이 저장되고, 목록을
손으로 나열하면 새 시장만 조용히 0건이 됩니다 — 유럽·일본이 실제로 그랬고 그 자리에
"체크포인트 섹션을 찾지 못했습니다"라는 없는 갭까지 붙었습니다.
Step 7 Research Quality 이후 저장 JSON에는 규칙 기반 `quality` 필드도 포함됩니다. 기존 저장 브리핑은 조회 시 `quality`가 없으면 자동 평가해 백필합니다. 평가는 sourceLedger가 없는 브리핑의 한계를 warning으로 남기며, markdown 본문은 변경하지 않습니다.
Step 11 Quality Generation 이후 생성 API는 `qualityMode`(`diagnose_only` 기본, `llm_section_improve`, `strict`)를 받을 수 있습니다. 생성 전에는 브리핑용 품질 목표(articles/rss 우선, 미국장/한국장 기준일, marketTape, 반론, 체크포인트, Source & Data Notes)와 evidence coverage preflight를 LLM 컨텍스트에 주입합니다. `llm_section_improve`는 품질 평가에서 약한 섹션만 기존 근거 범위 안에서 LLM으로 최대 1회 재작성하고, `strict`는 A-/85점 기준의 엄격 검토 경고를 추가합니다. `qualityGeneration`에는 preflight, weakSections, token/evidence telemetry, 보강 전후 점수를 저장합니다.
0.4.x Change Intelligence 연동으로 저장 JSON의 `marketDrivers`에는 동인별 `topDocs`(상위 3건 제목/출처/URL/날짜)와 상한 자르기 전 실제 문서 수 `docCount`가, `issueCoverage`에는 대표 `title`과 `topDocs`가 남습니다. 이 값이 변화 비교의 의미 분류(직전/현재 대표 기사 대조)와 대시보드 변화 상세의 입력 재료입니다. 본문 원문은 저장하지 않습니다. 브리핑 reader 상단에는 저장된 `changeSummary`만 읽는 "이 브리핑에서 달라진 것" 스트립이 표시됩니다(백엔드 추가 호출 없음).

## 프롬프트

```text
features/daily_briefing/prompt_us.md
features/daily_briefing/prompt_kr.md
```

미국장과 한국장 프롬프트는 물리적으로 분리되어 있다. `marketScope=us`는 `prompt_us.md`, `marketScope=kr`는 `prompt_kr.md`만 사용한다. `marketScope=both`는 두 시장을 각각 생성/검증하기 위해 두 프롬프트를 구분해 함께 전달한다. 기존 `prompt.md`는 legacy/fallback 호환용이다.

프롬프트 원칙:

- 특정 개인 포트폴리오 대응이 아니라 일반 투자자용 공개형 시장 해설을 지향
- **하루를 하나의 이야기로 엮는 서술이 최우선.** 섹션 구조는 뼈대일 뿐 채워야 할 양식이 아니며, "무슨 일이 있었나/왜 중요했나/..." 같은 내부 점검 항목을 출력에 굵은 라벨로 반복 노출하지 않는다.
- 핵심 동인은 기본 3개(정말 중요한 독립 동인이 있을 때만 4개), 약한 변수는 보조 변수로 시장 흐름·체크포인트에서만 언급
- 결론의 핵심 변수는 핵심 1개 + 보조 1~2개로 압축
- 출력 구조: 0. 오늘의 시장 성격 / 1. 시장 흐름 / 2. 시장을 움직인 핵심 변수 / 3~4. 주도 기업 / 5. 일반 투자자 관점 / 6. 내일 확인할 체크포인트 / 오늘의 결론
- **시장 흐름 섹션은 핵심 수치 앵커(지수·ETF·금리·환율·유가 등)를 먼저 제시한 뒤 그 수치로 장의 성격을 해석한다.** 숫자 나열이 아니라 "핵심 수치 → 장의 성격 → 미국·한국 연결/차별화" 순서. 수치가 없으면 추정하지 말고 명시. `build_llm_context`의 `## 시장 수치 사용 지침`이 이를 유도하고, 규칙 fallback은 `market_snapshot`과 `korea_market_data`를 받아 수치 표를 직접 넣는다.
- `## 한국장 시장 수치`에는 가능한 경우 KOSPI/KOSDAQ/KOSPI200 종가·등락률·거래대금, 투자자별 수급, 주요 업종, 원·달러 환율이 들어간다. `weekday_kr_open` 모드에서 KOSPI/KOSDAQ 종가 등락률이 확인되면 시장 흐름은 가능한 한 “한국장은 KOSPI가 전일 대비 X%, KOSDAQ이 Y%로 마감했다...” 형식을 따른다.
- **시장 스냅샷 날짜 정합성**: yfinance 일봉은 당일 EOD가 늦게 반영돼, 거래 캘린더상 미국 정규장 기준일(`usRegularSessionDate`)보다 스냅샷 데이터가 하루 이전일 수 있다(예: 6/10 브리핑인데 스냅샷 미국 주가가 6/8 종가). `snapshot.py`는 각 종목의 실제 일봉 날짜 `asOfDate`와 미국 주식 기준 `latestUsEquityDate`를 저장하고, `snapshot_staleness_note()`가 스냅샷 기준일이 정규장 기준일보다 이전이면 "이 수치는 N일 종가이니 정규장 결과로 제시하지 말라"는 경고를 LLM 컨텍스트(와 규칙 fallback)에 넣는다. 마감 수치는 로컬 기사를 1순위로 쓰고 스냅샷은 보조·교차검증용.
- 로컬 자료 우선, 웹 검색은 부족한 시장 데이터나 가격 반응 해석 보완에만 사용
- 시장 가격 스냅샷은 지수/금리/유가/달러/크레딧 해석 보조로만 사용
- (참고: `Market Tape`는 한국어 독자에게 어색해 `시장 흐름`으로 변경. 코드 내부 변수명은 유지)
- 누적된 시장 흐름 요약은 오늘 뉴스가 기존 흐름의 연장인지 판단하는 배경으로 사용
- 미국장과 한국장의 시간차를 명시적으로 고려
- 단순 링크/뉴스 나열이 아니라 시장 성격·핵심 동인·작동 경로·다음 확인점 중심
- "확인할 필요가 있다" 류 표현은 구체적 확인 대상을 붙여서만 사용

## 규칙 기반 fallback

LLM 키가 없거나 호출이 실패하면 `build_prompt_markdown()`이 규칙 기반 브리핑을 생성한다. fallback도 LLM 브리핑과 동일한 출력 구조(0. 오늘의 시장 성격 / 1. 시장 흐름 / 2. 시장을 움직인 핵심 변수 / 3~4. 주도 기업 / 5. 일반 투자자 관점 / 6. 내일 확인할 체크포인트 / 오늘의 결론)를 따른다. 단 LLM 수준의 긴 분석이 아니라 간결한 규칙 기반 요약이다. `market_drivers`가 있으면 '시장을 움직인 핵심 변수' 섹션에 우선 사용하고, 없으면 회사/섹터 그룹으로 대체한다. `market_snapshot`과 `korea_market_data`가 있으면 시장 흐름 섹션에 수치 표를 직접 넣는다.

## 조립식 브리핑

브리핑 작업 화면은 `시장 범위(종합/미국장/한국장)`와 `브리핑 유형(기본/시황 중심/간단 요약)`만 노출한다. 세부 섹션은 모든 유형에서 고정하며 기본값은 `종합 + 기본`이다. 선택값은 API Key 설정과 분리된 브라우저 `localStorage`에 저장되고 오늘 생성과 날짜 지정 생성에 동일하게 적용된다.

- `기본`: 현재 전체 구성과 분량을 유지한다.
- `시황 중심`: 기존 섹션을 유지하면서 지수·금리·환율·수급·시장 폭·섹터 내부 흐름의 해석 비중을 높인다.
- `간단 요약`: 기존 섹션과 한 줄 결론·가운뎃점 요약을 유지하되 줄글을 압축한다.

API, Agent CLI, 규칙 기반 fallback은 같은 `briefingType` 계약을 사용한다. CLI의 `concise` 최소 분량은 시장당 2,500자이고 다른 유형은 시장당 5,000자다.

## 저장 위치

```text
data/briefings/YYYY-MM-DD.json                  # legacy 합본(읽기 호환)
data/briefings/YYYY-MM-DD.{market}.json         # 일간, 그 시장의 세션일 기준
data/briefings/YYYY-MM-DD.{market}.weekly.json  # 주간, 발행일 기준
data/briefings/YYYY-MM-DD.visuals.json
data/briefings/YYYY-MM-DD.visuals.json.gz
```

신규 가격 시계열은 보고서 JSON의 `visualSnapshots`에 저장하고, 종목 수가 많은 시장 히트맵 rows는 날짜별 `.visuals.json.gz` 사이드카에 저장한다. `.visuals.json`은 legacy 읽기 전용으로 유지한다. 브리핑 화면은 과거 보고서를 열 때 이 저장 데이터만 사용하므로 이후 시세가 바뀌어도 생성 당시 차트가 달라지지 않는다.

## 생성 당시 시장 시각자료

- Lightweight Charts 5.2.0: 지수·기업 이름과 가격·등락폭을 크게 표시하고 한 번에 한 대상만 전체 너비로 그린다. 기본은 `1D + 라인`이며 `1D·1M·3M·YTD·1Y`와 라인·캔들을 전환한다.
- Plotly: 섹터→산업→종목 계층의 전체 시장 treemap을 그린다. KR처럼 산업명이 섹터명과 같은 경우는 중복 단계를 생략해 섹터→종목으로 표시한다. 면적은 시가총액, 색은 일간 등락률이다. viewport에 가까워질 때 lazy render하고 export 직전에는 렌더를 보장한다.
- 1D 5분봉이 없으면 일봉으로 가짜 1D를 만들지 않고 데이터 없음 상태를 표시한다.
- 차트 카드에는 기준일, provider, freshness, coverage를 함께 표시한다.
- 주도 기업 차트는 기사 그룹의 사전 후보가 아니라 최종 Markdown의 `주도한 기업 ①·② — 기업명` 제목을 company master·aliases로 해석해 수집한다. 기업 해석이나 시세 수집에 실패하면 다른 기업 차트를 대신 표시하지 않는다.
- 시장 흐름 섹션 제목 직후에는 해당 시장 지수 차트와 전체 히트맵을, 주도 기업 ①·② 섹션 제목 직후에는 해당 기업 차트를 삽입한다. 삽입은 렌더링된 DOM에서만 수행하며 Canonical Markdown은 바뀌지 않는다.
- HTML은 inline PNG, Obsidian은 Vault의 `Briefings/assets/`, Notion은 기존 imgbb 설정이 있을 때 PNG 이미지로 내보낸다. 이미지 경로가 없어도 Canonical Markdown은 그대로 내보낸다.
- 브라우저 캡처 이미지는 `market` 메타데이터를 함께 전달한다. `both` 브리핑을 Obsidian/Notion으로 내보낼 때는 미국장/한국장 단위로 분리하고, 각 노트·페이지에는 해당 시장 차트만 포함한다. HTML 복사는 단일 문서를 유지하되 차트 이미지를 inline PNG로 바꿔 붙여넣기 가능하게 만든다.
- Lightweight Charts의 Apache 2.0·TradingView attribution은 `THIRD_PARTY_NOTICES.md`와 사용자 화면에 유지한다.

### 생성 당시 / 현재 시장

브리핑 화면의 시각자료는 **생성 당시 immutable snapshot만** 보여준다. 과거 화면에 있던 `현재 시장` 토글은 제거했다. `현재 시장`은 저장 universe 전체(미국 수백 종목 + 한국 KOSPI 200)를 매번 라이브로 재조회해야 해서 토글을 누를 때마다 수십 초가 걸렸기 때문이다. 이는 캐싱으로 줄일 수 없는 구조적 비용이라, 인라인 브리핑은 빠른 저장 snapshot 전용으로 두고 현재 시장은 추후 별도 대시보드 위젯에서 제공한다.

- 생성 당시 보기는 보고서 JSON과 날짜별 시각 sidecar만 읽는다.
- 현재 시장 조회용 백엔드(`GET /api/briefings/{date}/visuals/current`)와 비교 로직(`load_current_visuals`)은 그대로 보존한다. 향후 대시보드 위젯이 read-only로 재사용한다. yfinance는 실시간 체결가가 아니므로 `snapshot`, `delayed`, `stale`, `unavailable`과 장 상태를 구분한다.
- 이 경로는 보고서 JSON과 `.visuals.json(.gz)`을 쓰지 않는 read-only 경로이며, 종목은 생성 당시 종가 대비 변화율, 히트맵은 섹터 성과 순위 변화를 비교로 제공한다.

저장된 JSON에는 디버깅용 `marketDrivers`(driver/score/markets/sources/tags/sectors/docCount), `koreaMarketData`, 그리고 `stats.driverCount`, `stats.topDrivers`, `stats.sourceCount`, `stats.koreaMarketDataOk`가 포함된다.

## 테스트와 검증

```powershell
# 단위 테스트(자료 선별/동인 그룹화/LLM context/참고자료 정렬/fallback 안전성)
py -3 -m features.daily_briefing.tests.test_briefing

# 브리핑 시황·시각화 고도화 Step 0 계약 테스트
py -3 -m features.daily_briefing.tests.test_contracts

# 실제 인덱스로 생성 경로 검증(기본 dry-run: data/ 와 메모리 DB 미변경)
py -3 -m features.daily_briefing.tests.verify_briefing            # 규칙 fallback
py -3 -m features.daily_briefing.tests.verify_briefing --llm      # LLM 경로(키/네트워크 필요)
py -3 -m features.daily_briefing.tests.verify_briefing --llm --persist  # 실제 저장까지
```

`build_briefing(..., persist=False)`는 결과만 반환하고 `data/briefings/`와 시장 메모리 DB에 쓰지 않으므로, 실제 서버에 저장하지 않고 출력 품질을 확인할 때 사용한다.

### 브리핑 고도화 Step 0 계약

`schema.py`는 향후 시장 범위·브리핑 유형·세션·freshness·본문 가용성·시장 반응 상태 enum과 시각 스냅샷 최소 메타데이터를 코드에서 고정한다. `normalize_briefing_contract()`는 기존 저장 브리핑의 Canonical `markdown`과 `personalOverlay`를 바꾸지 않고 신규 구조화 필드의 빈 기본값만 제공한다.

`contracts.py`와 `tests/fixtures/`는 현재 active prompt 섹션·규칙, 기존 JSON 필드, 시장 캘린더 모드, 출처 편중 baseline, issue clustering 평가용 50건 synthetic label을 고정한다. 편중 baseline에는 집계 수치만 있고 기사 제목·URL·로컬 파일 경로는 저장하지 않는다. 실제 시장 분리·출처 편향 개선은 Step 1에서 구현한다.

## 참고자료 링크 주의사항

브리핑 참고자료의 링크 텍스트(기사 제목)에 `[`나 `]` 문자가 포함된 경우 Markdown 링크 구문이 깨질 수 있습니다. `[외신 에스프레소]` 형태의 한국경제 등 매체 제목이 이에 해당합니다. `_escape_md_link_text()`는 링크 텍스트의 대괄호를 제거해 클릭 가능한 Markdown 링크 형태를 유지합니다. 프론트엔드는 `## 참고자료` 섹션 안에 실제 Markdown 링크가 없으면 저장 JSON의 `sources`/`headlines.sources`로 참고자료 패널을 보강합니다.

## 브리핑 회귀 체크리스트

차트·참고자료·시장별 저장/목록을 수정한 뒤에는 아래를 고정 회귀로 확인합니다.

- 저장본 열기: 기존 `{date}.json`과 신규 `{date}.us.json`/`{date}.kr.json` 모두 브리핑 본문이 열린다.
- 미국 시장 차트: 선택 strip이 `S&P 500 → Nasdaq → Dow Jones` 순서이며, `Nasdaq`은 `^IXIC` Nasdaq Composite 값을 표시한다.
- 차트 기준일: 저장 snapshot의 `marketSessionDate`와 hover 날짜가 4자리 연도(`YYYY-MM-DD HH:mm`)로 표시된다.
- 1D 수치: 헤더의 등락률은 5분봉 첫/마지막 값이 아니라 일봉 전일 종가 대비로 계산된다.
- Hover tooltip: 가격 차트에 마우스를 올리면 날짜, 가격, 등락폭/등락률이 함께 표시되고 카드 밖으로 크게 벗어나지 않는다.
- 주도 기업 차트: `시장을 주도한 기업 ①·②`처럼 시장명이 빠진 제목도 company master 기준으로 해당 기업 차트를 표시한다.
- 히트맵: 미국은 S&P 500, 한국은 KOSPI 200 구성종목 중심으로 보이며 KR 중복 sector/industry 라벨은 한 단계로 접힌다.
- 참고자료 링크: `## 참고자료` 섹션의 Markdown 링크가 클릭 가능하고, 링크 없는 섹션이면 저장 JSON sources 패널이 보강된다.
- 목록 피드: 카드 클릭 시 브리핑 보기(본문·차트·히트맵·참고자료)가 브리핑 탭 본문 자리의 인라인 리더로 열린다.
- 내보내기: Obsidian/Notion/HTML 내보내기가 시각자료 부재에도 본문을 실패 없이 내보낸다.
- 모바일: 390px 안팎 폭에서 차트 controls, tooltip, 히트맵, 참고자료, 목록 필터가 가로 overflow 없이 조작된다.

## 날짜 계산 주의사항

- `select_briefing_docs()`는 먼저 `briefing_market_windows(date)`로 source_dates를 계산한다.
- 인덱스에 source_dates 해당 문서가 없으면 가장 최근 문서로 fallback하지만, `market_windows`는 원래 브리핑 날짜 기준으로 유지한다.
- **공휴일/주말 fallback 버그**: fallback 시 문서 날짜로 `market_windows`를 재계산하면 `krPreviousSessionDate`가 잘못된 날짜를 가리키는 문제가 있었다. 수정됨.

## 관련 코드

- `features/daily_briefing/service.py`: `select_briefing_docs()`, `build_llm_context()`, `generate_llm_briefing()`, `build_prompt_markdown()`
- `features/daily_briefing/limits.py`: `CONTEXT_DOC_LIMIT`, `SOURCE_REF_LIMIT`, `merged_source_limit()` — 선별 상한의 단일 출처
- `features/daily_briefing/weekly.py`: `weekly_window()`, `weekly_title()`, `weekly_documents()`, `calendar_preview()`, `build_weekly_rules_markdown()`
- `features/daily_briefing/target.py`: `resolve_targets()`(일간 세션 판정), `resolve_weekly_targets()`(주간)
- `features/daily_briefing/selection.py`: `briefing_doc_score()`, `derive_market_drivers()`, `infer_drivers()`, `briefing_doc_excerpt()`
- `features/common/market_calendar.py`: `briefing_market_windows()`, `doc_market_bucket()`
- `features/common/market_data/providers.py`: `MarketDataProvider`, `fetch_korea_market_data()`
- `app.py`: `build_briefing()` (orchestration — `derive_market_drivers()` 호출 후 `generate_llm_briefing()`에 전달)
- `public/app.js`: `renderBriefing()`, `openBriefingReader()`/`closeBriefingReader()`(인라인 리더), `applyBriefingReaderHash()`(해시 라우팅), `refreshActiveBriefingVisuals()`
- `public/briefing-visuals.js`: `renderInline()`, `relayout()`(리더 폭 확정 후 차트/히트맵 리사이즈)

## API

```text
GET  /api/briefings
GET  /api/briefings/index
GET  /api/briefings/YYYY-MM-DD
GET  /api/briefings/YYYY-MM-DD/visuals
GET  /api/briefings/YYYY-MM-DD/visuals/current
POST /api/briefings
POST /api/briefings/{date}/export-notion
```

`POST /api/briefings`는 `date`, `strictDate`, `webSearch`, `markets`, `briefingType`, `kind` 값을 받을 수 있습니다. `kind: "weekly"`면 `date`는 세션일이 아니라 **발행일**이고 세션 판정(`resolve_targets`) 대신 `resolve_weekly_targets`를 탑니다 — 주말 발행이 정상인 산출물을 "그날은 거래일이 아니다"로 막으면 주간을 손으로 만들 길이 아예 없습니다. 아직 오지 않은 날짜는 `week_not_available`로 거부합니다.

`GET /api/briefings/{date}`는 `marketScope`와 `kind`를 받습니다. **주간을 물었는데 일간으로 되돌아가지 않습니다** — 같은 날 두 보고서가 나란히 있을 수 있어, 되돌아가면 화면이 다른 보고서를 열어 놓고 주간이라고 말합니다.

`GET /api/briefings/index`는 시장별 아카이브 메타 목록을 `{items,total,offset,limit,warnings,cache}` 형태로 반환합니다. `q`, `marketScope`, `briefingType`, `kind`, `dateFrom`, `dateTo`, `offset`, `limit` 필터를 지원합니다. `kind`는 `all | daily | weekly`이며 모르는 값은 400입니다. 메모리 캐시는 30초 TTL과 파일 `mtime_ns`·크기를 사용해 변경된 날짜 JSON만 다시 읽으며, 조회 과정에서 보고서 JSON을 쓰거나 별도 영구 인덱스를 만들지 않습니다.

`DELETE /api/briefings/{date}?market=us|kr&kind=daily|weekly`는 `kind`가 가리키는 종류만 지웁니다(기본 `daily`). 종류를 무시하면 주간 카드의 삭제가 그날 일간 브리핑을 지웁니다. 일간 삭제는 신규 시장별 저장 파일(`{date}.us.json`/`{date}.kr.json`)과 해당 시장 시각자료 사이드카만 삭제하고 아카이브 캐시를 즉시 갱신합니다. `market`을 생략하면 날짜 전체 삭제로 동작해 레거시 `{date}.json`과 양쪽 시장 파일·사이드카를 함께 삭제합니다. 기존 레거시 `{date}.json`만 있는 날짜는 시장 단위로 분리 삭제할 수 없으므로 날짜 전체 삭제 안내를 표시합니다. 잘못된 날짜/시장 형식은 400, 없는 파일은 404를 반환합니다.

프론트엔드 브리핑 탭은 **하나의 화면으로 통합**되어 있습니다(과거의 `생성`/`목록` 하위 탭과 좌측 사이드바 하위 탭은 제거). 위쪽에 생성 컨트롤, 아래쪽에 저장된 브리핑 피드가 함께 있습니다.

생성 박스는 단일 패널 `브리핑 설정`(시장 범위 세그먼트 + 브리핑 유형·품질 모드)과 하단 액션 바(`자료 다시 읽기` → `오늘 브리핑 생성` → 날짜 입력 → `이 날짜로 생성`)로 구성됩니다. 생성 방식은 설정 탭의 AI Agent 정책을 따릅니다. 저장된 브리핑 피드는 `/api/briefings/index`를 사용해 최신순 카드, 시장·유형·날짜·텍스트 필터, 페이지네이션, `시장별/날짜별` 보기 모드를 제공합니다. 카드는 제목·기준일·생성 시각만 노출하며, 각 카드의 휴지통 버튼으로 해당 날짜 브리핑을 삭제할 수 있습니다. 여러 시장을 함께 생성해도 카드는 시장별로 한 장씩 남습니다.

종합(both) 브리핑은 미국장·한국장 본문을 그대로 두고, 두 시장을 잇는 **한미 시장 연결 분석**(공통 흐름·시장별 고유 동인·스필오버·한계)을 별도 사이드카 `data/briefings/{date}.link.json`에 저장합니다(`features/daily_briefing/link_analysis.py`, LLM 없이 규칙 기반으로 동작). LLM이 켜져 있으면 `service.llm_enhance_link_analysis()`가 규칙 초안을 시나리오·반론까지 심화하되, 새 수치·출처를 만들지 않고 `### 한계와 불확실성`을 강제하며, 실패·무효 출력이면 규칙 본문으로 안전하게 되돌립니다(`llmEnhanced` 플래그로 표시). 결합 뷰를 읽을 때(`resolve_briefing(..., "both")`) 이 연결 분석이 본문 최상단에 결합되며, per-market 저장 파일과 각 시장 Canonical 본문은 변경되지 않습니다. 날짜 전체 삭제 시 `{date}.link.json`도 함께 삭제됩니다.

브리핑은 **생성 결과든 카드 클릭이든 모두 인라인 리더**로 브리핑 탭 본문 자리에서 열립니다(팝업 아님). 리더가 열리면 목록/생성 패널은 숨고, 상단 브레드크럼(`브리핑 › {날짜} {시장} 브리핑`)·Escape·브라우저 뒤로가기로 목록에 돌아옵니다. URL 해시 `#briefing/{date}/{us|kr|both}`로 새로고침·딥링크가 복원됩니다. 리더가 보여 폭이 잡힌 뒤 차트(Lightweight Charts)·히트맵(Plotly)을 렌더·리사이즈해 숨김 컨테이너 0폭 문제를 방지합니다. Personal Overlay와 내보내기(Obsidian/Notion/HTML) 액션은 리더 좌측 레일에서 동작하며, 우측 투자 노트 패널·AI 도크와 한 화면에 나란히 배치됩니다.

`POST /api/briefings/{date}/export-notion`은 저장된 브리핑을 Notion 데이터베이스 페이지로 내보냅니다. `NOTION_TOKEN`과 `NOTION_DB_ID`가 설정되어 있어야 합니다.

`GET /api/briefings/{date}/visuals`는 저장된 과거 히트맵 sidecar만 반환하며 현재 시세를 다시 조회하거나 보고서 JSON을 수정하지 않습니다.

`GET /api/briefings/{date}/visuals/current`는 저장된 종목 universe를 최신 무료 일봉으로 조회한 임시 응답을 반환합니다. 저장 보고서와 sidecar에는 쓰지 않으며, yfinance가 설치되지 않았거나 조회에 실패하면 `unavailable`과 warning을 반환합니다.


