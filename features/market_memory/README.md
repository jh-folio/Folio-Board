# 시장 내러티브 메모리

시장 내러티브 메모리는 일일 브리핑에서 반복적으로 등장하는 테마를 단기 기사와 분리해 누적하고, 현재 유효한 투자 내러티브 상태를 관리하는 기능입니다.

0.2 Deep Research는 현재 Market State를 `current|stale|fallback|empty`의 별도 source-grounded context로 참조할 수 있습니다. 이 참조는 보고서의 `evidenceItems`, `sourceLedger`, 인용, evidence coverage, 사용자 hypothesis를 바꾸지 않습니다.

## 담당 기능

- 브리핑 생성 시 주요 이슈 묶음을 `data/market-memory.sqlite3`에 저장합니다.
- 기사 제목/요약을 그대로 이어 붙이지 않고, 한국어 내러티브 문장으로 압축합니다.
- 영문 기사 본문은 길게 노출하지 않고 출처, 태그, 이벤트 성격을 바탕으로 한국어 관찰 포인트로 정리합니다.
- `Original link`, URL, `#` 등 RSS 원문 노이즈와 중복 문장을 제거합니다.
- 각 메모리에 최소 온톨로지를 붙입니다.
  - `category`: `stock_bond`, `geopolitics`, `emerging`
  - `region`: `US`, `KR`, `GLOBAL`
  - `importance`: `high`, `medium`, `low`
  - `entry_mode`: `issue`, `brief`
  - `event_kind`: `earnings`, `policy`, `geopolitics`, `industry_trend`, `market_move`, `brief`
- `story`, `story_family`, `story_thesis`, `story_checkpoint`로 메모리를 맥락화합니다.
- `state_label`, `story_family`는 `nvidia`, `samsung_electro_mechanics` 같은 slug가 아니라 사람이 읽는 제목으로 저장합니다.
- `market_narrative_states` 테이블에 현재 상태를 저장합니다.
  - `status`: `active`, `watch`, `resolved`, `overridden`
  - `bias`: `bullish`, `bearish`, `neutral`, `mixed`
  - `net_effect`: 해당 내러티브가 어떤 방향의 시장 효과를 갖는지에 대한 짧은 키
- Regime 추적 v2 필드를 같은 상태 테이블에 저장합니다.
  - `momentum`: `strengthening`, `stable`, `fading`, `turning`, `conflicted`
  - `confidence`, `evidence_count_7d/30d/90d`, `last_confirmed_at`, `last_challenged_at`
  - `falsification_triggers_json`, `next_checkpoints_json`
- `market_regime_evidence`, `market_regime_changes`, `market_regime_thesis_links` 테이블에 상태별 근거, 변화 로그, thesis 연결을 저장합니다.
- `market_memory_taxonomy` 테이블에 story, story_family, tag, industry, ticker, subject, event_kind, state_key의 사용량을 누적합니다.
- `market_story_links` 테이블에 branch와 family의 관계를 저장합니다.
  - `branches_from`, `same_family`, `confirms`, `conflicts_with`, `replaces`, `evolves_from`
- `market_story_family_suggestions` 테이블에 새 스토리가 기존 패밀리와 연결될 가능성을 저장합니다.
- story router가 개별 기업/섹터 이슈를 더 큰 family에 연결합니다.
  - 예: NVIDIA, Dell, SK하이닉스, 삼성전자 관련 AI 서버/반도체 이슈 → `AI 반도체 공급망`
  - 예: AI 데이터센터와 전력/유틸리티/전선 이슈 → `AI 데이터센터 전력 병목`
  - 예: 국채, 금리, 달러, FX 이슈 → `금리·달러 유동성`
- state router는 canonical state alias를 적용해 비슷한 active/watch 내러티브가 여러 개 뜨지 않게 합니다.
  - 예: `AI 공급망 병목 수혜 재선별` → `AI 반도체 공급망`
  - 예: `한국 반도체의 해외 자본시장 접근성과 수급 민감도` → `한국 반도체 수출 수혜와 원화·수급 긴장`
  - 예: `energy_geopolitical_risk` → `중동 에너지 리스크`
- 웹 UI의 `시장 내러티브` 탭에서 현재 중기 시장 상황과 누적 메모리 기반 판단을 확인합니다.
- 상태 카드에서 추세(momentum), 확신도(confidence), 7/30/90일 근거 수, 연결 기업, 연결 thesis 수를 확인하고 `추세 갱신`/`변화 로그`를 실행합니다. (표시명 `추세`/`확신도`는 내부 코드·API·테이블의 `regime`/`momentum`/`confidence`에 대응합니다.)
- Step 6 Data Foundation Lite 이후 Regime 추세 갱신은 `next_checkpoints_json`과 `falsification_triggers_json`도 함께 채워, 대시보드가 markdown 파싱 없이 이번 주 확인 항목을 읽을 수 있게 합니다.
- 서버 시작 시 active/watch 상태의 Regime 추세를 백그라운드에서 자동 갱신합니다. 시작 시 갱신을 끄려면 `STARTUP_REGIME_REFRESH=0`을 사용합니다.
- 웹 UI에서 내러티브 리포트, 품질 점검, 스토리 맵, 패밀리 리뷰를 함께 확인합니다.
- `시장 메모리 업데이트` 버튼을 누르면, 최신 뉴스 기반 내러티브 row 누적과 현재 시장 상태 스냅샷 생성을 순서대로 실행합니다.
- 브리핑 생성 전 LLM 컨텍스트에 최근 내러티브 메모리를 넣어 단발성 기사 나열을 줄입니다.

## 태그 어휘

