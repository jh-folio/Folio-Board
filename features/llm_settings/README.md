# LLM/설정/Web Search

이 기능은 AI Agent 생성 정책, LLM CLI/API Provider, 모델, 인증 및 웹 검색 보완 설정을 관리합니다.

## 담당 범위

- Codex CLI, Claude Code CLI, Antigravity CLI(`agy`, Gemini) 설치·로그인·Provider·Model 선택
- Antigravity는 `agy -p`로 Gemini 모델 비대화형 실행을 지원해 브리핑·보고서 생성 Direct Bridge에 연결
- OpenAI/GPT, Gemini, Claude API Provider 선택
- Provider별 API Key/Model 저장
- Provider별 공식 API Key 발급 페이지 연결
- 저장된 API Key와 선택 모델의 read-only 연결 확인
- AI Agent 생성 정책: ON/OFF와 LLM CLI / LLM API 실행 방식 선택
- 브리핑 웹 검색 보완 ON/OFF
- 기업분석 웹 검색 보완 ON/OFF
- Notion 연동 토큰(NOTION_TOKEN)과 데이터베이스 ID(NOTION_DB_ID) 저장

## 설정 위치

웹 UI:

```text
설정 탭
```

`AI Agent 설정`은 ON/OFF와 실행 방식 토글을 한 화면에서 관리합니다. CLI 모드는 구독 계정으로 인증된 로컬 Codex/Claude/Antigravity CLI를 사용하고 API Key를 요구하지 않습니다. API 모드는 기존 Provider API Key 경로를 사용합니다.

LLM API 연결 확인은 생성 요청을 보내지 않고 Provider의 모델 조회 endpoint를 사용합니다. 키가 없거나, 인증이 실패하거나, 선택 모델에 접근할 수 없거나, 사용량 제한에 도달한 상태를 구분해 표시합니다.

브리핑·기업분석·테마분석·시장 내러티브·투자 리뷰 화면은 더 이상 생성 방식 드롭다운을 노출하지 않습니다. 생성 시점에는 전역 `AI_AGENT_ENABLED`가 최상위 실행 허용 스위치로 적용되고, 설정에서 켠 작업만 별도 CLI/API·Provider·Model·추론 강도를 사용합니다. 작업별 토글이 꺼져 있으면 현재 전역 설정을 따르고, Agent가 꺼져 있으면 모든 작업이 규칙 기반으로 동작합니다.

설정 화면의 `AI Agent 모델 설정`은 상단의 전역 모델 설정과 브리핑·기업분석·딥 리서치·시장 내러티브 네 작업별 설정을 한 패널에서 편집합니다. 작업별 설정은 `data/ai-agent-task-settings.json`에 비밀 없는 설정을 저장합니다. 나머지 내부 작업 키도 저장소와 런타임에는 남아 있지만 화면에서 별도 설정을 켤 수 없고 저장 시 비활성으로 직렬화됩니다. 파일이 없는 기존 설치는 revision 0의 모든 작업 OFF로 읽으며 파일을 자동 생성하지 않습니다. ON으로 저장한 행은 실행 방식·Provider·Model·추론 강도를 모두 가지며, OFF로 바꾸어도 이전 별도 설정을 보관합니다. 전역 모델과 작업별 설정은 각각 저장·취소하며, 저장은 revision 충돌 확인과 원자적 교체를 사용합니다. 수동 실행과 예약 실행은 같은 task resolver를 거치고, 실행이 접수된 뒤에는 해당 job의 설정 snapshot을 사용합니다.

추론 강도에서 `제공자 기본값`은 전역 추론값을 이어받는 의미가 아니라 선택한 Provider/Model의 기본 동작을 뜻합니다. API에서 명시 강도는 OpenAI API의 `gpt-6-astra`에서만 허용하며 Gemini·Claude API와 다른 OpenAI 모델은 제공자 기본값만 저장할 수 있습니다. CLI는 Codex의 모델별 지원 목록을 `Light`부터 `Max`/`Ultra`까지, Claude Code는 모델별 지원 목록을 `Low`부터 `Max`까지, Antigravity는 `Low`부터 `High`까지 표시하고 해당 transport 값만 실행 프로세스에 전달합니다. 예를 들어 Claude Sonnet/Opus 4.6은 `Low|Medium|High|Max`를 지원하며 `Extra High`를 표시하지 않습니다. `auto` Provider를 확정할 수 없거나 저장 파일이 손상된 경우 다른 모델로 조용히 대체하지 않고 설정 오류를 표시합니다.

