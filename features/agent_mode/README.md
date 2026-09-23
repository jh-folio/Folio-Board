# AI Agent Mode

## 공통 CLI 결과 관측 (E0)

기업분석의 기존 종료 관측은 공통 `ExecutionResult` parser를 사용한다. 내부 호출자는
`run_agent_prompt(..., result_sink={})` 또는 `request_cli_text(..., result_sink={})`로
본문·관측 usage·비공개 provider 자료를 메모리에서 받을 수 있다. 기본 반환 문자열/tuple과
공개 응답 dict는 유지한다. `facts_sink`의 종료 상태와 `WebSearchFacts`도 호환된다.

- `ProviderPayload`에는 실제 출력에서 읽은 adapter/model·종료 원인·텍스트/도구 블록·인용·session ID만 둔다. 요청 모델로 실제 모델을 추정하지 않고, reasoning 원문·도구 입력·원시 이벤트는 보관하지 않는다. adapter ID는 선택된 실행 어댑터이며 실제 upstream 제공자를 증명하지 않는다.
- Claude 텍스트 블록의 native citation이 실제로 존재하면 본문 블록 위치와 원문 문서 위치를 구별해 보존한다. 같은 메시지 ID의 블록은 누적하고 하위 에이전트 메시지는 섞지 않는다. Codex Markdown 링크를 native citation으로 바꾸지 않는다. 없는 정보와 미확인 capability는 unknown이다.
- 본문을 편집하는 소비자는 `ExecutionResult.with_text()`를 사용한다. 그대로 남은 유일한 인용 대상 문자열만 재매핑하고, 수정·삭제·중복된 대상은 위치를 미확인으로 바꾼다. 출처가 남았다고 새 문장을 뒷받침한다고 간주하지 않는다.
- `safe_projection()`은 기존 진단 v1 필드 그대로다. private 객체·인용 URL/원문·모델 원문·response/session ID는 진단, Work Log, 공개 응답, 보고서 JSON에 자동 저장하지 않는다. 작업 종료 시 호출자 참조와 함께 해제하며 Folio의 별도 재개 파일은 만들지 않는다. 외부 CLI 자체 기록 정책을 바꾸지는 않는다.
- `ContinuationLease`는 지원 adapter가 명시적으로 발급할 때 쓰는 owner-bound/단일 소비/최대 1시간 TTL 메모리 계약이다. 만료·취소·사용 뒤 토큰을 제거한다. 현재 Folio CLI bridge는 자동 provider 재개를 구현하지 않았으므로 `continuation_capability=unsupported`이고 lease를 발급하지 않는다. pause/tool_pending 관측과 재개 가능 여부는 별개다.
- 실제 CLI 생성, native citation 영속화·reader/export 연결, Deep Research 재개 실행은 이 공통 계약의 로컬 fixture 검증과 구별한다.

