# 기업 분석

이 기능은 특정 기업에 대해 공시, 리포트, 뉴스 자료를 종합해 기업 분석 리포트를 생성합니다.

## 담당 범위

- 기업명/티커 입력 분석
- SEC ticker registry 기반 미국 상장사 식별
- SEC companyfacts 기반 재무 숫자 수집
- SEC 10-K HTML 수집과 문단 점수화
- DART corpCode 기반 국내 상장사 식별
- DART Open API 기반 국내 기업 재무 숫자 수집
- 로컬 공식자료 발췌 fallback(10-K/10-Q/S-1/20-F/8-K/prospectus/proxy 등)
- 공식자료 우선 컨텍스트 구성
- Financial Summary 하위의 재무 품질 분석
- LLM 기업분석 리포트 생성
- `analysisStyle=beginner|advanced` 기반 초심자/숙련자 보고서 모드
- data-gap resolver 기반 자료 한계·확인 시도 기록
- Jinja2 템플릿 기반 규칙 엔진 리포트 생성
- 생성된 기업분석 보고서 자동 저장(같은 기업·같은 날 덮어쓰기)/다시 열기/삭제
- 참고자료 표시
- 웹 검색 보완 ON/OFF
- 자동 preflight, evidence coverage, 품질 평가 결과 저장

## 생성 경로 — 0.5.6

### 생성 결과 보존

품질 결함은 보고서를 버리는 조건이 아닙니다. API와 CLI 모두 선택적인 구조 보완 재시도가
실패하거나 더 나아지지 않으면 먼저 받은 본문을 유지합니다. 구조 검사·계약 검증을 완료하지
못하면 `validationStatus: unassessed`와 고정 안내를 남기고 저장 경로로 전달합니다.
이는 검증 통과가 아니며 후속 품질 평가에서도 경고를 유지합니다. 원문 예외나 비밀값은
이 안내에 복사하지 않습니다. 명시적 취소와 저장 경로·원자적 커밋 검사는 완화하지 않습니다.

API 저장 자체가 실패하면 본문과 `saved: false`, 고정 `saveError`를 반환합니다.
화면은 반환된 본문을 먼저 표시하고 목록 새로고침 실패와 생성 실패를 구분합니다.
`saved: true`인 경우에만 자동 저장 성공과 저장본 링크를 표시합니다. 화면에 남아 있는
미저장 본문은 영구 보관된 것이 아니며 새로고침 후 복구를 보장하지 않습니다.
동일 날짜 정상본을 불완전 후보로 덮어쓰지 않는 후보 보관 정책은 아직 별도 구현 대상입니다.

기업분석에는 생성 경로가 둘이다.

```text
API   app.py → analyze_company()
CLI   app.py → submit_agent_task() → agent_mode/service.py::prepare_company_analysis_pack()
```

**조립기와 후처리기는 하나씩이다.** 두 경로가 각자 조립하던 시절 실제로 갈렸다:

- 산출물 계약(분량·근거 인용·서술 요구·웹 조회·검증)이 API 경로에만 붙어, CLI로 만든
  보고서에는 `contractValidation`이 아예 없었다. 사용자는 CLI를 쓰고 있었다.
- 자료 검색도 갈렸다. API는 회사를 해석하고 그 표기들로 검색해 합치는데
  (`search_company_documents`) CLI는 사용자가 친 문자열 하나로 찾았다 — 실측 **NVDA 문서
  겹침 8/30**, CLI 상위 3건에 엔비디아 기사가 하나도 없었다(세레브라스·SanDisk·CoreWeave).
- 팩의 `requiredSections`가 손으로 적은 6개라 경쟁우위·성장 전망·어떻게 접근할까가
  빠져도 아무도 몰랐다.

| 무엇 | 어디 |
|---|---|
| 자료 수집·컨텍스트 조립 | `generation_context.py::build_generation_inputs()` |
| 보고서 뼈대 | `generation_context.py::draft_artifact()` |
| 계약 검증·점수 상한 | `finalize.py::finalize_report()` |
| CLI 초안 재시도 | `agent_mode/bridge.py::run_agent_task` (브리핑과 같은 자리) |

**새 계약은 조립기에 붙인다.** 경로별로 붙이면 다시 갈린다.

주의:
- **데이터 갭은 설정이 아니라 실제로 웹 검색이 돌았는지로 정한다.** 조립기가 설정으로
  미리 굳히면 CLI 모드·LLM 실패·자료 없음처럼 검색이 한 번도 돌지 않은 경로에서도
  "시도함"으로 남는다. 조립기는 조회 발동 판단용 `dataGaps`만 갖고, 최종 갭은 생성 뒤에
  호출자가 정한다.
- **CLI 재시도는 실패로 끝내지 않는다.** 브리핑은 계약 위반이면 잡을 실패시키지만
  기업분석은 섹션 하나가 빠져도 나머지가 쓸모 있고, 계약 결함으로 남으면 점수 상한이
  그것을 말한다.