`TAG_ALIASES`, `INDUSTRY_ALIASES`, `canonical_tag()`, `canonical_industry()`는 `features/common/taxonomy.py`에서 가져옵니다. 태그 alias를 추가하거나 canonical label을 수정할 때는 `taxonomy.py`만 수정하면 market_memory와 research library indexing에 동시 반영됩니다.

## 주요 파일

- `features/market_memory/memory.py`: SQLite 저장, 조회, 온톨로지 추론, 상태 관리, 브리핑 기반 메모리 생성
- `features/market_memory/memory.py`: 감사 리포트, 스토리 맵, 패밀리 제안, 상태 수동 업데이트 로직
- `features/market_memory/service.py`: LLM 기반 내러티브 정리와 서버 시작 시 Regime 추세 자동 갱신 스케줄링
- `features/market_memory/regime_v2.py`: Regime 근거 분류, momentum/confidence 계산, 변화 로그, thesis 연결
- `features/market_memory/checkpoint_verdicts.py`: 구조화 체크포인트 판정 pass(규칙 기반)와 생성·교체 쓰기 경로
- `features/thesis_tracking/checkpoint_verdicts.py`: thesis 체크포인트 판정(근거 풀은 연구 인덱스 문서, 0건이면 인덱스를 열지 않음)
- `features/market_memory/verification_view.py`: 내러티브 검증 상태 읽기 projection(체크포인트 판정·무소식 배지·판정 이력)
- `features/common/research_schema/tracked_checkpoints.py`: 구조화 체크포인트 스키마·검증·병합 (market_memory와 thesis_tracking 공용)
- `features/market_memory/prompt.md`: LLM 기반 시장 내러티브 정리 프롬프트
- `app.py`: `/api/memory`, `/api/memory/states`, `/api/memory/regime/refresh`, `/api/memory/states/{state_id}/evidence|changes|thesis-links` API와 브리핑 생성 후 자동 저장
- `public/index.html`, `public/app.js`, `public/styles.css`: 시장 내러티브 탭 UI

## 설계 원칙

- 원문 전문을 다시 저장하는 기능이 아니라 summary-first memory입니다.
- UI에 표시되는 summary는 원문 인용 저장소가 아니라 “이 이슈가 왜 시장 상태로 남는지”를 설명하는 요약이어야 합니다.
- 원문 근거는 `research-inbox/rss`, `research-inbox/articles`, 브리핑 참고자료 링크를 우선합니다.
- 상태는 “현재 투자자가 기억해야 하는 흐름”만 담고, 개별 기사 목록은 메모리 로그에 남깁니다.
- 상태는 모든 엔트리에서 자동 생성하지 않습니다. 최소 반복 근거가 있거나, 중요도가 높고 복수 출처가 있을 때 active/watch로 올립니다.
- 기존 분류값을 우선 재사용하고, 새 키는 최소 단위로 추가합니다.
- `brief` 메모는 기본적으로 상태를 만들지 않고, `issue` 메모만 상태 후보가 됩니다.
- LLM은 버튼을 눌렀을 때만 실행합니다. 컨텍스트는 후보 이슈 4개, 각 이슈당 상위 자료 2개, 최근 메모리/상태/패밀리의 압축본으로 제한합니다.
- LLM 출력은 JSON으로 파싱하고 허용된 enum과 필드 길이를 코드에서 다시 정규화한 뒤 저장합니다.
- Regime v2의 최종 `momentum`과 evidence `role`은 코드 enum으로 검증합니다. LLM 자유 텍스트로 결론을 확정하지 않습니다.
- Thesis/Obsidian 노트는 hypothesis입니다. Regime v2는 `linked_regimes`, ticker overlap 등을 연결 정보로만 쓰며 외부 evidence처럼 취급하지 않습니다.
- `method='manual'`로 저장된 Regime↔thesis 링크의 `relationship`은 자동 추론 갱신(`refresh_thesis_links`)이 덮어쓰지 않습니다. 이 갱신은 서버 시작과 자동화마다 돌기 때문에, 보호하지 않으면 사용자가 지정한 값이 예고 없이 사라집니다.
- 메모리 재저장은 Regime 갱신이 계산한 `confidence`를 되돌리지 않습니다. 같은 날 같은 `state_key`는 같은 행이라 재저장이 흔한 경로이고, `momentum`·근거 카운트는 남는데 `confidence`만 기본값으로 돌아가면 행이 서로 모순됩니다.
- 규칙 추세 갱신은 `next_checkpoints_json`을 덮어쓰지 않고 병합합니다. 구조화 체크포인트의 판정 상태는 판정 pass만 바꾸며, 갱신은 템플릿 문장만 다시 씁니다.
- 체크포인트 판정은 `confirmed | challenged | no_signal` enum이며 규칙으로만 계산합니다. 판정이 내러티브 status/momentum이나 Thesis verdict를 자동으로 바꾸지 않습니다.
- 기본 브리핑 markdown은 추세 갱신으로 변경하지 않습니다.
- 기업 분석의 공식자료 우선순위와 섞지 않습니다.

## 구조화 체크포인트와 판정 pass (0.6 Stage A)

"다음에 이것을 확인하자"를 저장만 하고 그 '다음'이 와도 되짚지 않던 것을, 매일 돌아오는 루프로 바꿉니다.

### 저장 형태 — 한 리스트에 두 종류가 산다

저장 위치는 기존 컬럼 그대로입니다(`market_narrative_states.next_checkpoints_json`, thesis는 `thesis.next_checkpoints_json`). **새 테이블을 만들지 않습니다.** 리스트의 원소는 둘 중 하나이며 읽는 쪽은 둘 다 받습니다.