이벤트 형식 참고: [Codex JSONL](https://learn.chatgpt.com/docs/non-interactive-mode),
[Claude complete-message stream](https://code.claude.com/docs/en/agent-sdk/streaming-output).

기업분석의 선택적 구조 보완 재시도는 실패하거나 개선되지 않아도 먼저 받은 본문을 유지합니다.
구조 검증을 수행하지 못한 결과는 검수 미완료 경고와 함께 저장 경로에 전달하며 통과로 표시하지 않습니다.
취소된 기업분석 작업은 이 복구 경로를 통해 성공 저장으로 바꾸지 않습니다. 브리핑의 별도 생성·저장 계약은 변경하지 않습니다.

Claude 작성은 `plan`이 아닌 `dontAsk`로 실행한다. 도구는 Read/Glob/Grep만 허용하며, 명시적 웹 조회 호출에만 WebSearch를 더한다. 셸·편집·쓰기·상속 MCP 도구를 열지 않고 전역 설정도 수정하지 않는다. 브리핑은 공유 조립기가 만든 agentInstructions/prompt/context와 출력·저장 계약을 stdin으로 그대로 전달해, 큰 내부 차트 pack을 셸로 해체할 필요가 없게 한다. Codex는 기존 read-only 실행과 파일 pack 전달을 유지한다.

형식 거절은 `BriefingOutputContractError`로 구분하며 `contract_*` 코드만 대체 보고서의 `generation.rejectedReasonCodes`에 남긴다. 다른 `ValueError`를 형식 실패로 분류하거나 규칙 대체로 숨기지 않는다.

브리핑 규칙 대체 저장은 작업의 `finalEngine=rules`, `generationMode=rules`, `fallbackReason=engine_failed`로 기록한다. 보고서에는 상세 대체 사유와 허용된 최초 검증 거절 코드가 남으며, 취소·기한 초과는 대체 생성으로 숨기지 않는다.

규칙 기반 브리핑 대체 조립은 자료 그룹이 없거나 요청 시장에 해당하는 그룹이 없어도 처리합니다. 실행 중인 서버에는 Python 변경이 자동 반영되지 않으므로, 수정 적용 시 활성 작업이 없는지 확인하고 정상 재시작한 뒤 응답을 확인합니다.

브리핑 저장은 authored Markdown을 보존하면서 최종 형식·출처 URL·source ID·section whitelist를 확인합니다. 의미 기반 수치·단위·방향·날짜·상대강도 판정은 명시적 offline 평가에만 남고, 일반 CLI 저장 경로는 semantic/style/fact-repair/model 호출을 하지 않습니다. 취소·기한 초과·안전하지 않은 참조는 계속 저장을 막으며, 명시적 품질 보완은 별도 `quality_repair` 작업입니다. CLI 응답 형식이나 사용자가 선택한 모델 설정은 이 검사로 변경하지 않습니다.

작성용 한국장 자료에는 내부 provider 경고를 넣지 않으며, 최종 저장에서도 연결 설정·provider 경고 문구만 제거합니다. 수치의 실제 출처·기준일과 원래 진단 메타데이터는 유지합니다. 저장 브리핑 차트는 공통 정규장 가격 계열을 사용하며 Toss 실시간 화면 설정을 바꾸지 않습니다.

선택적으로 켠 일간 뉴스 의미 평가는 실행 중인 bridge의 실제 adapter/model/job과 남은 시간을 전달받습니다. 단독 context pack 준비는 CLI를 호출하지 않습니다. 시장당 한 번의 별도 평가이며 본문 보수 횟수를 늘리지 않고, 중첩 호출은 기존 세마포어를 다시 잡지 않습니다. 평가를 못 하면 기존 작성 입력을 유지합니다. 상한과 입력·출처 계약은 일일 브리핑 README를 따릅니다.

브리핑은 자료 보완 검색과 본문 작성을 분리합니다. Codex 작성 명령은 `web_search="disabled"`, 보완 조회는 `web_search="live"`를 명시하고 Claude 작성에서는 WebSearch/WebFetch를 제한합니다. 다른 작업의 검색 정책은 그대로입니다. 실행 도구 사용이 관측되지 않으면 미확인으로 기록하며, 명령에 설정했다고 실제 검색 증거로 계산하지 않습니다. CLI와 규칙 경로는 같은 시장별 이전 확인 사항 및 제한 뉴스 선별 컨텍스트를 사용합니다.

AI Agent Mode는 Codex, Claude Code 같은 로컬 CLI를 Folio Board의 AI 작성자로 사용하는 실행 기능입니다.

0.2에서는 Home과 Deep Research에서 Agent를 사용하고, 두 화면이 같은 metadata-only Work Log를 공유합니다. Work Log에는 prompt, reply transcript, Markdown, diff, attachment, 로컬 path, credential, raw stdout/stderr가 저장되지 않습니다. Canonical 보고서는 generate/regenerate 또는 명시적으로 승인된 proposal만 수정할 수 있습니다.

Folio Board는 자료 선별, context pack 생성, 저장 포맷, 품질 metadata를 맡고, 현재 채팅 중인 AI 에이전트가 context pack을 읽어 보고서/overlay/delta를 작성합니다. AI 작성은 CLI 브리지를 통해 실행합니다.

## Phase 1 흐름

```text
CLI로 context pack 생성
  -> 에이전트가 pack의 prompt/context를 읽고 Markdown 또는 JSON 작성
  -> CLI writeback으로 기존 data/* 저장소에 저장
  -> 웹앱은 기존 저장 보고서처럼 읽음
```

Context pack 저장 위치:

```text
data/agent-context/
```

최종 산출물은 기존 저장 위치를 그대로 씁니다.

```text
data/briefings/{date}.json
data/company-analysis/{id}.json
data/topic-reports/{file}.json
market-memory.sqlite3
```

## 지원 작업

| taskType | Prepare | Writeback | 산출물 |
| --- | --- | --- | --- |
| `briefing` | 지원 | Markdown | 일일 브리핑 JSON |
| `company_analysis` | 지원 | Markdown | 기업분석 JSON |
| `topic_report` | 지원 | Markdown | 테마분석 JSON |
| `personal_overlay` | 지원 | JSON | 기존 보고서의 `personalOverlay` |
| `thesis_delta` | 지원 | JSON | thesis delta SQLite row |
| `market_memory_llm` | 지원 | JSON | market memory SQLite row |
| `quality_repair` | 지원 | Markdown | 기존 보고서 markdown/quality metadata |
| `investment_review` | 지원 | Markdown | 투자 리뷰 JSON |

## Phase 2 Direct Agent Bridge

웹앱의 생성 화면은 더 이상 생성 방식 enum을 직접 노출하지 않습니다. 설정 탭의 `AI Agent 설정`이 전역 정책을 결정합니다.

```text
AI_AGENT_ENABLED=0      -> 규칙 기반
AI_AGENT_ENABLED=1
AI_AGENT_MODE=cli       -> 로컬 Codex/Claude Code/Antigravity CLI
```

CLI 모드가 활성화되어 있으면 기존 생성 API가 background job을 만들고 다음 순서로 실행합니다.

```text
context pack 생성
  -> 허용된 CLI adapter를 read-only/non-interactive로 실행
  -> stdout의 최종 Markdown/JSON 수집
  -> 코드에서 normalize/enum/quality 검증
  -> 기존 JSON/SQLite 저장소에 writeback
```

CLI 선택은 **범위가 둘**이다. 자리도 둘이고, 화면이 어느 쪽인지 말한다.

| 범위 | 어디서 | 무엇이 쓰나 |
| --- | --- | --- |
| 전역 기본 | 상단바 `Agent CLI` 메뉴, 설정 탭 | 예약 브리핑, 기업분석, 오버레이 등 도크 밖에서 도는 모든 작업 |
| 이 대화만 | Agent 도크의 `이 대화의 CLI` | 그 대화의 질문 하나뿐 |

- **설치·로그인은 화면에서 한다**(`web/src/app/AgentCliSetup.tsx`, 0.5.3). `POST /api/agent-bridge/install|login`은 오래전부터 있었지만 **부르는 화면이 저장소에 하나도 없었다** — 첫 실행 안내는 "설정 탭의 AI Agent에서 설치와 로그인을 마칠 수 있습니다"라고 적어 뒀고 설정 탭에도 그 버튼이 없어, 처음 쓰는 사람이 CLI를 고르면 갈 곳이 없었다. 지금은 안내와 설정 탭이 같은 컴포넌트를 쓴다.
- 어떤 버튼이 보일지는 `web/src/app/agentCliStatus.ts::adapterActions()`가 정한다. 순수 함수로 떼어 둔 이유는 **개발 기계에서 확인할 수 없기 때문**이다 — CLI가 이미 설치·로그인돼 있으면 설치·로그인 버튼이 아예 렌더되지 않는다. 정작 처음 쓰는 사람만 보는 경로라 테스트가 대신 본다.
- 설치는 job이라 `/api/jobs/{id}`를 폴링하며 진행 문구를 그대로 보여준다. 서버가 설치 스크립트에 최대 600초를 주므로 폴링 마감도 그보다 길다(620초) — 폴링이 먼저 포기하면 실제로는 도는 설치가 화면에서만 실패로 보인다.
- 상단바와 설정 탭은 **같은 값**을 본다. 한쪽에서 바꾸면 `folio:agent-settings-updated`로 다른 쪽도 즉시 따라온다.
- 도크 선택은 요청의 `options.adapter`로만 전달되며 전역 설정을 저장하지 않는다. 전역과 다를 때 도크가 `이 대화만 ...로 돕니다`라고 밝힌다. 새 대화는 다시 전역 기본에서 시작한다.
- 모델 ID는 CLI 명령의 인자 하나가 되므로 `_adapter_command()`가 실행 전에 `영문·숫자로 시작하는 [A-Za-z0-9._:-] 128자 이하`만 통과시키고 나머지는 `ValueError`로 거부한다(`model_catalog.is_safe_cli_model_id`). Windows npm 설치본(`codex.cmd`)은 cmd.exe를 거쳐 `&`·`|`·따옴표를 다시 해석하고, `-`로 시작하는 값은 다른 옵션으로 읽히기 때문이다. 도크 요청의 `options.model`도 여기서 걸러진다.
- 도크의 CLI·모델·노력은 **버튼 하나로 접어** 둔다. 도크는 384px이라 셋을 나란히 두면 폼이 461px로 벌어져 77px이 잘렸고, 줄바꿈을 허용해도 늘 두 줄이었다. 버튼에는 `Claude · Claude Opus 5.5 · 중간`처럼 요약을 그대로 적어 열지 않고도 무엇으로 도는지 읽힌다. 팝오버는 위로 열린다 — 도크 맨 아래라 아래로 열면 화면 밖이다.
- 도크 헤더의 `대화 목록`·`새 대화`·`닫기`는 **아이콘 셋**이다. 글자 버튼으로 두면 385px 헤더에서 액션이 175px을 가져가 제목이 두 줄로 접히고 헤더가 107px까지 자란다 — 그만큼 대화가 아래로 밀린다. 아이콘으로 줄여 116px이 되고 제목은 한 줄로 선다(넘치면 말줄임). 이름은 툴팁과 `aria-label`이 진다.
- 도크에서 CLI를 바꾸면 모델 목록이 통째로 달라지므로 모델도 그 CLI의 것으로 옮긴다. 이때도 전역 모델은 저장하지 않는다 — 저장하면 `이 대화에만`이 거짓이 되고 예약 브리핑의 모델까지 조용히 바뀐다.

설정 탭의 `AI Agent 설정`에서는 Agent 생성 ON/OFF를 설정하고, Codex CLI, Claude Code CLI, Antigravity CLI 중 하나를 선택해 모델을 지정합니다. 모델 목록은 마지막으로 갱신한 캐시를 기본으로 사용하고, 사용자가 새로고침을 누를 때만 CLI 모델 조회 명령을 실행합니다. 설치 명령은 실행 전에 사용자 확인을 받습니다.

### 예약이 고른 시장만 만든다

**범위 이름으로는 임의 조합을 담지 못한다.** 이름은 `us`/`kr`/`europe`/`jp`/`both`/`all` 뿐이라, 한국+일본은 `market_selection_scope(["kr","jp"]) == "multi"`가 되고 `multi`는 `normalize_market_selection()`에서 **네 시장 전부**로 풀린다.

`_run_briefing()`은 `markets` 목록을 함께 넘기는데 **`prepare_pack()` 디스패처가 그것을 버렸다.** 그래서 `prepare_briefing_pack()`이 `market_scope="multi"`로 되짚어 네 시장을 만들었다 — 실측 2026-08-13 18:18에 한국·일본 예약 하나가 파일 넷(`us`/`kr`/`jp`/`europe`)을 한꺼번에 썼고, 저장된 `generationMarkets`가 전부 `['us','kr','europe','jp']`였다.

- 디스패처가 `markets=kwargs.get("markets")`를 그대로 넘긴다. `prepare_briefing_pack()`은 원래 이 인자를 받고 있었고 목록이 있으면 범위 이름보다 우선한다.
- **`expectedTitles`도 계약이 자기 시장으로 좁힌다.** `_agent_prompt()`와 `_briefing_correction_prompt()`가 이 표를 **전부 펼쳐** "H1은 정확히 이것들이어야 한다"고 지시하므로, 넓은 표가 들어오면 모델에게 네 시장을 쓰라고 시키는 셈이다. 호출자가 범위 이름으로 만든 표를 넘겨도 `briefing_output_contract()`가 걸러 낸다.
- 규칙 기반 경로(`build_briefing(markets=...)`)는 목록을 직접 받으므로 영향이 없었다. 어긋난 것은 Agent 경로뿐이다.

### `_agent_prompt()`의 requiredSections 지시는 브리핑 전용이었다 (0.6, 2026-09-11)

**`requiredSections`를 채우는 taskType이 브리핑 하나가 아니다.** 기업분석도 누락 섹션을 잡으려고 `outputContract.requiredSections`를 쓴다(§company_analysis README "팩의 `requiredSections`가 손으로 적은 6개라..."). 그런데 `_agent_prompt()`의 `if required:` 블록은 `taskType` 게이트 없이 `requiredSections`가 있기만 하면 분량 하한·마켓 타이틀 서식·주도 기업 em dash 서식까지 통째로 붙였다 — 전부 `briefing_contract.py`만 채우는 필드라 다른 태스크에서는 값이 비어 있는데도 그렇다.

실측(P3, Claude Code CLI, SK하이닉스·RIVN): 기업분석 실행이 다음을 그대로 받았다.

- `"Minimum report length: 0 characters."` — 기업분석은 이 필드를 안 채우니 "최소 분량 0자"가 된다.
- `"Each market title must be an H1 with a session date and status, like '# US Market Briefing — YYYY.MM.DD 마감'..."` — 브리핑 제목 형식.
- `"...Do not add market-scope notes, source-date explanations, **blockquotes**, or any preamble."` — §company_analysis "글쓰기 방식"의 섹션 요약 blockquote 규칙과 **정면으로 충돌**한다. 실측 blockquote 준수율이 13/16(81%)에 그친 것과 맞아떨어진다.
- `"Leading company headings must include... '## 3. 미국장을 주도한 기업 ① — NVIDIA'"` — 역시 브리핑 전용.

모델이 결국 `beginner.md`의 올바른 지시(pack 파일 안, 나중에 읽음)를 따라가 제목 형식 자체는 맞게 나왔지만, 시작부터 모순되고 무관한 영어 지시문을 먼저 읽는 구조였다 — P1(동결 컨텍스트 + `beginner.md`만 이어붙인 단순 하네스)과 실제 파이프라인의 문체·형식 차이가 이 지시문 오염과 무관하지 않을 것으로 본다.

`if required:` 블록을 둘로 쪼갰다 — 태스크 공통(섹션 누락 금지 + 필수 제목 목록)은 그대로, 브리핑 전용(분량 하한·타이틀 서식·주도 기업 서식)은 `pack.get("taskType") == "briefing"`으로 게이트. `test_company_analysis_agent_prompt_does_not_leak_briefing_instructions`가 회귀를 잡는다.

### `prepare_topic_report_pack()`이 딥 리서치 planner를 강제로 껐다 (0.6, 2026-09-13)

**`llm_override=False`를 고정으로 넘겨, Agent CLI로 생성하는 custom 주제 딥 리서치는 항상 규칙 기반 planner로 떨어졌다.** 승인 플로우(`topic_report/approved_request.py`)는 `use_llm = request.plannerEngine != "rules"`(기본 True, 설정된 엔진을 그대로 씀)인데 이 함수만 별도로 `False`를 박아 뒀다 — 같은 `build_topic_plan()`을 두 경로가 공유해도 넘기는 값이 갈리면 같은 일이 난다(§6 규칙 14, 이번에도 같은 유형).

실측(2026-09-13, "AI 에이전트 웹 전환" 주제로 `run_agent_task("topic_report", ...)` 직접 실행, Claude Code CLI, `deep_research=True`): 하위질문 10개 전부 `custom_label` 원문을 기계적으로 잘라 붙인 문장(`"AI 에이전트 사람 대신해의 현재 상황과 핵심 동인은 무엇인가?"`)이 됐고 `candidateTickers`가 항상 빈 `{}`였다. 그 결과 마이크로소프트·아마존 같은 개별 기업 시세를 아예 못 가져왔고, 저장된 보고서는 사용자가 물은 "미국 기업별 영향"을 전부 "데이터 갭"으로 남겼다 — 계획을 세운 함수 하나가 조용히 규칙으로 떨어진 결과가 본문까지 그대로 이어졌다.

수정: `llm_override=False` 인자를 제거해 `build_topic_plan()` 자신의 기본값(`None`→`use_llm_analysis()`로 판단)을 쓰게 했다. 부수적으로 두 곳의 미가드 예외도 같이 잡았다(`planner.py::refine_plan_with_llm()`·`topic_report/service.py::generate_topic_report()`의 `selected_cli_config()` 호출이 잘못된 설정값에서 예외를 그대로 흘려보내 "실패하면 규칙으로" 계약을 못 지키고 있었다) — 상세는 [topic-report 가이드](../../docs/agent-guides/topic-report.md)를 본다. `features/agent_mode/`+`features/topic_report/` 763 passed(이 예외 미가드 하나가 이전에 "환경설정 문제"로 기록해 둔 무관 실패 36건 중 34건도 함께 해소했다).

### 브리핑 출력 계약은 시장마다 라벨이 다르다

`briefing_contract_violations()`의 검사 둘이 `us`가 아니면 전부 `한국장`으로 취급했다.

```python
expected = "## 0. 오늘의 미국장 성격" if key == "us" else "## 0. 오늘의 한국장 성격"
prefix = "미국장" if key == "us" else "한국장"
```

시장이 넷으로 늘면서 이것이 **계약을 자기 자신과 모순되게** 만들었다. 같은 계약의 필수 섹션 목록은 `0. 오늘의 일본장 성격`을 요구하는데, 제목 다음 줄 검사는 `0. 오늘의 한국장 성격`을 요구했다. 일본장·유럽장이 낀 조합은 **무엇을 써도 통과할 수 없었다.**

결과는 위반 → 재작성 1회 → 또 위반 → `internal_error`다. CLI를 두 번 돌리므로 한 번에 45분을 쓰고 아무것도 남기지 않는다(2026-08-12 18:00 한국·일본 예약 실측: 2,741초). 사용자에게는 `오류`만 보이고 무엇이 어긋났는지는 어디에도 남지 않는다.

- 라벨은 `MARKET_LABELS[key]`에서 가져온다. 같은 표를 필수 섹션 목록이 이미 쓰고 있었다.
- 주도 기업명 검사도 같은 하드코딩이 있었다. 이쪽은 문서 전체를 훑어서 **다른 시장의 헤딩이 대신 걸리면 통과**했다 — 조용히 검사를 건너뛴 셈이라 증상이 안 보였다.
- `features/agent_mode/tests/test_briefing_contract_all_markets.py`가 네 시장의 단일·2조합·전체를 모두 검사한다. **계약이 요구하는 그대로 쓴 보고서는 통과해야 한다**가 계약의 최소 조건이다.

실측으로 한국장 단독 생성은 codex에서 223초에 위반 0건으로 통과한다 — 실패한 것은 조합이지 CLI가 아니었다.

### agy headless는 파일을 읽지 못한다 (0.5.3 확인)

agy 1.1.12의 headless(`--print`)는 **파일 읽기 권한을 자동 거부한다.** 대화형이 아니라 물어볼 수 없으니 거부하는 것이고, exit 0에 stdout이 비어 끝난다:

```
jetski: no output produced — a tool required the "read_file" permission that headless
mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.allow
in settings.json (e.g. read_file(<target>)).
```

**Folio Board의 Agent task는 전부 컨텍스트 팩 파일을 읽는 것으로 시작한다.** 팩이 5.2MB라 프롬프트에 넣을 수 없고(게다가 agy는 프롬프트를 명령 인자로 받아 Windows 32,767자 한계가 걸린다), `--add-dir`로도 열리지 않는다(실측). 그래서 antigravity로는 브리핑·기업분석을 만들 수 없다. 파일을 읽지 않는 호출(도크 대화, 테마 계획)은 정상 동작한다 — 실측으로 짧은 프롬프트는 20초에 응답했다.

브리핑 Agent pack의 출처 카탈로그는 컨텍스트에 실제로 렌더링된 writer 자료 집합에서 만들어집니다. CLI 생성에서 같은 `sourceId` 집합을 사용하고, 시장별 ledger도 해당 시장 writer 자료만 보존합니다. Summary와 Full Text는 분리된 제한 발췌로 전달되며 페이지 메뉴·추천·자동 요약 문구는 제외됩니다.

- 실패는 `AGY_PERMISSION_DENIED_MARK`로 알아보고 `AGY_PERMISSION_HELP`를 올린다. 예전에는 일반 "빈 결과"와 구분되지 않아 예약 브리핑이 `internal_error`로만 남았고, 한 번에 **8분 30초**를 버린 뒤 실패했다(실측 2026-08-11 18:00 KR/JP 예약).
- 한 번 거부당하면 `_AGY_FILE_READS_BLOCKED`가 서고, 다음 팩 task는 팩을 만들기 전에 즉시 막는다. 상태 행도 `bridgeSupported: false`로 사유를 함께 낸다.
- `상태 새로고침`(`bridge_status(refresh=True)`)이 이 표시를 지운다. 설정을 고치고도 되돌릴 방법이 화면에 없으면 안 된다.
- **`--dangerously-skip-permissions`를 자동으로 붙이지 않는다.** 이름 그대로 파일 쓰기와 셸 실행까지 전부 자동 승인한다. 사용자의 자료가 든 폴더에서 도는 일이라 우리가 대신 정할 문제가 아니다. 설정 파일은 `~/.gemini/antigravity-cli/settings.json`이며, 여기에 규칙을 넣는 것도 사용자의 전역 CLI 설정을 바꾸는 일이라 앱이 손대지 않는다.

Antigravity CLI는 [공식 페이지](https://antigravity.google/product/antigravity-cli)의 `agy` 바이너리를 사용한다. 설치는 Windows `irm https://antigravity.google/cli/install.ps1 | iex`, 로그인은 인자 없이 `agy`(브라우저 OAuth)다. 실행은 `agy --model <model> --print <prompt>`로 단일 프롬프트를 비대화형 실행한다. 모델 이름에는 노력 단계가 함께 들어간다(`gemini-3.1-pro-high`, `gemini-3.6-flash-medium`, `claude-sonnet-4-6` 등). 단계 없는 예전 이름(`gemini-3.5-pro`)은 1.1.7이 `not recognized`로 거부하므로 기본 목록에서 뺐다 — 실시간 목록에 기본값이 덧붙는 구조라 선택지에 남아 있으면 고르는 순간 실행이 실패한다. 이 모델들로 브리핑·기업분석·테마분석 등 모든 Agent task를 작성할 수 있다.

**버전 게이트는 지웠다(0.5.3).** 예전에는 `AGY_HEADLESS_FIXED = (1, 1, 7)` 이상이면 브리지를 열었다. 1.0.10의 Windows `--print`가 모델 응답을 stdout으로 반환하지 못하던 업스트림 버그(`transcript.jsonl`을 POSIX 경로로 열려다 실패)가 1.1.7에서 고쳐진 것을 확인하고 연 것이다.

**그 확인이 틀린 것은 아니지만 충분하지 않았다.** 짧은 프롬프트 하나로 "출력이 돌아오는가"만 재고 열었는데, Folio Board의 Agent task는 예외 없이 컨텍스트 팩 **파일을 읽는 것으로 시작**한다. 그 경로는 한 번도 돌려보지 않았고, 1.1.12는 그 읽기를 거부한다. 결과는 기록에 그대로 남아 있다 — 게이트를 연 뒤 실행된 Agent 잡 두 건이 모두 실패했고, 그전까지 antigravity로 성공한 잡은 한 건도 없다.

**버전 비교는 권한 문제를 구조적으로 볼 수 없다.** 그래서 게이트를 `features/agent_mode/agy_capability.py`의 **실측**으로 바꿨다.

- 실제 팩과 같은 폴더(`data/agent-context/`)에 한 줄짜리 파일을 만들고 **읽어 오라고 시켜 본다.** 통과해야 연다.
- **재본 적이 없으면(`None`) 막는다.** 모르는 것을 된다고 가정한 것이 지난 실수다. 화면은 `상태 새로고침`을 누르면 확인한다고 안내한다(약 20초, 버전별 1회 캐시).
- 결과는 `data/agent-cli-capability.json`에 버전과 함께 남는다. 판올림하면 다시 잰다 — 고쳐졌을 수도, 새로 깨졌을 수도 있다.
- **플랫폼으로 가르지 않는다.** 거부를 실측한 것은 Windows지만 macOS/Linux를 재본 것도 아니다. 조회는 어느 플랫폼에서든 같은 방식으로 사실을 확인한다.
- 게이트를 둘 두지 않는다. 버전 게이트를 남겨 두면 "재봤더니 되는데 버전 때문에 막는" 모순이 생긴다.

**조회 파일의 위치가 판정을 가른다.** 처음에는 `%TEMP%`에 만들었는데 그건 통과하고 진짜 팩은 거부당했다. 실측으로 갈린 것은 크기가 아니다.

| 조건 | 결과 |
| --- | --- |
| 프로젝트 안 12바이트 파일 | 권한 거부 |
| `%TEMP%`의 5.2MB 파일 | 성공 |

agy headless는 프로젝트 안의 읽기를 거부한다. 바깥에 만든 파일로 재면 "된다"는 답을 받고 브리지를 열게 되는데, 그것이 정확히 같은 실수의 반복이다.

Codex/Claude는 stdout으로 결과를 정상 반환하고 프롬프트를 stdin으로 받으므로 영향이 없다.

Bridge 상태는 `GET /api/agent-bridge/status`에서 확인합니다. Codex/Claude는 버전 확인과 로그인 상태 확인이 모두 성공해야 사용 가능으로 처리하고, Antigravity는 `agy --version` 성공 시 사용 가능으로 처리합니다.
릴리즈 진단용 `GET /api/agent-bridge/preflight?adapter=codex|claude|antigravity`는 workspace, data directory, CLI 설치, 버전, 인증, Direct Bridge 지원 여부를 구조화된 check 목록으로 반환합니다. UI는 이 값을 그대로 사용해 "설치 필요", "로그인 필요", "현재 Windows 미지원" 같은 실패 상태를 명확히 표시할 수 있습니다.

```text
GET  /api/agent-bridge/settings
GET  /api/agent-bridge/preflight
POST /api/agent-bridge/settings
POST /api/agent-bridge/install/{codex|claude}
POST /api/agent-bridge/login/{codex|claude}
```

Codex는 `codex login status`, Claude Code는 `claude auth status`로 인증 상태를 확인합니다. 로그인 버튼은 별도 터미널에서 각 CLI의 대화형 인증을 시작합니다.

기본 탐색 명령은 `codex`, `claude`입니다. 별도 실행 파일을 사용할 때는 경로만 지정합니다.

```text
FOLIO_AGENT_CODEX_COMMAND=C:\path\to\codex.exe
FOLIO_AGENT_CLAUDE_COMMAND=C:\path\to\claude.exe
AGENT_CLI_PROVIDER=auto|codex|claude
FOLIO_AGENT_CODEX_MODEL=gpt-5.6-sol
FOLIO_AGENT_CLAUDE_MODEL=claude-sonnet-5
AGENT_CLI_TIMEOUT_SECONDS=1800
```

Bridge는 shell 문자열을 실행하지 않고 adapter별 고정 argument list만 사용합니다. Provider API Key 환경 변수는 child process에서 제거하며 저장된 CLI 인증을 사용합니다.

### Codex 브리핑의 브라우저 도구 제외

Codex로 실행하는 `briefing` task는 Context Pack을 로컬 UTF-8 파일로 읽는 보고서 작업이다.
팩 준비부터 본문 생성·계약 보정·동기 보조 조회·writeback까지 해당 실행의 자식 Codex에만
브라우저/컴퓨터 조작 feature와 플러그인 로딩을 끄고, 구형 `node_repl` MCP 연결도 비활성화한다.
기본 셸 파일 읽기, `--sandbox read-only`, 선택 모델과 별도 찾기 패스의 native 웹 검색은 유지한다.

시작 때 한 번 `codex mcp list --json`을 플러그인 비활성 상태로 조회해 기존 연결 이름만
확인한다. `node_repl`이 있을 때만 `enabled=false`를 적용하므로 연결 방식이나 새 설치의
설정을 임의로 만들지 않는다. 이 조회는 모델이나 MCP 서버를 실행하지 않고, 응답 원문을
기록하지 않는다. 설정을 확인하지 못하면 제한 없이 생성하지 않고 안전한 오류로 멈춘다.

전역 `config.toml`이나 설치된 플러그인은 수정하지 않는다. 일반 도크 대화·기업분석·테마분석,
Claude/Antigravity 실행 정책은 그대로이며 예외가 나도 실행별 제한을 되돌린다.
플러그인별 비활성화 대신 이 자식 실행에서 플러그인 전체를 제외하는 이유는 로컬 Codex
0.144.4의 읽기 전용 조회에서 개별 override가 적용되지 않았기 때문이다. 브리핑은 준비된
자료와 기본 검색을 사용하므로 플러그인 도구가 필요하지 않다.

이 제한은 알려진 Codex 브라우저 도구 경로를 제외하는 조치이며 임의의 사용자 정의 MCP나
셸 명령까지 막는 OS 수준 격리는 아니다. 실행별 설정 방식은
[Codex 설정 문서](https://learn.chatgpt.com/docs/config-file/config-reference)를 따른다.
변경은 Folio Board 서버를 재시작한 뒤 시작하는 작업부터 적용되며, 이미 실행 중인 브리핑을
취소하거나 열린 브라우저 탭을 닫지 않는다.

### 찾기 콜의 웹 검색 사용 여부는 어댑터의 구조화 출력에서 관측한다 (0.6, 2026-09-12)

`_used_web_search()`(→ `run_agent_prompt()`의 `webSearch` 키)는 **설정 가능 여부**(요청함 AND 그 어댑터가 정적으로 지원함)일 뿐 실행 중 관측이 아니다. `features/common/execution_result.py::WebSearchFacts{enabled, used: yes/no/unknown, observation}` 계약이 이 문제를 위해 있었지만 실제로는 어디에도 배선되지 않은 scaffold였다.

`web_search=True`인 찾기 콜(`run_agent_prompt(..., web_search=True)` — 본문 생성은 이 값을 넘기지 않는다)에서만 `_adapter_command()`가 어댑터 출력 형식을 구조화 형식으로 바꾼다: claude는 `--output-format text` → `stream-json`, codex는 `--json`을 추가한다. 실측(2026-09-12, claude-sonnet-5/codex-cli 0.153.4, 강제 검색 프롬프트 각 1회)으로 확인한 신호는 —

- **claude**: `stream-json`의 `assistant` 메시지 `content[].type == "tool_use" && name == "WebSearch"` 블록. 최종 `result` 이벤트의 `usage.server_tool_use.web_search_requests`는 검색이 실제로 일어나도 **0으로 남는다** — Claude Code가 WebSearch를 내부 보조 모델(`claude-haiku-*`)로 실행해서다. 그 모델의 `modelUsage["claude-haiku-*"].webSearchRequests`에만 잡히므로, 최상위 usage 요약이 아니라 이벤트 스트림 자체를 읽어야 한다.
- **codex**: `--json` JSONL의 `item.type == "web_search"` 이벤트.

`_extract_web_search_observation()`이 이 이벤트를 읽어 `WebSearchFacts`를 만들고, 최종 텍스트도 이벤트에서 다시 뽑는다(claude는 `result` 이벤트의 `result` 필드, codex는 마지막 `agent_message` 아이템 — 구조화 출력으로 바뀌면 stdout 전체가 더는 순수 응답 텍스트가 아니기 때문이다). 파싱 실패나 지원하지 않는 어댑터(antigravity — 웹 검색 자체를 지원하지 않는다)는 관측하지 않은 것으로 남기고 원래 stdout을 그대로 쓴다.

기존 계약 보존: 루트 `conftest.py`가 테스트의 실제 프로세스 실행을 막으려고 `_invoke_agent_cli`라는 함수 이름 자체를 전역 monkeypatch한다 — 그래서 이 함수의 이름·시그니처·반환 타입(`str`)은 그대로 두고, 새 keyword-only `facts_sink: dict | None = None`(안 넘기면 완전히 이전과 동일)으로만 관측값을 통과시킨다. `run_agent_prompt()` 반환 dict에는 additive `webSearchFacts` 키가 붙는다. `common/engine_lookup.py::invoke()`는 이 값을 반환된 콜러블 자기 자신의 `web_search_facts` 속성으로 얹어(`LookupCall = Callable[[str, str], str]` 타입은 불변 — company_analysis/topic_report는 이 값을 몰라도 그대로 동작한다) `daily_briefing/web_lookup.py`의 `toolUse`가 실제 값을 쓰게 한다.

## 사용 예시

브리핑 context pack 생성:

브리핑 task는 `marketScope: us | kr | europe | jp | both | all | multi`, `briefingType: default | market_focused | concise`, `kind: daily | weekly`를 전달할 수 있습니다. context pack과 writeback 모두 시장별 자료·이슈·세션 계약을 유지하며, 부분 시장 writeback은 저장된 반대편 시장을 보존하고 기존 Personal Overlay를 stale 처리합니다. 시장 내러티브는 `both` 결과에서만 누적합니다. `concise`도 섹션을 삭제하지 않고 시장당 최소 분량만 2,500자로 낮추며, 나머지 유형은 시장당 5,000자 계약을 유지합니다.

브리핑 context pack을 준비할 때 생성 당시 가격 series와 히트맵 사이드카 payload도 고정합니다. Agent가 Markdown 작성을 마친 뒤 writeback하면 같은 snapshot을 보고서와 `{date}.visuals.json`에 저장하므로 작성 시간 동안 시장 데이터가 바뀌어도 과거 보기가 흔들리지 않습니다.

CLI 브리핑은 API 브리핑과 동일한 시장별 프롬프트(`features/daily_briefing/prompt_{us,kr,europe,jp}.md`, 주간은 `prompt_weekly_{us,kr,europe,jp}.md`), 선별 context, evidence, quality preflight를 사용합니다. `outputContract`는 선택 시장별 `0~6 + 오늘의 결론 + Source & Data Notes`, 한 줄 결론, 가운뎃점 요약, 최소 분량과 코드가 계산한 정확한 `세션일 + 마감/장중` 제목을 요구합니다. 전체 자동 재작성은 하지 않습니다(`retryOnViolation: 0`). 형식 계약·출처 whitelist를 통과한 후보의 authored Markdown은 semantic/style/fact-repair/model 호출 없이 저장하며, 취소·기한 초과·안전하지 않은 참조는 기존 파일을 보존합니다. 계약 미달 본문은 `BRIEFING_REJECTION_DUMP_DIR`을 설정한 경우에만 위반 목록과 함께 `contract-*.json`으로 남습니다.

주간은 계약이 갈립니다. 섹션 골격과 제목 규칙(`{라벨} 주간 — {MM.DD}~{MM.DD}`, 마감/장중 없음)이 다르고, 자료 창이 발행일 기준 달력 7일입니다. **그 창이 비면 CLI를 부르지 않고 `WeeklyWindowEmptyError`로 먼저 멈춥니다** — 최소 분량 계약에 걸려 재작성 1회를 더 돌린 뒤 실패하므로 수십 초짜리 실행을 두 번 낭비하고 아무것도 남기지 못합니다. 주간은 세션 시각자료를 만들지 않고 시장 내러티브에도 적재하지 않습니다.

CLI writeback은 최종 Markdown의 주도 기업 ①·② 제목을 다시 해석해 사전 후보 회사 차트를 제거하고 해당 ticker의 생성 당시 차트로 교체합니다. 기업명을 해석할 수 없거나 가격 수집에 실패하면 다른 기업 차트를 순번만 맞춰 붙이지 않고 해당 차트를 생략하며 warning을 남깁니다. 지수와 히트맵 snapshot은 이 과정에서 다시 수집하거나 변경하지 않습니다.

```powershell
py -3 -m features.agent_mode.cli briefing --prepare --date 2026-06-15
```

생성 결과의 `packPath`를 열어 `agentInstructions`, `prompt`, `context`, `outputContract`를 읽고, 에이전트가 브리핑 Markdown을 작성합니다. 작성한 Markdown 파일을 저장한 뒤 writeback합니다.

```powershell
py -3 -m features.agent_mode.cli briefing --pack data\agent-context\briefing\2026-06-15_<packId>.json --write-markdown output.md
```

기업분석 context pack 생성:

```powershell
py -3 -m features.agent_mode.cli company_analysis --prepare --query SPCX
```

테마분석 context pack 생성:

```powershell
py -3 -m features.agent_mode.cli topic_report --prepare --topic-key custom --custom-label "AI 데이터센터 전력 병목" --user-context "전력 인프라와 반도체 공급망 연결 중심"
```

Personal Overlay context pack 생성:

```powershell
py -3 -m features.agent_mode.cli personal_overlay --prepare --report-kind company_analysis --report-id <report-id>
```

Overlay writeback은 JSON 객체를 받습니다.

```powershell
py -3 -m features.agent_mode.cli personal_overlay --pack data\agent-context\personal-overlay\<pack>.json --write-json overlay.json
```

## 안전 규칙

- `.env`, API Key, token, password는 context pack에 넣지 않습니다.
- Canonical 보고서 본문과 Personal Overlay는 분리합니다. Overlay writeback은 `personalOverlay` 필드만 갱신합니다.
- 사용자 Obsidian 노트와 thesis는 hypothesis이며, evidence로 승격하지 않습니다.
- 수치가 pack이나 직접 확인한 출처에 없으면 추정하지 않고 data gap으로 남깁니다.
- `generation.mode = "agent"`를 저장해 agent-authored 산출물임을 표시합니다.

## Persistent Investment Consultation (0.4)

- 상담은 `data/agent-consultations/{sessionId}.json`에 JSON-per-session으로 원자 저장한다.
- 상담 안에서는 bounded memory와 최근 turn으로 문맥을 이어가지만 `layer=hypothesis`, `sourceLayer=user_consultation`, `reuseAsEvidence=false`를 고정한다.
- research index, source ledger, Canonical 보고서, Market Memory, Change Intelligence에는 상담 transcript를 넣지 않는다.
- user turn을 Agent 실행 전에 먼저 저장하므로 재시작 뒤 `retryMessageId`로 이어갈 수 있다. 500-message/2-MiB 경계에서는 연결된 continuation session을 만든다.
- **continuation은 스레드당 하나다.** `operationId` 멱등 검사와 `retryMessageId` 처리는 상한 검사보다 앞서고, 이미 `continuedBy`가 가리키는 active 스레드가 있으면 그것을 재사용한다. 뒤에 두면 같은 요청의 HTTP 재시도마다 continuation이 새로 생기고 `continuedBy`가 덮여 앞선 continuation이 고아가 된다.
- Agent job과 Work Log에는 transcript·memory·Portfolio 상세를 남기지 않고 session/message ID와 terminal status만 남긴다.
- 보고서 proposal/writeback을 사용하지 않는다. 별도 `노트로 정리` preview를 명시적으로 확정할 때만 Native Note snapshot을 만든다.

API: `POST/GET /api/agent/consultations`, `GET/POST/DELETE /api/agent/consultations/{id}`, `POST .../{id}/messages|archive|note`.

## Global Agent Companion

The global Agent starts in Companion Mode on every screen. Companion Mode can answer questions, summarize visible context, suggest next actions, and explain implications without mutating saved reports or Market Memory.

When the user explicitly asks to revise, create, update, schedule, or write back work, the Agent switches to Task Mode. Task Mode must show the intended operation and require approval before saved JSON, SQLite, or report markdown is changed.

`POST /api/agent/companion`은 `message`, `context` 외에 채팅 도구 옵션 `options{model, effort, attachments}`를 받는다. `companion.normalize_agent_options()`가 effort enum(`low/medium/high/xhigh/max/ultra` — 2026-09-16까지 `low/medium/high/max`뿐이었다, 아래 참고), 모델 문자열 길이, 첨부(최대 5개, 이름 120자, 본문 4,000자)를 코드에서 정규화해 응답 `options` 필드로 되돌려준다. 첨부파일 본문은 사용자 참고 입력(hypothesis)일 뿐 evidence로 승격하지 않는다. **정식 이름은 `responseDepth`, `effort`는 하위 호환 별칭이다**(Agent Dock Stage B, 2026-09-15) — 둘 다 받고 둘 다 같은 값으로 돌려준다. Dock 화면의 실제 라벨/셀렉터는 이제 CLI·모델마다 실제로 받는 이름과 범위를 그대로 쓴다(아래 "노력 단계 표기" 참고).

**이미지 첨부는 CLI가 파일을 직접 읽는다 (0.5).** 이미지는 본문 텍스트가 없어 예전에는 프롬프트에 파일명만 실렸고, 이미지를 읽을 수 있는 Agent CLI에 파일이 닿지 못했다. 이제 `features/agent_mode/attachment_files.py`가 바이트를 임시 파일로 내리고 프롬프트에는 **경로만** 싣는다(`bridge.py`가 Agent Context Pack 경로를 싣는 방식과 같다).

- 형식 판정은 파일 시그니처로 한다. 브라우저 MIME과 확장자는 사용자 입력이라 신뢰하지 않는다. PNG/JPEG/GIF/WebP/BMP만 기록하고 그 외는 이유와 함께 거절한다.
- 상한: 이미지 1건 12MB(`MAX_IMAGE_BYTES`), 한 요청 4건(`MAX_IMAGE_FILES`). 초과분은 조용히 버리지 않고 사유를 프롬프트에 남긴다.
- 임시 파일 수명은 `StagedImages` 컨텍스트가 CLI 호출 구간으로 한정한다. 성공·실패·취소 모두에서 삭제한다. 원본을 `data/`에 남기지 않는다(0.4 스크린샷 계약과 동일).
- **바이트는 프롬프트·잡 결과·Work Log 어디에도 남지 않는다.** 잡 결과는 `data/jobs.json`에 저장되므로 `companion.public_options()`가 `imageData`를 떼고 `hasImage: true` 플래그만 남긴다.
- CLI가 없으면 이미지를 읽을 주체가 없다. 조용히 무시하지 않고 "Agent CLI가 없어 이미지를 열 수 없습니다"를 알린다.
- 포트폴리오 사진 가져오기 화면은 숨김 상태다. 기존 `import_image.py`와 `agent_import.py`의 CLI 추출·preview·임시 파일 수명 계약은 유지하며, 도크 이미지 첨부는 지원되는 CLI를 사용한다.

Deep Research의 `Agent에게 변화 묻기`는 frontend가 `collectionId`와 strict 정수 `collectionRevision`만 전달하는 명시적 Companion action이다. 서버는 저장된 Collection을 다시 조회하고 revision을 검사한 뒤, 한 번의 read-only resolve로 현재/이전 스냅샷 metadata, change counts/reason, 현재 외부 evidence 카드 최대 12개를 구성한다. Collection 정의는 ID/revision/definition hash만 포함한 `saved_filter_metadata_not_evidence`, 외부 카드는 `external_evidence_untrusted`로 표시한다. 카드의 title/source/url/snippet은 인용 데이터일 뿐 prompt 지시가 아니며 별도 untrusted delimiter 안에 둔다. 사용자 note/context, frontend가 보낸 match/evidence body, 보고서, Agent 응답은 이 projection에 들어가지 않는다.

Collection change-summary 응답은 conversational/non-mutating이다. workspace open과 Collection refresh는 Agent job을 만들지 않으며, Agent 조회도 스냅샷을 append하지 않는다. Work Log에는 기존 SharedJob의 task/status/timing/engine/artifact metadata만 남고 질문·context·evidence·reply는 복사되지 않는다.

### 개인 투자 맥락 위험 설명

Home·Market Memory·Smart Collection·Deep Research의 개인 맥락 카드에서 사용자가 `Agent로 위험 설명`을 직접 눌렀을 때만 `POST /api/agent/investment-context/explain`이 실행된다. 요청은 선택 ticker 최대 5개만 받으며, 서버가 저장된 context를 다시 조회해 포트폴리오/워치리스트 연결 metadata, Market Memory driver, thesis verdict, checkpoint, 연결 보고서와 외부 evidence 참조를 bounded pack으로 만든다. 수량·비중·note body는 pack에 포함하지 않는다.

Agent 출력은 해석·도전 근거·불확실성·모니터링 질문·한계의 strict JSON 계약을 통과해야 한다. 매수/매도/보유, 목표주가, 권장 비중 또는 포지션 크기 지침, 진입·청산·주문 지침이 감지되거나 출력 계약이 깨지면 결과를 렌더링하지 않고 추천 없는 규칙 설명으로 안전하게 전환한다. 이 작업은 기존 `agent_bridge` SharedJob을 사용하며, Work Log에는 selected ticker, prompt, evidence, reply가 아니라 실행 상태·engine·fallback reason 같은 metadata만 남는다.

## Agent Chat (실연결) + Task Mode Writeback

도크 채팅의 실제 실행 경로는 `features/agent_mode/chat.py`다.

- `POST /api/agent/chat` — `{message, context, options}`를 받아 `agent_bridge` job으로 제출한다(`submit_agent_chat`). CLI 실행이 오래 걸릴 수 있어 프론트는 `/api/jobs/{id}`를 폴링한다.
- **Companion 질문**: 현재 화면 컨텍스트 + 열린 보고서 markdown 발췌(최대 24,000자) + 첨부 + 노력 단계 힌트로 프롬프트를 구성해 `bridge.run_agent_prompt()`(pack/writeback 없는 read-only 원샷 실행, 모델 오버라이드 지원)로 답을 받는다.
- **Task 의도 + 저장 보고서 컨텍스트**(briefing/company_analysis/topic_report): CLI에 `{"summary", "revisedMarkdown"}` JSON으로 전체 수정본을 받아 unified diff와 함께 **제안(proposal)** 으로 `data/agent-proposals/{id}.json`에 저장한다. 이 시점에는 저장 보고서가 바뀌지 않는다.
- `GET /api/agent/proposals/{id}` — pending 제안의 bounded summary/diff/수정 본문을 승인 화면에서 다시 읽고, terminal 제안은 본문 필드가 제거된 상태/status projection으로 읽는다. 이 본문은 Work Log에 복사하지 않는다.
- `POST /api/agent/proposals/{id}` `{action: approve|reject}` — **승인 시에만** Canonical coordinator가 `markdown`, `checkpoints`, `quality`, `qualityGeneration`, `canonicalRevision`, `agentRevisions`를 함께 갱신한다. `personalOverlay` 본문은 보존하고 Canonical 변경 시 stale marker만 추가한다. 제안 생성 이후 저장본의 `canonicalRevision` number/hash가 달라졌으면 보고서를 쓰지 않고 `stale`로 terminalize한다. approve/reject 응답은 `proposalId/status/reportKind/reportId/marketScope/targetRevision` 여섯 필드만 반환한다.
- 제안 파일은 canonical revision과 정규화된 request/Markdown/diff hash를 묶고, apply journal로 prepared → applying → report_written → applied 순서를 복구한다. `applying` 상태의 외부 action은 409이며 startup recovery만 재개한다. 예상하지 못한 적용 오류는 private 예외 문자열을 노출하지 않고 safe error code로 응답한다.
- **CLI가 없으면** 규칙 기반 companion 응답으로 fallback한다(`engine: "rules"`) — LLM 없이도 동작 원칙 유지.
- 종합(`both`) 브리핑은 시장별 파일로 나뉘어 있어 단일 레거시 `{date}.json`이 있을 때만 수정 대상이 된다.

## Agent Work Log

Work Log는 SharedJob과 현재 proposal 파일에서 요청 시점에 파생되는 metadata-only 보기다. 별도 작업 본문을 복사해 저장하지 않으며, 각 entry는 엄격한 31개 필드만 반환한다(2026-09-15, Agent Dock Stage A에서 26→31: 아래 실행 타이밍 5종 추가). prompt/context, reply, Markdown, diff, 경로, traceback, operation/commit metadata와 report·artifact ID는 반환하지 않는다. Pending proposal의 본문이 필요하면 Work Log가 아니라 `GET /api/agent/proposals/{id}`로 다시 조회한다.

- `GET /api/agent/work-log` — `kind=all|companion|task`, `limit`, `offset`으로 파생 목록을 조회한다.
- `POST /api/agent/work-log/clear-preview` → `DELETE /api/agent/work-log` — preview token으로 현재 보이기만 숨긴다. SharedJob, 보고서, proposal 파일은 변경하거나 삭제하지 않는다.
- `POST /api/agent/work-log/migration-preview` → `POST /api/agent/work-log/migration-confirm` — legacy `jobs.json`을 명시적으로 preview한 뒤 v2 job store로 이동한다. 일회성 유지보수이므로 화면 진입점은 Work Log가 아니라 설정의 `이전 작업 기록` 패널이다.

보존 표시는 최대 30일/200건이며, companion만 `category=companion`, artifact-producing task는 `category=task`다. 동기 direct Briefing/Company, index/RSS/setup/install은 Work Log에 들어가지 않는다. Direct Topic과 CLI/Agent Briefing·Company는 SharedJob이므로 포함된다.

### 실행 phase·타이밍 관측 (Agent Dock Stage A, 2026-09-15)

`SharedJob`에 순수 관측 필드 6개를 추가했다 — 기존 `finalEngine`/`fallbackReason`처럼 값이 없으면 `null`이고, 없던 시절 저장된 job JSON도 그대로 읽힌다(옵셔널, 기본값 `None`).

- `phaseCode`(`context|wait_engine|generate|postprocess|commit|null`) — `status`/`messageCode`는 그대로 `queued/running/...`를 유지한 채, 그 안에서 지금 어디에 있는지만 덧붙인다. **`status`를 대신하지 않는다** — `messageCode`는 여전히 `status`와 항상 같아야 하는 별도 불변식이다. `wait_engine`은 Agent CLI 프로세스 전역 세마포어(`Semaphore(1)`) 대기 중, `generate`는 실제 CLI 실행 중을 뜻한다.
- `queueWaitMs`/`contextMs`/`cliMs`/`postprocessMs`/`totalMs` — 이미 진단 스테이지(`wait_engine`/`context`/`generate`/`postprocess`)가 측정해 두던 값을 job에도 투영한 것뿐이라 별도 시계를 새로 두지 않는다(`features/common/jobs.py::stage_timing_summary()`). `totalMs`는 job 시작~답변 저장 직전까지의 wall-clock이라 스테이지 합보다 큰 게 정상이다(스테이지 사이 빈틈 포함).
- 컨설테이션(`run_consultation_job`) 경로에서만 채워진다. rules fallback이면 `finalEngine="rules"`, `adapter="rules"`, `fallbackReason="engine_failed"`로 실제 원인이 job에 그대로 남는다 — 이전에는 이 배선이 없어 CLI가 실패해 규칙으로 떨어져도 `adapter: "auto"`, `finalEngine: null`로 보였다.
- Work Log(`WorkLogEntry`)에는 타이밍 5종만 옮긴다 — `phaseCode`는 완결된 항목(항상 종료 상태)에는 의미가 없어 뺐다.
- **이번 범위는 관측뿐이다.** 토큰 사용량(`UsageFacts`)은 아직 어느 provider에도 연결돼 있지 않고, Dock 화면이 이 값을 실제로 그리는 일은 후속 범위다 — 이번 변경은 API 응답 필드만 늘어난다.

### 프롬프트·토큰 효율 (Agent Dock Stage B, 2026-09-15)

컨설테이션 프롬프트 조립(`consultation_context.py::assemble_consultation_context()`, `chat.py::build_chat_prompt()`)에서 실측으로 확인한 낭비 세 가지를 고쳤다.

- **현재 질문 중복 제거.** 사용자 메시지는 job이 돌기 전에 이미 세션에 저장되므로 `recentMessages`(최근 대화 창)에 방금 그 질문이 포함돼 있었는데, `build_chat_prompt()`가 그 질문을 `message` 인자로 또 받아 프롬프트 끝에 붙이고 있었다 — 같은 문장이 두 번. `assemble_consultation_context(..., current_message_id=...)`가 그 메시지를 `recentMessages`에서 제외한다.
- **"general"(주제 없음) 대화의 fast signals는 관련 티커가 있을 때만.** 주제·보고서·티커 어느 것도 없는 순수 질문에도 티커별 조회인 fast signals까지 매번 붙이고 있었다 — 티커가 없으면 낼 수조차 없는 값이라 티커가 언급될 때만 붙인다. **2026-09-16 정정**: 처음엔 이 참에 marketState/recentChanges까지 함께 비웠는데, 실사용 확인 결과 "요즘 시장 어때" 류의 순수 일반 질문에서도 그 둘은 여전히 근거가 되고(둘 다 티커와 무관한 요약값, 프롬프트 부담도 작다) 완전히 비우면 답이 얕아진다는 게 확인돼 marketState/recentChanges는 general 대화에도 그대로 남기는 것으로 되돌렸다(`_scope_context()`).
- **롤링 요약과 최근 대화 창의 경계를 맞췄다.** `consultation_store.py::_update_memory()`는 메시지 20개가 쌓이면 그 중 오래된 부분(`messages[:-12]`)을 요약하는데, `recentMessages`는 요약 여부와 무관하게 항상 최근 20개를 그대로 실어 8개 구간이 요약과 원문 양쪽에 동시에 실렸다. 요약이 존재하면 `recentMessages`도 `messages[-12:]`로 좁혀 겹침을 없앤다.
- **대화 답변에 보고서 생성용 4M자 안전 상한을 쓰지 않는다.** `bridge.py`의 `MAX_OUTPUT_CHARS`(4,000,000)는 호출 목적과 무관하게 전부 같은 값이었다. 새 `MAX_CHAT_OUTPUT_CHARS`(60,000)를 컨설테이션 경로에만 적용한다(`_invoke_agent_cli`/`run_agent_prompt`의 새 `max_output_chars` 키워드 인자, 기본값은 기존 4M 그대로라 보고서 생성 경로는 무변경).
- **죽은 프롬프트를 지웠다.** `consultation_prompt.py::build_consultation_prompt()`는 "답변을 먼저, 정해진 질문지를 강요하지 않는다"는 좋은 원칙을 갖고 있었지만 프로덕션 어디서도 호출되지 않았다(유일한 참조는 테스트 하나). 그 원칙 문구를 실제 사용되는 `build_chat_prompt()`에 흡수하고 죽은 함수는 삭제했다.
- **이번 범위도 아직 안 한 것들이 있다.** provider별 tokenizer가 필요한 soft token budget은 Stage A에서 미룬 실측 사용량 조사와 같은 이유로 미뤘다. `effort`→`responseDepth`는 백엔드 계약만 정리했다(Dock 화면 라벨은 2026-09-16에 별도로 CLI·모델별 실제 이름으로 바뀌었다 — 아래 "노력 단계 표기" 참고).

### 단일 메시지 fetch·실시간 phase 표시 (Agent Dock Stage C, 2026-09-15)

Dock이 완료된 답변을 읽는 방법과 대기 화면이 실제로 무엇을 보여주는지를 고쳤다 — 이번이 Stage A/B와 달리 처음으로 `ReactAgentDock.tsx`/`useDockThreads.ts`/`AgentMessageContent.tsx`(프론트엔드)를 건드린 단계다.

- **완료된 답변을 전체 스레드 재조회 없이 읽는다.** `job_runtime.py::run_consultation_job()`이 `append_assistant_message()`의 반환값(새 메시지 id)을 이제 `assistantMessageId`로 job 결과에 담는다(`CompanionProjection.sessionId`/`assistantMessageId`, 둘 다 옵셔널). 새 `GET /api/agent/threads/{id}/messages/{messageId}` endpoint(`consultation_store.get_message()`)가 그 메시지 하나만 돌려준다. Dock(`useDockThreads.getMessage()`)은 `assistantMessageId`가 있으면 그것만 읽고, 없거나 실패하면 기존처럼 `latestReply()`(전체 스레드 재조회)로 떨어진다 — 하위 호환.
- **pending 카드가 실제 phase와 경과 시간을 보여준다.** Stage A가 만든 `job.phaseCode`를 이제 Dock이 읽는다 — `pollAgentJobBounded(..., { onUpdate })`가 매 폴링(1초)마다 `phaseHint()`(새 헬퍼, `context|wait_engine|generate|postprocess|commit`을 한국어 문구로 변환 + 경과 시간)로 pending 카드의 고정 문구 `"보통 40~60초"`를 실제 값으로 바꾼다. 첫 폴링 tick 전까지는 기존 고정 문구가 그대로 보여 화면이 비는 순간은 없다.
- **검증**: 새 Playwright e2e(`web/tests/e2e/verification-surfaces.spec.ts`)가 job을 두 tick 동안 `running`(다른 phaseCode)으로 유지한 뒤 `done`으로 만들어, 실제 브라우저에서 pending 카드 문구가 바뀌는 것과 완료 후 답변이 단일 메시지 endpoint에서 왔는지(전체 스레드 재조회 결과와 다른 문자열을 써서 구분)를 함께 확인한다 — mock만 쓰고 실제 CLI 사용량은 없다.
- **이번에 미룬 것.** 세마포어 대기 중 취소가 CLI 프로세스 시작을 막는지는 실측으로 확인한 진짜 결함(`cancel_agent_task()`가 등록된 프로세스가 없으면 아무 것도 못 멈춘다)이지만, job 상태 전이·취소 의미론을 잘못 건드리면 job이 멈추거나 이중 종결될 위험이 있어 별도 라운드로 남겼다. 120초 타임아웃 후 다른 대화를 열었다 돌아와도 재개되는지, first-turn 왕복 합치기도 마찬가지로 미착수.

### 웹 검색 백엔드 계약 (Agent Dock Stage D, 2026-09-15)

Dock 채팅이 웹 검색을 요청·관측·감사할 수 있게 됐다 — **이번엔 백엔드 계약만이다.** 실제 UI 컨트롤(`웹 검색: 끔/자동/사용` 셀렉터)은 Stage E(아래)가 붙였다.

- **`searchPolicy: off|auto|on`**(기본 `off`)이 `companion.py::normalize_agent_options()`의 새 옵션이다. 실제로 검색할지는 새 `bridge.resolve_effective_web_search(policy, adapter_override)`가 **그 turn에 실제로 쓰일 adapter**(`_select_adapter()`와 같은 방식으로 미리 확인) 기준으로 판정한다 — `off`는 항상 안 검색, `auto`/`on`은 그 adapter가 `adapter_supports_web_search()`(codex/claude만 지원, antigravity는 원래부터 아니다)를 지원할 때만 검색한다.
- **`on`인데 지원 안 되면 CLI를 아예 안 부른다.** 검색 없이 조용히 실행하고 성공처럼 보이지 않는다 — 즉시 규칙 기반 답변 + "선택한 CLI(...)는 웹 검색을 지원하지 않아 이 요청을 실행하지 않았습니다" notice로 답한다. `auto`는 반대로 조용히 검색 없이 진행한다(시도가 필수가 아니다).
- **관측은 새로 안 만들었다.** 이번 세션 맨 처음(Stage A 이전) Q4 작업으로 이미 구현된 `WebSearchFacts`/`_extract_web_search_observation()`(codex/claude의 구조화 출력에서 실제 tool-use를 읽는 메커니즘, `docs/agent-guides/daily-briefing.md` 참고)을 그대로 재사용한다 — `_run_with_images()`가 `web_search=`를 `bridge.run_agent_prompt()`에 넘기고, 돌아온 `result["webSearchFacts"]["used"]`(`yes|no|unknown`)를 그대로 `search.toolUsed`로 옮긴다.
- **실제로 검색을 썼을 때만(`toolUsed=="yes"`) URL을 감사한다.** 브리핑이 쓰는 것과 **같은 함수**(`features/common/web_search_scope.py::load_source_scope()`/`audit_urls()`)를 재사용한다. 허용 목록 밖 URL은 evidence처럼 안 보이게 그냥 뺀다(별도 "거부됨" 표시도 안 만듦), 최대 8개까지만 `search.sourceRefs`에 남는다.
- **`search` 메타데이터는 답변마다 저장된다.** `{"requestedPolicy", "toolEnabled", "toolUsed", "sourceRefs"}`가 `consultation_store.append_assistant_message(..., search=...)`를 통해 그 assistant 메시지에 그대로 남는다(옵셔널 필드 — 안 주면 메시지에 키 자체가 없다). task/revision 응답과 CLI-불가 경로도 일관되게 `toolEnabled=False`로 채워 모든 응답이 같은 모양을 갖는다.
- **보고서용 `USE_WEB_SEARCH_FOR_BRIEFING`/`USE_WEB_SEARCH_FOR_ANALYSIS`도 같이 고쳤다.** 실측으로 확인한 진짜 죽은 설정이었다 — `use_web_search_for_briefing()`은 이 이름이 아니라 `USE_LLM_BRIEFING`(LLM 전체 켜짐 여부)을 읽고 있었고, `use_web_search_for_analysis()`는 아예 `use_llm_analysis()`를 그대로 돌려주고 있어서, 두 문서화된 변수는 켜든 끄든 아무 효과가 없었다. 이제 각자 자기 이름의 변수를 읽되(미설정 시 기존처럼 `True`), LLM 자체가 꺼져 있으면 여전히 `False`다.

### Dock UX와 접근성 (Agent Dock Stage E, 2026-09-16)

Stage D가 만든 `searchPolicy` 백엔드 계약을 실제로 켤 수 있는 화면 컨트롤이 이번에 처음 생겼다 — 그 외에는 이미 있던 계약(pending phase 표시, notice/본문 분리, 색+모양 이중 상태 구분)을 손대지 않고 확인만 했다.

- **웹 검색 컨트롤은 새 영구 toolbar가 아니라 기존 접힌 run-settings popover 안에 있다.** `ReactAgentDock.tsx`의 CLI/모델/노력 단계 셀렉터 아래 `<div className="segment" role="group" aria-label="웹 검색">`(끔/자동/사용, `aria-pressed` 소유)를 추가했다 — `MarketChartFigure.tsx` 등 기존 화면과 같은 `.segment` 패턴 재사용. `searchPolicy`는 `providerOverride`/`effort`와 같은 자리의 로컬 state이고 전역 설정에 저장하지 않는다(대화마다 초기화). 어댑터가 `supportsWebSearch === false`(Antigravity)면 자동/사용 버튼이 비활성화되고 "이 CLI는 웹 검색을 지원하지 않습니다" 문구가 뜬다.
- **`useDockThreads.getMessage()`의 계약이 바뀌었다.** Stage C에서는 문자열(`Promise<string>`)만 돌려줬지만, 이제 `{ content, search? }` 객체를 돌려줘 Stage D가 메시지에 저장한 `search` 메타데이터(`requestedPolicy`/`toolEnabled`/`toolUsed`/`sourceRefs`)까지 Dock이 읽을 수 있다. 실패 시 `{ content: "" }`.
- **답변 아래 검색 출처 줄은 실제로 검색을 썼을 때만 보인다.** `SearchSourcesLine`이 `search.toolUsed === "yes" && sourceRefs.length > 0`일 때만 "웹 검색 · 출처 N개 — [출처1], [출처2] ... 외 M개"를 렌더한다(최대 5개 링크, 나머지는 텍스트 요약 — 드롭다운·내부 스크롤 없음). "켰는데 실제로는 안 씀" 같은 상태 고지는 Stage D가 이미 채운 `notice`가 맡아 중복을 안 만든다.
- **접근성**: 전역 제출 오류(`react-agent-error`)는 `role="alert"`(암묵적 `aria-live="assertive"`), notice/검색 출처 줄은 `role="status"`(암묵적 `polite`). 매초 갱신되는 pending 경과 시간(`pendingHint`)은 그대로 live 처리하지 않는다 — 대신 `runState`가 `done`/`error`로 바뀌는 순간에만 문구가 채워지는 별도 `<span className="sr-only" role="status" aria-live="polite">`를 둬서 스크린리더 소음을 피한다.
- **검증**: 소스 텍스트 회귀(`web/tests/reactAgentDockSource.test.mjs`, `getMessage` 객체 계약 포함), 새 Playwright e2e 4건(`web/tests/e2e/verification-surfaces.spec.ts`) — `searchPolicy` 제출 확인, 출처 줄 렌더링, 미지원 어댑터 비활성화, desktop Light/Dark axe(serious/critical 0, `.react-agent-dock` 스코프). 실행 중인 실제 서버(`localhost:8787`)에서 desktop Light/Dark 수동 확인 및 375px에서 `scrollWidth - clientWidth === 0` 확인 — 실제 CLI 호출은 하지 않았다(mock/구조 확인만, §12 정책과 동일).
- **미룬 것**: 기존 3개 `<select>`(CLI/모델/노력 단계)를 `.segment`로 재작업하는 것은 이번 요청 범위 밖이라 손대지 않았다. `effort` 라벨을 `답변 깊이`로 화면에 노출하는 것(Stage B가 남긴 항목)과 Dock search policy가 보고서 전역 검색 설정과 독립임을 화면 문구에 명시하는 것(Stage D가 남긴 항목)도 이번 Stage E 승인 범위에 포함되지 않아 그대로 남는다.

### streaming·추가 업그레이드 판정 (Agent Dock Stage F, 2026-09-16) — 판정: 이번 라운드는 streaming 보류

계획 §1이 F에 요구한 건 "조사와 채택/보류 판단"이다. 이번 세션은 조사 후 **채택하지 않기로(보류) 판정**했고, 코드 변경은 없다.

- **조사는 새 실제 CLI 호출 없이 했다.** `--help`/`changelog`(전부 로컬, 비용 없음)와 이 세션 이전 Q4(2026-09-12) 조사에서 이미 실측된 이벤트 종류만 근거로 삼았다 — 사용자가 이 계획 앞부분에서 확정한 "실사용 검증은 릴리스 후 직접"과 같은 결이다.
- **Claude Code CLI(2.1.266)는 `--include-partial-messages`를 공식 지원한다** — "Include partial message chunks as they arrive"로 문서화된, 세 어댑터 중 유일하게 진짜 토큰/청크 단위 스트리밍이 `--help`로 확인되는 경로다. 지금 코드는 이 플래그를 안 쓰고, `stream-json`은 Stage D의 웹 검색 관측용으로만 켜며 최종 완성 텍스트만 읽는다.
- **Codex CLI(0.153.4)의 `--json`은 Q4 실측에서 `item.type == "agent_message"`(완성된 전체 텍스트)와 `item.type == "web_search"`만 관측됐다** — 델타 이벤트 존재 여부는 이번 조사로 확인 못 했다.
- **Antigravity의 실제 실행 파일은 `agy`이며(설정상 이름, `antigravity`가 아니다) 이 환경에 설치돼 있다** — `agy --help`가 codex/claude와 같은 값 공간으로 `--output-format stream-json`을 이미 문서화한다. 이 계획이 지금까지 "Antigravity는 스트리밍도 조사 불가"로 가정하지 않았다는 점에서 이번 신규 발견이다. 다만 정확한 이벤트 스키마는 미확인이고, 웹 검색 지원 여부(`WEB_SEARCH_ARGS`, codex/claude만)와는 별개 축이라 Stage D의 "Antigravity 웹 검색 미지원" 판정은 그대로다.
- **보류 근거 세 가지** — (1) 지금 `_invoke_agent_cli()`는 `proc.communicate()`로 프로세스가 끝날 때까지 블로킹한 뒤 stdout 전체를 한 번에 받는다. 세 어댑터 전부, 웹 검색 여부와 무관하게 동일하다 — 저장소 어디에도 stdout을 프로세스 실행 중 줄 단위로 읽는 코드가 없다. (2) `cancel_agent_task()`는 `_RUNNING_PROCESSES`에 등록된, 즉 이미 시작된 프로세스만 종료할 수 있다 — `_RUN_SEMAPHORE` 대기 중인 job은 취소 요청이 와도 멈출 프로세스가 아직 없다(Stage C가 이미 발견해 별도 라운드로 남긴 구멍). Gate F 자신이 "cancellation이 가능할 때만 streaming을 연다"는 조건을 걸었는데 그 전제가 아직 안 갖춰졌다. (3) 부분 출력을 안전하게 버리는 장치가 없다 — 지금은 CLI가 끝까지 성공해야만 `append_assistant_message()`가 불려 이 위험 자체가 존재하지 않지만, streaming을 열면 새로 설계해야 한다. 위 셋이 갖춰지지 않은 채 streaming부터 열면 Gate F가 막으려는 정확한 실패 모드(취소 실패, 불완전 문장 저장)를 새로 만든다.
- **guardrail 항목은 지금 이미 참이라 확인만 했다.** streaming 미지원 adapter의 실제 단계+경과 시간 UI(Stage C/E의 `phaseHint()`/`pendingHint`, 지금은 셋 다 미지원이라 유일한 대기 화면)와 fake typewriter 미구현(코드 전체에 문자 단위 지연 렌더링 없음)은 새로 손대지 않고 그대로 유지된다.
- **adapter별 process warm-up/재사용**: 별도 결정 = 지금은 안 한다. 매 호출을 독립 `subprocess.Popen`으로 새로 띄우는 지금 방식이 프로세스 간 인증·컨텍스트 누수를 원천적으로 막는다 — 지연 시간이 실측 병목이라는 근거 없이 그 격리를 프로세스 수명 동안 공유 상태로 바꿀 이유가 없다.
- **대화별 feedback/regenerate — 설계만, 미구현**: 새 `POST /api/agent/threads/{id}/messages/{messageId}/regenerate`가 그 assistant 메시지의 원본 user turn을 다시 읽어 새 job을 돌리고, 결과를 기존 메시지를 덮어쓰지 않고 같은 메시지 아래 추가 attempt로 쌓는 설계를 남긴다 — "새 시도"는 새 레코드이지 기존 대화의 권위를 바꾸는 수정이 아니다. Thesis verdict/Portfolio review state 등 §10의 권위 저장소는 애초에 대화 생성 경로에서 안 건드리므로 이 설계로 새로 생기는 위험은 없다.
- **Gate F는 대부분 공허하게 충족된다.** streaming을 아예 안 열어서 "adapter별 지원/미지원"도, "partial output 실패 시 불완전 문장 저장"도 발생할 상황 자체가 아직 없다 — 둘 다 streaming을 실제로 채택할 때 다시 검증해야 할 항목으로 남는다.

### 노력 단계 표기 — CLI·모델마다 실제로 받는 이름·범위로 통일 (2026-09-16)

Dock과 Home 화면 composer의 "노력 단계" 셀렉터가 CLI/모델과 무관하게 항상 같은 4개(낮음/중간/높음/최대, 한글 번역 라벨)를 보여주고 있었다 — 실제로는 CLI마다, 같은 CLI 안에서도 모델마다 받는 값과 이름이 다르다(`features/llm_settings/reasoning.py`가 이미 이 계산을 갖고 있었고 Settings 화면은 이미 그걸 쓰고 있었다). 사용자 요청("Codex는 Light~Ultra, Claude Code는 Low~Ultra처럼 모델에 맞는 노력 수준이 대응되도록")으로 Dock·Home 두 화면을 이 실제 계약에 맞췄다.

- **표시는 provider-native 영어 이름이다.** Codex는 `low`를 "Light"로 부르고 Medium/High/Extra High/Max/Ultra까지, Claude Code는 "Low"로 부르고 대개 Max까지(모델에 따라 Extra High 없이 Max에서 끝나는 경우도 있다 — `CLAUDE_MODEL_REASONING_EFFORTS`), Antigravity는 Low/Medium/High만 지원한다. 라벨을 화면에서 다시 번역하지 않는다 — `reasoning_label()`이 이미 "Codex Ultra 같은 라벨을 지원 안 하는 값으로 잘못 보내는 사고를 막으려고" provider별로 고정해 둔 값이라(`features/llm_settings/reasoning.py` 모듈 docstring), 그 값을 그대로 쓰는 것 자체가 계약이다.
- **모델을 바꾸면 목록도 같이 바뀐다.** `/api/agent-bridge/settings`가 이미 각 어댑터에 `reasoningChoices`(현재 모델 기준)와 `reasoningByModel`(모델별 전체 목록)을 실어 보내고 있었다 — Settings 화면(`SettingsRoute.tsx`)은 이미 이걸 쓰고 있었지만 Dock(`ReactAgentDock.tsx`)과 Home composer(`agentWorkspace/presenters.ts`+`useAgentWorkspace.ts`+`AgentComposer.tsx`)는 각자 독립적으로 하드코딩된 4개짜리 목록을 갖고 있었다. 두 화면 모두 새 `reasoningChoicesFor(adapter, model)`(모델별 목록 우선, 없으면 어댑터 기본 목록, `provider_default`는 제외 — 도크는 항상 명시적인 단계 하나를 보낸다)로 바꿨다.
- **CLI·모델을 바꾸면 선택된 단계도 안전하게 옮긴다.** 예를 들어 Codex GPT-6 Astra에서 "Ultra"를 고른 채 GPT-5.5(Extra High까지만 지원)로 모델을 바꾸면, 새 목록에 "Ultra"가 없으므로 자동으로 "Medium"(있으면)이나 첫 번째 값으로 옮긴다 — 실측 확인(`localhost:8787`에서 직접 재현). 이 클램프가 없으면 다음 전송에서 `bridge.py::_cli_reasoning_effort()`가 그 조합을 `ValueError`로 거부한다(fail-closed 설계라 조용히 다른 값으로 안 바뀌고 그 자리에서 막힌다).
- **백엔드가 실제로 `xhigh`/`ultra`를 받게 고쳤다 — 이게 진짜 버그였다.** `companion.py::VALID_EFFORT_LEVELS`가 `{low, medium, high, max}` 넷뿐이라(2026-09-16까지), 화면에서 아무리 "Ultra"를 골라 보내도 `normalize_agent_options()`가 조용히 "medium"으로 깎아 CLI에는 전혀 다른 값이 전달됐을 것이다(§6 규칙14와 같은 유형 — 화면 계약과 서버 계약이 따로 놀았다). `xhigh`/`ultra`를 추가하고, `chat.py::EFFORT_HINTS`(프롬프트에 박히는 자연어 지침 문장)에도 두 단계의 문구를 새로 채워 넣었다(둘 다 없으면 그 자리도 조용히 "medium" 문구로 떨어진다).
- **검증**: 새 Python 테스트 2건(`test_companion.py::test_normalize_agent_options_accepts_the_full_provider_reasoning_range`, `test_chat.py::test_build_chat_prompt_carries_the_full_provider_reasoning_range`), `features/agent_mode/` 461 passed. 프론트 `tsc --noEmit` 0 errors, `test:source` 282·`test:unit` 184·영향 Playwright e2e 18 passed(회귀 없음). 실행 중인 실제 서버(`localhost:8787`)에서 Codex(Light~Ultra, GPT-6 Astra 기준)·Claude Code(Low~Max)·모델 전환 시 클램프를 직접 확인 — Antigravity는 이 환경에서 `bridgeSupported: false`(미인증)라 셀렉터 자체가 비활성화돼 실사용 확인은 못 했다(구조상 도달 불가능한 경로이므로 안전한 자리표시자 목록으로 대체). 테스트 중 전역 Codex 모델 설정이 일시적으로 바뀐 것을 원래 값으로 되돌렸다.

### 실사용 확인 — 노력 단계가 CLI에 안 닿던 결함, 일반 대화 컨텍스트 과다 축소 (2026-09-16)

사용자가 릴리스 없이 바로 실사용해보고 "확실히 빨라지긴 했는데, 분석이 필요한 질문에서도 생각하는 시간이 짧아지면서 답변 품질이 내려간 것 같다"고 보고했다. 원인을 추적해 서로 다른 두 가지를 찾았다.

- **진짜 결함: "노력 단계" 선택이 CLI의 실제 추론 강도에 한 번도 안 닿고 있었다(master에도 있던 오래된 문제, 이번 세션이 만든 게 아니다).** `chat.py::_run_with_images()`가 `bridge.run_agent_prompt()`를 부를 때 `reasoning_effort`를 아예 안 넘기고 있어서, `_cli_reasoning_effort()`가 항상 빈 값을 받아 `--effort`/`-c model_reasoning_effort=` 플래그 자체가 커맨드에 안 실렸다 — CLI는 매번 자기 기본값으로 돌았다. 지금까지 "노력 단계" 셀렉터는 프롬프트에 박히는 자연어 문장(`EFFORT_HINTS`, "응답 지침: ...")에만 영향을 줬다. `_run_with_images()`가 `options.get("effort")`를 `reasoning_effort=`로 넘기도록 고쳐 이제 실제로 CLI 추론 강도까지 바뀐다.
- **이번 세션이 만든 진짜 회귀: "general" 대화의 컨텍스트를 과하게 비웠다.** Stage B가 fast signals(티커별 조회라 애초에 티커 없인 낼 게 없다)와 함께 marketState/recentChanges까지 같이 비워서, "요즘 시장 어때" 같은 순수 일반 질문에서도 근거 자료가 완전히 사라져 답이 얕아졌다. 둘 다 이미 상한이 걸린 요약값(marketState는 최대 12개 필드씩, recentChanges는 최대 20건)이라 프롬프트 부담이 크지 않은데도 통째로 비운 것은 과했다 — `_scope_context()`가 이제 general 대화에도 marketState/recentChanges는 남기고, fastSignals만 티커가 있을 때로 좁힌다.
- **검증**: 새 테스트 2건(`test_chat.py::test_dock_chat_forwards_the_chosen_effort_to_the_cli_reasoning_flag`, `test_consultations.py::test_truly_general_scope_still_gets_lightweight_market_context` 갱신) 포함 `features/agent_mode/` 462 passed. 실제 CLI로 "전과 후 답변 깊이"를 비교하는 것은 이번 범위에 안 넣었다 — 사용자가 실사용하며 계속 확인하기로 한 기존 결정과 같은 결이다.

SharedJob/Work Log의 경로별 lock registry는 프로세스 수명 동안 항목을 퇴거하지 않는다. 실제 제품의 durable store 경로는 설정된 data root 아래의 유한한 집합이며, 오래 살아 있는 service와 새 service가 같은 경로에 서로 다른 lock을 받지 않도록 lock identity를 보존하는 것이 메모리 회수보다 우선한다.

실행 중인 CLI 작업을 취소할 때는 SharedJob을 먼저 `cancel_requested`로 기록한 뒤 등록된 child process를 종료한다. 이미 terminal이거나 `committing`인 작업은 취소와 process 종료를 모두 거부하며, 종료 경계에서 child가 먼저 끝나도 승인된 취소는 유지한다.

## 0.6 실행 진단 경계 (L1b–D3)

앱 API에서 제출된 Agent SharedJob은 기존 job/private lifecycle의 권위를 바꾸지 않은 채 안전한 실행 관측만 남길 수 있다. 관측은 private cleanup과 job terminal 저장이 성공한 뒤에만 terminal로 닫히며, Work Log의 31개 필드·prompt/reply/diff 보존 규칙은 바뀌지 않는다. Agent CLI의 stdout·stderr·context pack·본문은 diagnostics에 복사하지 않는다.

`GET /api/diagnostics/jobs/{jobId}`(및 job이 없는 자동화 경로용 `GET /api/diagnostics/runs/{runId}`)는 여전히 headless 상세 API이며 Work Log의 31개 필드 응답 자체를 바꾸지 않는다. 대신 각 Work Log 항목(`web/src/app/AgentWorkLog.tsx`)과 설정의 자동화 실행 내역(`web/src/app/SettingsRoute.tsx::LastRun`)이 공유 컴포넌트 `web/src/app/DiagnosticDetail.tsx`로 이 API를 펼쳐서 조회한다 — jobId가 있으면 그쪽을, 없으면 자동화 row의 `diagnosticRunId`를 쓴다. 실패 단계·확인된 원인·마지막으로 완료된 단계·경과 시간·다음 행동과, 접어 둔 개발자 정보(실행 ID·오류 ID·지문·소스 위치)만 보여주며 `기록 없음/보존 만료/기록 일부 누락/조회 실패/실행 중/규칙 기반으로 완료` 여섯 상태를 구분한다(`web/src/app/diagnosticCopy.ts`). L1c는 실제 CLI/process·chat·durable JSON/SQL producer의 safe stage/terminal 관측을 더했지만 provider protocol/parser 소비자 변경은 하지 않았다. record 품질은 누락·legacy·외부 변경을 숨기지 않기 위해 계속 partial일 수 있다(RSS·색인만 감사된 경로에서 complete). **공통 목록**은 기존 Work Log 안의 `실패·대체 실행 찾기`를 펼쳐서 `실패만`·`대체 실행만`·기간·`모든 실행 보기`로 전환한다. 목록/진단/숨기기 미리보기·확인·제안 조회 오류는 각각 해당 메시지 옆의 제한된 진단 상세로 연결하며, 응답이 없는 숨기기 확인은 결과 미확정으로만 안내하고 자동 재시도하지 않는다. `GET /api/diagnostics/runs` headless API는 구현되어 있으며 서버가 숨긴/현재 권위에서 사라진 job을 제외하고 기존 Work Log ID를 연결한다. 기존 31필드·clear/migration 계약과 진단 자체 내보내기(D4) 경계는 불변이다.

## 구현 위치

```text
features/agent_mode/schema.py   # context pack schema, secret scrubber, generation metadata
features/agent_mode/service.py  # prepare/writeback handlers
features/agent_mode/cli.py      # Phase 1 chat command entrypoint
features/agent_mode/bridge.py   # Phase 2 Direct Agent Bridge adapters/subprocess
features/agent_mode/collection_context.py # bounded Collection change-summary context
features/agent_mode/setup.py    # CLI 설치/로그인/제공자·모델 설정
features/agent_mode/generation_mode.py # rules/llm_cli normalization
```

## Stage 0.2.3 Investment Context 통합

`GET /api/investment-context/summary`와 `GET /api/investment-context/{ticker}`가
Home, Market Memory, Smart Collection, Deep Research에 동일한 read-only projection을
제공한다. 카드 표시·새로고침·checkpoint 조회만으로 Agent job을 만들지 않으며,
`Agent로 위험 설명` 버튼만 명시적 실행 경계다.

Agent는 선택 ticker를 서버 저장소에서 다시 조회하고 추천 없는 controlled 설명만
반환한다. 결과는 저장 보고서, 포트폴리오, 워치리스트, checkpoint를 자동 변경하지
않으며 Work Log에도 ticker, context, prompt, reply를 남기지 않는다.

## Agent 대화 (스레드) — 0.5

**도크가 대화의 집이다.** 주제가 붙은 대화(워치리스트·포트폴리오·보고서)는 도크 아래 한 종류이며, 별도 상담 패널은 없다. 화면에서는 전부 **대화**라 부르고 주제는 칩으로 보여준다.

`상담`이라는 말은 화면에서 뺐다 — 전문가가 조언한다는 뜻을 담는데 §5 원칙 3은 "사용자 생각을 옹호하지 말고 검증한다"이고 Agent는 투자 조언을 하지 않는다. 내부 식별자(`sourceLayer: user_consultation`, `consultationRef`)는 저장된 데이터와의 계약이라 그대로 둔다.

| | 값 |
|---|---|
| 저장 | `data/agent-threads/{id}.json` (JSON-per-thread) |
| API | `/api/agent/threads*` |
| 이관 | `agent-consultations/` → `agent-threads/` 첫 사용 시 1회. 복사 후 삭제라 실패해도 원본이 남고, 이름이 겹치면 양쪽 다 보존한다 |
| 브라우저 대화 | 첫 실행 시 서버 스레드로 1회 이관(`importMessages`). 옛 질문을 Agent로 재실행하지 않고 기록만 옮긴다 |

### 왜 서버에 저장하나

도크 대화가 `localStorage`에만 있으면 **Agent가 읽을 방법이 없다.** 세션이 끊겼다 돌아왔을 때 앞 맥락을 쓰는 것이 요구인데, 서버에 기록이 없으면 원천적으로 불가능하다.

### 생성과 저장이 한 경로다

스레드 러너(`job_runtime.run_consultation_job`)는 **맥락 조립과 저장만** 하고 생성은 도크와 같은 `chat.run_agent_chat`에 맡긴다. 두 경로로 나누면 같은 대화가 갈라져, 제안을 만들거나 거절한 사실이 대화 기록에 남지 않고 다음 세션의 Agent가 같은 제안을 다시 한다.

- 모델 입력은 전체 transcript가 아니라 **상한 있는 pack**이다: rolling summary + 최근 turn + 서버가 **매번 다시 읽은** 리서치 자료(32,000자, 넘치면 4단계 축약). 저장된 옛 시세·옛 브리핑을 재생하면 오래 쉬었다 돌아온 사용자에게 낡은 사실로 답하게 된다.
- **답변 본문은 잡 결과가 아니라 스레드에서 읽는다.** 잡 결과는 `data/jobs.json`과 Work Log에 저장되므로 transcript를 담지 않는다.
- 대화는 계속 hypothesis다. `layer=hypothesis`, `sourceLayer=user_consultation`, `reuseAsEvidence=false`가 코드 상수로 강제되고 화면에도 그 경계를 표시한다.
- scope를 주지 않으면 `general`이다. 예전에는 알 수 없는 kind가 조용히 `portfolio`로 떨어져, 주제 없는 도크 대화가 포트폴리오 대화로 둔갑하며 무관한 맥락을 끌어왔다.

투자 리뷰 반박은 예외적으로 정확한 저장 날짜/revision만 읽는다. 32,000자 상한에서도
해당 identity, 최소 종목 목록(최대 100), 실제 포함/제외 범위와 핵심 반증을 우선 보존하고
지난 대화·선택적 상세부터 줄인다. 화면 보고서나 일반 시장/컬렉션 맥락을 추가하지 않으며,
누락은 data gap으로 알린다. 이 대화가 리뷰·Thesis를 자동 수정하거나 evidence가 되지는 않는다.

### 원클릭 반박 대화 — 0.6 Stage D

시장 내러티브의 `이 전제를 반박해줘`와 Watchlist Thesis의 같은 이름 action은 기존 도크에 **새 scoped thread를 만들고 첫 질문을 정확히 한 번 자동 제출**합니다. 화면을 열거나 새로 고치는 동작은 Agent를 부르지 않습니다.

- 브라우저는 본문 사본이 아니라 제한된 scope만 보냅니다: 내러티브 `{kind: market_memory, id: stateId, intent: challenge}`, Thesis `{kind: watchlist, id: ticker, tickers: [ticker], intent: challenge}`. 서버가 매 turn 권위 저장소에서 선택 대상을 다시 읽습니다.
- `intent=challenge`는 스레드와 continuation에 보존되어 후속 질문도 같은 내러티브/Thesis를 사용합니다. ID가 없거나 stale이면 전체 시장/워치리스트로 넓히지 않고 좁은 data gap을 반환합니다.
- 근거 창은 실제 최근 90일로 제한합니다. hypothesis인 Thesis 본문과 source-grounded 검증·근거는 분리하고, 반대 근거·모순·불확실성·신뢰도·중요도를 요구합니다.
- 답변은 추천이 아니며 `reuseAsEvidence=false`입니다. verdict, checkpoint, Thesis, 포트폴리오를 자동 수정하지 않고 저장 변경은 기존 preview/명시적 확인 경계를 따릅니다.
- 내러티브 scope 칩은 내부 state ID를 노출하지 않고 `시장 내러티브`로만 표시합니다. Thesis는 사용자가 알아볼 수 있는 정규화 ticker를 표시합니다.

### 대화 관리

목록·전환·제목 수정·보관·삭제를 도크가 소유한다. 삭제는 되돌릴 수 없어 확인을 받으며, 저장소도 `delete_session(confirmed=True)` 없이는 지우지 않는다.

### E0 인용의 공개 투영

기업분석 bridge는 private `result_sink`를 호출별로 유지하고 실제 채택된 재시도 결과만 인용 연결에 사용한다. pack에는 private 결과 객체를 넣지 않는다. 최종 Markdown에는 출처 원장과 연결되고 위치가 유효한 링크만 투영한다(`features/common/report_citations.py`). provider 세션 이어쓰기는 여전히 미지원이며, 기존 job/candidate 복구와 구분한다.