- `engine_calls`는 브리지를 **호출 시점에** import한다. 최상단에서 가져오면
  `generation_context → engine_calls → bridge → agent_mode.service → generation_context`
  순환이 생긴다.

## 산출물 계약 — 0.5.6

프롬프트로 부탁한 것과 산출물이 지킨 것은 다르다. 지금까지 기업분석은 계약을
**프롬프트에만** 두고 결과를 확인하지 않았다 — `style.py::REQUIRED_SECTION_HEADINGS`에
9개 섹션이 정의돼 있지만 그것을 쓰는 함수는 `validate_prompt_structure(prompt)`
하나뿐이었고, 그것은 프롬프트 파일을 검사할 뿐 생성된 보고서를 보지 않았다.

실측(저장된 4건): SpaceX·LAM은 `어떻게 접근할까`와 `자료 한계와 참고자료`가 통째로
없었고, 섹션 길이가 2~3배로 흔들렸으며(실적 1,818~4,366자), 숨김 근거 태그가 **0개**라
`source_grounding`이 0.08~0.42로 네 건 모두 최하위 항목이었다. 보수 패스는 한 번도
돌지 않았다(`repairCount: 0`).

### 검증 (`report_contract.py`)

- `section_missing`(60) — 계약이 요구하는 9섹션 중 없는 것. 제목이 다르면 없는 것이다.
- `thin_section`(35) / `below_recommended_length`(45) / `above_safety_length`(45) — 분량.
- `unlinked_section`(35) / `unknown_source_tag`(40) / `low_source_linkage`(70) — 근거 연결.
- `hedge_overuse`(40) / `hedge_repetition`(35) / `speech_unattributed`(40) — 문체.
- **어느 결함도 산출물을 되돌리지 않는다.** 기업분석에는 딥 리서치 같은 후보·재시도
  구조가 없어, 차단하면 사용자가 아무것도 받지 못한다. 점수 상한과 보수 대상 지정으로만 쓴다.
- **재지 못한 것을 만점으로 보고하지 않는다.** 계약이 자기 섹션을 하나도 못 찾으면
  `sourceLinkage`는 `None`이다 — 1.0으로 두면 옛 제목을 쓴 보고서가 근거 연결 만점이 된다.

### 분량 (`depth_policy.py`)

- **목표 분량이 확보한 자료를 따라간다.** 기본 11,000자 + 보조자료 1건당 250자(최대 12건)
  + SEC 숫자 1,000 + 공시 서술 1,000, 상한 17,000. 고정 하한을 두면 자료가 0건인 회사에서
  모델이 없는 이야기로 칸을 채운다 — 딥 리서치에서 에디터가 초안을 +141% 늘려 근거 없는
  산문이 채워진 것과 같은 실패다.
- 섹션 예산은 **채워야 할 하한**이다. 쓸 말이 없으면 줄이지 말고 무엇을 확인하지
  못했는지를 그 자리에 쓴다.
- 컨텍스트에는 **숫자로** 준다(`render_length_contract`). "충실히 쓰세요"는 지침이고
  숫자는 과제다 — 이 세션에서 세 번 확인했다(웹 검색 허가 4회 실패 → 찾기 과제 1회 성공,
  유보 압축 원칙 3회 실패 → "21회 이하로" 1회 성공).

### 근거 인용

- `render_source_contract`가 인용 가능한 ID 목록과 태그 형식을 함께 준다. 규칙만 주면
  무엇을 인용할지 알 수 없다.
- 원장은 `source_ledger_from_items(selectedDocs, artifact_type="company_analysis")`이며
  보고서 JSON의 `sourceLedger`에 저장된다.
- `어떻게 접근할까`와 `자료 한계와 참고자료`는 면제다 — 판단을 적는 자리와 데이터 메모는
  근거를 인용하는 자리가 아니다.

### 점수 상한

`apply_report_ceiling`이 `common/research_quality/contract_ceiling.py`를 부른다(딥 리서치와
같은 눈금). 심각도 70 이상이면 69점, 40 이상이면 89점, 주요 결함 3건 이상이면 79점이다.

### 웹 조회 — 0.5.6

- **찾기와 쓰기를 분리한다**(`web_lookup.py`). 로컬 색인은 보관 기간상 약 3개월이라
  뉴스가 거의 없는 종목은 구조적으로 못 채운다(실측: 로컬 문서 11 / 5 / 2 / **0**건,
  0건인 회사는 데이터 갭 6개가 전부 "실적발표·컨퍼런스콜·리포트 없음"이었다).
- 찾는 것: 최근 분기 실적과 가이던스, **경영진의 실제 발언**(이름과 직함), 전망 변경.
  주가 전망이나 투자 의견은 찾지 않는다 — 근거가 아니라 남의 판단이다.
- 발동 조건은 보조 자료 6건 미만이거나 실적·IR 데이터 갭이 있을 때다. **자료가
  넉넉하면 부르지 않으므로 대부분의 실행에서 호출이 늘지 않는다.**
