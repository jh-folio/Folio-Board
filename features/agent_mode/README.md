# AI Agent Mode

기업분석의 선택적 구조 보완 재시도는 실패하거나 개선되지 않아도 먼저 받은 본문을 유지합니다.
구조 검증을 수행하지 못한 결과는 검수 미완료 경고와 함께 저장 경로에 전달하며 통과로 표시하지 않습니다.
취소된 기업분석 작업은 이 복구 경로를 통해 성공 저장으로 바꾸지 않습니다. 브리핑의 별도 생성·저장 계약은 변경하지 않습니다.

Claude 작성은 `plan`이 아닌 `dontAsk`로 실행한다. 도구는 Read/Glob/Grep만 허용하며, 명시적 웹 조회 호출에만 WebSearch를 더한다. 셸·편집·쓰기·상속 MCP 도구를 열지 않고 전역 설정도 수정하지 않는다. 브리핑은 공유 조립기가 만든 agentInstructions/prompt/context와 출력·저장 계약을 stdin으로 그대로 전달해, 큰 내부 차트 pack을 셸로 해체할 필요가 없게 한다. Codex는 기존 read-only 실행과 파일 pack 전달을 유지한다.

형식 거절은 `BriefingOutputContractError`로 구분하며 `contract_*` 코드만 대체 보고서의 `generation.rejectedReasonCodes`에 남긴다. 다른 `ValueError`를 형식 실패로 분류하거나 규칙 대체로 숨기지 않는다.

브리핑 규칙 대체 저장은 작업의 `finalEngine=rules`, `generationMode=rules`, `fallbackReason=engine_failed`로 기록한다. 보고서에는 상세 대체 사유와 허용된 최초 검증 거절 코드가 남으며, 취소·기한 초과는 대체 생성으로 숨기지 않는다.

규칙 기반 브리핑 대체 조립은 자료 그룹이 없거나 요청 시장에 해당하는 그룹이 없어도 처리합니다. 실행 중인 서버에는 Python 변경이 자동 반영되지 않으므로, 수정 적용 시 활성 작업이 없는지 확인하고 정상 재시작한 뒤 응답을 확인합니다.

브리핑 저장은 authored Markdown을 보존하면서 최종 형식·출처 URL·source ID·section whitelist를 확인합니다. 의미 기반 수치·단위·방향·날짜·상대강도 판정은 명시적 offline 평가에만 남고, 일반 CLI/API 저장 경로는 semantic/style/fact-repair/model 호출을 하지 않습니다. 취소·기한 초과·안전하지 않은 참조는 계속 저장을 막으며, 명시적 품질 보완은 별도 `quality_repair` 작업입니다. CLI 응답 형식이나 사용자가 선택한 모델 설정은 이 검사로 변경하지 않습니다.

작성용 한국장 자료에는 내부 provider 경고를 넣지 않으며, 최종 저장에서도 연결 설정·provider 경고 문구만 제거합니다. 수치의 실제 출처·기준일과 원래 진단 메타데이터는 유지합니다. 저장 브리핑 차트는 API와 같은 정규장 가격 계열을 사용하며 Toss 실시간 화면 설정을 바꾸지 않습니다.

선택적으로 켠 일간 뉴스 의미 평가는 실행 중인 bridge의 실제 adapter/model/job과 남은 시간을 전달받습니다. 단독 context pack 준비는 CLI를 호출하지 않습니다. 시장당 한 번의 별도 평가이며 본문 보수 횟수를 늘리지 않고, 중첩 호출은 기존 세마포어를 다시 잡지 않습니다. API fallback은 없으며 평가를 못 하면 기존 작성 입력을 유지합니다. 상한과 입력·출처 계약은 일일 브리핑 README를 따릅니다.

