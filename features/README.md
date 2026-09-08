# Features

`features/`는 Folio Board의 기능 설명서, 프롬프트, Python 런타임 코드를 모아둔 곳입니다.
폴더 구조는 가능한 한 웹 화면의 탭 흐름을 따르고, 여러 탭이 함께 쓰는 기반 기능은 `features/common/` 아래에 둡니다.

## 폴더 구조

| 폴더 | 화면/역할 | 설명 |
| --- | --- | --- |
| `daily_briefing/` | 브리핑 탭 | 미국장·한국장 범위별 브리핑, 이슈·출처 다양성, 생성 당시 가격 series·히트맵 사이드카, 생성 당시/현재 REST snapshot 전환, Lightweight Charts·Plotly 렌더링과 PNG 내보내기, 저장·품질 모드 |
| `company_analysis/` | 기업 분석 탭 | SEC/DART 숫자, 공시 문단, 로컬 자료를 결합한 기업분석 |
| `topic_report/` | 딥 리서치 탭 | 질문-first 계획 승인, Smart Collection 재사용, 근거 추적 보고서(내부 Topic Report v2 호환) |
| `smart_collections/` | 딥 리서치 내부 워크스페이스 | 결정적 저장 필터, 상태/reason, 제한된 snapshot 변화와 recovery |
| `portfolio/` | 포트폴리오 탭 | `보유·평가 | 투자 리뷰 | 프리셋 | 백테스트` 4탭: 보유 포지션, 날짜별 투자 리뷰, 목표 프리셋, 리서치용 백테스트 |
| `dashboard/` | 대시보드 탭 | Change Feed·이야기 비중·시장 일정·네이티브 차트로 구성한 Research Cockpit. Legacy 모드는 0.5에서 삭제 |
| `market_memory/` | 시장 내러티브 탭 | 중기 내러티브, regime 추세, story family 관리 |
| `market_calendar/` | 대시보드 내부 | 경제지표·중앙은행·휴장·실적·공시·배당 일정과 certainty badge |
| `watchlist_notes/` | 워치리스트 탭 | 관심 종목/키워드, 상세의 기업 정보·차트·수집 뉴스와 Thesis 생성·수정·최신 근거 검토 |
| `investment_notes/` | Native Investment Notes | Obsidian 없이 운용되는 Folio 로컬 투자 노트(hypothesis) 저장·인덱스 |
| `investment_review/` | Portfolio `투자 리뷰` 하위 탭 | 날짜별 v2 저장 리뷰의 입력 기준·변화·우선 포지션·공동 위험·자료·이력 |
| `automation/` | 설정 탭 | RSS 수집·시장 메모리 갱신·브리핑 예약 스케줄러와 실행 기록 |
| `market_widgets/` | 설정 read-only | 예전 TradingView 위젯 설정. 0.5.4에서 마지막 소비자와 브리지를 삭제했고 집중 종목 fallback으로만 읽는다 |
| `llm_settings/` | 설정 탭 | LLM provider, API Key 저장, 웹 검색 보완 설정 |
| `obsidian/` | 설정/보고서 공통 | Obsidian 내보내기, 사용자 노트 회수, 템플릿 생성, frontmatter 검사 |
| `notion_export/` | 보고서 공통 | 브리핑/기업분석/테마분석 Notion DB 내보내기 |
| `personal_overlay/` | 보고서 공통 | Canonical 보고서를 사용자 hypothesis 노트와 대조한 개인 해석 레이어 |
| `thesis_tracking/` | Watchlist 상세/기업 공통 | 기업 Thesis 등록·수정, 최신 근거 대비 6값 Delta, 반대 근거·다음 확인·이력 |
| `agent_mode/` | 보고서 생성 공통 | Codex/Claude Code 같은 외부 AI 에이전트용 context pack 생성과 writeback |
| `onboarding/` | 첫 실행 안내 | 첫 실행 판정(사용자 자료 유무), 5단계 위저드와 완료 단계의 선택 둘러보기, 완료·건너뛰기 기록 |
| `frontend_ui/` | 웹 UI | 탭 구조, 렌더링, 모바일 대응, Markdown/Plotly 주의점. 디자인 언어·토큰·프리미티브는 [frontend_ui/DESIGN_SYSTEM.md](frontend_ui/DESIGN_SYSTEM.md) |
| `pixel_office/` | 보류 | 리서치 상태를 픽셀 오피스 장면으로 보여주는 기반. 0.3.0에서 배선을 끊고 릴리즈 패키지에서 제외했으며 소스만 재개용으로 남는다 |
| `common/` | 공통 기반 | 자료 레이어, 품질/근거성, 시장 데이터, 공통 스키마, 유틸 |