- **한 출처는 한 ID를 갖는다.** 사실마다 번호를 매기면 원장의 URL 중복 제거와 어긋나
  본문이 인용한 ID가 원장에 없어진다(딥 리서치 실측: 28건 중 10건).
- **화자 귀속은 이름으로 본다.** `CFO`는 직함 목록에 넣지 않는다 — 기업분석 본문에서
  그 세 글자는 대부분 영업현금흐름이라(`CFO/영업이익 92.1%`) 직함으로 세면 재무표만
  있어도 귀속이 통과한다. 기업 임원은 본문이 라틴 이름을 그대로 쓰는 편이라
  `speaker_identity()`가 성(姓)을 뽑아 대조한다.

### 초안 재시도 — 0.5.6

- 초안이 고정 9섹션을 빠뜨리거나 다른 제목으로 쓰면 **쓰기만** 한 번 더 시킨다.
  실측 4건 중 3건이 계약과 다른 제목을 썼고 두 섹션이 통째로 빠졌는데, 보수 패스는
  섹션 3개를 손볼 뿐이라 골격이 어긋난 초안을 되살리지 못한다.
- 앞의 자료 수집·웹 조회는 재사용되므로 다시 시키는 것은 쓰기 한 번뿐이다.
- **실패한 초안을 되돌려 주지 않는다**(앵커가 되어 같은 실수를 되풀이한다). 재시도가
  더 낫지 않으면 처음 것을 쓴다 — 나쁜 초안이라도 없는 것보다 낫다. 결과는 `draftGuard`.

### 서술 요구 — 0.5.6

품질 평가가 찾는데 프롬프트가 요구하지 않던 것들이다. 네 건 모두 같은 자리에서 점수를
잃었는데 **재료가 없어서가 아니라 쓰라고 한 적이 없어서**였다(실측: 범위 선언 0/4건,
시나리오 조건어 0회).

- `scope_undefined`(40) — `핵심 판단` 안에 다루는 것과 **다루지 않는 것**을 밝힌다.
- `scenario_not_conditional`(35) — 시나리오는 숫자로 된 조건으로 쓴다.
  조건 낱말은 **평가기가 세는 목록 그대로**다. 여기서 넓히면 계약은 통과시키고 점수는
  안 오르는 표현이 생기고, 예시가 그런 말을 가르치면 모델은 시킨 대로 쓰고도 벌을 받는다
  (실제로 `밑돌면`으로 쓸 뻔했다 — 평가기는 그 낱말을 세지 않는다).
- 섹션 간 중복도 함께 막는다(실측 LAM 26.4%). 딥 리서치에서 축끼리 서로의 몫을 알려
  준 것과 같은 처방이며, 여기서는 9섹션이 고정이라 컨텍스트 한 줄로 끝난다.

## 자료 우선순위

```text
research-inbox/filings
> research-inbox/reports
> research-inbox/articles
> research-inbox/rss
> 기타 research-inbox 자료
```

미국 상장사는 로컬 수동 사전보다 SEC `company_tickers.json`를 먼저 조회해 CIK를 찾습니다. 국내 상장사는 DART `corpCode.xml`을 캐시해 종목코드/회사명으로 `corp_code`를 찾습니다. 로컬 `config/company_master.json`, `config/company_aliases.json`는 사용자 별칭이나 애매하게 잡히는 회사 보정용입니다.

숫자 데이터는 미국 기업은 SEC companyfacts API, 국내 기업은 DART Open API를 최우선으로 사용합니다. 이후 공식 자료인 SEC 10-K HTML 또는 DART 사업보고서/분기보고서와 로컬 공시 자료를 사용하고, 증권사 리포트와 IR 자료, 마지막으로 기사/RSS를 참고합니다.

## 컨텍스트 구성 방식

기업분석은 전체 파일 본문을 LLM에 넣지 않습니다. 토큰 비용과 환각을 줄이기 위해 아래 순서로 입력을 축약합니다.

1. `공식 숫자 데이터`
   - 미국 기업은 SEC companyfacts API에서 CIK 기준으로 재무 항목을 불러옵니다.
   - 국내 기업은 DART Open API에서 corp_code 기준으로 최근 3개년 재무 항목을 불러옵니다.
   - 매출, 매출총이익, 영업이익, 순이익, EPS, 영업현금흐름, CapEx, 현금, 자산, 부채, 장기부채를 우선 정리합니다.
   - SEC/DART 접근 실패 시 캐시가 있으면 캐시를 사용하고, 없으면 로컬 자료와 웹 검색 보완으로 넘어갑니다.
2. `SEC 10-K HTML 상위 문단`
   - SEC submissions에서 최신 10-K HTML 원문 URL을 찾습니다.
   - 기업 섹터/GICS 성격에 따라 중요한 Item과 키워드 묶음을 선택합니다.
   - 문단 단위로 Item, 키워드, 숫자 포함 여부, 문단 길이를 점수화합니다.
   - 상위 문단, 점수, 키워드, filing metadata만 입력합니다.
