# Folio OS Agent Instructions

> **Folio OS** — A Local Investment Research Workspace for Individual Investors
>
> 이 문서는 Folio OS를 맡는 AI/LLM 에이전트가 **가장 먼저, 끝까지** 읽어야 하는 최상위 작업 지침이다.
> 사용자용 설명은 [README.md](README.md), 기능별 세부 규칙은 `features/*/README.md`를 본다.
> `roadmap/`은 개인 개발용 로컬 계획 폴더이며 공개 저장소와 릴리즈 패키지에는 포함하지 않는다. 사용자가 로컬 roadmap 문서를 제공한 경우에만 참고한다.
>
> **동기화 지침**: `AGENTS.md`와 `CLAUDE.md`는 항상 동일한 본문을 유지한다. 한 파일을 수정하면 반드시 다른 파일도 같은 내용으로 업데이트한다.
>
> **명칭 메모**: 표시명/문서상 명칭과 기본 로컬 폴더명은 **Folio OS**다. 로컬 경로에 공백이 포함될 수 있으므로 경로를 다루는 스크립트와 명령에서는 반드시 따옴표로 감싼다.

---

## 0. 30초 요약

Folio OS는 개인 투자자가 **자기 PC에서** 돌리는 로컬 투자 리서치 워크스페이스다.
RSS·기사·리포트·공시·PDF를 모아 인덱싱하고, 매일 시장 브리핑·기업분석을 만들며, 일부 테마/딥리서치 런타임은 저장 보고서 호환을 위해 유지한다.
여기에 더해, 사용자가 Obsidian에 적어둔 **자기 생각(투자 thesis·메모)을 다시 읽어 최신 자료로 검증**하는
양방향 피드백 루프를 지향한다. 단, 사용자 생각이 보편 보고서를 오염시키지 않도록 **2계층으로 분리**한다.

기술 스택: Python 3 + FastAPI 백엔드(`app.py`), React/TypeScript SPA(`web/` → `public/react/folio-react.js`), 정적 bridge/assets(`public/`), SQLite/JSON 저장소,
선택적 LLM(OpenAI/Gemini/Claude). LLM 없이도 규칙 기반 fallback으로 동작해야 한다.

---

## 1. Folio OS란 — 2계층 모델

모든 산출물은 두 계층으로 나뉜다. 이 분리가 프로젝트의 척추다.

```text
Canonical Report   = 외부 자료 기반의 보편 1차 가공 보고서 (브리핑/기업분석/테마분석)
Personal Overlay   = Canonical을 사용자의 Obsidian 노트·포트폴리오·thesis와 연결한 개인용 해석 (별도 레이어)
```

데이터는 3계층 위계를 가지며 **절대 섞지 않는다**.

```text
외부 기사/공시/실적/리포트   = evidence            (객관적 근거)
Folio OS가 만든 보고서        = source-grounded      (근거 기반 분석)
사용자 Obsidian 노트          = hypothesis           (가설 — 근거가 아님)
```

핵심 흐름:

```text
Raw Data → Folio OS 1차 가공(Canonical) → Obsidian 2차 사고 → Folio OS가 다시 검증·연결(Personal Overlay)
```

---

## 2. 아키텍처 한눈에

```text
research-inbox/ (원천 자료)
      │  common/research_library/indexing → research-index.sqlite3 (문서 + FTS5 + 해시 임베딩 + file_manifest)
      ▼
  hybrid_search ──┬─→ daily_briefing      ─┐
                  ├─→ company_analysis     ├─→ Canonical Report (data/<종류>/{id}.json)
                  └─→ topic_report         ─┘         │
                                                      │  ← personal_overlay: Obsidian hypothesis와 대조
  market-memory.sqlite3 (내러티브/taxonomy/      ─────┤
   story-links/thesis·Regime·note_index)            ▼
                              obsidian/export / notion_export (Canonical 내보내기)
                                     ▲
                              obsidian/importer ← 사용자 2차 사고 회수 (frontmatter 타입별)
```

---

## 3. 핵심 디렉터리와 파일

```text
app.py                         # FastAPI 조립, 라우팅, 요청/응답 변환, 얇은 orchestration만
features/                      # 기능별 문서, 프롬프트, Python 런타임 코드 (실제 로직은 전부 여기)
features/common/               # 기능 간 공통 Python 코드와 Polars 계산 유틸
web/                           # React/TypeScript SPA 소스(AppShell, routes, feature screens)
public/index.html              # React SPA를 로드하는 최소 HTML entrypoint
public/app.js                  # React가 재사용하는 bridge-only helpers(Markdown/visual/source/Agent context)
public/react/folio-react.js    # Vite 빌드 산출물. web/src 변경 후 갱신 필요
public/styles.css              # UI 스타일
research-inbox/                # 사용자가 넣는 원천 자료 (개인 데이터)
data/                          # 앱 생성물: DB, 캐시, 저장 보고서, 포트폴리오 (개인 데이터)
config/                        # 회사 마스터/별칭 설정
.env                           # 로컬 API Key와 설정. 절대 출력하지 말 것
start.sh / start.ps1           # macOS·Linux / Windows 실행 스크립트
```

Python 패키지명에는 하이픈을 쓸 수 없으므로 런타임 코드는 underscore 폴더를 사용한다.
예: `features/company_analysis`, `features/common/research_library/rss`, `features/common/research_library/indexing`.
새 import와 새 코드는 `features/` 기준으로 작성한다.

---

## 4. 저장소 모델 (반드시 따른다)

데이터 형태로 저장소를 가른다. 단일 저장소로 강제하지 않는다.

| 데이터 형태 | 저장소 | 예 |
|---|---|---|
| 1:1 보고서(문서형) | **JSON-per-report** | `data/briefings/{date}.json`, `data/company-analysis/{id}.json`, `data/topic-reports/{id}.json` |
| 대량 문서 + 검색 인덱스 | **`research-index.sqlite3`** | documents, FTS5, 해시 임베딩, file_manifest |
| 지식그래프(관계형·누적·질의) | **`market-memory.sqlite3`** | 내러티브 상태, taxonomy, story-links, thesis·Regime·note_index |
| 작은 싱글톤/캐시 | **JSON 파일** | portfolio.json, watchlist.json, *-settings.json, *-cache |

원칙: **문서 = JSON-per-report / 지식그래프 = SQLite.**
- Personal Overlay와 Topic Report v2 산출물(topicPlan·evidencePackSummary·sourceLedger·quality)은 해당 보고서 JSON 안의 필드로 넣는다.
- thesis·Regime·note 링크처럼 join·시계열·티커별 질의가 필요한 것은 새 SQLite 파일을 만들지 말고 **`market-memory.sqlite3`를 "knowledge graph DB"로 확장**한다(Regime↔thesis↔note를 한 DB에서 join).
- 반복적인 필터링/정렬/집계는 `features/common/dataframe_ops.py`의 Polars 유틸을 우선 사용한다.

---

## 5. 최상위 아키텍처 원칙 (절대 규칙과 동급)

1. **2계층 분리** — Canonical 보고서 본문(`markdown`)은 Personal Overlay 생성으로 **절대 바뀌지 않는다**. Overlay는 별도 필드/요청으로만 생성·저장한다.
2. **3계층 데이터 위계** — evidence / source-grounded / hypothesis를 섞지 않는다. 사용자 노트와 userContext는 근거가 아니라 가설·관심 방향이다.
3. **확증편향 방지** — Overlay·Thesis·Regime·Topic 산출물에는 `counterEvidence`/`contradictions`/`uncertainties`(또는 challenging evidence)를 항상 포함한다. 사용자 생각을 옹호하지 말고 검증한다.
4. **결론은 enum으로 통제** — verdict·momentum·report_type·evidenceRole 등 결론·분류는 코드에서 enum/길이/출처를 검증한다. LLM 자유 텍스트로 결론을 확정하지 않는다.
5. **자기참조 금지** — Folio OS가 Obsidian으로 내보낸 노트(`generated_by`, `source_layer: primary_processed`, `reuse_as_evidence: false`)를 다시 evidence로 쓰지 않는다.

---

## 6. 절대 규칙

1. `.env`의 실제 API Key를 출력, 요약, 문서화하지 않는다.
2. `data/`, `research-inbox/`, `config/`는 사용자 개인 자료와 생성물이 들어갈 수 있다. 명시 요청 없이 삭제, 초기화, 대량 이동하지 않는다.
3. RSS 저장 위치는 `research-inbox/rss/` 하나다. 예전 `archive/` 폴더를 다시 만들지 않는다.
4. WSJ, FT 등 유료 매체의 유료 본문 우회 수집을 구현하지 않는다. 공개 RSS, 공개 링크, 사용자가 직접 저장한 자료만 쓴다.
5. 브리핑은 `filings`와 `reports`를 직접 근거로 쓰지 않는다.
6. 기업 분석의 숫자는 SEC companyfacts를 최우선으로 한다.
7. 기업 분석의 공시 서술은 SEC 연차보고서(10-K/20-F) HTML 문단 점수화 결과를 우선 사용하고, **최근 10-Q의 MD&A 문단을 함께 읽는다**(연차를 대체하지 않고 덧붙인다 — 연차만 읽으면 8월 보고서가 1월에 끝난 회계연도 서술로 회사를 설명한다). 실패 시 로컬 공식자료(10-K/10-Q/S-1/20-F/8-K/prospectus/proxy 등) 발췌를 보조 공식자료로 사용한다.
8. 보조 자료는 관련성 점수화 결과를 사용한다. 단순 검색 결과 앞부분을 LLM이나 규칙 엔진에 그대로 넣지 않는다.
9. 웹 검색은 로컬 자료를 대체하지 않는다. 부족한 지수/가격 반응/공식 자료를 보완하는 용도다.
10. 미국 상장사 식별은 SEC `company_tickers.json` 기반 CIK 조회를 우선하고, 수동 사전은 한국 종목/별칭/예외 보정에만 쓴다.
11. UI는 모바일 브라우저에서도 읽을 수 있어야 한다.
12. Markdown 렌더링 변경은 브리핑과 기업분석을 동시에 깨뜨릴 수 있으므로 React report reader가 호출하는 `public/app.js::renderMarkdown()` bridge 수정 시 주의한다.
13. `app.py`에 기능 로직을 추가하지 않는다. `app.py`에는 API endpoint, request body 정리, feature service 호출, HTTP 예외 변환만 둔다(§아래 app.py 경량화 규칙).

### UI 구현 일관성 규칙

사용자에게 보이는 화면을 새로 만들거나 구조·스타일·상호작용을 바꾸는 작업은 프로젝트 로컬 `.agents/skills/ui-ux-pro-max/SKILL.md`가 설치된 환경에서는 이를 함께 적용하고, 설치되지 않은 환경에서는 아래 규칙을 직접 따른다. 이 스킬은 패턴 검색과 품질 검수 도구이며 Folio OS의 기존 디자인을 대체하는 새 디자인 시스템 생성기로 사용하지 않는다.

- 구현 전에 `features/frontend_ui/DESIGN_SYSTEM.md`(디자인 언어·토큰·프리미티브·패턴)와 `features/frontend_ui/README.md`(화면 구조·화면별 값)를 읽고, 브라우저에서 가장 가까운 기존 화면을 데스크톱·모바일로 직접 확인한다. 재사용할 컴포넌트, CSS 클래스, 토큰, 간격, 타이포, 상태 표현과 반응형 동작을 먼저 식별한다.
- 새 기능은 새 시각 언어를 만들 권한이 아니다. 가장 가까운 기존 패턴을 확장하고, 기존 패턴으로 해결할 수 없는 경우에만 새 패턴을 제안한다.
- 기존 React + TypeScript + plain CSS 구조를 유지한다. 명시 요청 없이 Tailwind·shadcn·새 UI 프레임워크·새 폰트·새 아이콘 라이브러리를 도입하지 않는다.
- 색상·타이포·간격은 기존 토큰을 우선한다. 스킬이 추천한 팔레트·폰트·스타일이 기존 계약과 충돌하면 `AGENTS.md`, `features/frontend_ui/DESIGN_SYSTEM.md`, 기존 토큰과 인접 화면이 우선한다.
- 사용자가 새 디자인 시스템 산출물을 명시적으로 요청하지 않은 한 스킬의 `--persist`를 실행하거나 `design-system/` 폴더를 만들지 않는다.
- **프리미티브 우선(0.5 Stage D)**: 버튼·칩·세그먼트·패널 면은 `public/styles.css` 말미의 프리미티브 4종(`.btn` / `.surface` / `.chip` / `.segment`)을 쓴다. 화면 전용 CSS에서 이들의 **모양을 다시 선언하지 않는다** — 배치만 갖는다. 의미색·화면별 배치가 필요하면 프리미티브 뒤에 훅 클래스를 덧붙인다(`className="chip status-chip"`). 모서리와 굵기는 토큰(`--r-control|group|panel|pill`, `--fw-normal|medium|bold`)만 쓰고 숫자를 직접 넣지 않는다. 선택 상태는 `aria-pressed`가 소유하며 `.active`로 칠하지 않는다. 컨테이너에서 자손 `button`을 통째로 칠하지 않는다(세그먼트 알약까지 덮어쓴 사례가 있다). 상세 규칙과 새 화면 체크리스트는 `features/frontend_ui/DESIGN_SYSTEM.md`를 따른다.
- **폼 컨트롤도 프리미티브 언어**: `input`/`select`/`textarea`는 버튼과 같은 무테 회색 fill·36px 높이를 쓴다. 컨트롤에 `border`를 다시 주지 않고 상태는 hover 배경과 `:focus-visible` 링으로 표현한다. 라벨이 붙은 select는 래퍼만 면을 갖고 안쪽 select는 면을 그리지 않는다(상자 안 상자 방지).
- 완료 전 실제 화면을 데스크톱과 모바일, 지원되는 Light/Dark 테마에서 캡처해 인접 화면과 비교한다. 키보드 focus, reduced motion, 가로 overflow, loading/empty/error 상태를 확인하고 관련 Playwright/axe 및 프론트엔드 검증을 실행한다.
- UI 작업의 완료 기준은 코드 동작만이 아니라 기존 Folio OS와의 시각적·상호작용적 일관성까지 확인한 상태다.

### app.py 경량화 규칙

`app.py`는 FastAPI 앱 조립, 라우팅, 요청/응답 변환, 아주 얇은 orchestration만 담당한다.

- 새 기능 코드는 반드시 `features/<feature_name>/` 또는 공통 코드인 경우 `features/common/` 아래에 둔다.
- 기능별 계산, 데이터 수집, 파일 파싱, LLM context 생성, 보고서 생성, 백테스트, 차트 데이터 생성 같은 로직은 feature service/module로 분리한다.
- 기존 `app.py`의 큰 함수나 긴 helper를 수정해야 한다면, 먼저 해당 기능 폴더로 옮긴 뒤 수정한다.
- 라우터가 필요하면 `features/<feature_name>/routes.py`, 서비스가 필요하면 `features/<feature_name>/service.py`를 만든다.
- 기능 간 공유 유틸은 특정 기능 폴더에 복사하지 말고 `features/common/`으로 올린다.
- 레거시 패키지를 되살리지 않는다. 새 런타임 코드는 `features/` 아래에 둔다.

---

## 7. 자료 폴더 계약

```text
research-inbox/articles/   # 직접 저장한 기사, 웹페이지, txt, md, html
research-inbox/rss/        # RSS 수집 결과. RSS 저장 위치는 오직 여기
research-inbox/reports/    # 기업분석용 증권사 리포트, IR 자료
research-inbox/filings/    # 기업분석용 SEC/DART 공시, 10-K/10-Q/S-1 등 로컬 공식자료
research-inbox/links/      # URL 목록
```

- 브리핑과 뉴스 검색 입력: `articles/rss`만 사용한다.
- 기업 분석 우선순위: `filings > reports > articles > rss > 기타`.

작업 상태/개인 데이터 저장 위치:

```text
data/jobs.json                 # 백그라운드 작업 상태 요약
data/portfolio.json            # 현재 보유 포지션
data/portfolio-presets.json    # 목표 포트폴리오 프리셋
data/portfolio-backtests/      # 저장된 백테스트 결과
data/briefings/                # 저장된 브리핑
data/company-analysis/         # 저장된 기업분석 보고서
data/topic-reports/            # 저장된 테마분석 보고서
data/obsidian-settings.json    # Obsidian Vault 경로
data/dashboard-settings.json   # Research Cockpit 대시보드 설정
data/agent-threads/            # Agent 대화 스레드 (hypothesis, evidence 아님)
```

현재 active prompt 위치:

```text
features/daily_briefing/prompt.md
features/company_analysis/prompts/beginner.md
features/company_analysis/prompts/advanced.md
features/company_analysis/financial_quality_prompt.md
```

예전 최상위 `prompts/` 폴더는 사용하지 않는다. 새 프롬프트는 기능 폴더 아래에 둔다.
기업분석의 `features/company_analysis/prompt.md`는 legacy pointer이며 active prompt가 아니다.

