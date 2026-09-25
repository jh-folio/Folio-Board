# 기능 카탈로그

> 기능 범위·화면 구성을 확인할 때만 읽는다. 공통 규칙은 [AGENTS.md](../../AGENTS.md), 기능 README는 [features 인덱스](../../features/README.md)를 따른다.

## 8. 기능 카탈로그

### 구현됨 (runtime/API 또는 내부 기능)

| 기능 | 폴더 | 한 줄 | 계층 |
|---|---|---|---|
| 자료 라이브러리 | `common/research_library` | inbox 폴더 계약·RSS 수집·증분 인덱스·하이브리드 검색 토대 | — |
| 공통 Research Schema / Market Tape Lite | `common/research_schema`, `common/market_data/tape.py` | checkpoint/evidence/sourceLedger/dataGap/marketTape 공통 구조 | — |
| 일일 브리핑 | `daily_briefing` | 미/한 시장 일일 브리핑 | Canonical |
| 기업 분석 | `company_analysis` | SEC 숫자+10-K 기반 분석 | Canonical |
| 테마분석 (Topic Report v2) | `topic_report` | 투자 질문 해결기: Planner→Evidence Pack→유형별 템플릿→Quality Gate→Personal Overlay | Canonical + Personal Overlay |
| Smart Collections | `smart_collections` | Deep Research 안의 결정적 저장 필터·상태·snapshot 변화/recovery | metadata |
| 포트폴리오 | `portfolio` | 보유 종목 직접 입력·revision 저장, 평가 요약·구성 분석·투자 리뷰·목표 프리셋·백테스트. 화면은 `보유·평가 | 투자 리뷰 | 프리셋 | 백테스트` 4탭이며 기본은 보유·평가다 | — |
| 시장 내러티브 메모리 / Regime 추적 v2 | `market_memory` | 중기 내러티브 상태·taxonomy·momentum/confidence·thesis 연결 | source-grounded |
| 워치리스트 | `watchlist_notes` | 워치리스트·상세(기업 정보/네이티브 차트/실적/수집 뉴스)와 종목별 Thesis 생성·수정·최신 근거 검토·반대 근거·다음 확인·이력 | metadata + hypothesis |
| Native Investment Notes | `investment_notes` | Obsidian 없이 운용되는 Folio 로컬 투자 노트와 `native_note_index` | hypothesis 입력 |
| 자동화 | `automation` | RSS 수집·시장 메모리 갱신·브리핑 예약 스케줄러와 실행 기록(`data/automation-settings.json`, `data/automation-runs.json`). 서버가 켜져 있을 때만 돈다 | — |
| LLM/설정/웹검색 | `llm_settings` | CLI 설정·웹검색 보완 | — |
| Notion 내보내기 | `notion_export` | 보고서 → Notion DB | — |
| Obsidian 연동 | `obsidian` | 보고서/내러티브 → Vault, 사용자 노트 회수, thesis/memo/review 템플릿·검사 | hypothesis 입력 |
| Personal Overlay | `personal_overlay` | Canonical을 사용자 노트와 대조한 개인 해석 (브리핑/기업분석) | Personal Overlay |
| Thesis Tracking | `thesis_tracking` | 종목 Thesis/Delta 권위 저장소와 6값 판정(`strengthened|maintained|weakened|at_risk|broken|insufficient_evidence`)·검증 이력 | Personal Overlay |
| Research Quality | `common/research_quality` | 산출물 공통 품질 평가: sourceGrounding·risk·coverage | source-grounded |
| Quality Generation | `common/quality_generation` | 생성 품질 목표·자료 루트·preflight·evidence coverage·생성 후 평가·약한 섹션 LLM 개선·telemetry | source-grounded |
| Execution Diagnostics | `common/diagnostics` | 실행별 privacy-safe 단계·오류·엔진·권위 관측과 bounded JSON 저장, Work Log/자동화 상세 및 보고서 생성 오류 연결. 공통 목록·기간/실패/대체 필터의 headless API는 구현되어 있으며 목록 UI·나머지 행동 연결은 후속이다. SharedJob/commit/자동화 권위 불변 | 관측 metadata |
| AI Agent Mode | `agent_mode` | Codex/Claude/Antigravity CLI용 context pack·Direct Bridge·기존 저장소 writeback + 도크 Agent 대화 스레드(`/api/agent/threads`)·수정 제안 diff 승인 writeback(`/api/agent/proposals/{id}`) | source-grounded + Personal Overlay |
| 투자 리뷰 | `investment_review` | Portfolio `투자 리뷰` 하위 탭이 읽는 날짜별 v2 점검: 입력 기준·변화·우선 포지션·공동 위험·자료·이력 | Personal Overlay |
| 현재 시장 위젯 | `market_widgets` | 예전 TradingView Current Market 위젯 설정. 0.5에서 Legacy 모드를, 0.5.4에서 마지막 소비자였던 워치리스트 상세 위젯과 브리지(`public/tradingview-widgets.js`)를 삭제했다. 설정 파일은 집중 종목 fallback으로만 read-only로 읽는다 | — |
| Data Source Reliability | `common/data_reliability` | 공식자료 우선순위·provider status·한국 데이터 보강 경로·Thesis evidence 확장·공식자료 semantic cache/fetch runtime | source-grounded |
| Fast-Origin Signals | `common/research_library/signals` | 기존 KR RSS(연합인포맥스·연합뉴스)의 빠른 게시 headline을 metadata-only lead로 수집·표시. 자격증명 없이 기본 동작하며 lead는 evidence count/source ledger 제외 | lead (evidence 이전 단계) |
| Change Intelligence | `common/change_intelligence` | 보고서/스냅샷 커밋 시 artifact-native ChangeBasis 비교로 changeSummary 생성. 추가 LLM 호출 없음 | source-grounded 파생 metadata |
| 시장 캘린더 | `market_calendar` | 경제지표·중앙은행·휴장일·실적·공시·배당 6종 일정 수집·정규화와 confirmed/estimated badge | — |
| Research Cockpit 대시보드 | `dashboard` | 변화 피드·시장 캘린더·네이티브 차트. 0.5에서 Legacy 모드 삭제 | — |
| Pixel Office (보류) | `pixel_office` | 리서치 상태를 하나의 픽셀 오피스 장면으로 보여준다. 0.3.0에서는 배선을 전부 끊고 릴리즈 패키지에서도 제외한다. 소스(백엔드 service·PixiJS 씬·13개 오브젝트 레이어)는 재개용으로 저장소에만 남는다. | 보류 |
| 첫 실행 안내 | `onboarding` | 첫 실행 판정과 5단계 안내 위저드(환영·화면·AI·관심 시장·시작) + 완료 단계의 선택 튜토리얼. 어느 단계에서든 건너뛸 수 있다 | — |
| 프론트엔드 UI | `frontend_ui` | React SPA(`web/`)가 기본 프론트엔드. `public/app.js`는 bridge-only, `public/index.html`은 최소 entrypoint | — |