3. `로컬 공식 공시 발췌 fallback`
   - SEC HTML 수집이 실패하거나 공식 문단이 부족하면 `research-inbox/filings`의 직접 관련 공식자료를 사용합니다.
   - 같은 form 등급(10-K끼리 등) 안에서는 최신 공시부터 사용합니다. 발췌 수 제한에 걸릴 때 최신 공시가 빠지지 않게 하기 위해서입니다.
   - 10-K/10-Q/20-F는 Item 구조를 우선 추출합니다.
   - S-1/F-1/prospectus/proxy/8-K처럼 Item 구조가 다르거나 저장 HTML이 깨진 자료는 사업·리스크·성장·재무·규제 키워드 기반 발췌를 보조 공식자료로 사용합니다.
   - 로컬 공시의 수치 정확성은 SEC/DART 구조화 데이터 또는 웹 검색 공식자료로 교차검증하는 것을 원칙으로 합니다.
4. `보조 자료`
   - reports, articles/rss, 기타 자료를 그대로 앞에서부터 넣지 않고 기업분석 전용 점수로 재정렬합니다.
   - 점수는 회사 직접 관련성, 자료 유형, 본문 길이, 출처 신뢰도, 재무/사업/성장/리스크/밸류에이션 키워드, 본문 정제 상태를 함께 봅니다.
   - 보조 자료는 `financial`, `business`, `growth`, `risk`, `valuation`, `general` 버킷으로 나누어 한쪽 주제만 과도하게 들어가지 않게 제한합니다.
   - 기사/RSS는 최근 이슈, 촉매, 시장 반응 보완용이며 회사 직접성이 낮거나 본문이 빈약한 자료는 제외합니다.

## LLM 버전

LLM에는 전체 10-K나 전체 PDF를 넣지 않습니다. 입력은 `공식 숫자 데이터 + 공식 공시 상위 문단 + filing metadata + 점수화된 보조 자료 일부`로 제한합니다. 웹 검색은 로컬/SEC/DART 자료로 설명이 부족한 부분을 공식 SEC/DART/IR/회사 홈페이지/실적발표 자료로 보완할 때만 사용합니다.

생성 모드는 `analysisStyle`로 선택합니다.

- `beginner`: 큰 틀은 기존 기업분석 구조를 유지하되, 어려운 용어를 풀어 쓰고 숫자의 의미를 줄글로 설명하는 초심자 친화 보고서입니다.
- `advanced`: 같은 9개 섹션 골격을 유지하되, 경쟁우위·재무품질·밸류에이션·반증조건을 더 압축적이고 깊게 다루는 숙련자용 보고서입니다.

두 모드는 공통 base prompt를 조합하지 않고 완전히 분리된 prompt 파일을 사용합니다. 다만 두 prompt는 같은 9개 섹션 순서, 자료 우선순위, 조작 금지, data gap 처리 규칙을 반드시 공유해야 합니다.

자료가 부족할 때는 곧바로 "확인 불가"로 끝내지 않고 `features/company_analysis/data_gap_resolver.py`의 data-gap resolver가 먼저 SEC companyfacts/DART, SEC 10-K HTML, 로컬 공식자료, 시장 데이터, 로컬 IR·기사·RSS, 웹 검색 허용 여부를 기준으로 어떤 확인 경로를 시도했는지 구조화합니다. 보고서 JSON에는 `dataGaps`와 `resolutionAttempts`가 저장되고, Reader는 해결되지 않은 항목을 "자료 한계"로 보여줍니다.

## 규칙 기반 버전

LLM이 꺼져 있거나 API Key가 없거나 호출에 실패하면 `features/company_analysis/report_rules.py`가 섹션별 규칙 엔진으로 보고서를 만듭니다.

- 재무 섹션: SEC companyfacts 또는 DART 재무제표의 핵심 항목을 표로 구성
- 사업/경쟁우위: SEC 10-K 상위 문단 또는 로컬 공식자료 발췌 중 product, platform, customer, segment, network 등 키워드가 강한 문단 사용
- 리스크: SEC 10-K Item 1A 또는 로컬 공식자료의 risk, regulation, competition, supply, margin 등 리스크 문단 사용
- 성장/전략: AI, data center, expansion, international, automation, partnership 등 성장 문단 사용
- 종합평가: 숫자 데이터와 공시 문단의 충실도를 기준으로 보수적으로 작성

보고서 렌더링은 Jinja2 템플릿을 사용합니다. 의존성은 `requirements.txt`의 `jinja2`입니다.

규칙 기반 버전도 LLM 버전과 동일한 자료 선별 결과를 사용합니다. 따라서 규칙 엔진은 단순 검색 결과 앞부분이 아니라 점수화된 공시, 리포트, 뉴스 자료와 SEC/DART 숫자 데이터를 기준으로 보고서를 구성합니다.

## 국내 기업 DART 설정