파일:

```text
OS 자격 증명 저장소  # API Key와 토큰
.env                 # 모델·Provider 등 비밀이 아닌 설정
.env.example
```

설정 화면에서 저장한 API Key와 토큰은 운영체제 자격 증명 저장소에 보관합니다. 이전 버전의 `.env`에 남아 있는 비밀값은 자격 증명 저장소 기록이 성공한 뒤 자동으로 파일에서 제거되며, 이전이 실패하면 기존 값을 보존합니다.

## 주요 환경 변수

```text
LLM_PROVIDER=openai
AI_AGENT_ENABLED=1
AI_AGENT_MODE=cli
USE_LLM_BRIEFING=1
USE_LLM_ANALYSIS=1
USE_WEB_SEARCH_FOR_BRIEFING=1
USE_WEB_SEARCH_FOR_ANALYSIS=1

OPENAI_MODEL=gpt-5.6-sol
OPENAI_API_KEY=...

GEMINI_MODEL=gemini-3.5-flash
GEMINI_API_KEY=...

ANTHROPIC_MODEL=claude-sonnet-5
ANTHROPIC_API_KEY=...

NOTION_TOKEN=secret_xxx
NOTION_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

AGENT_CLI_PROVIDER=codex
FOLIO_AGENT_CODEX_MODEL=gpt-5.6-sol
FOLIO_AGENT_CLAUDE_MODEL=claude-sonnet-5
```

설정 화면의 모델 목록은 고정 목록이 아니라 `features/llm_settings/model_catalog.py`가 만든 동적 catalog를 사용한다. 기본 로딩은 `data/llm-model-cache.json`에 저장된 마지막 모델 목록을 계속 재사용하며, 오래된 캐시라도 자동으로 다시 조회하지 않는다. 사용자가 설정 화면에서 모델/상태 새로고침을 눌러 `refresh=true` 요청을 보낼 때만 API Provider의 read-only model list endpoint 또는 CLI의 `models`/`model list` 계열 명령을 실행해 캐시를 갱신한다. 수동 새로고침이 실패하면 마지막 캐시를 유지하고, 저장된 캐시가 없거나 키 없음·CLI 미지원이면 아래 fallback 목록을 즉시 사용한다.

fallback 모델 목록:

```text
Codex CLI: GPT-6 Astra, GPT-5.6 Sol, GPT-5.6 Terra, GPT-5.6 Luna, GPT-5.5, GPT-5.4-mini
OpenAI API: GPT-6 Astra, GPT-5.6 Sol, GPT-5.6 Terra, GPT-5.6 Luna, GPT-5.5, GPT-5.4, GPT-5.4-mini
Claude: Claude Fable 5, Claude Sonnet 5, Claude Opus 5, Claude Haiku 4.5, Claude Opus 4.8, Claude Sonnet 4.6
Gemini: Gemini 3.6 Flash, Gemini 3.5 Flash, Gemini 3.5 Flash-Lite, Gemini 3.1 Pro Preview
```

## GPT-6 Astra 사용과 Folio OS 설정