- `str`: 규칙 엔진이 갱신마다 다시 만드는 템플릿 문장. 기존 저장본은 전부 이것입니다.
- `dict`: 구조화 체크포인트. `features/common/research_schema/tracked_checkpoints.py`가 스키마와 검증을 소유합니다.

```text
{ "id": "cp_<정규화(item+matchers) 해시 8자>",   // 재생성·중복 판별 키
  "item": "전력 설비 기업 실적 가이던스 상향",     // <=120자
  "direction": "supporting" | "challenging",       // 이 신호가 잡히면 무슨 의미인가
  "matchers": { "tickers": [...], "keywords": [...] },
  "dueBy": "2026-09-15" | null,
  "status": "open" | "confirmed" | "challenged" | "expired",
  "createdAt": "...",
  "lastVerdict": { "verdict": "confirmed|challenged|no_signal", "at": "...",
                   "evidence": [{"memoryId","date","title","role"}] },   // <=3건 사본
  "history": [ {"at","from","to","verdict"} ] }                          // 상한 20
```

- **enum과 길이는 코드가 집행합니다.** `direction`은 뜻이 뒤집히는 값이라 기본값을 주지 않습니다 — enum을 벗어나면 그 원소를 버립니다. `status`·`lastVerdict.verdict`는 모르는 값이면 기본값(`open`)으로 내려가고, 모르는 키는 제거합니다.
- **상태 라벨 전문을 keyword로 쓸 수 없습니다.** 라벨을 keyword로 쓰면 그 상태의 모든 근거가 매칭돼 과잉 확인이 됩니다 — 실측으로 근거의 `matched_terms`에 `state_key` 자체가 들어 있습니다. 비교는 공백을 지우고 합니다.
- **내러티브는 keyword >=1, thesis는 ticker >=1 그리고 keyword >=1을 요구합니다.** 티커만으로는 "그 회사 뉴스가 있다"이지 가설 신호가 아닙니다.
- 상태당 구조화 체크포인트는 8개까지, `dueBy`는 생성 시점 이후의 ISO 날짜만 받습니다.
- **검증 실패의 처분은 경로에 따라 다릅니다.** 생성 경로(LLM 출력·수동 입력)에서 실패한 원소는 버리고 규칙 템플릿 문장이 그 자리를 대신합니다(화면이 비지 않습니다). **저장된 원소의 재검증 실패는 버리지 않고 그대로 보존하며 판정에서만 뺍니다** — 그 실패는 원소가 아니라 규칙 쪽 변화(라벨 개명 등)이고, 매일 도는 갱신·판정이 그것을 지우면 체크포인트와 이력이 소리 없이 사라집니다. 화면은 이 원소에 `검증 불가`를 표시합니다. 생성 경로의 원소는 `status`/`lastVerdict`/`history`/`createdAt`을 낼 수 없습니다 — 서버가 찍습니다(받으면 '이미 확인됨'으로 태어나는 체크포인트가 생깁니다). `id`에는 스코프 정체성(state_key/ticker)이 들어가 서로 다른 상태의 같은 문구가 다른 id를 받습니다.

### 갱신 생존 — 규칙 갱신은 덮어쓰지 않고 병합합니다

`refresh_regime_state`는 예전에 `next_checkpoints_json`을 통째로 새 템플릿으로 덮어썼습니다. 이 갱신은 서버 시작마다·RSS 수집마다 돌기 때문에, 그대로 두면 구조화 체크포인트를 만들어도 다음 갱신에 status가 초기화됩니다. 지금은 `merge_with_templates()`로 **구조화 원소는 보존하고 템플릿 문장만 오늘 것으로 갈아끼웁니다.**

구조화 체크포인트의 생성·교체는 규칙 갱신이 아니라 명시적 쓰기 경로에서만 일어납니다(`checkpoint_verdicts.merge_state_checkpoints`). 같은 `id`는 `status`·`history`·`lastVerdict`·`createdAt`을 승계하고, 새 것은 추가하며, 사라진 것 중 `open`은 유지하고 해소된 것은 상한 안에서 오래된 것부터 정리합니다.

### 판정 pass

`features/market_memory/checkpoint_verdicts.py`가 소유하며 `run_rss_market_memory_update()`의 `refresh_all_regimes` **뒤**에 돕니다(근거 행이 방금 갱신된 뒤라야 대조할 것이 있습니다). **LLM을 부르지 않습니다.**