---

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
| 포트폴리오 | `portfolio` | 보유 종목 직접 입력·revision 저장, 평가 요약·구성 분석·목표 비중·백테스트. 0.5.1에서 하위 탭 3개로 재연결. 스크린샷 가져오기는 0.5.0에서 뺐고 도크로 재설계 예정 | — |
| 시장 내러티브 메모리 / Regime 추적 v2 | `market_memory` | 중기 내러티브 상태·taxonomy·momentum/confidence·thesis 연결 | source-grounded |
| 워치리스트 | `watchlist_notes` | 워치리스트·상세(기업 정보/네이티브 차트/실적/수집 뉴스) | — |
| Native Investment Notes | `investment_notes` | Obsidian 없이 운용되는 Folio 로컬 투자 노트와 `native_note_index` | hypothesis 입력 |
| LLM/설정/웹검색 | `llm_settings` | API Key·웹검색 보완 | — |
| Notion 내보내기 | `notion_export` | 보고서 → Notion DB | — |
| Obsidian 연동 | `obsidian` | 보고서/내러티브 → Vault, 사용자 노트 회수, thesis/memo/review 템플릿·검사 | hypothesis 입력 |
| Personal Overlay | `personal_overlay` | Canonical을 사용자 노트와 대조한 개인 해석 (브리핑/기업분석) | Personal Overlay |
| Thesis Tracking | `thesis_tracking` | 기업 thesis의 강화/유지/약화/이탈 추적 | Personal Overlay |
| Research Quality | `common/research_quality` | 산출물 공통 품질 평가: sourceGrounding·risk·coverage | source-grounded |
| Quality Generation | `common/quality_generation` | 생성 품질 목표·자료 루트·preflight·evidence coverage·생성 후 평가·약한 섹션 LLM 개선·telemetry | source-grounded |
| AI Agent Mode | `agent_mode` | Codex/Claude/Antigravity CLI용 context pack·Direct Bridge·기존 저장소 writeback + 도크 Agent 대화 스레드(`/api/agent/threads`)·수정 제안 diff 승인 writeback(`/api/agent/proposals/{id}`) | source-grounded + Personal Overlay |
| 투자 리뷰 | `investment_review` | regime/thesis/portfolio/checkpoints/obsidian을 묶은 투자 리뷰 홈 | Personal Overlay |
| 현재 시장 위젯 | `market_widgets` | 예전 TradingView Current Market 위젯 설정. 0.5에서 Legacy 모드를, 0.5.4에서 마지막 소비자였던 워치리스트 상세 위젯과 브리지(`public/tradingview-widgets.js`)를 삭제했다. 설정 파일은 집중 종목 fallback으로만 read-only로 읽는다 | — |
| Data Source Reliability | `common/data_reliability` | 공식자료 우선순위·provider status·한국 데이터 보강 경로·Thesis evidence 확장·공식자료 semantic cache/fetch runtime | source-grounded |
| Fast-Origin Signals | `common/research_library/signals` | 기존 KR RSS(연합인포맥스·연합뉴스)의 빠른 게시 headline을 metadata-only lead로 수집·표시. 자격증명 없이 기본 동작하며 lead는 evidence count/source ledger 제외 | lead (evidence 이전 단계) |
| Change Intelligence | `common/change_intelligence` | 보고서/스냅샷 커밋 시 artifact-native ChangeBasis 비교로 changeSummary 생성. 추가 LLM 호출 없음 | source-grounded 파생 metadata |
| 시장 캘린더 | `market_calendar` | 경제지표·중앙은행·휴장일·실적·공시·배당 6종 일정 수집·정규화와 confirmed/estimated badge | — |
| Research Cockpit 대시보드 | `dashboard` | 변화 피드·시장 캘린더·네이티브 차트. 0.5에서 Legacy 모드 삭제 | — |
| Pixel Office (보류) | `pixel_office` | 리서치 상태를 하나의 픽셀 오피스 장면으로 보여준다. 0.3.0에서는 배선을 전부 끊고 릴리즈 패키지에서도 제외한다. 소스(백엔드 service·PixiJS 씬·13개 오브젝트 레이어)는 재개용으로 저장소에만 남는다. | 보류 |
| 첫 실행 안내 | `onboarding` | 첫 실행 판정과 5단계 안내 위저드(환영·화면·AI·관심 시장·시작) + 완료 단계의 선택 튜토리얼. 어느 단계에서든 건너뛸 수 있다 | — |
| 프론트엔드 UI | `frontend_ui` | React SPA(`web/`)가 기본 프론트엔드. `public/app.js`는 bridge-only, `public/index.html`은 최소 entrypoint | — |

0.4 기본 사용자 화면에서의 노출 상태:

- **보이는 핵심 화면**: Home/AI Agent, Dashboard(Research Cockpit), Watchlist, Portfolio, Briefing, RSS Feed, Market Memory, Company Analysis, Deep Research, Settings.
- **보이는 보조 기능**: Deep Research의 question-first 계획 승인, Smart Collection 상세/상태/변화, Market State, Agent Work Log, 보고서 reader의 Folio Note·규칙 기반 note/thesis 검토, 기존 리서치 화면의 읽기 전용 Investment Context, Obsidian/Notion 내보내기, Agent Dock/Ask Agent/제안 승인 흐름, Dashboard의 Change Feed·시장 캘린더, Watchlist/Portfolio `짚어보기` 대화와 `노트로 정리`.
- **CLI 선택은 범위가 둘이다.** 전역 기본은 상단바 `Agent CLI` 메뉴와 설정 탭이 소유하며 예약 브리핑·기업분석 등 도크 밖 작업이 쓴다. 도크의 `이 대화의 CLI`는 요청의 `options.adapter`로만 전달되어 그 대화에만 적용되고 전역을 저장하지 않는다 — 전역과 다르면 도크가 그 사실을 밝히고, 새 대화는 다시 전역 기본에서 시작한다.
- **Agent 실행 경계**: 설정에서 LLM API 키를 넣거나 Agent CLI를 연결한 순간부터, 사용자는 그 프로젝트의 모든 동작에 대해 Agent 사용을 허락한 것으로 본다. 사용자가 요청한 산출물을 만드는 일(계획 작성·보고서 생성·분석)은 버튼을 한 번 더 누르게 하지 않는다. **명시적 action이 계속 필요한 것은 사용자 개인 맥락을 읽거나 저장물을 바꾸는 쪽이다** — Thesis Delta, Collection 변화 질문, Investment Context 위험 설명, 대화 답변, 보고서 수정 제안. freshness/health/context 배지와 `changeSummary`는 계속 규칙으로 자동 계산한다(Agent를 쓰지 않는다).
- 엔진을 부르는 화면은 **얼마나 걸리는지 미리 말하고**, 실패하면 규칙 결과로 내려간 사실을 숨기지 않는다. Agent CLI는 한 번에 수십 초가 걸린다.
- **테마/접근성**: 전체 공개 화면은 Light/Dark/System 테마를 지원하고, 기존 사용자 기본값은 Light, 신규 사용자 기본값은 System이다. 키보드 탐색, 명확한 focus, WCAG 2.2 AA 대비를 공개 화면 계약으로 둔다.
- **숨김/축소 유지**: Investment Review의 독립 화면은 전면 재출시로 설명하지 않으며, 개인 맥락은 보이는 리서치 화면의 제한된 projection으로만 노출한다. Portfolio 독립 화면은 0.4에서 공개로 복귀했다.
- **문서 원칙**: 사용자용 README는 현재 릴리즈에서 실제로 보이는 기능만 현재 기능으로 설명한다. 숨김/축소 기능은 개발자 문서나 후속 로드맵에서 다룬다.

### 설계 확정·구현 예정

| 작업 | 계획 위치 | 범위 |
|---|---|---|
| 0.1 공개 릴리즈 | 로컬 `roadmap/` 문서가 있을 때만 참고 | Home/Agent, Briefing, RSS, Market Memory v3, Company Analysis v2, Agent-assisted Investment Notes v2, Settings/Automation 간소화, release QA |
| 0.3.0 공개 릴리즈 | 로컬 `roadmap/` 문서가 있을 때만 참고 | Light/Dark/System, Dashboard/Watchlist 공개, 공개 화면 WCAG 2.2 AA, responsive/release QA |
| 후속 제품 로드맵 | 로컬 `roadmap/` 문서가 있을 때만 참고 | 고급 portfolio/note workflow 재평가, installer/tray polish |
| AI Agent Mode hardening | 로컬 `roadmap/` 문서가 있을 때만 참고 | CLI/API bridge preflight, Direct Bridge 안정화, proposal writeback, job lifecycle, restart recovery, context/log retention |

> 개선안 01~04(Personal Overlay / Thesis Tracker / Regime 추적 v2 / Topic Report v2)와 post-v1 Step 6~11은 구현되어 위 표로 승격되었다.

---

## 9. 기능별 문서

작업 전에 [features 인덱스](features/README.md)를 보고, 관련 기능 README를 먼저 읽는다. 기능별 README 링크 목록은 features/README.md가 관리한다.

---

## 10. 주요 기능 경계 (구현 디테일)

### 첫 실행 안내 (Onboarding)

- 로직은 `features/onboarding/`, 화면은 `web/src/app/WelcomeWizard.tsx`다. 기록은 `data/onboarding-state.json`.
- **첫 실행은 "안내 파일이 없다"가 아니다.** 그 파일은 배포 zip에 없으므로 그렇게 잡으면 쓰던 사용자가 새 버전으로 올릴 때마다 처음 쓰는 사람 취급을 받는다. `firstRun = 안내 기록 없음 AND 사용자 자료 없음`이며, 사용자 자료는 portfolio/watchlist/market-scope/briefings/company-analysis/topic-reports/notes/agent-threads/research-inbox 하위로 판정한다.
- 서버가 스스로 만드는 파일은 판정에 넣지 않는다. 실측으로 빈 워크스페이스에서 서버를 처음 켜면 파일 10개(설정 기본값·빈 DB·SEC 캐시)가 생기지만 사용자 자료는 없다.
- **건너뛰어도 기록한다.** 다음 실행에 또 띄우면 건너뛰기가 아니다. 상태 파일이 깨져 있으면 완료로 보지 않는다(앱이 안 켜지는 것보다 낫다).
- 위저드는 라우트가 아니라 앱 위에 덮는 카드다. 뒤에 실제 앱이 떠 있어야 건너뛴 순간 바로 쓸 수 있다.
- **테마는 자기 단계다.** 환영 카드에 얹으면 첫 화면이 "이 앱은 무엇인가"와 "무슨 색으로 볼 것인가"를 동시에 묻는다. 고르는 즉시 반영되므로 저장 버튼이 없다.
- AI 단계는 "AI가 없어도 앱은 그대로 동작합니다"를 먼저 말한다. 키를 넣어야 쓸 수 있는 도구로 보이면 안 된다.
- **AI 선택지는 `AI 없이` / `CLI` / `API` 셋이고 부담이 적은 것부터다.** 라벨은 짧게 두고 설명이 무게를 진다 — 처음 쓰는 사람에게 `CLI`와 `API`는 그 자체로 아무 뜻이 없다.
- **CLI를 고르면 안내 안에서 설치·로그인까지 끝낸다**(`web/src/app/AgentCliSetup.tsx`, 설정 탭과 공유). 예전에는 "설정 탭에서 마칠 수 있습니다"라고만 적어 뒀는데 설정 탭에도 그 버튼이 없었다 — install/login API를 부르는 화면이 저장소에 하나도 없었다. 설치는 Windows에서만, 로그인은 별도 콘솔 창이며 화면이 그 사실을 먼저 말한다.
- **완료 단계는 둘러보기를 묻기만 한다.** 고르면 카드가 닫히고 둘러보기가 **앱 위에서** 돈다(`web/src/app/AppTour.tsx`) — 카드 안에서 돌면 정작 보여줄 화면이 가려진다. 들르는 곳은 RSS 피드 → 시장 내러티브 → 브리핑 셋이고, 실제로 그 탭으로 이동해 좌측 내비의 그 자리를 조명한다. 조명은 오려내기가 아니라 대상 크기 상자의 9999px 그림자이며, **기하를 transition하지 않는다**(실측으로 전환이 시작값에 갇혀 조명이 따라오지 않았다). 건너뛰면 둘러보기도 하지 않는다.
- **안내의 색은 앱 계약을 따른다.** 눌린 면과 CTA는 블루가 아니라 `.btn--primary`와 같은 잉크 면이다 — 블루는 verdict 칩이 쓰는 의미색이라 UI 액센트로 쓰면 §5 원칙과 DESIGN_SYSTEM 원칙 4를 깬다.
- 성공 문구를 남기지 않는다. 단계가 넘어가는 것이 이미 확인이고, 남기면 다음 단계 아래에 붙어 그 단계를 저장했다고 읽힌다.
- `aria-modal="true"`를 선언하므로 포커스를 가둔다(Tab 순환, 단계 전환 시 제목으로 이동, Escape는 건너뛰기).
- 판정을 못 읽으면 안내를 띄우지 않는다. 쓰던 사람에게 뜨는 쪽이 더 나쁘다.
- 다시 보기는 설정 > 자료 위치의 버튼이며 `folio:show-welcome` 이벤트로 화면만 연다. 서버 판정을 지우는 방식은 쓰지 않는다 — 자료가 있는 사람은 지워도 `firstRun`이 false라 안내가 뜨지 않는다.

### 자료 위치 (Workspace)

- 사용자 자료(`data`/`research-inbox`/`config`)의 위치는 `features/common/workspace.py` 하나가 정한다. **`ROOT / "data"`를 새로 쓰지 않는다** — `data_dir()`, `research_inbox_dir()`, `config_dir()`를 부른다.
- **이유**: 배포 zip은 `FolioOS-v0.5.0/`처럼 버전이 박힌 폴더로 풀리고 `data/`는 빈 채로 나온다. 새 버전을 받으면 새 폴더에 빈 워크스페이스가 생기고 이전 자료는 옛 폴더에 남는다(실측 22,715개·914MB). 코드와 자료가 한 폴더에 섞여 있는 것이 원인이다.
- 찾는 순서: `FOLIO_HOME` → 앱 폴더 `workspace.json` 표지 → 앱 폴더 `data/`에 파일 있음 → `~/Documents/FolioOS`에 자료 있음 → 앱 폴더.
- **기본값은 앱 폴더다.** 옮기는 것은 선택이고 아무것도 새로 만들지 않는다(2026-08-08 사용자 결정 — 홈 폴더에 앱이 폴더를 만드는 것을 싫어하는 사용자가 있다).
- 폴더 존재가 아니라 **파일 유무**로 판정한다. 배포 zip이 빈 폴더를 만들어 두므로 존재만 보면 갓 푼 설치도 쓰던 워크스페이스로 오인한다.
- 표지가 필요한 이유는 옮기기가 **원본을 지우지 않기** 때문이다. 표지가 없으면 앱 폴더 규칙이 먼저 걸려 방금 옮긴 곳이 아니라 옛 자료를 계속 쓴다. 표지는 배포 zip에 없으므로 새 버전 폴더에서는 문서 폴더 규칙이 자료를 다시 찾는다.
- **경로를 앱 폴더 기준으로 만들지 않는다.** `documents.path`는 자료 폴더 기준 상대 경로이며 `indexing/service.py::workspace_relative()`가 만든다. 앱 폴더(`ROOT`) 기준으로 두면 자료를 문서 폴더로 옮긴 순간 `path.relative_to(ROOT)`가 `ValueError`를 던져 인덱싱 전체가 멈춘다 — 옮기기가 성공해도 앱을 못 쓴다. 기본값에서는 자료 폴더가 곧 앱 폴더라 저장되는 문자열이 같아 기존 색인은 그대로 읽힌다.
- 판정은 프로세스당 1회 캐시한다. 모듈 상수 수십 곳이 import 시점에 읽는다. 옮긴 뒤에는 재시작이 필요하며 화면이 그렇게 안내한다.
- **옮긴 뒤 재시작 전까지 RSS 수집과 보관 기간 정리는 쉰다.** 표지가 쓰인 순간부터 한 프로세스가 두 워크스페이스를 동시에 본다 — 모듈 상수(`RSS_INBOX_DIR`)는 옛 폴더, 수집 서브프로세스와 호출 시점에 판정하는 경로(`data_dir()`·`research_inbox_dir()`)는 새 폴더다. 그대로 수집하면 Markdown은 옛 폴더에·evidence 행은 새 DB에 갈려, 재시작 뒤 그 기사가 파일 없는 행으로만 남아 색인·브리핑에서 사라진다. 정리는 반대로 방금 복사한 사본을 지운다. `workspace.moved_pending_restart()`가 그 창을 표시하고, 건너뛴 작업은 `skipped: "workspace_moved"`와 재시작 안내를 함께 돌려준다 — 조용히 건너뛰면 자동 수집이 도는 줄 알고 며칠을 보낸다.
- 옮기기(`features/common/workspace_service.py`)는 복사 → 파일별 크기 검증 → 표지 순이다. 검증 실패 시 표지를 쓰지 않아 앱이 계속 원본을 쓴다. 목적지에 자료가 있으면 `merge` 없이 진행하지 않고, 목적지는 `documents`/`app` 둘뿐이다(임의 경로 금지). `FOLIO_HOME`이 설정돼 있으면 옮기기를 막는다 — 표지를 써도 다음 시작에서 환경변수가 이기므로 옮겼다고 말하면 거짓말이 된다.
- 문서 폴더는 Windows 레지스트리(`User Shell Folders\Personal`)로 읽는다. OneDrive 리디렉션 시 `~/Documents`가 실제 문서 폴더가 아니다. 목적지가 OneDrive 아래면 막지 않고 경고만 한다.

### 파일 저장 (원자적 교체)