국내 기업 분석에서 DART 재무 데이터를 사용하려면 설정 탭에서 `DART API Key`를 저장하거나 `.env`에 아래 값을 넣습니다.

```text
DART_API_KEY=your-opendart-api-key-here
DART_TIMEOUT_SECONDS=30
```

DART 키가 없으면 국내 기업 분석은 로컬 자료와 뉴스/웹 검색 보완 중심으로 동작하며, 공식 재무 숫자 섹션에는 API 키가 없다는 안내가 표시됩니다.

## 보고서 저장

기업분석을 생성하면 자동으로 아래 폴더에 저장됩니다. 보고서 id는 `ticker:날짜` 기준이라, 같은 기업을 같은 날 다시 분석하면 새 파일을 쌓지 않고 최신본으로 덮어씁니다(덮어쓸 때 기존 Personal Overlay는 보존). 여기서 "같은 날"은 **한국시간 날짜**입니다 — 생성 시각은 UTC로 저장되므로 앞 10자를 그대로 쓰면 한국시간 00~09시 생성분이 전날로 묶여 덮어쓰기 대신 파일이 하나 더 생깁니다. 목록 카드의 생성일도 같은 기준으로 표시합니다. 수동 `이 보고서 저장` 버튼도 그대로 동작합니다.

```text
data/company-analysis/
```

웹 UI의 기업 분석 탭은 저장된 보고서를 **카드 피드**로 보여주며, 카드를 누르면 보고서가 React report reader로 열립니다. 각 카드의 휴지통 버튼으로 삭제합니다(이전 드롭다운 선택 방식은 폐기). Reader 안에서 Agent 문의, 노트 연결, Notion/Obsidian 내보내기, Folio Note 작성, 기업 분석 시각화가 동작합니다.

## 프롬프트

```text
features/company_analysis/prompts/beginner.md
features/company_analysis/prompts/advanced.md
```

`features/company_analysis/prompt.md`는 legacy pointer이며 active prompt가 아닙니다.

두 프롬프트는 서로 다른 문체와 깊이를 가지지만 같은 9개 섹션 구조를 따릅니다.

1. 핵심 판단
2. 기업 개요와 사업 구조
3. 실적 요약
4. 밸류에이션
5. 경쟁우위 분석
6. 리스크 + 반증조건
7. 성장 전망 + 앞으로의 주요 이벤트
8. 어떻게 접근할까
9. 참고 자료

## 관련 코드

- `app.py`: `analyze_company()`
- `app.py`: `build_company_analysis_context()`
- `app.py`: `generate_llm_company_analysis()`
- `app.py`: `infer_requested_company()`
- `features/company_analysis/sec_companyfacts.py`: SEC companyfacts API 조회와 재무 테이블 구성
- `features/company_analysis/sec_filings.py`: SEC 10-K HTML 수집, 문단 분리, 섹터별 점수화
- `features/company_analysis/filing_items.py`: 10-K/10-Q Item 분리와 S-1/prospectus 등 로컬 공식자료 키워드 발췌
- `features/company_analysis/report_rules.py`: 규칙 기반 섹션별 보고서 생성
- `public/app.js`: `renderAnalysis()`

## 보조 프롬프트

```text
features/company_analysis/financial_quality_prompt.md
```

이 보조 프롬프트는 기업분석 프롬프트에 자동으로 덧붙어 `Financial Summary` 아래의 `재무 품질 분석` 작성 기준을 제공합니다. 보고서에는 별도 점수 체계 이름을 쓰지 않고, 자본효율성·현금전환·성장 품질·재무 안정성·자본배분을 해석합니다.

## API

```text
GET  /api/analyze?q=UBER&webSearch=1
GET  /api/analyze?q=UBER&webSearch=0
GET  /api/analyze?q=UBER&analysisStyle=beginner
GET  /api/analyze?q=UBER&analysisStyle=advanced
GET  /api/analysis-reports
GET  /api/analysis-reports/<report_id>
POST /api/analysis-reports
DELETE /api/analysis-reports/<report_id>
POST /api/export-notion/analysis
```

`analysisStyle` query parameter는 보고서 모드를 고릅니다. 기본값은 `beginner`입니다.

품질 관련 preflight와 evidence coverage 평가는 내부적으로 자동 수행됩니다. 0.2 UI에서는 사용자가 품질 모드를 직접 선택하지 않습니다.

`POST /api/export-notion/analysis`는 요청 본문으로 저장된 보고서 JSON을 받아 Notion 데이터베이스 페이지로 내보냅니다. `NOTION_TOKEN`과 `NOTION_DB_ID`가 설정되어 있어야 합니다.

## 주의점

- 웹 검색은 로컬 자료가 부족한 경우 보완용으로만 사용합니다.
- SEC API는 `SEC_USER_AGENT` 환경변수를 사용할 수 있습니다. 지정하지 않으면 기본 User-Agent를 사용하지만, 안정적인 사용을 위해 개인 연락처가 포함된 값을 권장합니다.
- 웹 검색 OFF 상태에서는 현재 요청에 `webSearch=0`이 전달되어야 합니다.
- LLM 결과 안의 `Sources Used` 섹션은 UI에서 제거하고, 앱이 별도 참고자료 박스를 표시합니다.