브리핑은 자료 보완 검색과 본문 작성을 분리합니다. Codex 작성 명령은 `web_search="disabled"`, 보완 조회는 `web_search="live"`를 명시하고 Claude 작성에서는 WebSearch/WebFetch를 제한합니다. 다른 작업의 검색 정책은 그대로입니다. 실행 도구 사용이 관측되지 않으면 미확인으로 기록하며, 명령에 설정했다고 실제 검색 증거로 계산하지 않습니다. API와 CLI는 같은 시장별 이전 확인 사항 및 제한 뉴스 선별 컨텍스트를 사용합니다.

AI Agent Mode는 OpenAI/Gemini/Claude API Key 없이도 Codex, Claude Code 같은 구독형 AI 에이전트를 Folio Board의 최종 작성자로 쓰기 위한 보조 기능입니다.

0.2에서는 Home과 Deep Research에서 Agent를 사용하고, 두 화면이 같은 metadata-only Work Log를 공유합니다. Work Log에는 prompt, reply transcript, Markdown, diff, attachment, 로컬 path, credential, raw stdout/stderr가 저장되지 않습니다. Canonical 보고서는 generate/regenerate 또는 명시적으로 승인된 proposal만 수정할 수 있습니다.

Folio Board는 자료 선별, context pack 생성, 저장 포맷, 품질 metadata를 맡고, 현재 채팅 중인 AI 에이전트가 context pack을 읽어 보고서/overlay/delta를 작성합니다. 앱 내부 LLM API를 호출하지 않는 경로입니다.

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
AI_AGENT_MODE=api       -> 앱 내부 LLM API
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
- 도크의 CLI·모델·노력은 **버튼 하나로 접어** 둔다. 도크는 384px이라 셋을 나란히 두면 폼이 461px로 벌어져 77px이 잘렸고, 줄바꿈을 허용해도 늘 두 줄이었다. 버튼에는 `Claude · Claude Opus 5 · 중간`처럼 요약을 그대로 적어 열지 않고도 무엇으로 도는지 읽힌다. 팝오버는 위로 열린다 — 도크 맨 아래라 아래로 열면 화면 밖이다.
- 도크 헤더의 `대화 목록`·`새 대화`·`닫기`는 **아이콘 셋**이다. 글자 버튼으로 두면 385px 헤더에서 액션이 175px을 가져가 제목이 두 줄로 접히고 헤더가 107px까지 자란다 — 그만큼 대화가 아래로 밀린다. 아이콘으로 줄여 116px이 되고 제목은 한 줄로 선다(넘치면 말줄임). 이름은 툴팁과 `aria-label`이 진다.
- 도크에서 CLI를 바꾸면 모델 목록이 통째로 달라지므로 모델도 그 CLI의 것으로 옮긴다. 이때도 전역 모델은 저장하지 않는다 — 저장하면 `이 대화에만`이 거짓이 되고 예약 브리핑의 모델까지 조용히 바뀐다.

설정 탭의 `AI Agent 설정`에서는 Agent 생성 ON/OFF와 CLI/API 모드를 토글하고, CLI 모드에서는 Codex CLI, Claude Code CLI, Antigravity CLI 중 하나를 선택해 모델을 지정합니다. 모델 목록은 마지막으로 갱신한 캐시를 기본으로 사용하고, 사용자가 새로고침을 누를 때만 CLI 모델 조회 명령을 실행합니다. 설치 명령은 실행 전에 사용자 확인을 받습니다.

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

브리핑 Agent pack의 출처 카탈로그는 컨텍스트에 실제로 렌더링된 writer 자료 집합에서 만들어집니다. API와 CLI 모두 같은 `sourceId` 집합을 사용하고, 시장별 ledger도 해당 시장 writer 자료만 보존합니다. Summary와 Full Text는 분리된 제한 발췌로 전달되며 페이지 메뉴·추천·자동 요약 문구는 제외됩니다.

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

`POST /api/agent/companion`은 `message`, `context` 외에 채팅 도구 옵션 `options{model, effort, attachments}`를 받는다. `companion.normalize_agent_options()`가 effort enum(`low/medium/high/max`), 모델 문자열 길이, 첨부(최대 5개, 이름 120자, 본문 4,000자)를 코드에서 정규화해 응답 `options` 필드로 되돌려준다. 첨부파일 본문은 사용자 참고 입력(hypothesis)일 뿐 evidence로 승격하지 않는다.