- 대조 기준일: 판정 이력이 있으면 마지막 verdict **날짜이고 그 날짜는 다시 봅니다**(오전 판정 뒤 같은 날짜로 들어온 반증이 영구 스킵되면 confirmed가 하루 종일 눌러앉습니다 — 같은 행을 다시 봐도 판정은 결정적이고 이력은 바뀔 때만 남아 멱등합니다). 첫 판정은 `createdAt` **날짜를 제외합니다** — 체크포인트는 대개 그날의 근거에서 태어나므로 낳아 준 근거로 즉시 확인되는 것은 자기확인입니다.
- 매칭: keyword가 근거의 제목+요약+`matchedTerms`에 **공백 제거 부분일치**, 또는 ticker가 `matchedTerms`에 있으면 hit입니다. 티커를 본문에서 찾지 않는 것은 의도입니다 — 짧은 티커가 한국어 본문에 우연히 걸리면 그 회사와 무관한 기사가 확인 신호가 됩니다.
- **과잉 판정 방지와 판정 규칙**: (1) `neutral` role은 절대 세지 않습니다(실측 898행 중 364행이 neutral — 이걸 세면 매일 confirmed가 됩니다). (2) **role이 판정을 정합니다** — 매칭된 supporting행은 확인 신호, challenging행은 반증 신호이며 체크포인트 direction과 무관합니다(direction으로 거르면 반증 단독이 무시됩니다). direction은 체크포인트가 무엇을 기다리는지의 메타데이터이고, role이 없는 풀(thesis)에서만 판정 방향을 정합니다. (3) `score >= 0.5`만 셉니다(실측 실사용 근거는 0.71~1.0). (4) 반증이 하나라도 있으면 **challenged**입니다 — 확증편향 방지는 반증에 우선권을 줍니다. 근거 사본도 반증을 먼저 싣습니다(잘리면 challenged 배지 아래 확인 기사만 보입니다).
- verdict 의미: 반증 신호가 있으면 `challenged`, 확인 신호만 있으면 `confirmed`, 아무것도 없으면 `no_signal`(아무것도 바꾸지 않습니다). `dueBy` 경과 + 판정 없음이면 `status=expired`이며, 이것은 판정이 아니라 상태 전환이라 이력에만 남습니다.
- **같은 날 두 번 돌아도 안전합니다.** 판정은 같은 입력에 결정적이고, 이력과 저장은 verdict가 **바뀔 때만** 씁니다. 판정 pass는 **읽기 우선**입니다 — 바뀐 원소만 제자리 교체하고 검증 실패 dict·템플릿·순서는 건드리지 않으며, 변화가 없으면 쓰지 않습니다. `market_regime_changes`에 남기는 근거 참조는 `memory:` 접두의 memory_id 사본입니다(이 컬럼의 다른 생산자는 진짜 evidence_id를 쓰므로 이름공간을 가릅니다).
- **판정은 기록이지 상태 전환이 아닙니다.** 내러티브의 `status`/`momentum`은 기존 규칙이 계속 소유하고, 이 pass는 체크포인트 자신의 `status`만 바꿉니다.

### 판정 이력

내러티브는 기존 `market_regime_changes` 테이블에 `field="checkpoint:<id>"` 행으로 남깁니다. **근거 참조는 `evidence_id`가 아니라 `memory_id` 사본입니다** — 근거 행은 갱신마다 `DELETE` 후 재삽입이라 `evidence_id`가 다음 갱신에 사라집니다(`regime_v2.py` 실측). 같은 이유로 체크포인트의 `lastVerdict.evidence`도 `memoryId` + 날짜·제목 사본을 들고 있습니다. thesis는 체크포인트 dict 안의 `history` 배열(상한 20)과 기존 `thesis_delta`를 쓰며 새 테이블을 만들지 않습니다.

### 생성 경로 — LLM 시장 메모리 업데이트

구조화 체크포인트는 **시장 메모리 업데이트**에서 태어납니다. LLM 엔트리의 `nextCheckpoints` 필드이며 모양은 `[{item, direction, matchers:{tickers,keywords}, dueBy?}]`, 엔트리당 최대 3개입니다.

- **LLM은 `id`·`status`·`createdAt`·`lastVerdict`·`history`를 내지 않습니다.** 서버가 찍습니다 — 맡기면 "이미 확인됨"으로 태어나는 체크포인트가 생깁니다. 입력 모양에서 그 키들을 들이지 않고(`service.llm_checkpoint_inputs`), validator가 `trusted=False`로 한 번 더 벗깁니다.
- **프롬프트는 부탁이고 집행은 validator입니다.** `prompt.md`가 모양·direction enum·keyword 규칙(각 2~40자, 상태 라벨 전문 금지, 방향을 담은 구체어)·엔트리당 3개 상한을 지시하지만, 검증은 `tracked_checkpoints`가 병합 시점에 합니다.
- **귀속은 엔트리의 `stateKey`를 따릅니다.** 엔트리가 active/watch 상태를 만들거나 갱신할 때 그 상태에 `merge_state_checkpoints`로 병합하고, **새 상태를 파생하지 않아도**(중요도 미달 등) `stateKey`의 살아 있는 상태가 있으면 거기에 붙습니다(`current_state_id_for_key`). 상태로 승격되지 않은 issue 메모의 체크포인트만 버리고 **버린 개수를 결과 요약에 남깁니다**(`checkpointsMerged`/`checkpointsDropped`). 병합 **실패**는 dropped에 섞지 않고 `checkpointErrors`+`checkpointErrorCode`(예외 클래스)로 따로 셉니다 — 섞으면 기능 전체가 죽어도 "LLM이 나쁜 체크포인트를 냈다"와 구분되지 않습니다.
- **체크포인트는 계보(state_key)의 소유물입니다.** 상태 행은 날짜별로 회전하고(state_id = sha(state_key:date)) 이전 행은 overridden으로 밀리는데, `upsert_state_from_memory`가 회전 시 밀려나는 행의 목록을 새 행에 **승계**합니다 — 없으면 같은 체크포인트가 매일 open으로 다시 태어나고 어제의 판정·이력은 판정 pass가 다시는 방문하지 않는 행에 고립됩니다. `dueBy` 없는 open도 구조 판정 창(90일)을 신호 없이 넘기면 `expired`가 됩니다(병합은 open을 자르지 않으므로 만료가 무한 누적의 유일한 출구).
- **생성 경로가 둘이라 저장을 한 함수로 모았습니다**(`service.save_memory_entries`). `/api/memory/llm`(API 키)과 Agent CLI writeback이 같은 함수를 쓰므로 병합 계약이 한쪽에만 붙는 일이 구조적으로 불가능합니다.
- **`storyCheckpoint`(자유 문장)는 그대로 병존합니다.** 사람이 읽는 한 줄 요약이고, 구조화 체크포인트는 기계가 대조하는 층입니다. 대체하면 LLM 구조화 실패가 곧 표시 실패가 됩니다.
- 상태 스냅샷 경로는 체크포인트를 내지 않습니다 — 생성 경로가 늘수록 병합 규칙이 갈라집니다.