## 외국 기업 (SEC 20-F, Tier 0)

외국 민간 발행인은 10-K 대신 **20-F**를 냅니다. 자동 SEC 경로가 세 곳에서 닫혀 있어 20-F 제출사는 재무도 서술도 나오지 않았고, 사용자가 `research-inbox/filings/`에 직접 넣은 경우에만 fallback으로 보였습니다. 셋 다 열었습니다.

**회계기준은 하나만 씁니다.** 도요타·소니처럼 `us-gaap`과 `ifrs-full`을 함께 가진 제출사가 있는데, 개념별로 맞는 쪽을 골라 읽으면 매출은 한 기준, 자산은 다른 기준이 되어 **어느 재무제표도 아닌 표**가 됩니다. `select_taxonomy()`가 하나를 고르고 그 선택이 숫자와 함께 저장됩니다.

고르는 기준은 **개념 수가 아니라 최신성**입니다. IFRS로 전환한 기업은 더 크지만 멈춘 us-gaap 이력을 남기므로, 개수로 고르면 5년 전 재무를 현재로 내놓습니다(도요타 실측: 2020-03-31).

**통화도 하나만 씁니다.** 20-F 제출사는 자국 통화로 보고하고 일부만 USD 환산치를 함께 냅니다. USD를 우선하면 그 몇 줄이 있는 지표만 USD, 나머지는 자국 통화가 되어 **한 표에 통화가 섞입니다.** `reporting_currency()`가 행 수가 가장 많은 통화를 신고 통화로 잡고, 그 통화로 된 행이 없는 지표는 **추정하지 않고 결측으로 남깁니다.** 표시도 그 통화로 합니다(`€36.80B`, `¥48.04T`).

**IFRS 개념 표는 따로 있습니다.** us-gaap과 이름 체계가 달라 기존 표를 재사용할 수 없습니다(`Revenue`, `ProfitLoss`, `ProfitLossFromOperatingActivities`, `CashFlowsFromUsedInOperatingActivities`). `IFRS_METRIC_CANDIDATES`의 이름은 SAP·도요타의 실제 companyfacts에서 읽은 것만 넣었습니다.

**20-F는 Item 번호 체계가 다릅니다.**

| 내용 | 10-K | 20-F |
| --- | --- | --- |
| 사업 개요 | 1 | 4 |
| 위험 요소 | 1A | 3.D |
| 경영진 논의(MD&A) | 7 | 5 |
| 시장 위험 | 7A | 11 |
| 재무제표 | 8 | 18 |

섹터 프로필의 `items`는 10-K 번호로 쓰여 있어 그대로 대면 20-F에서 **엉뚱한 구획에 가산**됩니다(사업 개요 자리가 제출사 신원으로). `equivalent_items()`가 같은 뜻의 구획끼리 옮깁니다.

**제목은 문단 필터보다 먼저 읽습니다.** 제목은 본래 짧아 문단 필터(80자 이상)가 버리므로, 걸러낸 문단 안에서만 `ITEM 5.`를 찾으면 제목이 본문과 한 줄에 붙은 서식에서만 잡힙니다. ASML의 20-F는 제목이 각자 한 줄이라 모든 문단이 `Unknown`이었습니다.

### 안내 문구도 form을 따릅니다

보고서와 LLM 프롬프트가 "10-K Item 1을 추가하면 보강됩니다"처럼 안내하는데, 20-F 제출사에는 **존재하지 않는 구획**입니다(그 회사의 사업 개요는 Item 4). 규칙 보고서의 안내 문구, source ledger 표기(`SEC 20-F HTML`), LLM 컨텍스트 지침이 모두 실제 form을 따릅니다.

LLM 지침에는 20-F의 Item 대응(사업 4 · 위험 3.D · 경영진 논의 5 · 시장위험 11 · 재무제표 18)도 함께 넣어, 모델이 발췌의 Item 번호를 10-K 기준으로 오해하지 않게 합니다.

### 차트의 통화

재무 차트(실적·현금흐름)는 **신고 통화**, 주가 기반 차트(DCF 내재가치·PER 시나리오)는 **상장 통화**로 표시합니다. 내재가치/주는 현재가와 나란히 읽히므로 주가 쪽을 따릅니다. 마진·수익률 차트는 %라 통화가 없습니다.

DCF 차트는 통화가 `USD`로 하드코딩돼 있었습니다.

### 보고서의 통화

재무 표와 재무 품질·밸류에이션 서술은 **신고 통화**로 표시합니다(`€36.80B`, `¥48.04T`). 0.5 이전에 저장된 보고서에는 통화 필드가 없으므로 USD로 읽어 기존 표시가 그대로 유지됩니다.

