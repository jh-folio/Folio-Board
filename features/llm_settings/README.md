# AI Agent와 연동 설정

Folio Board의 AI 실행은 Codex, Claude Code, Antigravity CLI를 사용합니다. CLI 인증과 사용 요금은 해당 CLI 제공자의 정책을 따릅니다.

## 설정과 전환

- `AI Agent 연동`에서 AI를 켜고 CLI 설치·로그인 상태를 확인합니다. AI를 끄면 기존 규칙 생성·계산·조회 기능을 사용합니다. AI가 필수인 스냅샷 등은 생성할 수 없다고 안내합니다.
- `AI Agent 모델 설정`에서 전역 CLI·모델·추론 강도를 정합니다. 브리핑·기업분석·딥 리서치·시장 내러티브는 별도 설정을 켤 수 있습니다. 작업별 설정이 꺼져 있으면 전역 설정을 따릅니다.
- 이전 `api` 전역/작업별 설정은 조회만으로 수정하지 않습니다. 화면에서 CLI로 전환해 저장하거나 AI를 꺼야 합니다. 지원 종료된 설정의 새 저장·실행·재개는 `llm_api_removed`로 거부합니다. 비활성 작업의 예전 설정은 보관하지만 다시 켜기 전에 CLI로 바꿔야 합니다.
- 이전 LLM 키는 `.env`와 OS 자격 증명 저장소에서 자동 삭제·이전·조회하지 않습니다. 과거 보고서·작업·로그의 provider/usage는 읽기 호환을 유지합니다.
- 이전 API 설정을 명시적으로 저장·전환할 때 원본 복구 사본을 남깁니다. 전역은 `.env.llm-api-transition.bak`, 작업별 설정은 원본 옆의 `.llm-api-transition.bak` 파일입니다. 기존 복구 사본은 덮어쓰지 않으며 전역 사본도 비밀이 포함될 수 있는 개인 파일로 취급합니다.

작업별 설정은 `data/ai-agent-task-settings.json`에 비밀 없는 값으로 저장합니다. revision 충돌 검사와 원자적 교체를 사용하며, 파일이 없는 설치에서는 조회만으로 파일을 만들지 않습니다. 전역 설정과 작업별 설정은 각각 저장합니다. 실행을 접수한 뒤에는 고정된 작업 snapshot의 provider/model/effort를 본문과 보조 호출에 전달합니다. Agent 대화별 CLI 선택은 보고서 전역 설정과 별개입니다.

`제공자 기본값`은 선택한 모델의 기본 동작이며 별도 추론 override를 전송하지 않습니다. 모델별 지원값은 `reasoning.py`와 CLI catalog에서 관리합니다. 지원하지 않는 조합은 저장 전에 거부합니다.

## 모델 목록과 외부 데이터

모델 목록은 `data/llm-model-cache.json`의 CLI 항목을 우선 사용합니다. 명시적으로 새로고침할 때만 CLI 모델 목록 명령을 실행합니다. 실패하면 기존 CLI 캐시 또는 내장 목록을 사용하며 API 목록 endpoint를 호출하지 않습니다.

SEC/DART/FRED/BOK/Toss/Notion 등 데이터·내보내기 API와 내부 FastAPI endpoint는 유지합니다. 해당 키·토큰은 기존 OS 자격 증명 저장소를 사용합니다. 이 데이터 연동의 `.env` 비밀값 이전 규칙은 그대로이며 LLM 키는 대상에서 제외합니다. 실제 비밀값을 로그·문서에 출력하지 않습니다.

## 주요 환경 변수

```dotenv
AI_AGENT_ENABLED=1
AI_AGENT_MODE=cli
AGENT_CLI_PROVIDER=codex
AI_AGENT_REASONING_EFFORT=provider_default
FOLIO_AGENT_CODEX_MODEL=gpt-6-sol
FOLIO_AGENT_CLAUDE_MODEL=claude-sonnet-5
USE_WEB_SEARCH_FOR_BRIEFING=1
USE_WEB_SEARCH_FOR_ANALYSIS=1
```

웹 검색 허가는 생성 ON/OFF와 독립입니다. 요청됨·지원됨·실제 사용됨을 구분하며, CLI 장애는 해당 작업의 실패/fallback 계약으로 처리합니다. CLI 출력의 정확한 토큰 사용량과 토큰 상한 적용 여부를 추정치와 혼동하지 않습니다.

## 구현 경계

- `client.py`: CLI 공통 요청, 고정 작업 설정, 환경·데이터 API 키·JSON 유틸.
- `task_policy.py`, `task_runtime.py`, `task_policy_check.py`: 작업별 저장·실행 snapshot·CLI 연결 확인.
- `settings_service.py`: 공개 설정·전환 오류·데이터 연동 저장.
- `model_catalog.py`, `reasoning.py`: CLI 목록과 지원 추론 강도.
- `../agent_mode/setup.py`, `../agent_mode/bridge.py`: CLI 설치·인증·실행. 같은 스레드의 보조 호출을 허용하는 직렬화 잠금을 사용합니다.
- `../../web/src/app/SettingsRoute.tsx`, `WelcomeWizard.tsx`: CLI 설정 및 AI 없이 사용 안내.

과거 `/api/settings/llm/test/{provider}`는 HTTP 410을 반환합니다. 지원 종료된 실행 설정은 HTTP 409로 거부합니다.