### thesis 판정 — 근거 풀은 연구 인덱스 문서

`features/thesis_tracking/checkpoint_verdicts.py`가 소유하며 내러티브 판정과 같은 자리에서 돕니다. 판정 코어는 같고 근거 풀만 다릅니다.

- 풀은 **연구 인덱스 문서를 직접 훑어** 그 회사 태그가 붙은 뉴스만 **날짜순**으로 모읍니다(컷오프 이후만, 안전판 상한 500은 가장 오래된 쪽을 자름). `search_documents` 브라우즈의 관련도순 상한 200을 쓰지 않습니다 — 보도가 많은 종목(실측 GOOGL 9,387건 태그)에서 이번 주 기사가 상한 밖으로 잘려 판정이 영영 `no_signal`이 됩니다. `market_memory` 행을 보조로 섞지 않습니다: 두 풀을 합치면 어느 풀이 판정했는지 설명할 수 없습니다.
- **구조화 체크포인트를 가진 thesis가 하나도 없으면 인덱스를 열지 않습니다.** `load_index()`는 실측 4.7초라 수집 자동화 경로에서 공짜가 아닙니다.
- 문서가 그 회사 **태그를 실제로 갖고 있어야** 근거입니다. 제목 부분일치로 딸려 온 남의 기사는 걸러냅니다(워치리스트가 배운 것과 같은 규칙 — 연결 열쇠는 종목 코드).
- **문서 풀에는 role 분류가 없습니다.** 그래서 체크포인트의 `direction`이 판정 방향을 정하고(supporting → `confirmed`, challenging → `challenged`, enum 밖은 판정하지 않음), 근거 사본 키는 `memoryId`가 아니라 `docId`(**URL 우선** — 파일 경로는 보관 기간 정리가 지웁니다)이며 `role`을 싣지 않습니다.
- **회사명·티커는 매칭 재료가 아닙니다.** 풀이 이미 그 종목으로 걸러져 있어 회사 태그가 haystack에 들어가면 회사명 keyword가 모든 기사에 걸립니다 — 행에 matchedTerms를 싣지 않고(haystack = 제목+요약) validator 금지어에 티커·회사명을 넘깁니다. **keyword가 방향을 담아야 합니다**("가이던스 상향").
- 판정 이력은 체크포인트 dict 안의 `history` 배열입니다(상한 20). thesis 하나가 실패해도 나머지 판정은 계속됩니다(결과 행에 오류 코드).
- 쓰기는 `store.save_thesis_checkpoints`로 `next_checkpoints_json`만 제자리 교체합니다. **`last_reviewed_at`도 `updated_at`도 바꾸지 않습니다** — Delta의 `since_last_review`가 `updated_at`으로 물러나는 폴백이 있어, 올리면 기계 판정이 사용자 검토로 읽힙니다. 노트 재동기화(`upsert_thesis`)는 문자열 목록만 갈아끼우므로 판정 status와 이력이 살아남습니다.

### 화면 — 내러티브 검증 상태 (0.6 Stage C.1·C.3)

시장 내러티브 탭의 드라이버 카드 **아래**에 `내러티브 검증 상태` 패널이 있습니다(`web/src/app/marketMemory/NarrativeVerificationPanel.tsx`, payload는 `GET /api/memory/verification`).

- **위 카드와 같은 층이 아닙니다.** 드라이버 카드는 스냅샷이 쓴 해석이고 이 패널은 저장된 `market_narrative_states`의 규칙 판정입니다. 스냅샷 드라이버에는 상태 정체성이 없어(`snapshot-driver:N`) 체크포인트를 붙일 수 없고, 제목으로 이어 붙이는 매칭은 이 저장소가 여러 번 데인 방식입니다 — 그래서 섞지 않고 자기 자리에서 보여줍니다.
- 상태마다 **구조화 체크포인트의 판정**(확인됨/반증 신호/확인 대기/기한 경과)과 그 판정이 쓴 **근거 제목 사본**(최대 3건), 기한을 보여줍니다.
- **무소식 배지**가 죽어가는 이야기와 살아있는 이야기를 갈라 보여줍니다. 계획 §4의 고정 사다리를 그대로 씁니다 — 14일이면 `식어가는 중`, 30일이면 `정리 후보`입니다. **30일은 제안일 뿐 상태를 자동으로 바꾸지 않으며**, 화면이 그 문장을 함께 적습니다.
- **검증 불가**: 저장돼 있지만 지금 규칙으로 재검증되지 않는 dict 원소는 지워지지 않고 보존됩니다. 화면은 그 건수를 밝히고 판정에서 빠진다고 말합니다 — 조용히 사라지면 사용자가 이력을 잃습니다.
- **판정 이력**(C.3)은 기존 `market_regime_changes`를 읽습니다. `evidence_ids_json`의 `memory:` 접두 항목은 memory_id 사본이라 join하지 않고 **건수만** 보여주며, 화면에 내부 id를 흘리지 않습니다. 전환 값(`open`→`confirmed`)은 사람 말로 옮겨 보여줍니다.
- 상태는 **색만으로 전달하지 않습니다** — 기호와 라벨이 함께 가고 색은 보조입니다(WCAG 1.4.1). 표시 언어는 Watchlist Thesis workspace와 `web/src/app/verification.ts` 하나를 공유합니다.
- 이 패널은 **읽기 전용**입니다. 판정은 자료 수집 뒤 규칙 pass가 이미 끝냈고 화면은 그 결과를 읽을 뿐입니다.