## 공통 기반 폴더

| 폴더 | 설명 |
| --- | --- |
| `common/research_library/` | `research-inbox` 폴더 계약, RSS 수집, 증분 인덱싱, 하이브리드 검색 |
| `common/research_library/signals/` | fast-origin metadata-only lead, provider health, TTL/cursor query |
| `common/change_intelligence/` | artifact-native 구조화 비교, JSON/snapshot authority, 재구축 가능한 변화 projection |
| `common/research_schema/` | checkpoint, evidence, sourceLedger, dataGap 공통 스키마 |
| `common/market_data/` | 시장 스냅샷, 한국장 provider, Market Tape Lite |
| `common/research_quality/` | 저장 보고서/Delta/regime의 규칙 기반 품질 평가 |
| `common/quality_generation/` | 생성 전 품질 목표, preflight, 약한 섹션 1회 보강, telemetry |
| `common/data_reliability/` | 공식자료 우선순위, provider 상태, 한국 수동 데이터 보강 경로 |
| `common/diagnostics/` | 실행별 bounded privacy-safe diagnostics, Work Log/자동화 상세·보고서 생성 오류 연결, 공통 목록 API와 Work Log의 전체/실패/대체/기간 조회; 선택 진단 내보내기·보존 관리 구현 및 로컬 수용 |
| `common/instruments/` | 종목·지수 식별자 레지스트리와 스키마 |
| `common/text/` | 보고서 산문 공통 도구(토큰화 등) |
| `common/*.py` | 텍스트/JSON 유틸, 회사명 조회, taxonomy, Polars 계산, 시장 캘린더 |

## 문서 읽는 순서

처음 사용하는 사람은 최상위 [README.md](../README.md)를 먼저 읽고, 필요한 화면별 문서를 이어서 보면 됩니다.

1. 자료를 넣고 검색하려면 [common/research_library](common/research_library/README.md)
2. 매일 브리핑을 만들려면 [daily_briefing](daily_briefing/README.md)
3. 기업을 분석하려면 [company_analysis](company_analysis/README.md)
4. 딥 리서치/투자 질문을 분석하려면 [topic_report](topic_report/README.md)
5. 내 Obsidian 노트와 연결하려면 [obsidian](obsidian/README.md), [personal_overlay](personal_overlay/README.md), [thesis_tracking](thesis_tracking/README.md)
6. 품질/근거성 구조를 이해하려면 [common/research_schema](common/research_schema/README.md), [common/research_quality](common/research_quality/README.md), [common/quality_generation](common/quality_generation/README.md)

## 작업 규칙

- 새 기능은 가능한 한 기존 탭 폴더 안에 넣습니다.
- 여러 탭에서 공유하는 런타임 코드는 `features/common/` 아래에 둡니다.
- 새 프롬프트는 전역 `prompts/`가 아니라 해당 기능 폴더 아래에 둡니다.
- README는 처음 쓰는 사용자가 이해할 수 있게 목적, 화면에서 하는 일, 입력 자료, 저장 위치, 주의점, 관련 API를 함께 설명합니다.
- 사용자 데이터가 들어가는 `data/`, `research-inbox/`, `config/`는 기능 문서에서 경로를 명확히 적되, 임의 삭제나 초기화를 안내하지 않습니다.
- Python import 경로와 문서 경로는 underscore 이름을 기준으로 합니다. 하이픈 이름의 중복 폴더를 만들지 않습니다.

기본 사용자 화면은 Home/AI Agent, 대시보드, 워치리스트, 포트폴리오, 브리핑, RSS 피드, 시장 내러티브, 기업 분석, 딥 리서치, 설정입니다. 전체 공개 화면은 Light/Dark/System 테마와 반응형 탐색을 지원합니다. fast-origin lead는 근거가 아니며, 보고서 변화·개인 투자 맥락·대화는 각각 분리된 계층으로 유지합니다.