- durable write는 전부 `features/common/atomic_replace.py`를 거친다. `os.replace()`를 직접 부르지 않는다.
- **이유**: `os.replace()`는 POSIX에서 대상이 열려 있어도 성공하지만 Windows는 `WinError 5`(액세스 거부)나 `WinError 32`(사용 중)로 거부한다. 백신 실시간 검사·검색 색인기·탐색기 미리보기가 잡고 있을 때 나며, 보통 수십 밀리초 안에 풀린다. 한 번 거부됐다고 실패로 끝내면 사용자가 작업 상태나 보고서 저장을 잃는다.
- `replace_with_retry()`는 `PermissionError`만 최대 6회(총 0.31초) 물러나며 재시도하고, 끝내 안 되면 원래 예외를 올린다. 경로 없음처럼 기다려도 안 풀리는 오류는 즉시 올린다.
- `write_bytes_atomic()`은 임시 파일에 쓰고 제자리로 옮기며, 실패 시 임시 파일을 남기지 않는다.
- **임시 이름은 호출마다 다르다**(`{대상}.{uuid}{suffix}`). 이름을 고정하면 같은 파일을 동시에 쓰는 두 호출이 한 임시 파일을 공유해, 나중 내용이 먼저 제자리로 가고(응답과 저장 내용이 어긋난다) 뒤이은 교체는 임시 파일이 이미 사라져 `FileNotFoundError`로 500이 된다(실측 6,000회 중 1,260회). pid로는 부족하다 — 겹치는 쪽은 한 프로세스 안에서 sync 엔드포인트를 나눠 처리하는 스레드풀 스레드이고, `watchlist.json`·`portfolio-presets.json`·각종 설정 파일에는 호출자 잠금이 없다.
- **삭제도 같은 재시도를 쓴다.** job 비공개 pack 폴더 제거는 `shared_jobs_private.rmtree_with_retry()`를 거친다. 쓰기만 물러났다 다시 쓰고 삭제는 한 번에 포기하면, 그 비대칭이 잡 종료와 시작 복구를 통째로 실패시킨다.
- 전체 테스트를 반복 실행해 잡은 실제 오류가 근거다. 파일을 쓰는 테스트라면 어느 것이든 드물게 걸렸고 단독 실행 시에는 통과해, 오래 `간헐적 실패`로만 남아 있었다.

### 웹 검색 출처 범위 (Web Search Scope)

- 허용 목록은 `config/web_search_sources.yaml`이고 로직은 `features/common/web_search_scope.py`다. 등급은 **둘**이다 — `official`(공시·통계·중앙은행)과 `media`(신뢰 금융 매체).
- **목록에 없는 도메인은 근거로 쓰지 않는다.** 로컬 자료에는 출처 우선순위를 엄격히 매기면서 웹에는 계층을 두지 않으면 가장 약한 자료가 가장 느슨하게 들어온다.
- 두 겹으로 막는다. 프롬프트에 허용 목록을 명시하고(요청 단계), 생성된 본문의 URL을 목록과 대조해 `webSearchAudit`에 남긴다(응답 단계). **프롬프트는 부탁이지 제한이 아니다.**
- 유료 매체(WSJ·FT·日経 등)도 목록에 넣되 `paywalled: true`로 표시한다. 검색 결과의 제목·요약과 공개 페이지까지만 쓰고 유료 본문은 우회하지 않는다(원칙 4).
- **회사 공식 도메인은 목록에 두지 않는다.** 1만 종목의 IR 주소를 손으로 관리할 수 없어 yfinance `website`에서 도출하고 그 회사 분석에서만 허용한다. 도출이 틀리는 예외만 `company_domain_overrides`에 적는다. 서브도메인은 같은 출처로 본다(`investor.nvidia.com` ⊂ `nvidia.com`).
- 설정을 못 읽으면 **아무 도메인도 허용하지 않는다.** 목록 없이 웹 검색을 여는 것보다 쓰지 않는 편이 낫다.

### 산업·정책 맥락 검색

- 회사 질의와 별개로 업종(`yfinance industry`) 기반 산업 질의와 정책·거시 질의를 함께 던진다. 회사 공시만으로는 경쟁우위·리스크·성장 전망이 반쪽이다.
- **이 결과는 배경이다.** Market Memory와 같은 경계를 쓴다 — 회사의 매출·이익·가이던스·제품 같은 고유 사실의 근거로 인용하지 않는다. 실제로 산업 검색 없이도 무관한 기사가 회사 근거로 올라온 적이 있어(NVDA 보고서의 LATAM 항공 실적) 경계를 명시한다.
- `Sources Used`에 `회사 / 산업 / 정책`을 구분해 남긴다. 산업 기사 수가 많다고 회사 근거가 충분한 것은 아니다.

### 자동 새로고침 (Content Revisions)

- `GET /api/content-revisions`는 저장소별 마지막 변경 시각(`briefing`/`companyAnalysis`/`topicReport`/`marketMemory`/`rss`/`note`/`portfolio`/`watchlist`)만 돌려준다. 로직은 `features/common/content_revision.py`이며 **파일 mtime만 읽고 내용을 열지 않는다** — 몇 초 간격 폴링을 견뎌야 하기 때문이다.
- 디렉터리는 **자신의 mtime도 함께** 본다. 자식 파일만 보면 가장 최근 파일이 삭제될 때 값이 내려가 삭제가 신호로 전달되지 않는다.
- 화면은 `web/src/app/useContentRevision.ts`로 구독한다. 값이 **달라지면**(커질 때만이 아니라) 목록을 다시 읽는다. 첫 응답은 기준점이라 화면을 여는 순간 두 번 읽지 않는다.
- 탭이 보이지 않으면 묻지 않고, 탭으로 돌아오면 기다리지 않고 바로 확인한다.
- 이 신호는 출처를 가리지 않는다. 자동화, 다른 탭, Agent 도크가 만든 변화가 모두 같은 경로로 화면에 반영된다. 예전에는 자기가 실행한 작업이 끝났을 때만 다시 읽어서, 자동 생성된 브리핑은 사용자가 직접 새로고침하기 전까지 목록에 없었다.

### 서버 재시작

- 웹 UI 상단의 `서버 재시작` 버튼은 `POST /api/server/restart`를 호출한다.
- `schedule_server_restart()`는 0.5초 후 `os._exit(RESTART_EXIT_CODE)`로 프로세스를 종료한다. **재시작 신호는 7이다.**
- **3을 쓰지 않는다.** `uvicorn.config.STARTUP_FAILURE`가 3이라, 포트 충돌을 비롯한 모든 uvicorn 시작 실패가 같은 코드로 끝난다. 예전에는 런처가 그것을 재시작 신호로 읽어 무한히 다시 띄웠다 — 시작 → 바인드 실패 → `Restarting...` → 시작 → … (실측: 서버가 이미 떠 있을 때 `py -3 app.py`가 exit 3). 사용자가 `.cmd`를 두 번 실행하면 바로 걸린다.
- `main()`은 uvicorn을 부르기 전에 포트를 직접 잡아 본다(`_port_owner_message()`). 이미 우리 서버가 떠 있으면 그 주소를 안내하고, 다른 프로그램이면 `PORT`를 바꾸라고 말한 뒤 코드 1로 끝낸다. uvicorn의 영어 소켓 오류를 그대로 보여주지 않는다.
- `start.ps1`과 `start.sh`는 종료 코드 7이면 루프를 돌며 `py -3 app.py`(또는 Python 경로)를 재실행한다. 0도 7도 아니면 `start.ps1`은 창을 붙잡아(`Read-Host`) 실패 이유가 사라지지 않게 한다.
- `start-archive.cmd`나 `start.ps1` / `start.sh`로 실행 중일 때만 재시작이 자동으로 동작한다. 터미널에서 `py -3 app.py`를 직접 실행 중이면 서버가 종료만 된다.
- `_RESTART_REQUESTED` 플래그로 동시에 여러 재시작 요청이 들어와도 한 번만 실행한다.
- 재시작 후 `load_jobs()`는 `jobs-v2.json`과 legacy `data/jobs.json` 양쪽의 `queued`/`running`/`cancel_requested` 작업을 `failed_restart`로 변환한다(좀비 잡 방지). **legacy 파일도 실제로 고쳐 쓴다** — API는 `JOBS` 캐시가 아니라 매 요청 `_store().merged()`를 다시 읽고 merged()가 legacy 행을 그대로 싣기 때문에, 캐시만 고치면 구버전에서 남은 `running` 행이 영원히 실행 중으로 보인다.
- **비공개 pack 삭제가 막혀도 기동을 멈추지 않는다.** `recover_startup()`은 실패한 잡을 `cleanup_blocked`에 남겨 잡 조회를 503으로 닫되(fail-closed), 나머지 잡 전환과 orphan 정리를 끝내고 마지막에 알린다. `load_jobs()`는 그 예외를 잡고 계속한다 — 백신이 pack을 수십 밀리초 잡았다고 앱 전체가 안 켜지는 것이 더 나쁘다.

### 백그라운드 작업과 증분 인덱싱

- `/api/index`와 `/api/rssarchive/import`는 오래 걸리는 작업을 직접 응답하지 않고 job을 생성한다.
- 작업 상태는 `/api/jobs/{job_id}`에서 조회한다.
- 프론트는 상단 `#status`와 진행률 바에 job 상태를 표시한다.
- `build_index(incremental=True)`는 `research-index.sqlite3`의 `file_manifest` 테이블을 사용해 파일 크기/수정시각이 변하지 않은 자료를 건너뛴다.
- market-relevant 문서는 SQLite `documents` 테이블에 저장하고, 관련 없는 파일도 `file_manifest`에 저장해 다음 인덱싱 때 재처리하지 않는다.
- `data/index.json`은 더 이상 문서 목록이나 파일 매니페스트를 포함하지 않으며, `generatedAt`, `count`, `incremental`, `sqlite` 같은 상태 요약만 저장한다.
- SQLite/FTS 동기화는 `contentHash`가 같은 문서의 chunk embedding 재생성을 건너뛴다.
- job 결과에는 전체 `documents`를 저장하지 않는다. `count`, `generatedAt`, `incremental`, `sqlite` 같은 요약만 저장한다.

### 하이브리드 검색

- 텍스트 쿼리가 있으면 `hybrid_search()`가 유일한 랭킹 경로다. in-memory 키워드 스캔은 사용하지 않는다.
- 2단계: FTS5 BM25로 최대 120개 청크 후보 추출 → 후보에 한해 해시 임베딩 코사인 유사도 계산 (전체 스캔 없음).
- RRF(k=60)로 FTS 랭크와 벡터 랭크를 합산하고, 토큰 겹침은 타이브레이커로만 쓴다.
- 문서 단위 중복 제거: 같은 문서의 여러 청크 중 점수가 가장 높은 청크를 대표 스니펫으로 반환한다.
- 쿼리 없는 회사/범위 필터는 in-memory 문서 목록을 그대로 사용한다.
- `sanitize_fts_query()`가 특수문자를 이스케이프하고 토큰을 OR로 연결해 FTS5 에러를 방지한다.

### 관심 시장 범위 (Market Scope)

- 로직은 `features/common/market_scope.py`, 저장은 `data/market-scope.json`(기본 `US/KR`). API는 `GET/PUT /api/market-scope`.
- **범위는 필터가 아니라 제품의 바깥 테두리다**(2026-08-07 사용자 결정). 꺼진 시장은 RSS 수집에서 해당 피드가 제외되고(GLOBAL 피드는 항상 수집), RSS 목록·시장 필터, 브리핑 생성 선택지, 시장 캘린더, 내러티브 세그먼트에서 함께 숨는다. Task 1.4의 필터는 범위 **안에서** 좁힐 때만 쓴다.
- GLOBAL/UNKNOWN 태그 자료는 어떤 범위에서도 보인다. 유가·달러·공급망 기사는 특정 시장 소유가 아니다.
- 시장을 다시 켜면 그 시장 피드만 즉시, 나이 제한 없이 수집한다(`--only-markets`, `--max-age-days 0`). RSS는 피드가 내어주는 최근 항목까지만 받을 수 있어 꺼져 있던 기간의 공백이 남는다 — 설정 화면이 그 한계를 먼저 말하고, 언제 켰는지는 `enabledAt`에 남는다.
- 기업 분석은 회사 단위라 범위와 무관하다. 범위를 못 읽으면 화면은 전부 보이는 쪽으로 되돌아간다(서버 오류가 데이터 소실처럼 보이면 안 된다).

### RSS와 뉴스 검색 (Evidence Intake)