**주가와 재무의 통화가 다를 수 있습니다.** ASML은 나스닥에서 달러 ADR로 거래되지만 재무는 유로로 신고합니다. 이때 PSR·EV/EBITDA·FCF Yield는 **USD 시가총액을 EUR 매출로 나눈 값**이라 단위가 없는 숫자입니다. 환산하지 않고 보고서에 `통화 주의` 문단으로 그 사실을 밝힙니다 — 환율을 끌어와 조용히 맞추면 어느 시점 환율인지가 숫자에서 사라집니다.

실측(2026-08-06):

| 기업 | 기준 | 통화 | 지표 | 상위 문단 Item |
| --- | --- | --- | --- | --- |
| ASML | US-GAAP | EUR | 22/24 | 5 |
| SAP | IFRS | EUR | 20/23 | 5·18·4 |
| 도요타 | IFRS | JPY | 19/23 | 4·18·5 |
| 애플(회귀) | US-GAAP | USD | 23/24 | 7 |

## 입력 기업 판단 — 0.5

분석 대상 입력칸은 생성 전에 **무엇으로 읽었는지** 보여준다. 판단은 `features/common/company_resolution.py`가 하고 `GET /api/company/resolve`로 노출된다. 규칙 기반이라 LLM 토큰을 쓰지 않는다.

| status | 화면 동작 |
|---|---|
| `confident` | "Howmet Aerospace (HWM)으로 분석합니다." 그대로 생성 |
| `ambiguous` | 후보 목록을 띄우고 사용자가 고른다 |
| `unknown` | 아는 기업이 없다고 알린다. 진행은 막지 않되 결과가 빈약할 것임을 밝힌다 |

확정되면 `/api/analyze`에 입력 원문이 아니라 **확정된 티커**를 보낸다. "마이크론"을 그대로 넘기면 서버가 다시 추측해 화면에서 고른 것과 달라질 수 있다.

**왜 필요했나.** 예전에는 해석에 실패해도 입력 문자열이 그대로 티커가 되어 분석이 진행됐다. 사용자는 빈 보고서를 받고 나서야 잘못 읽혔다는 걸 알 수 있었다.

## 밸류에이션 (valuation.py)

### 통화·주식 단위 확인

`valuation_basis.py`가 공식 재무의 신고 통화, 주가 단위, 시장가치 통화와 공급자 재무 통화를
구분합니다. 규칙 보고서·차트·API/CLI 공통 생성 입력이 이 판정을 사용합니다.
통화가 다르거나 확인되지 않은 입력을 섞는 계산, 명시된 ADR 비율·주식종류 불일치에
영향받는 주당 계산은 제외하고 `analysisCharts.valuationBasis`와 계산 객체에 사유를 남깁니다.
펜스와 파운드는 같은 값으로 취급하지 않으며, 환율·ADR 환산을 새로 수행하지 않습니다.
시가총액이 없을 때도 주가×주식수 유도에 같은 안전조건을 적용합니다. 다른 통화의 주가로
시가총액을 채우지 않으며, 별도로 통화가 확인된 기업가치와 EBITDA의 계산은 유지합니다.

공식 재무와 주가 통화가 일치하는 계산은 유지합니다. 공급자 재무·현금흐름은 별도로
신고 통화와 일치함을 확인한 경우에만 합칩니다. 주식수 값이 있다는 사실만으로
ADR 비율이나 주식종류를 검증했다고 주장하지 않으며, 공급자가 제공하지 않은 단위
메타데이터까지 확인하는 것은 이 최소 정책의 범위 밖입니다.

계산 제외는 보고서 생성·저장을 막는 조건이 아닙니다. 사업 설명·공식 재무와 유효한
독립 수치는 유지하고, 모델 입력에는 제외 사유와 숫자를 추정하지 말라는 지침을 전달합니다.
임의의 LLM 산문을 사후 환산·재작성하거나 전부 정확하다고 보증하는 검증은 아닙니다.
기존 저장 보고서는 다시 쓰지 않습니다.

### 공통 시나리오

시나리오의 **단일 출처**다. 본문과 차트가 각자 계산하던 시절 한 보고서에 밸류에이션이
두 벌 있었다(실측 HWM 2026-08-27: 본문 EPS 5.54×30/45/60 vs 차트 EPS 4.081×54/73/94).

- `build_valuation_scenarios()` — forward EPS ↔ **forward PER**로 기준을 맞춘다. trailing
  PER을 forward EPS에 곱하면 기본 시나리오가 정의상 `현재가×(1+성장률)`이라 어떤
  회사든 상승으로 나오는 항등식이 된다.
- `render_valuation_contract()` — 컨텍스트에 표를 통째로 싣고 재계산을 금지한다.
- 차트(`service.py::build_company_analysis_charts`)와 컨텍스트(`generation_context.py`)가
  **같은 객체**를 읽는다. `analysisCharts.valuation`에 저장된다.