### 남은 것

- **thesis 체크포인트를 만드는 화면·API가 아직 없습니다**(Stage B). 티커·회사명 keyword 금지는 이제 검증이 겁니다(`_forbidden_terms` — 저장·판정 양쪽 동일).
- 화면 표시(`검증 불가` 배지, 무소식 배지, 판정 타임라인)는 Stage C입니다.

## RSS Short-Term Memory Intake

Market Memory can be updated from RSS/evidence before a briefing is generated. RSS items are first grouped into short-term digest items. Only repeated, source-diverse, market-relevant digest items are promoted into medium-term Market Memory entries.

This keeps the hierarchy explicit: RSS/evidence is short-term memory, Market Memory is medium-term memory, and reports consume both.

`run_rss_market_memory_update()`는 digest 반영 후 active/watch 상태의 규칙 기반 추세 갱신(`refresh_all_regimes`)과 체크포인트 판정 pass(내러티브 `run_checkpoint_verdicts`, thesis `run_thesis_checkpoint_verdicts`)까지 함께 실행한다. 판정 실패는 수집 잡을 죽이지 않는다. RSS 수집·Market Memory 자동화가 돌 때마다 momentum/confidence/근거 카운트가 자동으로 갱신되며, 화면에서 상태별 수동 갱신 버튼은 제공하지 않는다.

Market State Snapshot 생성 시에는 코드가 축별 점수로 강하게 선별하지 않는다. `build_market_state_context()`는 최신 RSS 후보를 넓게 압축한 `rssCandidates`(기본 최대 120개)를 LLM에 넘기고, 기존 축별 `shortTermDigest`는 탐색 보조 인덱스로만 제공한다. 중요한 드라이버 선택, 방향성 판단, 행동 가이드 작성은 LLM이 수행한다.

기존 Market Memory 상태(`existingStates`)는 보존해야 할 결론이 아니라 재검증할 중기 가설이다. LLM은 최신 `rssCandidates`가 기존 상태를 지지하는지, 약화시키는지, 변화시키는지, 또는 무효화하는지를 판단해야 하며 기존 요약을 재귀적으로 반복하지 않는다.

Market/macro context extension:

- `marketTape`: yfinance 기반 가격 흐름. 미국장은 S&P 500, Nasdaq, Dow, VIX, 10Y proxy, WTI, 달러 proxy를 우선하고, 한국장은 KOSPI, KOSDAQ, USD/KRW, MSCI Korea ETF를 우선한다.
- `macroSnapshot`: 공식 거시 데이터. 미국장은 FRED, 한국장은 BOK/ECOS를 주요 입력원으로 삼아 금리, 물가, 환율, 수출, 경기 흐름을 구조화한다. API key가 없거나 조회 실패 시에는 결측 사유를 context에 남긴다.
- yfinance/FRED/BOK 값은 LLM이 시장 판단을 작성하기 위한 structured evidence다. 코드는 freshness/staleness, provider, window, 단위, 결측 여부를 정리하고 검증하지만 시장 결론을 규칙으로 확정하지 않는다.
- `market_scope`가 `overall`이 아니면 `rssCandidates`와 `shortTermDigest`는 그 시장 태그와 `GLOBAL`만 남긴다. 비교는 시장 계약(`PRODUCT_MARKETS`) 파생이라 US/KR뿐 아니라 EUROPE/JP에도 같은 필터가 걸린다 — instruction이 모델에게 "이 목록은 이 marketScope로 이미 걸러졌다"고 보증하기 때문이다.
- `build_market_state_context()`는 `rssCandidates`, `shortTermDigest`, `existingStates`와 함께 `marketTape`, `macroSnapshot`을 LLM에 넘긴다. LLM은 이 값을 뉴스 기반 내러티브를 확인하거나 약화시키는 보조 근거로 사용한다.

## Market State Dashboard v3 (기본 화면)

시장 내러티브 탭의 기본 화면은 `GET /api/memory/state-dashboard`가 반환하는 **현재 중기 시장 상황** 하나다.