**이미지 첨부는 CLI가 파일을 직접 읽는다 (0.5).** 이미지는 본문 텍스트가 없어 예전에는 프롬프트에 파일명만 실렸고, 이미지를 읽을 수 있는 Agent CLI에 파일이 닿지 못했다. 이제 `features/agent_mode/attachment_files.py`가 바이트를 임시 파일로 내리고 프롬프트에는 **경로만** 싣는다(`bridge.py`가 Agent Context Pack 경로를 싣는 방식과 같다).

- 형식 판정은 파일 시그니처로 한다. 브라우저 MIME과 확장자는 사용자 입력이라 신뢰하지 않는다. PNG/JPEG/GIF/WebP/BMP만 기록하고 그 외는 이유와 함께 거절한다.
- 상한: 이미지 1건 12MB(`MAX_IMAGE_BYTES`), 한 요청 4건(`MAX_IMAGE_FILES`). 초과분은 조용히 버리지 않고 사유를 프롬프트에 남긴다.
- 임시 파일 수명은 `StagedImages` 컨텍스트가 CLI 호출 구간으로 한정한다. 성공·실패·취소 모두에서 삭제한다. 원본을 `data/`에 남기지 않는다(0.4 스크린샷 계약과 동일).
- **바이트는 프롬프트·잡 결과·Work Log 어디에도 남지 않는다.** 잡 결과는 `data/jobs.json`에 저장되므로 `companion.public_options()`가 `imageData`를 떼고 `hasImage: true` 플래그만 남긴다.
- CLI가 없으면 이미지를 읽을 주체가 없다. 조용히 무시하지 않고 "Agent CLI가 없어 이미지를 열 수 없습니다"를 알린다.
- 포트폴리오 사진 가져오기는 **0.5.0 화면에서 빠졌다**(`features/portfolio/README.md`). 로컬 OCR·외부 Vision 런타임은 코드로만 남아 있고 화면도 route도 없다 — 0.5.X에서 사진 인식을 이 도크 경로 하나로 옮길 때 재료로 쓴다. **막힌 지점**: 이 첨부 경로는 CLI 전용이라(`_run_with_images`) 도크가 API 모드일 때는 이미지를 못 읽는다.

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

Work Log는 SharedJob과 현재 proposal 파일에서 요청 시점에 파생되는 metadata-only 보기다. 별도 작업 본문을 복사해 저장하지 않으며, 각 entry는 엄격한 26개 필드만 반환한다. prompt/context, reply, Markdown, diff, 경로, traceback, operation/commit metadata와 report·artifact ID는 반환하지 않는다. Pending proposal의 본문이 필요하면 Work Log가 아니라 `GET /api/agent/proposals/{id}`로 다시 조회한다.

- `GET /api/agent/work-log` — `kind=all|companion|task`, `limit`, `offset`으로 파생 목록을 조회한다.
- `POST /api/agent/work-log/clear-preview` → `DELETE /api/agent/work-log` — preview token으로 현재 보이기만 숨긴다. SharedJob, 보고서, proposal 파일은 변경하거나 삭제하지 않는다.
- `POST /api/agent/work-log/migration-preview` → `POST /api/agent/work-log/migration-confirm` — legacy `jobs.json`을 명시적으로 preview한 뒤 v2 job store로 이동한다. 일회성 유지보수이므로 화면 진입점은 Work Log가 아니라 설정의 `이전 작업 기록` 패널이다.

보존 표시는 최대 30일/200건이며, companion만 `category=companion`, artifact-producing task는 `category=task`다. 동기 direct Briefing/Company, index/RSS/setup/install은 Work Log에 들어가지 않는다. Direct Topic과 CLI/Agent Briefing·Company는 SharedJob이므로 포함된다.