현재 기본 사용자 화면과 개인 판단 표면:

- **보이는 핵심 화면**: Home/AI Agent, Dashboard(Research Cockpit), Watchlist, Portfolio, Briefing, RSS Feed, Market Memory, Company Analysis, Deep Research, Settings.
- **보이는 보조 기능**: Deep Research의 question-first 계획 승인, Smart Collection 상세/상태/변화, Market State, Agent Work Log, 보고서 reader의 Folio Note·규칙 기반 note/thesis 검토, 기존 리서치 화면의 읽기 전용 Investment Context, Obsidian/Notion 내보내기, Agent Dock/Ask Agent/제안 승인 흐름, Dashboard의 Change Feed·시장 캘린더, Watchlist 상세의 Thesis 생성·수정·`최신 근거로 검토`·반대 근거·다음 확인·이력, Portfolio의 날짜별 `투자 리뷰`, Watchlist/Portfolio `짚어보기` 대화와 `노트로 정리`.
- **CLI 선택은 범위가 둘이다.** 전역 기본은 상단바 `Agent CLI` 메뉴와 설정 탭이 소유하며 예약 브리핑·기업분석 등 도크 밖 작업이 쓴다. 도크의 `이 대화의 CLI`는 요청의 `options.adapter`로만 전달되어 그 대화에만 적용되고 전역을 저장하지 않는다 — 전역과 다르면 도크가 그 사실을 밝히고, 새 대화는 다시 전역 기본에서 시작한다.
- **Agent 실행 경계**: 설정에서 Agent CLI를 연결한 순간부터, 사용자는 그 프로젝트의 일반 산출물 생성에 Agent 사용을 허락한 것으로 본다. 개인 판단 표면의 반박은 예외적으로 **명시 클릭**에서만 실행한다: 내러티브 `{kind: market_memory, id: stateId, intent: challenge}`와 Thesis `{kind: watchlist, id: ticker, tickers: [ticker], intent: challenge}`는 매 turn 정확한 권위 객체와 최근 90일 근거를 다시 읽는다. 투자 리뷰 `{kind: investment_review, id: date, revision: reviewRevision, intent: challenge}`는 정확한 `date + reviewRevision`의 저장된 구조화 리뷰만 다시 읽으며, 일반 Portfolio 맥락이나 새 근거 조회로 넓히지 않는다. ID/revision이 stale이면 모두 넓은 맥락으로 폴백하지 않고 data gap을 돌려준다. 화면 로드·판정 pass는 Agent를 부르지 않으며, 대화는 `reuseAsEvidence=false` hypothesis다. 답변은 Thesis verdict·checkpoint·review state를 자동 변경하지 않고, 구조화 저장은 preview와 명시적 확인 뒤에만 가능하다. freshness/health/context 배지와 `changeSummary`는 계속 규칙으로 자동 계산한다(Agent를 쓰지 않는다).
- 엔진을 부르는 화면은 **얼마나 걸리는지 미리 말하고**, 실패하면 규칙 결과로 내려간 사실을 숨기지 않는다. Agent CLI는 한 번에 수십 초가 걸린다.
- **테마/접근성**: 전체 공개 화면은 Light/Dark/System 테마를 지원하고, 기존 사용자 기본값은 Light, 신규 사용자 기본값은 System이다. 키보드 탐색, 명확한 focus, WCAG 2.2 AA 대비를 공개 화면 계약으로 둔다.
- **개인 판단 주 표면**: Watchlist 상세의 Thesis와 Portfolio의 `투자 리뷰`는 개인 판단을 읽고 점검하는 주 표면이다. 별도 최상위 Investment Review 화면이나 두 번째 Portfolio 화면은 만들지 않으며, Canonical 보고서·외부 근거·일반 대화와의 계층 분리는 유지한다.
- **문서 원칙**: 사용자용 README는 현재 릴리즈에서 실제로 보이는 기능만 현재 기능으로 설명한다. 숨김/축소 기능은 개발자 문서나 후속 로드맵에서 다룬다.