- 우선순위는 `market_state_snapshots`의 최신 LLM-authored `MarketStateSnapshot`이다. 스냅샷이 없거나 구버전 스냅샷이면 기존 `market_narrative_states` 기반 fallback을 쓰되, 이는 표시 호환용이며 시장 판단의 주 경로가 아니다.
- `POST /api/memory/state-snapshot`은 RSS 단기 digest와 기존 중기 상태를 Agent/LLM context pack으로 묶어 현재 시장 전체판단 스냅샷을 생성한다.
- `GET /api/memory/state-snapshot`은 최신 스냅샷을 반환한다.
- 화면용 판단은 LLM이 snapshot 안에 쓰는 `beginnerSummary`, `actionGuide`, 그리고 드라이버별 `directionLabel`/`marketImpact`/`nextMemoryCheck`를 우선 사용한다. 코드는 이 값을 검증하고 렌더링할 뿐, 정상 경로에서 시장 판단을 규칙으로 새로 만들지 않는다.
- `stale` 스냅샷은 본문을 가리지 않는다. 화면 상단의 한 줄 최신성 알림으로 업데이트 필요 사유와 새 자료 기준 시각을 표시하고, 이전 스냅샷의 시장 해석·행동 가이드·드라이버·반대 근거·불확실성·출처는 계속 읽을 수 있게 유지한다. 단, stale 판단을 현재 상태로 승격하거나 보고서 evidence로 주입하지 않는다.
- 최신성 정책은 스냅샷 생성 후 24시간 동안 새 외부 자료에 대한 유예기간을 둔다. 24시간을 초과한 뒤 입력 기준점보다 새 자료가 있으면 `업데이트 필요`, 새 자료 여부와 관계없이 72시간을 초과하면 `최신성 만료`로 표시한다. 정확히 24시간과 72시간인 경계값은 아직 유효하다.
- Snapshot은 선택적으로 `marketViews.overall/us/kr`를 포함한다. 화면은 스냅샷에 시장별 view가 있으면 `종합 / 미국장 / 한국장` 세그먼트로 같은 `시장 해석`과 `판단 및 투자 행동` 구조를 전환한다.
- 상단은 요인 나열이 아니라 `시장 해석`과 `판단 및 투자 행동` 두 개의 큰 본문으로 구성한다. `시장 해석`에는 기존 source-grounded 요약을 보존하고, `판단 및 투자 행동`에는 결론, 행동 가이드, 다음 확인 항목을 묶어 보여준다.
- 드라이버 카드는 `도움/부담/변동성/중립` 같은 방향 칩과 짧은 판단 요약을 먼저 보여준다. 세부 근거는 카드 안 `근거 보기` 접기에 `근거 요약`, `시장 영향`, `다음 확인`만 간결하게 표시한다.
- Agent-authored 스냅샷에서는 반대 근거(`counterEvidence`), 불확실성(`uncertainties`), 사용 출처(`sourceRefs`)를 기본 화면 하단에 노출한다.
- `render_market_memory_context()`는 기존 context block을 유지한다. Agent Dock/Home 채팅, 브리핑 생성, 기업분석 생성은 이 block을 중기 시장 배경으로 읽으며, 화면 표시용 `beginnerSummary/actionGuide`와 혼동하지 않는다.
- 기업분석에서는 이 block을 회사 고유 사실의 evidence로 쓰지 않고, 시장 프레이밍/context로만 사용한다.
- 보고서 Reader의 Folio Note `AI 정리`는 `/api/agent/chat`을 통해 동작하므로 같은 Market Memory context block을 읽는다. Agent가 만든 초안은 바로 저장하지 않고 노트 본문에만 반영되며, 사용자가 확인 후 저장한다.
- taxonomy, story map, 패밀리 제안, audit, 내러티브 리포트, 개별 메모리 기록 목록은 기본 UI에서 제거되었고 API로만 접근한다(아래 API 목록 유지). 데이터 파이프라인과 유지보수 로직은 그대로 백엔드에서 동작한다.
- `시장 메모리 업데이트` 버튼은 기존 중기 내러티브 row 누적(`/api/memory/llm`)을 먼저 실행한 뒤 MarketStateSnapshot 생성(`/api/memory/state-snapshot`)을 이어서 실행한다. 생성 방식은 설정 탭의 AI Agent 정책을 따르며, 실행은 계속 사용자 트리거만 사용한다.
- CLI 기반 시장 메모리 업데이트는 브라우저 화면이 열려 있는 동안 고정 타임아웃 없이 같은 서버 작업을 완료 상태까지 자동 추적한다. 화면을 떠나거나 다시 연 경우에는 저장된 job id로 동일 작업에 재연결한다.

## FinancialTransactionAssistantAgent 월드 메모리와의 관계

이 기능은 FinancialTransactionAssistantAgent의 `world_memory_cli.py`에서 쓰는 철학을 참고·확장한 기능입니다.
원본 프로젝트의 전체 CLI를 복제하지는 않았지만, 현재 웹앱에는 다음 계층을 반영했습니다.

1. append-only 성격의 내러티브 메모리 로그
2. 현재 유효한 상태를 별도로 읽는 state 테이블
3. 기본 온톨로지와 dedupe key
4. taxonomy 사용량 추적
5. story link graph
6. family review suggestion
7. audit harness
8. narrative report view

## API

```text
GET /api/memory?limit=50
GET /api/memory/states?status=current&limit=20
GET /api/memory/taxonomy?type=story_family&limit=20
GET /api/memory/story-links?story=ai_semiconductor_supply_chain&limit=20
GET /api/memory/story-map?limit=80
GET /api/memory/suggestions?status=suggested&limit=20
GET /api/memory/audit?days=30
GET /api/memory/report?limit=8
GET /api/memory/state-dashboard?limit=5
GET /api/memory/state-snapshot
GET /api/memory/verification
POST /api/memory
POST /api/memory/llm
POST /api/memory/state-snapshot
POST /api/memory/states/{state_id}
POST /api/memory/regime/refresh
GET /api/memory/states/{state_id}/evidence
GET /api/memory/states/{state_id}/changes
GET /api/memory/states/{state_id}/thesis-links
POST /api/memory/states/{state_id}/thesis-links
POST /api/memory/suggestions/{suggestion_id}
```

## 화면에 나가는 문장