SharedJob/Work Log의 경로별 lock registry는 프로세스 수명 동안 항목을 퇴거하지 않는다. 실제 제품의 durable store 경로는 설정된 data root 아래의 유한한 집합이며, 오래 살아 있는 service와 새 service가 같은 경로에 서로 다른 lock을 받지 않도록 lock identity를 보존하는 것이 메모리 회수보다 우선한다.

실행 중인 CLI 작업을 취소할 때는 SharedJob을 먼저 `cancel_requested`로 기록한 뒤 등록된 child process를 종료한다. 이미 terminal이거나 `committing`인 작업은 취소와 process 종료를 모두 거부하며, 종료 경계에서 child가 먼저 끝나도 승인된 취소는 유지한다.

## 0.6 실행 진단 경계 (L1b–D3)

앱 API에서 제출된 Agent SharedJob은 기존 job/private lifecycle의 권위를 바꾸지 않은 채 안전한 실행 관측만 남길 수 있다. 관측은 private cleanup과 job terminal 저장이 성공한 뒤에만 terminal로 닫히며, Work Log의 26개 필드·prompt/reply/diff 보존 규칙은 바뀌지 않는다. Agent CLI의 stdout·stderr·context pack·본문은 diagnostics에 복사하지 않는다.

`GET /api/diagnostics/jobs/{jobId}`(및 job이 없는 자동화 경로용 `GET /api/diagnostics/runs/{runId}`)는 여전히 headless 상세 API이며 Work Log의 26개 필드 응답 자체를 바꾸지 않는다. 대신 각 Work Log 항목(`web/src/app/AgentWorkLog.tsx`)과 설정의 자동화 실행 내역(`web/src/app/SettingsRoute.tsx::LastRun`)이 공유 컴포넌트 `web/src/app/DiagnosticDetail.tsx`로 이 API를 펼쳐서 조회한다 — jobId가 있으면 그쪽을, 없으면 자동화 row의 `diagnosticRunId`를 쓴다. 실패 단계·확인된 원인·마지막으로 완료된 단계·경과 시간·다음 행동과, 접어 둔 개발자 정보(실행 ID·오류 ID·지문·소스 위치)만 보여주며 `기록 없음/보존 만료/기록 일부 누락/조회 실패/실행 중/규칙 기반으로 완료` 여섯 상태를 구분한다(`web/src/app/diagnosticCopy.ts`). L1c는 실제 CLI/process·chat·durable JSON/SQL producer의 safe stage/terminal 관측을 더했지만 provider protocol/parser 소비자 변경은 하지 않았다. record 품질은 누락·legacy·외부 변경을 숨기지 않기 위해 계속 partial일 수 있다(RSS·색인만 감사된 경로에서 complete). **공통 목록**은 기존 Work Log 안의 `실패·대체 실행 찾기`를 펼쳐서 `실패만`·`대체 실행만`·기간·`모든 실행 보기`로 전환한다. 목록/진단/숨기기 미리보기·확인·제안 조회 오류는 각각 해당 메시지 옆의 제한된 진단 상세로 연결하며, 응답이 없는 숨기기 확인은 결과 미확정으로만 안내하고 자동 재시도하지 않는다. `GET /api/diagnostics/runs` headless API는 구현되어 있으며 서버가 숨긴/현재 권위에서 사라진 job을 제외하고 기존 Work Log ID를 연결한다. 기존 26필드·clear/migration 계약과 진단 자체 내보내기(D4) 경계는 불변이다.

## 구현 위치

```text
features/agent_mode/schema.py   # context pack schema, secret scrubber, generation metadata
features/agent_mode/service.py  # prepare/writeback handlers
features/agent_mode/cli.py      # Phase 1 chat command entrypoint
features/agent_mode/bridge.py   # Phase 2 Direct Agent Bridge adapters/subprocess
features/agent_mode/collection_context.py # bounded Collection change-summary context
features/agent_mode/setup.py    # CLI 설치/로그인/제공자·모델 설정
features/agent_mode/generation_mode.py # rules/llm_api/llm_cli normalization
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