- **배수는 가정이다.** 비교 기업·과거 밴드 자료가 없으므로 현재 배수 대비 비율로만 두고
  `multipleBasis`가 그 사실을 밝힌다. 근거 있는 배수는 새 데이터소스가 필요하며
  `plan/COMPANY_ANALYSIS_QUALITY_TRANSFER_PLAN.md` §8.2에 미뤄 뒀다.

## 자사주 매입의 질 (buyback.py)

금액만 있으면 매입은 언제나 주주환원으로 읽힌다. **주식 수가 줄지 않는 매입은 환원이
아니라 희석 상쇄다.**

- `build_buyback_quality()` — 매입액, 주식보상 상쇄 비율, 희석주식수 전년 대비,
  매입 수익률, (공시될 때만) 평균 매입가. `buybackQuality`로 저장된다.
- SEC companyfacts만 쓴다(`ShareBasedCompensation`, `TreasuryStockSharesAcquired`를
  0.5.4에 등재). 새 데이터소스가 필요 없다.
- `TreasuryStockSharesAcquired`는 등재하지 않는 회사가 많아(실측 HWM 없음) 평균 매입가는
  있을 때만 낸다. 없으면 없다고 적는다.
- **판정하지 않는다.** 비율을 보여줄 뿐 좋다·나쁘다는 본문이 쓴다(§5 원칙 4).

## DCF (dcf.py)

예전 모델의 문제는 정교함이 아니라 **모든 회사에 같은 답을 준다**는 것이었다. 실측
5개사가 전부 "현재가의 37~62%"였고, 가치의 71~76%가 터미널인데 보고서 어디에도 그
사실이 없었다.

- `build_dcf()` — 정상화 → 할인율 → 감쇠 → 시나리오 → 역산. `analysisCharts.dcf`에
  저장되고 차트·본문 컨텍스트·규칙 보고서가 **같은 객체**를 읽는다.
- `normalized_base_fcf()` — 중앙값 FCF 마진 × 최근 매출. 최근 1년이 회사 가치를 정하지
  않게 한다. 어느 방법으로 내려갔는지 `method`가 말한다.
- `growth_driver()` — 매출 CAGR 우선. FCF 성장률은 매출과 부호까지 어긋난다.
- `estimate_discount_rate()` — 회사별 WACC, 블룸 조정 베타. 입력이 없으면 고정값으로
  내려가되 `method: fallback_fixed`와 `missing`을 남긴다.
- `implied_growth()` — 현재가를 정당화하는 초기 성장률. **이 층의 핵심 숫자다.**
- 예측 기간 10년, 선형 감쇠, 터미널 비중 공시(`TERMINAL_SHARE_WARN` 70%).
- 시나리오는 성장률만, 민감도 표가 할인율·영구성장. 둘은 같은 모델을 쓴다.
- `assumption_sensitivity()` — 무위험수익률(±0.5%p)·ERP(4/5/6%)가 내재가치와 역산
  성장률을 얼마나 움직이는지의 감도표(`assumptionSensitivity`). **값을 맞히는 것보다
  그 값이 답을 얼마나 지배하는지 보이는 쪽이 먼저다** — 실측 ERP 4~6%가 MSFT 내재가치를
  37% 흔든다. WACC 경로에서만 낸다(고정 할인율은 두 입력을 읽지 않는다). 본문 컨텍스트와
  규칙 보고서 둘 다 이 표를 싣고, 내재가치를 하나의 값이 아니라 범위로 읽으라고 적는다.
- 무위험수익률·위험프리미엄은 **가정**이다. `risk_free` 인자로 살아 있는 값을 주입할
  수 있지만 이 모듈은 스스로 조회하지 않는다.
- 조회는 `risk_free.py::current_risk_free()`가 한다 — USD만, 키는
  `llm_settings.client.fred_api_key()`로 읽어(설정 화면이 `.env`에 쓴 키가 보인다)
  FRED `DGS10`, 없으면 yfinance `^TNX`. 캐시는 1일 TTL + shape 버전
  (`data/company-analysis/market-cache/risk-free.json` — **상위 폴더에 두면 보고서
  목록 glob이 캐시를 보고서 카드로 올린다**), 조회 실패 시 stale 캐시(상한 7일 —
  무제한이면 낡은 금리가 살아 있는 값처럼 주입된다) → 통화 상수 순 폴백이고, 실패도
  기록해 1시간 쿨다운을 둔다(오프라인에서 보고서마다 timeout을 되풀이하지 않게).
  `build_dcf`는 meta dict를 통째로 받아 `riskFreeMeta`(source·asOf·관측일)를 스스로
  싣는다 — 호출부가 사후 주입하지 않는다. 테스트 가드는 함수 맨 위라 pytest에서는
  실워크스페이스 캐시조차 읽지 않는다. 비USD는 OECD 월간 계열이 9개월 뒤처져 있어
  (실측 2025-11) 상수 유지 — 쓰기로 결정하면 관측일을 함께 실어야 한다. 두 생성
  경로(API·CLI)가 같은 조회를 거친다(`report_rules`·`service`의 `build_dcf` 호출부).