- 스냅샷 본문에는 `rss:item:13` 같은 내부 참조 id가 남으면 안 됩니다. 이 id는 코드가 context 항목에 붙인 것이고 프롬프트는 `sourceRefs` 배열에 담으라고 하지만, 모델은 문장 안에도 인용처럼 써넣습니다. `scrub_inline_refs()`가 아는 id는 매체명으로 바꾸고 모르는 id는 지웁니다. 저장 시점과 화면 조립 시점 양쪽에서 돌기 때문에 이미 저장된 스냅샷도 재생성 없이 정리됩니다. `sourceRefs`·`id` 키는 id가 값이므로 건드리지 않습니다.
- `marketInterpretation`은 화면 상단의 큰 본문입니다. 상한은 폭주 방지용이고 문장 경계에서 자릅니다(`_body_text`). 짧은 라벨과 같은 하드컷을 쓰면 근거를 덧붙이는 모델일수록 문장 중간에서 끊깁니다.
- **뷰의 `headline`에도 계약이 있습니다.** 예전에는 최상위 `headline`만 "short Korean title"이라고 적혀 있고 `marketViews[].headline`은 필드 이름만 나열돼 계약이 없었습니다. 그래서 분류 라벨이 나왔습니다 — `기후발 공급 충격이 지역 비용·성장 위험을 높임`, `에너지 경로의 지정학 위험을 점검하는 유럽`처럼 사건도 판단도 없는 명사구입니다. 지금은 (1) 판단을 말할 것, (2) 시장 이름으로 끝내지 말 것(화면이 이미 어느 시장인지 말합니다), (3) 그 뷰의 `marketInterpretation`이 지배적이라고 본 원인을 빠뜨리지 말 것, (4) 다른 시장과의 비교만으로 제목을 쓰지 말고 전달 경로를 지목할 것을 겁니다. 20~40자 한 줄입니다.
- **헤드라인이 비면 `EUROPE`가 아니라 `유럽`이 나옵니다**(`_view_label`). 나머지가 전부 한국어인 자리에 영문 코드가 앉으면 값이 빠진 티가 아니라 고장으로 읽힙니다.
- **이 필드에는 길이 계약이 있습니다 — 3~4문장, 300자 안팎(최대 400자).** 다른 필드는 전부 프롬프트가 크기를 지정하거나 상한이 낮아 어느 엔진이 써도 비슷하게 나오는데, 예전에는 여기만 크기 지시가 없어 엔진의 기본 장황함이 그대로 화면에 나왔습니다(실측 저장본 11건: 다른 필드 편차 2배 안쪽, 이 필드만 79~823자로 10배).
- **문장 수만으로는 계약이 되지 않습니다.** 3~5문장으로 먼저 제한했더니 정확히 5문장을 지키면서 526자가 나왔습니다 — 한 문장이 쉼표로 네 항목을 이어 붙이면 문단입니다(실측 문장당 155·116·125·102자). 그래서 계약은 문장 수와 총 글자 수를 함께 걸고, 문장당 한 가지 생각(60~80자)을 명시합니다.
- **확인은 해석이 아닙니다.** 지수가 얼마 내렸는지 적는 문장은 옆의 드라이버와 차트가 이미 보여주는 것을 되풀이합니다. 모든 문장이 주장을 하나씩 지고, 등락은 그것이 뒷받침하는 주장 안에 숫자 하나로 들어갑니다. 첫 문장은 그 시장이 **어떤 상태이고 왜 그런지**이며(화면이 이 문장을 강조합니다) 장 마감 요약에 쓰지 않습니다.
- **규칙 15와 17이 서로 반대를 말하고 있었습니다.** 15는 "판단으로 시작하라", 17은 "무슨 일이 있었는지에서 시작하라"였고 모델은 뒤엣것을 따랐습니다 — 같은 프롬프트에 `퍼센트 나열로 열지 말 것`이 있는 채로 `파리가 1.6%, 밀라노가 1.17%, 마드리드가 0.9%, 런던이 0.7% 내렸습니다`가 나왔습니다. 17은 이제 첫 문장이 아니라 **근거의 출처**를 말합니다(뉴스 흐름이 1차, marketTape·macroSnapshot은 확인·반박).
- **계약을 지켰는지 재서 남깁니다**(`interpretationAudit`: `chars`/`sentences`/`numbers`/`leadNumbers`). 같은 금지 규칙이 프롬프트에 있는 채로 두 번 깨졌고, 프롬프트는 부탁이라 지켜졌는지 아무도 모르면 다음 판단이 눈대중이 됩니다. **재는 것과 되돌리는 것은 다른 결정입니다** — 자르면 결론이 사라지고 재생성은 수십 초짜리 CLI 호출이라, 감사는 기록만 하고 산출물을 막지 않습니다. `leadNumbers`가 크면 첫 문장이 등락 나열입니다.
- **나열을 금지합니다.** 그 526자에서 가장 긴 문장은 4개 종목의 등락과 근거를 각각 적은 것이었는데, 그것은 옆의 `keyDrivers`가 이미 보여주는 목록입니다. 예시는 한둘까지고 수치는 그것이 없으면 판단이 달라질 때만 답니다.
- 계약은 프롬프트가 지고 코드는 폭주 방지 상한(800자)만 유지합니다. 상한을 계약 값까지 낮춰 자르는 방식은 쓰지 않습니다 — 마지막 문장이 결론(`따라서 지금의 중기 상태는 …`)이라 뒤를 자르면 판단이 사라집니다.
- **이 필드의 인용은 매체명으로 살리지 않고 지웁니다**(`_REF_DROP_KEYS`). 다른 필드에서는 `rss:item:13`을 매체명으로 바꾸는 것이 읽는 사람에게 도움이 되지만, 화면의 큰 본문에서는 문장마다 `(Bloomberg, 연합뉴스)`가 붙어 오히려 읽히지 않습니다(실측 한 해석에 9곳). 프롬프트로도 금지하되, 프롬프트는 부탁이라 코드가 함께 지웁니다. 그 뷰의 `sourceRefs`가 출처를 이미 갖고 있어 잃는 것이 없고, 저장 시점과 화면 조립 시점 양쪽에서 돌기 때문에 이미 저장된 스냅샷도 재생성 없이 정리됩니다.
- 화면은 첫 문장만 강조하고 나머지를 본문으로 두되 **버리지 않습니다**. 문장 분리는 소수점을 문장 끝으로 읽지 않아야 합니다 — `7736.52`, `+1.79%`가 세 문장으로 쪼개진 적이 있습니다.