- 수집은 RSS 단독이 아니라 Folio OS Evidence Intake 경로다. 최종 단위는 `IntakeEvidenceItem`이고 RSS는 `collector=rss` 입력원 중 하나다.
- 모듈 경계(단방향 DAG): `rss_archive.py`(얇은 CLI/orchestration) → `fetch.py`(HTTP retry/backoff) → `parser.py`(RSS/Atom→raw item) → `article.py`(본문/요약 추출) → `relevance.py`(시장 관련성 게이트) → `normalizer.py`(raw→EvidenceItem) → `policy.py`(dedupe/retry/relevance score/full-text/paywall) → `collectors.py`(official adapter) → `writer.py`(YAML front matter Markdown 아카이브 IO + state) → `store.py`(`research-index.sqlite3::evidence_items`). `rss_archive.py`에는 run-level orchestration만 둔다(parse/fetch/write 로직 추가 금지).
- 설정 파일로 분리: `config/rss_feeds.yaml`, `config/evidence_sources.yaml`. 코드 수정 없이 feed enable/disable이 가능하다.
- **피드는 정기적으로 죽는다.** 매체가 호스트를 옮기면 기존 URL이 200 OK와 옛 항목을 계속 반환해 정상처럼 보인다(2026-08 확인: WSJ `feeds.a.dj.com` 3개가 553일, MarketWatch `feeds.marketwatch.com`이 396일 정체 상태로 응답 중이었고 `feeds.content.dowjones.io`가 현행 호스트다). 커버리지가 이상하면 건수가 아니라 **최신 항목 시각**을 먼저 확인한다.
- `only_publishers`를 지정하면 aggregating 피드에서 해당 발행처 항목만 남기고 저장 시 **원 발행처 이름으로 태그**한다(Yahoo Finance→Reuters). 발행처는 RSS `<source>`에서 읽는다.
- feed의 `source_type`이 소비 경로를 가른다. 기본 `news`만 사용자에게 보이는 뉴스 경로에 들어간다. **`press_release`(PR Newswire·GlobeNewswire 같은 보도자료 와이어)는 브리핑과 RSS 피드 화면 양쪽에서 제외한다.** 브리핑은 `is_news_document()`가, RSS 화면은 `_HIDE_PRESS_RELEASE_SQL`이 담당하며 목록과 출처 드롭다운이 같은 조건을 공유한다(출처를 직접 골라도 보이지 않는다). 이야기 비중 패널도 `news_documents()`를 거치므로 함께 제외된다. 같은 문서는 인덱스에 그대로 남아 워치리스트 종목 뉴스와 기업분석 보조자료로 쓰인다. 브리핑은 교차 보도량(`publisherCount`)으로 이슈를 고르는데 보도자료는 발행처가 1곳뿐이라 이슈로 뜨지 않으면서 클러스터링만 흐리고, RSS 화면에서는 발행량이 많아 뉴스를 밀어내기 때문이다.
- feed는 **직접 피드**와 **aggregator 경유**로 성격이 다르다. 직접 피드(CNBC·Yahoo Finance·The Guardian·BBC·한국 매체)는 본문까지 확보되지만, `news.google.com` 검색 경유(Reuters·Bloomberg·WSJ·Barron's 등)는 `AGGREGATOR_REDIRECT_HOSTS` 정책상 기사 HTML을 가져오지 않아 **제목·링크만 남는다**. 커버리지 논의에서 수집 건수와 실제 사용 가능한 본문 수를 구분한다. Reuters·AP·Bloomberg 등은 공개 RSS를 종료했거나 라이선스 전용이라(2026-08 확인: Reuters 401·도메인 소멸, AP 401/404) 제목 신호로만 유지하며, 제3자 RSS 변환기나 scraping으로 우회하지 않는다.
- 신규 Markdown은 YAML front matter(`collector`/`source_type`/`normalized_url`/`collection_status`/`reliability_tier`/`query` 등) + body section 포맷이다. legacy line-oriented Markdown은 읽기 호환을 유지한다.
- CLI 기본 실행은 기사 전문을 저장하지 않는다. `--save-full-text` 명시 시에만 `Full Text` 섹션에 전문을 쓴다. 웹 앱이 실행하는 수집(RSS 수집 버튼/자동화)은 설정 탭의 `rss.saveFullText`(automation-settings, 기본 켜짐)에 따라 이 플래그를 전달한다. 유료 본문 우회는 금지한다.
- paywall 판정은 게이트 문구("구독 후 이용", "subscribe to continue" 등) 기준이다. 한국 뉴스 푸터의 "구독"/"로그인" 단어만으로 유료벽 판정하지 않으며, 충분한 공개 본문이 추출되면 페이지 내 구독 배너가 full_text 판정을 막지 않는다. `news.google.com` 리다이렉트 링크는 기사 HTML을 가져오지 않고 RSS 요약을 유지한 `summary_only`로 저장한다(aggregator 페이지 요약으로 덮어쓰기 금지). 기사 페이지 요청은 표준 브라우저 UA를 사용한다.
- normalized URL 기준 dedupe를 사용한다. `summary_only`/`needs_manual_save`/`legacy_rss`/`fetch_failed`는 기본적으로 반복 재수집하지 않는다(`--retry-failed`/`--retry-summary-only`로만).
- 공식자료(SEC/OpenDART/FRED/BOK)는 `source_type=official_filing|macro_data|official_release`, `reliability_tier=1`로 구분한다. 현재 adapter는 fake data 없는 stub이며 브리핑 직접 근거로 쓰지 않는다.
- 외부 검색 API 기반 추가 수집은 사용하지 않는다. RSS 수집 버튼(`/api/rssarchive/import`)은 RSS collector만 실행한다.
- **임베딩은 `chunks.embedding`에 float32 + zlib blob으로 담는다.** JSON 텍스트는 값 하나가 20여 글자라 청크 42,471개가 342MB였다(실측). 이 형식은 14.85배 작고 디코드가 9배 빠르며, 변환+VACUUM 후 DB가 728MB → 380MB가 됐다. float32 오차는 최대 1.4e-08이고 코사인은 RRF에서 순위로만 쓰여 한국어 포함 8개 질의의 상위 20위가 완전히 같았다.
- 판올림한 DB는 시작 직후 배경에서 batch 500개씩 변환한다(`migrate_embeddings()`). 전부를 한 트랜잭션으로 밀면 그동안 검색이 멈춘다. `parse_embedding()`이 blob과 옛 JSON을 모두 읽으므로 변환 중에도 검색이 동작한다. 변환해도 파일은 줄지 않으며 회수는 `지금 정리`가 한다.
- **보관 기간이 곧 검색 DB 크기다.** 인덱스된 문서는 100%가 RSS이고, 한 건이 파일 3.5KB로 끝나지 않는다 — 문서 하나와 청크 3~4개가 따라붙어 실측 2.5개월치 22,609건에 `research-index.sqlite3`가 728MB였다(그중 342MB가 `chunks.embedding_json`). 설정은 `automation-settings.json`의 `rss.retentionDays`(기본 90일)이고 로직은 `features/common/research_library/rss/retention.py`다.
- 정리는 **파일만 지운다.** 나머지 행은 이미 있는 경로가 걷어낸다 — `refresh_rss_feed_cache()`가 `rss_feed_items`를, `build_index(incremental=True)`가 `documents`/`chunks`/FTS/`file_manifest`를 정리한다. 같은 일을 하는 삭제 SQL을 따로 쓰면 인덱서가 바뀔 때마다 조용히 어긋난다. 어느 쪽도 손대지 않는 `evidence_items`만 재색인 뒤에 정리한다.
- **기본값은 설치 상태에 따라 다르다.** 새 설치는 90일, 이 기능 이전에 만들어진 설정 파일이 있으면 `계속 보관`(0)이다(`schema.py::_retention_for`). 쓰던 설정에 90일을 먹이면 반년치를 모아 둔 사람이 판올림만으로 석 달치를 잃는다 — 지우겠다고 말한 적이 없는데 지워진다(§6 절대 규칙 2). 줄이는 것은 화면에서 고르고, 그때는 몇 건이 지워지는지 먼저 보여준다.
- 날짜는 파일명 접두로 읽고, 날짜를 못 읽는 파일과 `.state.json`은 건드리지 않는다. 기간은 `RETENTION_CHOICES` 값만 받는다 — 임의의 숫자로 자료가 지워지지 않는다.
- **VACUUM은 `지금 정리` 버튼에서만** 한다(`run_retention_now()`). 실측 728MB 기준 29초 동안 DB를 통째로 잠그므로 매시간 도는 수집에 물릴 수 없다. 자동 수집은 지운 자리를 SQLite가 재사용하게 두어 크기를 묶어 두고, 파일을 실제로 줄이는 일은 사용자가 부를 때 한다.
- RSS API: `app.py::rss_feed_payload()`, `rss_merge_payload()`. import 경로는 `service.py::import_rssarchive()`.
- 출처 필터 드롭다운은 **현재 `config/rss_feeds.yaml`에서 수집 중인 매체만** 노출한다(`_selectable_sources()`). 피드를 지웠거나 aggregating 피드가 원 발행처로 재태그해서 더는 새 항목이 들어오지 않는 매체는 고를 수 있어도 결과가 늘지 않아 사용자를 오도한다. 과거 수집분은 목록에 그대로 보이며 필터 대상에서만 빠진다. 설정을 읽지 못하면 전부 노출하는 기존 동작으로 되돌아간다.
- 화면: RSS 피드 탭. 한 페이지 20개 표시. 시간, 소스, 시장 필터를 제공한다.
- RSS 피드 목록은 Markdown 파일 전체를 매 요청마다 읽지 않고 `data/research-index.sqlite3`의 `rss_feed_items` 캐시 테이블에서 `LIMIT/OFFSET`으로 읽는다. 캐시는 파일 `mtime_ns`/크기 기준으로 증분 갱신하며 기본 TTL은 `RSS_CACHE_REFRESH_TTL_SECONDS=30`초다. RSS 수집 직후에는 강제 갱신한다. 캐시는 각 항목의 `markets` 태그를 `US`, `KR`, `GLOBAL`, `UNKNOWN` 중 하나 이상으로 저장하며, `/api/rss/items`와 `/api/rss/merge`는 `market=US|KR|GLOBAL|UNKNOWN` 필터를 지원한다.
- 인덱싱은 front matter metadata(`collector`/`sourceType`/`reliabilityTier`/`query`/`relatedTickers`/`narrativeIds` 등)를 문서/chunk metadata로 보존해 briefing/topic/market_memory 소비자가 읽을 수 있게 한다. 단, 브리핑 입력 범위는 계속 `articles/rss` 원칙을 지킨다.
- 별도 뉴스 검색 탭은 없다. RSS 피드 탭 안에서 `articles/rss` 자료를 검색한다.

### 일일 브리핑

- 브리핑 입력은 `articles/rss`만 사용한다.
- 저장 JSON에는 Step 6 공통 구조 필드 `checkpoints`, `dataGaps`, `marketTape`를 포함한다. 이 필드는 대시보드/품질 평가용이며 기본 `markdown`을 바꾸지 않는다.
- 생성 당시 가격 시계열은 보고서 JSON `visualSnapshots`, 히트맵 상세 rows는 `data/briefings/{date}.visuals.json`에 저장한다. 화면은 Lightweight Charts 5.2.0(가격)과 Plotly(히트맵)로 이 immutable snapshot을 렌더링한다. `GET /api/briefings/{date}/visuals`는 사이드카 조회만 하며 현재 데이터를 섞지 않는다.
- Lightweight Charts의 `layout.attributionLogo`와 사용자 화면의 TradingView 링크·copyright, `THIRD_PARTY_NOTICES.md`를 제거하지 않는다.
- `GET /api/briefings/{date}/visuals/current`는 저장 snapshot의 종목 universe만 최신 일봉으로 재조회하는 read-only 경로다. current payload를 보고서 JSON이나 `.visuals.json`에 merge/write하지 않는다. yfinance 일봉은 실시간 체결가가 아니므로 `snapshot/delayed/stale/unavailable`과 장 상태를 명시한다.
- 한국시간 기준 날짜 `D` 브리핑은 미국장 `D-1` 마감과 한국장 `D-1` 결과 및 `D` 개장/장중을 구분해야 한다.
- 시장별 세션은 `briefing_market_windows()`의 `marketSessions.{us,kr,europe,jp}`로 읽는다. 기존 `us*`/`kr*` 키는 호환을 위해 그대로 둔다. 유럽은 미국처럼 한국시간 자정 이후 마감하므로 항상 직전 완료 세션을, 일본은 한국처럼 생성 시각으로 `pre_open|intraday|closed`를 가른다.
- 유럽·일본 휴장일 표는 `features/common/exchange_holidays.py` 하나이며 세션 판정과 시장 캘린더가 함께 읽는다. 유럽은 거래소별로 판정하고(런던만 쉬는 날이 연 십여 일) 표가 없는 연도는 `coverage_expired`로 보고한다. 평일을 개장으로 추측하지 않는다.
- 대표 지수는 `features/common/markets.py`의 `MARKET_REGISTRY.representative_indices`가 단일 출처다. 통화·시간대는 시리즈마다 붙는다. 유럽은 GBP와 EUR이 한 차트에 섞이므로 스냅샷 통화를 하나로 stamp하지 않는다(`currencies` 목록, 섞이면 `currency: MIXED`).
- 히트맵 상자 크기는 `weightBasis`와 함께 저장한다. 유럽은 EUR 환산 시가총액(`market_cap_eur`)이며 환율 없이 GBP와 EUR을 더하지 않는다.
- **읽을 때는 창이 저장된 `sessionDate`를 이긴다.** 저장값은 원래 그 창에서 파생된 것이라 제대로 만들어진 보고서에서는 둘이 같다. 다른 경우는 창을 못 받고 만들어져 발행일이 박힌 보고서뿐이고, 그때 저장값을 믿으면 틀린 제목이 영원히 남는다 — 실제로 월요일 08:03에 만든 브리핑이 본문은 `2026.08.07 마감`인데 카드만 `2026.08.10 마감`이라고 계속 말했다. 창이 없는 옛 보고서는 저장값을 그대로 쓴다.
- **세션 창(`marketWindows`)을 `enrich_briefing_sections()`에 반드시 넘긴다.** 창이 없으면 세션일이 발행일로 떨어지고, KR은 `krSessionPhase`가 없다는 이유로 세션 모드까지 버린다 — 08:00에 만든 브리핑이 아직 열지도 않은 그날 장을 `마감`이라 하고, 장중 생성은 `장중`이 아예 나오지 않으며, 미국장은 항상 D-1이라 전부 하루씩 틀린다. 창은 `select_briefing_docs()`가 돌려준 값이며 생성 시각(`as_of`) 기준으로 phase가 매겨져 있다. 규칙 생성(`builder.py`)과 Agent 생성(`agent_mode/service.py`) 두 경로가 모두 넘겨야 같은 시각에 같은 제목이 저장된다.
- **시장이나 요일을 하나도 안 고른 예약은 스스로 꺼진다.** 마지막 하나를 끄는 것도 선택이므로 막지 않는다 — 예전에는 그 클릭을 무시해 눌러도 아무 일이 없는 버튼으로 보였고, 서버는 빈 목록을 기본값으로 되돌려 끄겠다는 선택이 정반대로 저장됐다. 단 빈 목록과 읽을 수 없는 값(`marketScope: "bad"`)은 가른다 — 후자는 고장이라 기본값으로 되돌린다.
- **사전작업(`runPrerequisites`)도 예약별이다.** 브리핑 전에 RSS 수집과 시장 메모리 갱신을 돌릴지이며, 값이 없으면 켠 것으로 읽는다. **화면이 보여주는 내러티브까지 만든다** — 규칙 기반 갱신은 `market_memory` 행과 regime 카운트만 바꾸고 시장 내러티브 탭이 읽는 `market_state_snapshots`를 만들지 않아서, 사전작업이 도는 날에도 화면은 며칠 전 해석 그대로였다(실측으로 스냅샷은 전부 사용자가 버튼을 누른 것이었다). 버튼과 같은 경로를 쓰고, 실패해도 브리핑을 막지 않는다. 0.5.2에서 화면 토글이 사라지고 값만 `true`로 박혀 있었다 — RSS 자동 수집을 끈 구성에서는 이것이 유일한 수집 경로다.
- **예약마다 도는 요일을 고른다**(`briefingSchedules[].days`, 0=월 … 6=일). 예전에는 요일을 보지 않아 08:00 예약이 토·일에도 돌았고, 장이 열리지 않은 날 금요일 자료로 만든 브리핑이 매주 두 건씩 쌓였다. **거래일 판정으로 대신하지 않는다** — 그러면 주말 브리핑(주간 요약·다음주 프리뷰)을 만들 길이 막히고, 판정 대상이 직전 세션이라 공휴일이 끼면 꼬인다. 새 예약은 평일로 시작하고, 이 항목이 없는 저장된 예약은 매일로 읽는다(판올림으로 발행이 사라지면 안 된다).
- **브리핑에는 종류가 있다**(`kind ∈ {daily, weekly}`, 0.5.4). `briefingType`(편집 강조점)과 직교한다 — 그쪽 세 값은 모두 "기존 섹션 구성을 유지하라"고 지시하므로 골격이 다른 주간을 그 enum에 넣으면 계약이 자기 자신과 모순된다. 저장된 예약·보고서에 값이 없으면 일간이다.
  - **주간 저장 키는 `{발행일}.{시장}.weekly.json`이다.** 접미사가 없으면 일요일 실행이 `_scope_session_date()`가 돌려준 금요일 파일로 떨어져 그 주 금요일 일간 브리핑을 통째로 덮어쓴다. 이름 규칙을 아는 곳이 셋이다 — `schema.py::_scoped_file_stem()`, `archive.py` 정규식, `canonical_identity.BRIEFING_KIND_SUFFIXES`. 마지막 것을 빼먹으면 저장이 정체성 검증에서만 조용히 막힌다.
  - **주간에는 세션이 없다.** 제목은 `{라벨} 주간 — {MM.DD}~{MM.DD}`이며 `마감`/`장중`을 붙이지 않고 세션 제목 정규화를 태우지 않는다. 자료 창은 발행일 기준 달력 7일(`P-6 … P`)이고 비어도 넓히지 않는다 — 넓히면 "지난주"가 거짓이 된다.
  - **다음주 프리뷰는 시장 캘린더 표를 그대로 싣는다.** 프롬프트와 컨텍스트 양쪽이 "표에 없는 일정을 기억으로 채우지 말라"를 못박고 `confirmed`/`estimated`를 구분해 남긴다. 프롬프트에만 적으면 부탁이지 제한이 아니다.
  - **주간은 시장 내러티브에 적재하지 않는다.** 같은 이슈를 일간이 이미 그 주에 넣었고, 다시 넣으면 한 사건이 두 번 세어져 regime 근거 카운트가 부푼다.
  - **주간은 세션 시각자료를 만들지 않는다.** 시각자료는 하루 세션의 가격 계열이라, 한 주를 덮는 보고서에 붙이면 특정 하루가 그 주를 대표하는 것처럼 읽힌다.
  - 프롬프트는 별도 파일 넷(`prompt_weekly_{us,kr,europe,jp}.md`)이고 출력 계약·프롬프트 계약도 갈린다. 규칙 fallback은 사실 목록과 캘린더 표만 싣고 **해석 문장이 비어 있다는 사실을 본문에 적는다** — 한 주의 이야기를 엮는 일은 LLM 산출물이고 규칙이 흉내 내면 근거 없는 문장이 남는다.
  - **보고서의 정체성에도 종류가 들어간다.** 변화 감지의 `artifactId`(`{발행일}.{시장}.weekly`)와 `lineageId`(`briefing:{시장}:weekly`) 둘 다다. 빠뜨리면 `change_event_index`의 PK 충돌로 평일 주간이 그날 일간의 변화 이벤트를 덮어쓰고, `select_report_baseline`이 주간을 직전 일간과 — 그다음 일간을 그 주간과 — 비교한다. 뒤엣것은 **이미 있던 일간 Change Feed를 주간이 생긴 순간부터 망가뜨린다.**
  - **리더의 액션(개인 해석·내보내기)도 종류를 싣는다.** 없으면 `resolve_briefing`·`_briefing_overlay_path`가 일간으로 떨어져, 주간을 열어 두고 누른 개인 해석이 그날 일간 보고서를 고친다. CLI 경로는 report id에 `{발행일}.weekly`로 싣는다.
  - **자료가 없는 주는 CLI를 부르지 않는다**(`WeeklyWindowEmptyError`). 창을 넓히지 않으므로 0건이 될 수 있고, 그대로 보내면 최소 분량 계약에 걸려 재작성 1회 뒤 실패한다 — 수십 초짜리 CLI를 두 번 돌리고 아무것도 남기지 못한다. 규칙 경로는 비용이 없으므로 "자료 0건" 보고서를 그대로 낸다.
  - 아카이브 카드 dedup 키와 화면 해시(`#/briefing/{date}/{scope}/{kind}`), 삭제 요청에 모두 종류가 들어간다. 빠지면 같은 날 두 보고서 중 하나가 조용히 사라지거나, 주간 카드의 삭제가 일간을 지운다.
  - 스케줄러 중복 억제 키에도 종류가 들어간다. 같은 시장의 일간·주간 예약이 한 주기에 걸리면(일요일 아침) 뒤가 조용히 스킵된다.
- **참고자료 티어 표가 시장을 안다**(0.5.4). 한국장 키워드 티어를 어느 시장 브리핑에서든 걸던 시절에는 유럽장·일본장 참고자료 상위 다섯 건이 전부 국내 매체였다 — 프롬프트는 같은 자리에서 "국내 매체 보도는 보조자료로 쓰세요"라고 지시하는데 목록이 정반대였다. `_HOME_MARKET_TIERS`가 시장별 고유 티어를 소유하고, 범위를 모르거나 종합이면 예전처럼 전부 켠다. 매체 적합도(`_publisher_fit_band`)는 **같은 티어 안의 저울**이며 거친 밴드 셋으로 두어 문서 점수를 덮어쓰지 않는다.
- **`SOURCE_PROFILES`는 네 시장 모두에 전문성 값을 갖는다.** `us`/`kr` 둘뿐이던 시절 유럽·일본은 fallback으로 떨어져 매체 권위 점수가 무작동이었다. 새로 등재한 유럽·일본 매체는 `region: "regional"`이다 — `domestic`은 한국장 교차 확인 판정 전용이라, 주면 KR 이외 이슈에 교차 확인 보너스가 붙는다.
- **`allow_full_text`는 소비자가 없는 죽은 설정이었다**(0.5.4에 제거). 본문 확보는 수집 시점에 정해진다. 실측하면 CNBC와 국내 매체는 본문이 거의 100%, Bloomberg·WSJ·Reuters는 5% 미만이며 그쪽은 전부 유료벽이다 — 유료 본문 우회가 금지이므로 추가할 피드가 없고, 국내 매체 비중을 더 줄이면 본문 있는 근거를 제목뿐인 근거로 바꾸는 거래가 된다. **설정과 실제가 어긋난 신호를 남겨 두면 다음 판단이 그것을 믿는다.**
- **선별 개수 상한은 `features/daily_briefing/limits.py` 하나에서 나온다**(0.5.4). 예전에는 `limit=14`가 기본 인자 여섯 곳과 호출부 전부에 흩어져 있어 어느 하나를 고쳐도 나머지가 그대로였다. **참고자료는 프롬프트가 본 문서 전부**이며(`SOURCE_REF_LIMIT == CONTEXT_DOC_LIMIT`) 표시 개수 설정은 만들지 않는다 — 24건을 보고 14건만 보여주면 근거로 쓰였을 수 있는 열 건이 출처 목록에서 사라진다. 다시장 병합 상한은 고정값이 아니라 시장 수에서 산출한다(28로 두면 네 시장에서 뒤쪽 시장 출처가 통째로 빠진다).
- **아카이브 카드는 항상 시장별 한 장이다.** 여러 시장을 함께 생성해도 접지 않는다 — 접힌 카드는 모든 시장을 이어 붙인 합본(실측 15,828자)으로 열려서, US+KR을 함께 예약하면 각 시장 보고서를 화면에서 읽을 수 없었다(2026-08-10 사용자 결정).
- 시장별 독자용 제목은 세션일과 상태를 함께 쓴다(`US ... D-1 마감`, `Korea ... D 장중|마감`). 발행일은 별도 `publicationDate`/`KST 발행` 메타데이터로 표시하고 저장 키·기본 정렬 기준으로 유지한다. Agent/API/규칙 생성과 아카이브가 같은 계약을 사용해야 한다.
- **화면의 날짜 선택은 발행일이 아니라 그 시장의 세션 기준일이다.** 한 브리핑 안에서 미국장은 발행일 D의 D-1 정규장을, 한국장은 D 장을 다루므로 변환은 시장마다 다르다: 미국장·유럽장은 `세션일 다음 거래일`, 한국장·일본장은 `세션일 그대로`. 변환은 `publication_date_for_session()` 하나가 담당한다. 저장 키·아카이브 정렬·기존 보고서는 계속 발행일 기준이라 호환이 깨지지 않는다.
- **예약이 고른 시장만 만든다.** 범위 이름(`us`/`both`/`all`)으로는 임의 조합을 담지 못해 한국+일본은 `multi`가 되고, `multi`는 네 시장 전부로 풀린다. `_run_briefing()`이 넘기는 `markets` 목록을 `prepare_pack()` 디스패처가 버려서 한국·일본 예약이 미국장·유럽장까지 만들었다(실측 2026-08-13 18:18에 파일 넷). 디스패처가 목록을 그대로 넘기고, `expectedTitles`도 계약이 자기 시장으로 좁힌다 — 두 프롬프트가 그 표를 전부 펼쳐 모델에게 제목을 지시하기 때문이다.
- **발행일이 갈리면 실행을 나눈다**(`publication_date_groups()`, `POST /api/briefings`). 예전에는 여러 시장을 함께 고르면 밤샘 마감 시장 기준 발행일 하나로 합쳤는데, 그러면 나머지 시장이 그 발행일을 **자기 세션일로** 읽는다 — 금요일(08-07)을 고르고 미국장·한국장을 함께 만들면 한국장은 월요일(08-10) 장을 다뤘고, 고르지 않은 날의 브리핑이 아무 경고 없이 나왔다. 저장 파일이 이미 시장별(`{발행일}.{시장}.json`)이라 그룹마다 따로 만들면 둘 다 고른 세션을 다룬다. 그룹은 최대 둘이며(미국·유럽 / 한국·일본), 응답은 그룹이 둘일 때만 `jobs`(CLI) 또는 `reports`(규칙) 목록이 된다. 날짜를 주지 않은 오늘 생성은 그룹이 하나라 예전과 같다 — `marketScope=both`로 도는 시장 메모리 writeback도 그대로다.
- **한국장 수치도 발행일이 아니라 세션일로 부른다**(`cached_korea_market_data(_scope_session_date("kr", windows))`). 차트는 세션일로 가는데 수치만 발행일로 가면 한 브리핑 안에서 날짜가 갈린다 — 월요일 08:03에 만든 금요일 브리핑에 지수는 금요일 종가가 들어갔는데(월요일 봉이 아직 없어 떨어졌다) 환율만 일요일 값이 들어갔다. 환율은 24시간 거래라 주말 봉이 잡힌다. 장이 열린 뒤 같은 요청을 하면 아직 마감도 안 한 당일 장중 값을 받는다. 규칙 생성과 Agent 생성 두 경로가 같다.
- 한국장 핵심 수치는 `features/common/market_data/providers.py`의 provider 체인을 사용한다. 지금 체인은 yfinance 하나이며, KOSPI/KOSDAQ 종가 등락률이 없으면 추정하지 말고 한계를 명시한다.
- **pykrx는 2026-08-12에 제거했다.** 1.2.x부터 지수 조회에 KRX 계정(`KRX_ID`/`KRX_PW`)을 요구해, 자격증명이 없는 설치에서는 매번 실패하고 조용히 yfinance로 떨어졌다(이 PC의 캐시 12건이 모두 그랬다). 사용자에게 API 키를 하나 더 받아 되살릴 만한 가치가 없다고 봤다. 히트맵 universe가 같은 이유로 이미 같은 결정을 했다(`kospi200_universe`). 실제로 잃은 것은 없다 — 투자자 수급·업종 등락·거래대금은 이미 모든 브리핑에서 비어 있었고, 이제 그 사실이 문서와 일치한다.
- LLM 실패 시 규칙 기반 브리핑이 필요하다. 참고자료 섹션은 유지한다.
- `select_briefing_docs()`의 fallback 경로에서 `market_windows`는 브리핑 날짜 기준 원본을 유지한다. 문서 날짜로 재계산하면 공휴일/주말에 `krPreviousSessionDate`가 틀린 날짜를 가리키는 버그가 발생한다.

### 기업 분석

- 입력은 `build_company_analysis_materials()`에서 구성한다.
- SEC companyfacts, SEC 10-K HTML 상위 문단, 로컬 공식자료 fallback, 점수화된 보조 자료 순서다.
- LLM 버전과 규칙 기반 버전 모두 같은 선별 결과를 사용해야 한다.
- 기업분석은 `analysisStyle=beginner|advanced`를 지원한다. 두 모드는 서로 다른 완전한 prompt 파일을 사용하지만 같은 9개 섹션 골격, 자료 우선순위, no-fabrication, data gap 규칙을 유지해야 한다.
- 제공 자료가 부족하면 먼저 `features/company_analysis/data_gap_resolver.py`로 확인 경로와 미해결 항목을 구조화하고, 보고서 JSON에는 `dataGaps`와 `resolutionAttempts`를 보존한다.
- 보고서는 생성 시 `data/company-analysis/`에 **자동 저장**된다(`api_analyze`가 `save_analysis_report` 호출). 보고서 id는 `ticker:날짜` 기준이라 같은 기업을 같은 날 재분석하면 최신본으로 덮어쓴다(파일 무한 누적 방지). 덮어쓸 때 기존 `personalOverlay`는 보존한다.
- 영어 10-K 원문은 규칙 기반 보고서에서 그대로 나올 수 있다. 번역은 브라우저 번역이나 LLM 버전에 맡긴다.

- **분기 자료**: companyfacts 분기 행은 이미 컨텍스트 표(`Recent Quarter`)에 들어간다. 차트는 연간만 읽고 있어서 `분기 흐름` 차트를 따로 만든다(최근 8개 기간, **전년 동기 대비** — 분기는 계절성이 있어 직전 분기와 비교하면 오해한다). 10-Q 서술은 `rankedQuarterlyFiling`으로 붙는다. 10-Q는 Item 번호 체계가 10-K와 달라(`Item 2` = MD&A) `_ITEM_PATTERNS`·`_ITEM_EQUIVALENTS`에 따로 등재돼 있다.
- **차트 계약**: 값이 하나도 없는 계열은 그리지도 **부제에서 약속하지도** 않는다(`_present_subtitle`). 마진처럼 단위가 다른 계열은 오른쪽 축으로 분리한다 — 금액 축에 얹으면 0에 붙어 사라진다. 기간 구간이 hover 대상이고 그 기간의 모든 계열과 증감을 그림 밖 고정 상자에 보여준다.

### 테마분석 (Topic Report v2)

- 파이프라인: Topic Planner → Evidence Pack → report_type 템플릿 결합 → LLM/규칙 보고서 → Quality Gate → (선택) Personal Overlay.
- 저장 JSON에는 `checkpoints`, `evidenceItems`, `sourceLedger`, `dataGaps`, `marketTape`를 공통 schema 형태로 포함한다. 구조화 필드 생성은 기본 `markdown`을 수정하지 않는다.
- `reportType`(12종)·`evidenceRole`(5종)은 `topic_schema.py`에서 enum 검증한다. LLM 자유 텍스트 분류를 그대로 신뢰하지 않는다.
- custom 주제는 planner가 `searchQueries`/분석 축/후보 티커를 만든다. 기존 `label.split()` 검색은 폐기. 프리셋은 `plan_from_preset`으로 backward compatible.
- **계획은 주제어 위에 세운다.** 사용자는 질문칸에 배경까지 한 문단으로 적는다. 그 240자를 주제 라벨로 쓰면 축 질문 다섯 개가 같은 문단이 되고 검색어에 질문 전문이 들어간다. `topic_subject()`가 첫 구획을 40자 이내로 끊고, 원문은 `topic`에 남는다.
- **계획의 `searchQueries`는 그대로 근거 검색을 돌린다.** 한 단어 질의와 질문 전문 질의를 만들지 않는다(실제로 `피크`는 전력망 기사를, 질문 전문은 그날 시장 기사 아무거나 물어왔다 — FTS에서 토큰이 OR로 풀린다). 2어절 이상 40자 이하만 남기며, 이 게이트는 LLM 계획에도 똑같이 적용한다.
- **계획 미리보기는 기본적으로 설정된 엔진이 쓴다**(`plannerEngine=auto`). 계획을 보려고 버튼을 두 번 누르게 하는 것은 확인이 아니라 절차다. 빠른 계획이 필요할 때만 `plannerEngine=rules`를 고른다. CLI는 한 번에 40~50초가 걸리므로 화면이 그 사실을 먼저 말한다.
- `POST /api/topic-reports/plan/replan`은 계획을 다시 쓴다. `instruction`이 있으면 지금 계획을 그 요청대로 고치고, 없으면 처음부터 다시 쓴다. `revise`와 같은 `_swap_plan` 경로로 새 planHash를 만들고 기존 승인을 supersede한다.
- **화면의 계획 수정은 요청 문장 하나로 받는다.** 칸을 하나씩 편집하는 UI는 축 다섯 개에 텍스트 영역이 열한 개가 됐다. 항목 단위 수정 API(`plan/revise`)는 엔진 없이 고쳐야 하는 호출자용으로 남는다.
- 엔진이 없거나 실패하면 규칙 계획이 그대로 남는다. `plannerMode`(`rules|llm|preset|edited`)를 계획에 남겨 화면이 표시한다 — 무엇이 쓴 계획인지 모르면 얼마나 믿을지 정할 수 없다.
- **테스트는 Agent CLI를 부르지 않는다.** `features/topic_report/tests/conftest.py`가 `run_agent_prompt`를 막는다. 막지 않았을 때 아무것도 stub하지 않은 테스트가 실제 CLI를 실행해 스위트가 멈춰 섰고, 멈춘 이유가 코드 문제인지 CLI 문제인지 구분되지 않았다.
- 플래너는 API 키와 Agent CLI 둘 다 쓴다. `AI_AGENT_MODE=cli` 환경에서는 `apiKey`가 비어 있어 플래너만 엔진을 못 찾고 있었다. 키가 없으면 `run_agent_prompt()`로 같은 프롬프트를 보낸다(`TOPIC_PLANNER_TIMEOUT_SECONDS`, 기본 120초).
- 승인 전 계획 수정은 `POST /api/topic-reports/plan/revise`다. `confirm-degraded`와 같은 모양으로 **서버가** payload를 고치고 planHash를 다시 계산해 기존 승인을 supersede한다. 클라이언트가 계획을 통째로 밀어넣는 통로는 없고, 축은 key로 찾을 뿐 새로 만들 수 없다.
- `userContext`는 관심 방향이지 evidence가 아니다. 외부 자료와 충돌하면 충돌을 명시하고 반대 근거를 함께 제시한다.
- Quality Gate(`evaluation.py`)는 규칙 기반이다. markdown 섹션 존재 + Evidence Pack 커버리지로 점수/등급/경고를 만든다. LLM 없이 동작한다.
- Personal Overlay와 Quality 재평가는 **저장된 보고서에만** 동작한다(파일 기준). overlay 생성은 기본 `markdown`을 수정하지 않는다(Step 2 `with_overlay` 재사용).
- 보고서는 승인된 `POST /api/topic-reports` SharedJob의 committing 단계에서 `data/topic-reports/`에 **자동 저장**된다. 공개 save route는 없으며, 명시적 proposal 승인만 기존 Canonical revision을 바꾼다. 저장 JSON에는 `topicPlan`/`researchResolution`/`executionProvenance`/`evidencePackSummary`/`sourceLedger`/`quality`/`personalOverlay`를 함께 둔다.
- LLM이 없어도 규칙 fallback이 리서치 계획 요약·데이터 부족 경고·체크포인트·Source & Data Notes를 포함한 보고서를 만든다.

### 포트폴리오

- 현재 범위는 사용자가 직접 입력한 보유 포지션 분석, 목표 프리셋, 리서치용 백테스트다.
- 저장 위치는 `data/portfolio.json`이다. 개인 입력 데이터이므로 명시 요청 없이 삭제하거나 초기화하지 않는다.
- 목표 프리셋은 `data/portfolio-presets.json`, 백테스트 결과는 `data/portfolio-backtests/`에 저장한다.
- 현재가, 종목명, 섹터, 자산군, 시장, 통화는 `yfinance` 조회 결과를 우선 사용한다. `quoteError`가 있어도 화면이 깨지지 않아야 한다.
- KRW 자산과 USD 자산이 섞이면 USD 기준 비중 계산을 위해 환율을 반영한다.
- 목표 포트폴리오 비교는 현재 비중, 목표 비중, 비중 차이, 금액 차이, 매수/매도 필요 수량을 보여준다.
- 백테스트는 리서치용이다. yfinance 과거 가격과 일자별 환율을 사용하며, 실제 세금/수수료/체결오차/배당 처리에는 한계가 있다.
- 백테스트 실행 결과는 자동 저장하지 않는다. 사용자가 결과 카드의 저장 버튼을 눌렀을 때만 저장한다.
- 거래 내역 기반 원가 계산, 배당 현금흐름, 자동 리밸런싱 제안은 아직 범위 밖이다.
- 저장은 additive `revision`을 가지며 `expectedRevision` 불일치 시 409와 최신본을 반환한다. 동시 수정은 사용자가 최신본과 다시 합친다.
- **화면은 하위 탭 셋이다**(0.5.1, 0.5.4에 이름 변경): 보유·평가 / **프리셋** / 백테스트.
- **프리셋이 1급 시민이다**(0.5.4). 목표 비중은 프리셋으로 할 수 있는 여러 일 중 하나이고 백테스트·비교 백테스트의 입력도 같은 프리셋이라, 탭 이름이 그 셋 중 하나만 가리키면 나머지를 어디서 하는지 알 수 없다. `POST /api/portfolio/backtests/compare`는 예전부터 있었는데 **부르는 화면이 없었다** — 프리셋 2개 이상을 골라 지표 표와 겹친 시계열을 본다. 지표마다 나은 쪽 하나만 굵게 하고 동점이면 강조하지 않는다. **최대 낙폭은 음수로 오므로 `nearZero`(0에 가까울수록 낫다)로 비교한다** — "작을수록 좋다"로 두면 더 깊은 낙폭을 최선으로 강조한다. 빈도가 다르기 때문이다 — 세로로 쌓으면 매번 보는 것이 거의 안 쓰는 것에 밀린다. 저장 후 `revision`을 내려보내 시세·비중·목표 차이를 다시 받는다.
- **목표는 프리셋이다.** `analytics.targetWeights`는 원래 포지션의 `targetWeight`만 봤고 프리셋과 서로 몰랐다. 그 값을 넣을 칸이 화면에 없어 `hasTargets`가 언제나 False였고 **목표와의 차이 표가 한 번도 뜨지 않았다**. `GET /analytics?presetId=`로 비교할 목표를 받는다. 프리셋에만 있고 아직 안 산 종목도 한 줄로 낸다.
- `POST /presets/from-current`는 **지금 평가액 비중**을 목표로 삼는다. 예전에는 이미 설정된 `targetWeight`만 담아 실측으로 보유 3종목에서도 빈 프리셋이 나왔다.
- 초기 공개 릴리즈에 실려 온 `.portfolio-donut-grid` 등 CSS 46개는 D1 프리미티브 이전 디자인(테두리 카드)이라 되살리지 않는다.
- **스크린샷 가져오기는 0.5.0 화면에 없다.** 시간 대비 인식이 만족스럽지 않았고 첫 설정에 한 번 쓰는 도구였다(2026-08-07 사용자 결정). 버튼·다이얼로그·`/import-image/*` route를 걷어냈고 보유 종목은 직접 입력한다.
- 다시 만들 때는 **Agent 도크 하나로 통일한다** — 사용자가 도크에 사진을 붙이고 포지션 입력을 요청할 때만 인식한다. 도크가 설정의 CLI/API 모드를 따르므로 엔진 선택을 따로 두지 않고, 로컬 Tesseract는 도크에 자리가 없어 함께 사라진다. **막힌 지점**: 도크 API 모드는 지금 이미지를 못 읽는다(`chat.py::_run_with_images`가 CLI 전용). 리뷰 표는 없애지 못한다 — 저장 전 확인이 안전 계약이라, 읽은 행을 Portfolio 편집표에 얹고 기존 저장 버튼이 커밋하게 한다. 기존 proposal 배관은 markdown 보고서 전용이라 쓸 수 없다.
- `features/portfolio/import_image.py`·`agent_import.py`·`vision_import.py`·`import_schema.py`는 호출자가 없어도 **죽은 코드가 아니라 0.5.X용으로 남긴 것이다.** 지우기 전에 `roadmap/release/0.5_PLAN.md`를 본다.

### Obsidian 내보내기

- 브리핑, 기업분석, 테마분석(Topic Report), 시장 내러티브(active/watch)를 로컬 Obsidian Vault의 Markdown 노트로 내보낸다.
- 테마분석은 `Topic Reports/` 폴더로 내보내며 frontmatter에 `report_type`, `quality_score`, 그리고 자기참조 방지 마커(`generated_by`/`source_layer: primary_processed`/`reuse_as_evidence: false`)를 붙인다.
- Vault 경로는 `data/obsidian-settings.json`에 저장한다. 사용자 설정 파일이므로 명시 요청 없이 삭제하지 않는다.
- 내보내기 로직은 `features/obsidian/export/`에 있다. `app.py`에는 엔드포인트만 둔다.
- 태그는 Obsidian이 공백을 허용하지 않으므로 `normalize_tag()` 후 공백을 언더스코어(`_`)로 변환한다.
- `config/company_master.json`은 최상위가 배열이 아니라 `{"companies": [...]}` 구조다. 직접 iterate하지 말고 `.get("companies", [])`로 접근한다.
- `## 사용자 메모` 구분자 이하 내용은 재내보내기 시 보존한다.
- 회사명·별칭을 `[[wikilink]]`로 자동 변환한다. 길이 역순으로 처리해 부분 매칭을 방지한다.
- **자기참조 주의(Folio OS 원칙 5)**: 내보내는 노트에는 `generated_by`, `source_layer: primary_processed`, `reuse_as_evidence: false`를 붙여, 향후 Obsidian importer가 이를 evidence로 재사용하지 않도록 한다.

### Notion 내보내기

- 브리핑, 기업분석, 테마분석 보고서를 Notion 데이터베이스 페이지로 내보낸다.
- `NOTION_TOKEN`과 `NOTION_DB_ID`는 `.env`에 저장하고, 설정 탭 UI에서 입력할 수 있다.
- Notion 데이터베이스는 이름(title), 날짜(date), 유형(select), 주제(rich_text) 속성으로 구성한다.
- 내보내기 로직은 `features/notion_export/`에 있다. `app.py`에는 엔드포인트만 둔다.
- Markdown → Notion 블록 변환은 `features/notion_export/client.py::markdown_to_blocks()`가 담당한다.
- 100개 초과 블록은 PATCH로 분할 추가한다.
- 인라인 데이터베이스를 사용하는 경우 데이터베이스가 있는 상위 페이지에 통합을 공유해야 한다.
- `NOTION_TOKEN` 실제 값을 로그, 응답, 문서에 출력하지 않는다.

### 시장 내러티브 메모리

- 브리핑 생성 시 주요 흐름을 중기 내러티브로 누적한다.
- 최소 온톨로지와 상태(`active/watch/resolved/overridden`)를 유지한다.
- taxonomy 테이블로 category, region, importance, entry_mode, story, family, relation, tag, industry, ticker, subject, subject_type, event_kind, state_key, net_effect 사용량을 추적한다.
- story link graph로 개별 branch가 어떤 큰 family에서 분기되는지 기록한다.
- `AI 반도체 공급망`, `AI 데이터센터 전력 병목`, `금리·달러 유동성`, `중동 에너지 리스크`처럼 큰 story family를 우선 재사용한다.
- 모든 이슈를 바로 현재 상태로 올리지 않는다. `issue` 메모 중 반복 근거가 있거나, 중요도가 높고 복수 출처가 있을 때만 active/watch 상태 후보가 된다.
- 시장 내러티브 탭의 기본 UI는 Market State Dashboard v3(`GET /api/memory/state-dashboard`) 하나다. 상단은 `시장 해석`과 `판단 및 투자 행동` 두 개의 큰 본문으로 보여주고, 스냅샷에 `marketViews.overall/us/kr`가 있으면 `종합 / 미국장 / 한국장` 세그먼트로 전환한다. 드라이버 카드는 짧은 판단 요약과 방향 칩만 먼저 보여준다. 세부 근거는 카드 안 `근거 보기` 접기에 `근거 요약`, `시장 영향`, `다음 확인`만 간결하게 표시한다. taxonomy·story map·audit·패밀리 제안·개별 기록 목록 UI는 제거되었고 API로만 접근한다.
- Market State Snapshot context는 `rssCandidates`, `shortTermDigest`, `existingStates`에 더해 yfinance 기반 `marketTape`와 FRED/BOK ECOS 기반 `macroSnapshot`을 포함할 수 있다. 이 값은 LLM이 시장 판단을 작성하기 위한 structured evidence이며, 코드는 provider/freshness/결측을 정리할 뿐 시장 결론을 규칙으로 확정하지 않는다.
- **시장 해석 문장은 뉴스 흐름에서 시작한다.** `rssCandidates`가 1차 근거 풀이고 `marketTape`/`macroSnapshot`은 그 이야기를 확인·반박하는 맥락이다. 해석을 지수 레벨이나 퍼센트 나열로 열지 않는다(프롬프트 규칙으로 강제, `snapshot.py`). 수치가 앞장서면 근거 위계가 뒤집힌다.
- audit, story-map, family-review, narrative-report는 API로 유지되므로 품질 저하나 잘못 묶인 패밀리는 API 응답으로 점검한다.
- active/watch 상태의 추세·근거 카운트 갱신은 `run_rss_market_memory_update()`가 규칙 기반 `refresh_all_regimes`로 자동 수행한다(RSS/Market Memory 자동화 실행 시 포함). 화면에는 상태별 수동 갱신 버튼이 없다.
- LLM 기반 정리는 사용자가 `시장 메모리 업데이트` 버튼을 눌렀을 때만 실행한다. 이 버튼은 `/api/memory/llm`으로 기존 중기 내러티브 row를 누적한 뒤 `/api/memory/state-snapshot`으로 화면용 현재 시장 상태 스냅샷을 이어 생성한다. 자동 브리핑 생성 과정에서는 규칙 기반 후보 저장을 유지한다.
- LLM에는 전체 원문을 보내지 말고 후보 이슈, 상위 자료 요약, 기존 memory/state/taxonomy/story-links의 압축본만 보낸다.
- LLM 결과는 JSON으로 받고, 코드에서 enum/길이/출처를 검증한 뒤 `upsert_memory()`로 저장한다.
- 기사 링크 나열이 아니라 요약, 중요성, 포트폴리오 연결, 체크포인트 중심이어야 한다.
- Regime 추적 v2는 위 상태에 momentum/confidence/evidence window/thesis 연결을 더한다.
- Regime 추세 갱신은 `next_checkpoints_json`과 `falsification_triggers_json`을 채워 Step 8 대시보드가 구조화 checkpoint를 읽을 수 있게 한다.
- `momentum` enum은 `strengthening/stable/fading/turning/conflicted`, evidence role은 `supporting/challenging/neutral`만 허용한다.
- Regime 근거는 기존 `market_memory` 엔트리를 상태별로 분류해 `market_regime_evidence`에 저장하고, 변화는 `market_regime_changes`에 남긴다.
- Thesis/Obsidian 노트는 hypothesis다. `linked_regimes`, ticker overlap 등은 `market_regime_thesis_links` 연결 정보로만 쓰며 evidence로 승격하지 않는다.
- 기존 active/watch/resolved 호환성과 기본 브리핑 markdown 불변을 최우선으로 유지한다.

### 공통 Research Schema / Market Tape Lite

- 공통 구조는 `features/common/research_schema/`에 둔다: `checkpoints.py`, `evidence.py`, `source_ledger.py`, `data_gaps.py`, `service.py`.
- 시장 수치 freshness/status 정규화는 `features/common/market_data/tape.py`에 둔다. Step 6에서는 새 provider를 추가하지 않고 기존 snapshot/provider 산출물을 감싼다.
- read API는 `/api/research-data/checkpoints|evidence|source-ledger|data-gaps|market-tape`를 사용한다.
- `user_note` evidence type은 hypothesis 연결용일 뿐 evidence 집계에서 제외한다.
- 구조화 필드는 항상 보고서 JSON의 별도 필드로 저장하고 Canonical markdown은 바꾸지 않는다.

### Research Quality

- 공통 품질 평가는 `features/common/research_quality/`에 둔다. `features/topic_report/evaluation.py`는 호환 wrapper로 유지한다.
- 평가 입력은 Step 6의 `checkpoints`, `evidenceItems`, `sourceLedger`, `dataGaps`, `marketTape`를 우선 읽는다.
- `sourceGrounding`, `hallucinationRisk`, `personalBiasRisk`는 규칙 기반으로 계산하고 LLM 자유 텍스트를 신뢰하지 않는다.
- `user_note`는 hypothesis이며 source grounding의 evidence count에 포함하지 않는다.
- 평가 결과는 artifact의 별도 `quality` 필드에 저장한다. Canonical markdown은 품질 평가로 수정하지 않는다.
- API는 `/api/research-quality/evaluate`, `/api/research-quality/{artifact_type}/{artifact_id}`, `/api/research-quality/recheck/{artifact_type}/{artifact_id}`를 사용한다.

### Quality Generation

- 로직은 `features/common/quality_generation/`에 둔다. 생성 품질 목표/자료 수집 루트, 생성 전 preflight, prompt/rule hints, 생성 후 `research_quality` 평가, 제한적 repair loop를 담당한다.
- 브리핑/기업분석/테마보고서 생성 컨텍스트에는 보고서 유형별 품질 목표(`quality_targets.py`)를 먼저 주입한다. 최소 근거, 필요한 evidence mix, 자료 보강 루트, 필수 산출 요소가 생성 전부터 반영되어야 한다.
- 내부 `qualityMode` 호환 값은 `diagnose_only`(기본), `llm_section_improve`, `strict`만 허용한다. 레거시 `improve_once` 요청은 `llm_section_improve`로 매핑한다. 기존 생성 API는 기본값이 `diagnose_only`라 기존 동작을 깨지 않는다.
- 0.2 웹 UI에서는 품질 모드를 사용자 선택 항목으로 노출하지 않는다. 기본 생성은 자동 품질 진단(`diagnose_only`)으로 처리하고, 섹션 개선 모드는 내부/API 호환 경로로만 남긴다.
- `llm_section_improve`와 `strict`는 약한 섹션 LLM 개선을 최대 1회로 제한한다. 반복 재작성 루프를 만들지 않는다.
- 섹션 개선은 현재 artifact의 `sourceLedger`, `evidenceItems`, `checkpoints`, `dataGaps`, `marketTape` 범위 안에서만 한계·반론·확인 경로·Source & Data Notes를 보강한다. 새 수치나 새 출처를 만들어내지 않는다.
- 결과는 보고서 JSON의 별도 `qualityGeneration` 필드에 저장한다. `qualityBefore`/`qualityAfter`/`repairApplied`/`repairCount`/`repairType`/`weakSectionsBefore`/`weakSectionsAfter`/`telemetry`/`preflight`/`warnings`를 포함하며, Canonical markdown은 품질 진단만으로 바꾸지 않는다.
- 사용자 Obsidian 노트는 계속 hypothesis다. preflight나 repair에서 evidence count/source grounding으로 승격하지 않는다.
- API는 `/api/quality-generation/preflight`, `/api/quality-generation/repair`, `/api/quality-generation/run`을 사용한다.

### 투자 리뷰 (Investment Review)

- 로직은 `features/investment_review/`에 둔다. **Personal Overlay 계층**이다 — Canonical 보고서를 수정하지 않고 별도 리뷰 객체/캐시로만 만든다.
- regime_v2(`list_states`)·thesis(`list_theses`+`latest_delta`)·portfolio·watchlist·Step 6 checkpoints(`checkpoints_from_*`)·obsidian `note_index`를 한 리뷰로 집계한다. 집계는 주입식 순수 함수로 분리해 DB 없이 테스트한다.
- **LLM 없이 규칙 기반**으로 생성한다. 데이터가 없으면 빈 섹션 + warning(원문 불변).
- 일 1회 생성 후 `data/investment-review/{date}.json`에 캐시한다. 해당 날짜 저장본이 없으면 최신 저장본 + `stale` 표시. `forceRefresh`로 재생성한다.
- 포트폴리오 영향(impact: positive/watch/neutral)은 투자 판단 보조이며 **매수/매도 지시가 아니다**. keyCheckpoints는 Step 6 구조화 checkpoint를 쓴다.
- API는 `/api/investment-review`, `/api/investment-review/generate`, `/api/investment-review/{date}`를 사용한다.

### Data Source Reliability

- 로직은 `features/common/data_reliability/`에 둔다. 공식자료 우선순위, source reliability, provider status, 한국 market-data CSV 보강 경로를 담당한다.
- 기업분석/Thesis Delta source priority는 `SEC/DART filings > companyfacts/XBRL > 10-K/10-Q 문단 > IR/실적자료 > 리포트 > 기사 > RSS` 순서를 따른다.
- Thesis Delta는 기존 로컬 뉴스 evidence에 `company_analysis materials` 기반 SEC companyfacts/DART, SEC 10-K/10-Q 상위 문단, 로컬 filings/reports evidence를 보강한다.
- 한국 데이터 보강 MVP 경로는 `research-inbox/market-data/krx_foreign_flows.csv`, `sector_performance.csv`, `bok_macro.csv`다. 자동 연동이 부족하면 `dataGaps.suggestedAction`으로 이 경로를 안내한다.
- provider status는 `ok/degraded/failed/unknown`으로 기록하며, Market Tape에는 `providerStatus` 요약이 포함된다. API는 `/api/data-reliability/provider-status`, `/api/data-reliability/market-data-files`를 사용한다.
- 사용자 노트는 계속 hypothesis이며 source reliability나 evidence count에 포함하지 않는다.

### Obsidian Workflow

- 로직은 `features/obsidian/workflow/`에 둔다. 기존 `features/obsidian/export/`의 Vault 설정을 재사용하고 새 설정 파일을 만들지 않는다.
- UI/API는 `company_thesis`, `market_memo`, `topic_review` 템플릿 노트를 생성할 수 있다. 이미 같은 파일이 있으면 기본적으로 덮어쓰지 않고 기존 경로를 안내한다.
- 생성 노트는 `source_layer: user_synthesis`, `reuse_as_hypothesis: true`를 가진다. `topic_review`도 Obsidian Import에서 hypothesis로 인식한다.
- Folio OS가 내보내는 1차 보고서/내러티브는 `generated_by: Folio OS`, `source_layer: primary_processed`, `reuse_as_evidence: false`를 가진다.
- frontmatter validator는 type/ticker/topic/source_layer/reuse_as_hypothesis 누락과 `generated_by`·`user_synthesis` 충돌을 감지한다.
- API는 `/api/obsidian-workflow/create-note`, `/api/obsidian-workflow/linked-notes`, `/api/obsidian-workflow/validate`를 사용한다.

### Fast-Origin Signals (빠른 시장 신호)

- 로직은 `features/common/research_library/signals/`에 둔다. 수집 단위는 metadata-only lead(제목/URL/시각/티커/신뢰 등급)이며 본문·이미지·provider raw response·비밀값을 저장하지 않는다.
- provider allowlist는 **기존 한국 RSS 하나**(`APPROVED_PROVIDERS = {"kr_existing"}`)다. 새 provider는 별도 계획 변경 없이 추가하지 않는다. 0.4.5에서 제외 확정: Benzinga(공개 피드 목록이 비어 있거나 404, 응답하는 피드도 시장 속보가 아님), FinancialJuice(한 줄짜리 지표 속보라 브리핑·기업분석 어느 쪽에도 쓰임 없음), Investing.com(공개 피드 주소 없음, 약관상 사전 승인 필요). 셋 다 어댑터·설정·env 키·UI·런타임을 모두 제거했다.
- **fast-origin 경로에 자격증명·사용자 설정이 없다.** `promote_kr_rss_leads()`는 이미 수집된 `evidence_items` 행을 다시 읽을 뿐 네트워크를 쓰지 않으므로 **RSS 수집 작업에 함께 실린다**. 대상 매체는 연합인포맥스·연합뉴스이며 매일경제는 일반 RSS로만 분류한다.
- provider 켜고 끄는 설정 화면과 `signal-provider-settings.json` 오버레이는 없다. 설정할 provider가 없기 때문이며, 다시 필요해지면 계획 변경으로 되살린다.
- lead끼리의 교차 확인(`corroborated`)은 독립 provider가 둘 이상일 때만 성립하므로 현재 도달하지 않는 경로다. 확인은 공식 자료 경로(`confirm_signal`)가 담당한다.
- **별도 `signals` 자동화는 0.5에서 삭제했다.** 승인 provider가 하나뿐이라 lead를 보여주는 화면이 없고, 하는 일이 RSS 수집과 겹쳤다. 설정 항목(`저지연 리드 수집`)과 스케줄 kind를 모두 없앴으며 승격은 RSS 수집이 계속한다.
- `evidence_items.intake_stage=lead`는 `is_countable_evidence()`에서 항상 제외되고 source ledger에 들어가지 않는다. corroboration/공식 확인 후 승격된 row만 evidence가 된다.
- retention 기본값: 일반 lead 3일, 티커가 연결된 lead 14일, corroborated 30일(`normalize_signal`은 `related_tickers`가 비었는지만 본다 — 워치리스트·포트폴리오 보유 여부를 따로 확인하지 않는다). **집행은 두 곳이다** — `promote_kr_rss_leads()`가 승격 전에 `purge_expired()`를 부르고(RSS 수집·`지금 수집` 버튼과 함께 돈다), `query_signals()`가 아직 지워지지 않은 만료 lead를 결과에서 뺀다. 승격만 남기고 purge 호출부를 없애면 보존 계약이 집행되지 않는다 — lead 행은 `markdown_path`가 비어 있어 `prune_orphan_evidence()`도 걷어내지 못한다.
- 상시 WebSocket 연결은 두지 않는다(`start_signal_runtime`은 lifespan 호환용 no-op).
- run log에는 provider/count/status/error code만 남기고 headline/raw payload를 남기지 않는다.
- **0.4.8부터 lead를 보여주는 화면이 없다.** 워치리스트 상세의 `빠른 시장 신호` 레일은 승인 provider가 하나만 남아 교차 확인이 불가능해졌고 lead 티커가 워치리스트 종목과 맞는 경우가 없어 제거했다. 승격·retention 런타임은 그대로 남아 대화 context(`sourceContext.fastSignals`)가 계속 읽는다.

### Change Intelligence

- 로직은 `features/common/change_intelligence/`에 둔다. 보고서/스냅샷 commit 시 artifact별 adapter(briefing/company/topic/market_memory)가 native 구조화 입력으로 `ChangeBasis`를 만들고 공통 comparator가 `changeSummary`를 생성한다. markdown은 comparator 입력이 아니다.
- status enum: `baseline_created | major_change | developing_signal | conflicting_uncertain | no_material_change | insufficient_basis`. `major_change`는 높은 materiality와 tier-1 근거 1개 또는 독립 tier-2 근거 2개 이상이 필요하며 unconfirmed lead만으로는 만들 수 없다.
- 권위 저장소: Briefing/Company/Topic은 보고서 JSON의 `changeSummary`, Market Memory는 `market_state_snapshots.payload_json`. `market-memory.sqlite3::change_event_index`는 양쪽에서 재구축 가능한 projection이며 projection 실패는 commit을 롤백하지 않는다.
- `change_event_index`의 PK는 `(artifact_kind, artifact_id)`다. 브리핑은 시장별로 저장되므로 `artifactId`에 시장을 붙인다(`2026-08-04.us`). 날짜만 쓰면 KR 커밋이 US 변화 이벤트를 덮어쓰고 Change Feed가 어느 브리핑을 열어야 할지 알 수 없다.
- 변화 단위의 `magnitude`는 [0,1] 범위의 상대 크기여야 한다. 브리핑 동인 점수처럼 상한 없는 합계를 절대값으로 쓰면 모든 재생성이 `major_change`가 된다. 동인은 그날 전체 점수 대비 비중과 순위로 비교한다.
- 변화 판정은 두 층이다. 규칙 비교기가 순위·비중·지표 이동과 증거 게이트를 결정하고, 의미 비교(`semantic.py`)가 브리핑 LLM 생성 잡 안에서 시장당 1회 대표 기사 제목을 대조해 `semanticVerdict` enum으로 내용 변화를 분류한다. `new_information/reversal`+증거 등급만 코드 게이트로 `major_change` 승격, `coverage_shift_only/no_new_information`은 강등, LLM 없으면 `not_evaluated`로 major 미확정. 변화 판정용 별도 Agent job은 만들지 않고 RSS/index job에는 change hook이 없다.
- 변화 단위의 대표 기사 제목은 `contextDocs`(hash 비교 밖)에 둔다. currentValue에 넣으면 제목 회전만으로 매일 모든 단위가 changed가 된다. 브리핑 저장 시 동인 `topDocs`(상위 3건 제목/출처/URL)와 이슈 대표 `title`을 보존한다.
- 수동 저장(`POST /api/analysis-reports`)이나 proposal 승인 편집은 새 change event를 만들지 않는다.

### 시장 캘린더 (Market Calendar)

- 로직은 `features/market_calendar/`에 둔다. `features/common/market_calendar.py`(거래일 helper)와는 별개 모듈이다.
- event kind는 `macro | central_bank | holiday | earnings | filing | dividend` 6종만 허용하고 `market-memory.sqlite3::market_calendar_events`에 upsert한다.
- `confirmed | estimated | tentative | actual`을 source tier로 결정한다. 회사 IR/공식 일정이 우선이고 yfinance/Nasdaq 등 제3자 예정치는 `estimated`로만 표시한다.
- NYSE/KRX 휴장일과 FOMC는 공식 발표 연간 일정을 adapter에 전사해 등재한다(confirmed + 공식 sourceUrl, 새 연도 공시 시 표만 갱신). 브리핑 세션 기준일은 코드가 결정하며, Toss Open API 거래소 캘린더가 연결되어 유효한 응답을 주면 해당 응답을 정적 휴장일 표보다 우선하고 미연결·실패·응답 불일치 시 정적 표로 fallback한다. 미국 지표 발표일은 `FRED_API_KEY`가 있을 때만 수집하고 없으면 `fred_key_required`를 남긴다. 실적/배당은 포트폴리오+워치리스트 티커 대상 yfinance estimated이며, 워치리스트 표시명은 SEC company_tickers 기반 `sec_ticker_for_name()`으로 해석한다.
- **FRED 발표 결과는 vintage로 맞춘다.** 최신 관측치를 지나간 모든 발표일에 붙이면 지난 발표가 전부 오늘의 숫자를 말한다 — 실측으로 8/12 CPI 행에 6월 관측치가, 7/2 고용 행에 7월치가 붙어 있었다. `output_type=3`(신규·개정분)의 `SERIES_YYYYMMDD` 열이 공표일이며, 발표일과 정확히 맞은 값만 붙인다. 그날 공표된 값이 없으면 비워 두고 `confirmed`로 남긴다 — 지난 값을 오늘 발표라고 말하지 않는다.
- **지표 수집 창은 과거 45일부터 연다.** 오늘부터 시작하면 결과가 실린 발표가 하나도 안 들어와 지난달 지표가 캘린더에 없다. 게다가 집계가 최근 날짜부터 내려주므로 한 창으로 과거까지 물으면 앞쪽 페이지가 전부 미래 일정으로 차서 과거에 닿지 못한다 — **과거 구간과 미래 구간을 따로 요청한다**(실측: 26건 전부 미래 → 83건 중 과거 57건 전부 결과 포함).
- yfinance 경제 캘린더에 `Expected`(컨센서스) 열은 있으나 값이 오지 않는다(과거·미래 네 구간 600여 건 전부 결측). 그래서 화면의 결과 비교는 예상치가 아니라 **직전 값** 기준으로 읽는다. `forecastValue` 필드는 다른 provider가 컨센서스를 주면 실리도록 남긴다.
- 실적·배당 추정은 매 수집마다 티커 목록에서 통째로 다시 만들어지므로, 이번 수집에 안 나온 `estimated` 행은 갱신 실패가 아니라 **더는 성립하지 않는 행**이다(`prune_stale_estimates`). 날짜로 자르지 않는다 — 시장 판정을 고쳤을 때 `8316.T` 실적이 도쿄와 뉴욕 두 줄로 남았고 둘 다 과거 날짜였다. 공식 일정(휴장·FOMC·지표)과 확정 행은 건드리지 않는다.
- 실적·배당 행은 `companyName`을 함께 싣는다(`_company_name.py`). 일본 구성종목은 `englishName`을 우선해 `三井住友フィナンシャルグループ` 대신 읽히는 이름을 쓰고, KOSPI 구성종목은 `373220`으로 저장되므로 `.KS`/`.KQ` 형태도 함께 색인한다.
- raw page/PDF를 장기 보존하지 않고 normalized event와 source URL만 저장한다. refresh는 automation job이며 Agent를 호출하지 않는다.

### Research Cockpit 대시보드

- 로직은 `features/dashboard/`에 둔다. 화면은 `cockpit` 하나이며 0.5에서 Legacy 모드를 삭제했다(저장된 `legacy` 설정은 `cockpit`으로 승격). 패널 순서는 변화 피드 → 시장 캘린더 → 네이티브 차트다.
- 기존 `data/market-widget-settings.json`은 삭제·수정하지 않고 read-only fallback으로만 읽는다. 새 설정은 `data/dashboard-settings.json`에 저장한다.
- 초기 cockpit payload에는 외부 network 호출·chart series·iframe이 없고 차트/일정 상세는 lazy fetch한다. 네이티브 차트는 `GET /api/market/chart`와 기존 Lightweight Charts 전역을 재사용한다.
- `무엇이 달라졌나` 패널 상단 `오늘의 이야기 비중`(`story_share.py`)은 그날 수집된 articles/rss 전체를 동인별로 묶은 보도량 비중이다(상위 4 + 그 외, 직전 거래일 %p 델타, 시장 토글 US/KR/EUROPE/JP). 규칙 계산 전용이고 브리핑과 독립이며, 비중 이동은 내용 변화가 아니라는 경고 문장을 UI에 고정한다. `GET /api/dashboard/story-share`는 10분 캐시, RSS 수집 시 무효화. **한 시장만 물어봐도 네 시장을 모두 계산해 캐시한다** — 인덱스 로드가 4.7초라 시장을 바꿀 때마다 그 값을 다시 치르고 있었다(시장당 6초). 문서를 한 번 읽어 온 김에 나머지를 채우면 첫 조회 8초·이후 전환 0초다. 날짜별 문서 선별과 문서별 동인 추론은 시장과 무관하므로 `_SharedWork`가 한 번만 계산한다. 내용의 변화 카드의 `Agent에게 묻기`는 dock을 열어 질문을 채울 뿐 자동 제출하지 않는다.
- 기존 `/api/dashboard` 응답은 기존 consumer 호환을 위해 유지한다.
- **이야기 비중의 비교 기준은 직전 5거래일 합산이다**(0.5.4). 하루끼리 비교하면 그날 수집량이 흔들리는 것만으로 비중이 수십 %p 움직인다. 날짜별 비중을 평균 내지 않고 창 전체를 하나의 분포로 세며, **문서는 한 번만 센다** — `select_briefing_docs`가 돌려주는 것이 세션 창(보통 이틀)이라 이웃 기준일의 창이 겹쳐 그대로 더하면 같은 기사가 두세 번 세어진다. 표본 부족 임계도 창 길이에 비례한다.
- **동인 어휘표(`DRIVER_TERMS`)는 브리핑 동인 선정과 공유하므로 측정 없이 손대지 않는다.** 0.5.4에서 `금` 한 글자를 뺐다 — 한글 토큰은 단어 경계 없이 부분일치라 금리·금융·자금·세금을 전부 물었고, 실측으로 문서의 14.8%가 그 한 어휘만으로 원자재/유가에 들어와 있었다(실제 매칭은 금리 2,712건). 원자재/유가가 35.0% → 20.4%가 됐다. **한 글자 한글 어휘를 새로 넣지 않는다.** `크립토`를 새로 등재했다.
- **의미 판정은 `llm`과 `agent` 두 모드에서 돈다**(0.5.4). Agent 산출물의 mode는 `agent`인데 예전에는 `llm`만 통과시켜 CLI 구성에서는 판정이 아예 돌지 않았고, `semantic.py`도 API 키만 봐서 이중으로 막혔다. 키가 없으면 Agent bridge로 같은 프롬프트를 보내되 **`serialize=False`로 부른다** — `_RUN_SEMAPHORE`는 재진입이 안 되고 브리핑 생성 잡이 커밋까지 그것을 쥐고 있어, 다시 잡으면 그 잡이 영원히 멈춘다.
- **화면은 "정상 판정된 변화 없음"과 "아직 판정 못 함"을 가른다.** 예전에는 확정 판정이 아닌 것을 전부 미판정으로 세서, 판정이 멀쩡히 끝난 날에도 이미 연결된 Agent를 연결하라고 안내했다. 의미 비교는 브리핑 변화 단위에만 걸리므로 다른 아티팩트에 verdict가 없는 것은 정상이다.

### 워치리스트 상세 (차트·실적)

- 상세는 **재무·투자 지표(회사 소개 세 줄 접기·섹터·산업 포함) → 네이티브 차트(가격·등락 표시) → 실적(지난 발표 분기 목록 포함) → 수집 뉴스** 순이며, 데스크톱에서 차트·실적이 2컬럼으로 나란히 선다. **섹션 구분은 면이 아니라 구분선과 여백이 맡는다** — 네 섹션을 회색 상자(`surface--group`)로 감싸는 안을 먼저 시도했지만 면이 많아지니 오히려 항목이 서로 구분되지 않았다(2026-08-21 사용자 피드백). 섹션 머리는 같은 문법(굵은 제목 + 아래 헤어라인)이고, 면은 실적의 "다음 발표" 강조 상자 하나만 남는다. 간격은 `.watchlist-detail-grid`의 gap 하나가 소유한다 — 자식 margin이 더해지면 섹션 간격이 갈려 무엇이 한 묶음인지 읽히지 않는다(실측으로 그랬다). 모바일 1컬럼 규칙은 **기본 그리드 정의보다 뒤에** 있어야 한다(같은 특이도라 앞쪽 media 블록은 진다).
- 재무·투자 지표는 `GET /api/market/fundamentals`(`features/common/market_data/fundamentals_service.py`) — yfinance `info`와 분기 손익계산서(매출·영업이익·순이익, 최근 5분기)를 차트와 같은 캐시 정책(1시간 TTL + 하루 stale-while-revalidate)으로 감싼다. **캐시 키에 스키마 버전이 들어간다** — 없으면 필드를 추가한 판올림 직후 TTL이 지날 때까지 옛 모양의 캐시가 내려와 새 화면이 조용히 비어 있다(실측). 각 지표에는 계산식 한 줄(주가 ÷ 주당순이익 등)을 붙이고, 분기 차트가 **이익/재무/안정성/현금흐름 네 세트**를 세그먼트로 전환한다(그리드라인·분기별 값 표 포함, 막대 스케일은 0 포함 — 적자를 0으로 접으면 "이익 없음"으로 읽힌다). **안정성(유동비율·부채비율)은 별도 탭의 선 차트다** — 금액 막대와 한 그림에 두면 축을 섞거나 밴드를 쌓아야 하는데 쌓아 보니 한 차트처럼 읽히지 않았다(2026-08-22 사용자 피드백). 선 스케일은 0을 강제하지 않고(29~35% 구간이 바닥에 눌린다), 비율의 증감은 %가 아니라 **%p**다. **세트마다 자기 색 농담을 갖는다** — 이익=초록, 재무=네이비(`--folio-chart-1`), 현금흐름=골드, 안정성 선=의미색(초록/버건디). 첫 계열(규모 기준)은 공통 중립 잉크이고, 한 세트 안에 여러 색을 섞지 않는다. hover 상자·판독 패널은 기업분석 차트의 클래스를 재사용한다. 회사 소개는 provider 원문(영문) 그대로다 — LLM 번역을 붙였다가 뺐다(키가 있는 설치만 한국어가 되는 반쪽 기능은 없느니만 못하다). **가격은 차트가 말한다** — 머리에도 올려 봤지만 차트 종가와 신선도가 갈려 두 숫자가 모순처럼 읽혀 차트 하나만 남겼다(2026-08-22 사용자 결정). **모바일 그리드는 `minmax(0,1fr)`이다** — `1fr`은 min-content가 셀을 밀어내 nowrap 값 한 줄로 모달에 가로 스크롤이 생긴다(실측 +26px). 프로필의 섹터·산업 값은 문장형이라 지표 행의 nowrap을 물려받지 않는다. 결측은 `—`로 표시한다(삼성전자의 PER처럼 provider가 실제로 비워 둔다). **배당수익률은 이미 % 단위다** — fraction으로 오해해 100을 곱하면 도요타가 326%가 된다. 출처 문구는 모달 하단에 11px로 하나만 둔다(패널마다 반복하지 않고, "등급" 같은 내부 용어를 화면에 쓰지 않는다). **TradingView 임베드는 0.5.4에 전부 걷어냈다** — 이 모달이 브리지(`public/tradingview-widgets.js`)의 마지막 소비자였고, iframe 세 장은 앱 토큰을 따르지 않으며 종목 정보·펀더멘털 위젯은 제목줄·실적 패널·기업분석과 역할이 겹쳤다. Lightweight Charts의 `attributionLogo`와 `THIRD_PARTY_NOTICES.md`는 그대로 둔다.
- 차트는 대시보드와 같은 `MarketChartFigure`다(그림 한 장만 갖고 종목 선택·설정 저장은 대시보드가 소유). 기간·유형은 이 화면 안에서만 살며 대시보드 설정을 건드리지 않는다. **트레이드오프**: 준실시간·지표를 잃고 yfinance 지연 시세를 쓰며 freshness 라벨로 지연을 밝힌다.
- 실적은 `GET /api/market/earnings`(`features/common/market_data/earnings_service.py`)이며 **상세를 열 때만** 부른다 — 티커당 provider 호출이라 카드 그리드에 걸면 종목 수만큼 네트워크가 된다. 차트·실적 요청은 상세 응답을 기다리지 않고 함께 시작한다(카드 표가 이미 티커를 안다).
- **다음 발표일과 컨센서스는 제3자 예정치다.** 확정 배지를 붙이지 않고 IR 재확인을 함께 적는다. 숫자는 yfinance라 기업분석의 SEC 숫자와 등급이 다르며(§6 절대 규칙 6) 패널이 출처를 적어 그 차이를 숨기지 않는다.
- **지난 분기의 매출 컨센서스는 어느 종목에도 없다.** provider가 다음 분기 것만 주므로 매출 서프라이즈는 재현할 수 없다. 빈칸이 아니라 "매출 컨센서스 없음"이라고 적는다 — 빈칸은 이 종목만 없는 것처럼 읽힌다.
- **작년 동기간은 인덱스로 세지 않는다.** `earnings_history`가 4분기만 주므로 4칸 뒤를 보면 가장 최근 분기의 작년 동기가 늘 비어 있다. 손익계산서는 더 뒤까지 주므로 연도만 빼고 종료월이 같은 키를 찾는다. 분기 이름도 **종료월**로 부른다 — 회계연도가 달력과 다른 회사(LRCX는 6월 결산)에서 번호를 뽑으면 틀린다.

### 입력 기업 판단 (Company Resolution)

- 로직은 `features/common/company_resolution.py`에 둔다. `GET /api/company/resolve?q=&limit=`을 쓰며 **LLM을 호출하지 않는다** — SEC `company_tickers.json`, DART 상장 종목, 수동 사전을 같은 기준으로 채점하는 규칙 기반이다.
- status는 `confident | ambiguous | unknown` 셋이다. **모르면 모른다고 답한다.** 예전 `infer_requested_company()`는 아무것도 못 찾으면 입력 문자열을 그대로 티커로 돌려줘, "하우멧"이나 오타를 넣어도 분석이 진행되어 빈 보고서가 나왔다.
- **DART 캐시는 상장 종목만 쓴다.** 전체 118,664건에는 비상장 법인이 대부분이라, 부분일치가 먼저 걸려 "마이크론"이 LG마이크론이 되고 "델타"가 신성델타테크가 됐다. `stock_code`가 있는 3,981건만 후보가 된다.
- 질의 문자로 시장을 가른다. 라틴 문자면 미국장, 한글이면 한국장에 가산한다(`MICRONIX`도 "Micron"에 접두 일치하기 때문).
- 질의 **전체**가 티커 모양일 때만 티커로 본다. 문자를 걷어낸 나머지를 쓰면 "없는회사이름123"이 "123"이 되어 한국 코드에 붙는다.
- 정확한 티커 일치는 이름 접두 일치를 이긴다(`MU`가 MUELLER INDUSTRIES와 저울질되면 안 된다).
- SEC는 클래스 구분에 하이픈을 쓴다. `BRK.B`는 `BRK-B`로 정규화한다.
- SEC 파일에 한글 표기가 없으므로 한국 사용자가 실제로 치는 표기(마이크론·알파벳·존슨앤존슨 등)는 `company_lookup`의 수동 사전 별칭으로 보정한다(원칙 10의 "별칭·예외 보정" 용도).
- **자국 원주와 미국 ADR은 다른 증권이다.** 도요타는 도쿄(`7203.T`)와 뉴욕 ADR(`TM`) 양쪽에 있고 통화·시간대·가격이 다르다. `prefer_home`(`GET /api/company/resolve?prefer=home`)은 둘이 갈릴 때 자국 상장을 대표로 세운다. **워치리스트만 쓴다** — 기업분석은 SEC companyfacts와 10-K가 붙는 등록분이라야 보고서가 채워지므로 기본값이 계속 SEC다.
- 일본·유럽 구성종목 파일에 `englishName`을 함께 저장한다(생성 시 yfinance `longName`). 위키백과 표기만 두면 `トヨタ自動車`라 "Toyota"로 찾을 때 자국 상장이 후보에 아예 없었다. 표시 이름은 라틴 문자 쪽을 고르고 자국 표기는 별칭으로 남는다.
- 한글 별칭은 `config/foreign_company_aliases.json`에 둔다(키는 yfinance providerSymbol). 구성종목 파일은 다시 생성되므로 거기 적으면 사라진다.
- 같은 회사로 묶는 기준은 표시 이름 하나가 아니라 **그 항목의 모든 이름**(영문명·별칭 포함)이다. `トヨタ自動車`와 `TOYOTA MOTOR CORP`는 글자가 하나도 겹치지 않는다.
- 가산점은 같은 등급 안의 저울이다. 정확한 이름 일치가 접두 일치를 이긴다(`_tier`) — "Mitsubishi Corporation"이 미국장 가산점을 받은 MUFG의 접두 일치와 동점이 되어 매번 애매로 떨어졌다.
- 화면은 기업분석 입력칸에서 생성 전에 무엇으로 읽었는지 보여주고, 애매하면 후보 목록을, 모르면 경고를 낸다. 확정된 경우 `/api/analyze`에는 원문이 아니라 티커를 보낸다.
- **워치리스트 카드의 `N건`은 색인 전체에서 그 회사가 언급된 뉴스 문서 수다.** 카드와 상세가 `watchlist_news()` 하나에서 나온다 — 예전에는 카드만 검색 상위 200건 안에서 세어 AMD가 295건인데 69건으로 나왔고, 매칭이 0건이면 검색 결과 개수를 그대로 써서 색인에 한 건도 없는 Howmet Aerospace가 107건으로 보였다(같은 항목의 상세는 0건). 종목은 실제로 언급된 문서만 뉴스이고 없으면 없다고 말한다. 테마 키워드는 검색 결과가 곧 답이다.
- 연결 열쇠는 **종목 코드**다. 워치리스트는 해석된 정식명(`ADVANCED MICRO DEVICES INC`)을 저장하는데 기사에 붙은 회사는 `AMD`라 이름끼리 한 글자도 겹치지 않는다. 코드가 없거나 표기가 다를 때(도쿄 `6501.T` vs ADR `HTHIY`) 이름이 받는다.
- 워치리스트·포트폴리오 입력도 같은 해석기를 쓴다. 워치리스트는 주제 키워드를 함께 받으므로 `unknown`이 오류가 아니라 키워드이며, 이름 일부만 겹친 약한 후보(`strong: false`)에는 후보 목록을 띄우지 않는다("반도체"에 한미반도체가 걸린다고 목록을 열면 안 된다). 포트폴리오 보유 표는 입력을 벗어날 때 한 번만 해석해 티커로 바꾸고 비어 있는 시장 칸을 채운다(표 안이라 글자마다 호출하지 않는다).

### Agent 대화 (Threads)

- 로직은 `features/agent_mode/consultation_*.py`에 둔다(내부 식별자는 저장 데이터와의 계약이라 유지). `data/agent-threads/{id}.json` JSON-per-thread가 권위 저장소이며 research inbox/index 경로 밖이라 어떤 evidence loader·indexer도 읽지 않는다. 예전 `data/agent-consultations/`는 첫 사용 시 1회 이관한다(복사 후 삭제, 이름 충돌 시 양쪽 보존).
- **도크가 대화의 집이다.** 주제가 붙은 대화(워치리스트·포트폴리오·보고서)는 도크 아래 한 종류이며 별도 상담 패널을 만들지 않는다. 화면 용어는 전부 `대화`이고 주제는 칩으로 보여준다. `상담`은 전문가 조언을 뜻해 §5 원칙 3(사용자 생각을 옹호하지 말고 검증한다)과 충돌하므로 화면에서 쓰지 않는다.
- 세션·메시지·노트 snapshot은 `layer=hypothesis`, `sourceLayer=user_consultation`, `reuseAsEvidence=false`를 코드 상수로 강제하고 화면에도 그 경계를 표시한다.
- scope를 주지 않으면 `general`이다. 알 수 없는 kind를 `portfolio`로 떨어뜨리지 않는다(주제 없는 대화에 포트폴리오 맥락이 딸려 들어간다).
- **생성 경로는 하나다.** 스레드 러너(`job_runtime.run_consultation_job`)는 맥락 조립과 저장만 하고 생성은 도크와 같은 `chat.run_agent_chat`에 위임한다. 제안 생성·거절 같은 사건도 같은 transcript에 남겨 다음 세션의 Agent가 같은 제안을 반복하지 않게 한다.
- 모델 입력은 전체 transcript가 아니라 rolling summary + 최근 8개 메시지 + 서버가 **매번 다시 조회한** 최신 리서치 context로 구성한 32,000자 이하 pack이다. 저장된 옛 시세/브리핑을 재생하지 않는다.
- **답변 본문은 잡 결과가 아니라 스레드에서 읽는다.** 잡 결과는 `data/jobs.json`과 Work Log에 남으므로 transcript를 담지 않는다.
- user turn을 먼저 저장한 뒤 Agent job을 실행하므로 재시작 후에도 질문이 남고 retry할 수 있다. `operationId`로 중복 응답을 막는다. 저장 성공 후 폴링이 실패해도 작성칸을 되돌리지 않는다(재전송이 새 `operationId`로 같은 질문을 두 번 저장한다).
- **빈 대화는 저장하지 않는다.** 스레드는 첫 메시지에서 만들어진다. `새 대화`와 `짚어보기`는 화면 상태만 바꾸고 주제는 `pending`으로 들고 있다가 첫 질문에서 함께 넘긴다. 예전에는 도크를 열 때마다 만들어서, 아무것도 묻지 않고 떠난 대화가 목록에 남았다.
- **인사말은 대화가 아니다.** 저장·이관 모두 `storage.ts::isGreeting()` 하나로 거른다. 저장은 `id`로, 이관은 `variant`로 걸렀던 적이 있는데 인사말에는 `variant`가 없어 이관 필터가 한 번도 걸리지 않았고, 브라우저가 새로 열릴 때마다 인사말 한 줄짜리 스레드가 저장됐다(실제로 54개가 쌓였다).
- **제목은 첫 질문에서 만든다.** 기본 제목일 때만 40자로 잘라 넣고 사용자가 붙인 제목은 건드리지 않는다. 전부 `새 대화`면 목록에서 대화를 구분할 단서가 없다.
- 대화 관리(목록·전환·제목·보관·삭제)는 도크가 소유한다. 삭제는 확인을 받고 저장소도 `confirmed` 없이는 지우지 않는다.
- memory 갱신은 규칙 기반 rolling summary다. 계획의 구조화 memoryPatch 계약은 미도입 상태이며 상세는 `.planning/folio-os-0.4-x-research-intelligence/task_plan.md`의 구현 편차 기록을 본다.
- `노트로 정리` 명시적 action만 Native Investment Note snapshot을 만들며 노트에도 `consultationRef`와 hypothesis 경계가 유지된다.
- Work Log/API/exception/telemetry에 transcript·session memory·Portfolio 민감 context를 남기지 않는다.
---

## 11. 실행에 필요한 것

- Windows와 macOS 모두 지원한다.
- Python 3가 필요하다. Windows는 `py -3`, macOS/Linux는 `python3`을 사용한다.
- 필수 Python 패키지는 [requirements.txt](requirements.txt)에 있다.
- 시장 가격 스냅샷은 `yfinance`가 있으면 활성화된다. 한국장 수치도 yfinance를 쓴다(pykrx는 KRX 계정을 요구해 2026-08-12에 제거).
- `polars`는 대량 문서 필터링, 점수 정렬, 재무/포트폴리오 집계 계산 엔진으로 사용한다.
- Jinja2는 규칙 기반 기업분석 보고서에 필요하다.
- Node.js는 React SPA 개발, typecheck/test/build, 그리고 bridge JS 문법 검사에 필요하다. 일반 0.2 사용자 패키지는 최신 `public/react/folio-react.js`가 포함되어 있으면 Node.js 없이 실행할 수 있다.
- LLM 기능은 선택 사항이다. API Key가 없으면 규칙 기반 fallback이 동작해야 한다.
- SEC API 안정 사용을 위해 `.env`에 `SEC_USER_AGENT`를 둘 수 있다.

```text
# Windows
start-archive.cmd
# macOS / Linux
bash start.sh
```

접속 주소: `http://localhost:8787`

---

## 12. 검증 명령

코드 수정 후 가능한 범위에서 최소 검증을 실행한다.

```powershell
py -3 -m py_compile app.py
py -3 -m py_compile features\common\research_library\rss\rss_archive.py
node --check public\app.js
```

서버가 켜져 있다면 API 확인:

```powershell
Invoke-RestMethod -Uri http://localhost:8787/api/dashboard
Invoke-RestMethod -Uri "http://localhost:8787/api/rss/items?offset=0&limit=20"
```

---

## 13. 개발 메모

- `app.py`가 커져 있지만 새 기능의 실제 로직은 가능하면 `features/<feature_code>/` 아래로 분리한다.
- SQLite/JSON은 저장소와 검색 인덱스 역할을 유지하고, 반복적인 필터링/정렬/집계는 `features/common/dataframe_ops.py`의 Polars 유틸을 우선 사용한다.
- 여러 기능이 공유하는 코드는 `features/common/`에 둔다.
- `data/index.json`은 상태 요약 파일로, 문서/파일 매니페스트는 `research-index.sqlite3`에 있다. 인덱싱 관련 로직을 변경하면 브리핑, 검색, 기업분석이 동시에 영향받는다.
- 문서 수정 시 AGENTS/CLAUDE는 AI 작업자 관점, README/README.ko는 일반 사용자 관점으로 유지한다. README.dev는 예전 상세 사용자/개발 문서 백업이며 일반 0.2 릴리즈 패키지에는 포함하지 않는다.
- README는 프로젝트를 처음 사용하는 사람이 읽는 문서다. 0.2에서 실제로 보이는 기능의 목적, 화면에서 하는 일, 필요한 입력 자료, 저장 위치, 주의점을 쉬운 말로 설명한다. 내부 구현 추적, Step 번호 중심 설명, 후속 아이디어, 숨김/비활성 기능을 현재 기능처럼 서술하지 않는다.
- README는 기본적으로 화면 탭 단위로 정리한다. 여러 탭에서 함께 쓰는 자료·품질·연동 기능은 `features/common/` 또는 명확한 통합 폴더(예: `features/obsidian/`)의 상위 README에서 관리하고, 하위 README를 불필요하게 늘리지 않는다.
- `roadmap/`은 개인 개발용 로컬 계획 폴더이며 GitHub/source archive/릴리즈 패키지에는 포함하지 않는다. 새 대형 작업은 `master`에서 독립 브랜치를 따고, 사용자가 로컬 roadmap 문서를 유지하는 경우에만 그 문서에 제품 순서와 진행 상태를 반영한다.
- 앞으로 계획 관리는 GitHub Issues와 로컬 계획문서를 함께 사용한다. 공개적으로 추적할 작업은 GitHub Issue를 기준으로 삼고, 세부 실행 메모·개인 맥락·agent handoff는 `roadmap/` 또는 공개-safe한 `docs/superpowers/` 계획문서에 둔다. 자세한 규칙은 `docs/PLANNING_WORKFLOW.md`를 따른다.
- 브랜치를 `master`에 머지하기 전에, 변경을 작성한 세션이 아니라 **새 컨텍스트에서 diff를 리뷰한다**(서브에이전트 리뷰 또는 `/code-review`). 작성자 세션은 자기 가정을 그대로 물려받아 같은 오류를 놓친다. 리뷰어에게는 변경 의도와 관련 기능 README를 함께 주고, 특히 §5 아키텍처 원칙(2계층 분리, 3계층 데이터 위계, 확증편향 방지, enum 검증, 자기참조 금지) 위반 여부를 확인한다.

---

## 14. 문서 관리 규칙

기능을 추가하거나 수정할 때 문서를 함께 갱신한다.

- **새 기능 폴더 생성 시**: 반드시 `features/<feature_name>/README.md`를 함께 만든다. 담당 범위, 관련 코드, API, 주의점을 포함한다.
- **기존 기능 수정 시**: 해당 기능의 README를 수정 내용에 맞게 업데이트한다. API 추가/변경, 동작 변경, 환경 변수 추가가 있으면 반드시 반영한다.
- **`features/README.md` 테이블**: 새 기능 폴더를 만들면 폴더 역할 테이블에 한 줄 추가한다.
- **`AGENTS.md`와 `CLAUDE.md`**: 본문을 항상 동일하게 유지한다. 기능 카탈로그(§8)·링크 목록(§9)·기능 경계(§10)에 새 기능을 두 파일 모두 반영한다.
- **`README.md` / `README.ko.md`(최상위 사용자 문서)**: 사용자가 직접 쓰는 기능만 현재 기능으로 설명한다. 두 문서는 같은 제품 범위를 유지한다.
- **README에 버전을 박지 않는다**: 제목·본문 어디에도 릴리즈 번호를 넣지 않는다(`## What You Can Do` / `## 할 수 있는 일`). 버전은 `VERSION` 파일과 버전 이름이 붙은 배포 폴더가 이미 말하며, README에 넣으면 릴리즈마다 고쳐야 하는데 얻는 것이 없다. `web/tests/test_navigation_contract.py`가 검사한다.
- **README는 릴리즈 노트가 아니다**: 최상위 README는 "이걸로 뭘 할 수 있나"만 간략히 적는다. 동작 규칙과 경계(세션일 기준, 보도량 이동의 의미 등)는 기능별 README가 갖는다.
- **README에 스크린샷을 넣지 않는다**: 화면 미리보기 섹션을 두지 않는다. 이미지는 UI가 바뀔 때마다 낡고, 낡은 스크린샷은 없는 것보다 나쁘다. 화면 설명은 글로 한다.
- **README 용어는 화면과 같아야 한다**: 화면에서 쓰지 않는 내부 용어(hypothesis, Canonical, provenance, bounded, metadata-only, freshness, artifact, fallback 등)를 사용자 문서 설명 문장에 쓰지 않는다. 기능명과 짧은 영문 부제목(Deep Research, Market Memory, Smart Collection)은 허용하되, 그것이 무엇인지 설명하는 문장은 화면에 표시되는 말과 같은 단어로 쓴다. UI 문구를 바꾸면 README도 함께 바꾼다.
- **`README.dev.md`**: 이전 장문 README 백업이다. 일반 사용자 릴리즈 문서로 링크하거나 포함하지 않는다.
- **신규 기능 표기 규칙**: §8에서 "구현됨 / 구현 예정"을 분리해 유지한다. 예정 기능은 구현 완료(해당 Step의 Acceptance Criteria 충족) 전까지 "있는 기능"으로 서술하지 않는다.