2026-09-05 확인한 [공식 모델 가이드](https://developers.openai.com/api/docs/guides/latest-model)와
[모델 사양](https://developers.openai.com/api/docs/models/gpt-6-astra)에 따라 `gpt-6-astra`를 선택할 수 있다.
API 접근은 순차 제공 중이므로 기본값 `gpt-5.6-sol`과 저장된 사용자 모델은 유지한다.
설정에서 OpenAI 모델을 선택하고 연결 확인을 실행한다. 모델 목록에 있다는 사실은 계정 접근 권한의 증명이 아니다.
연결 확인도 모델 조회만 수행하므로 실제 생성 품질·속도까지 검증하지는 않는다.

- API 생성은 기존 Responses API를 사용한다. Astra는 도구 호출에 Responses가 필요하며 `temperature`, `top_p`, `top_logprobs`를 보내지 않는다.
- `OPENAI_ASTRA_REASONING_EFFORT`는 Astra에만 적용하며 기본은 `low`다. `medium`, `high`, `xhigh`, `max`도 허용한다. 이전 설정의 `none`/`minimal`은 `low`로 보정하고 오타는 요청 전에 거부한다.
- 내부 호출자는 `cfg["reasoningEffort"]`로 환경 변수보다 우선하는 강도를 지정할 수 있다. 다른 모델의 기존 요청 파라미터는 유지한다.
- 추론 강도 권장 시작점은 정해진 자료를 요약하는 브리핑에 `low`, 상충 근거를 비교하는 기업분석에 `medium`이다. 이는 아직 실측 전인 운영 권고이며 기능별 자동 라우팅은 구현하지 않았다.
- 출력 토큰 상한과 timeout은 기존 기능별 값을 유지한다. 모든 OpenAI API 응답에서 미완료·실패·거절·빈 본문을 예외로 돌려 기존 생산자의 실패/규칙 대체 정책으로 처리한다. 잘린 본문을 정상 보고서로 반환하거나 자동으로 토큰 예산을 늘리지 않는다.
- 요청의 기존 instructions, JSON 형식, 웹 검색 ON/OFF를 유지한다. 최신 모델을 선택해도 근거 검증과 Canonical/Personal Overlay 분리는 그대로 적용된다.
- 작업별 CLI 설정은 선택한 모델과 지원되는 추론 강도를 해당 실행 한 번에만 전달한다. Codex는 `model_reasoning_effort` 설정 override를, Claude Code와 Antigravity는 `--effort`를 사용하며 사용자 CLI 전역 설정은 바꾸지 않는다. `제공자 기본값`은 별도 인자를 보내지 않는다.

API 모드에서 Astra를 선택한 경우의 선택적 로컬 설정:

```dotenv
OPENAI_MODEL=gpt-6-astra
OPENAI_ASTRA_REASONING_EFFORT=low
```

실제 비교는 동일한 저장 입력과 출력 상한에서 기존 모델과 비교한다. 근거 일치, 반대 근거, JSON/enum 검증,
완료율, 지연, 사용 토큰을 함께 보고 모델·추론 강도를 결정한다. 고강도 추론이나 큰 컨텍스트만으로 보고서 품질이 보장되지는 않는다.
이번 변경의 검증은 모의 HTTP 경계를 사용한 회귀 테스트이며 유료 생성이나 기존 보고서 재생성은 수행하지 않았다.

## 관련 코드

- `features/llm_settings/settings_service.py`: `public_settings()`, `save_settings()` (Notion 설정 포함)
- `features/llm_settings/provider_status.py`: 공식 Key 발급 URL과 Provider 연결 확인
- `features/llm_settings/model_catalog.py`: API/CLI 모델 목록 수동 조회, fallback 병합, 캐시 우선 로딩
- `features/llm_settings/task_policy.py`: 작업별 설정 schema, revision-safe 저장, runtime task alias와 실행 resolver
- `features/agent_mode/setup.py`: CLI 설치, 로그인 실행, Provider/Model 설정
- `features/agent_mode/bridge.py`: CLI 인증 상태 확인과 최종 생성 실행
- `app.py`: `selected_llm_config()`
- `features/llm_settings/client.py`: `request_openai()`, `request_gemini()`, `request_claude()` 공통 API 호출
- `public/app.js`: `renderSettings()`, 설정 저장 이벤트

## 보안 규칙

- 실제 API Key를 문서, 로그, 최종 답변에 출력하지 마세요.
- `.env`는 gitignore 대상이지만 API Key와 토큰의 영구 저장소로 사용하지 않습니다.
- 설정 API는 키 전체가 아니라 masking된 값만 프론트에 내려야 합니다.
