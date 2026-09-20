# 프론트엔드 UI

이 기능은 로컬 웹 워크스페이스의 화면 구성, 내비게이션, Agent Dock, 보고서 리더, 렌더링, 반응형 대응을 담당합니다.

## 현재 프론트엔드 구조

기업 분석은 생성 응답의 본문을 목록 갱신보다 먼저 표시한다. 목록 조회 실패가 이미 받은
본문을 숨기거나 생성 실패로 바꾸지 않으며, `saved: true`인 경우에만 자동 저장 성공을
안내하고 저장본 URL로 이동한다. 미저장 결과도 기존 리더에서 읽고 닫을 수 있지만
영구 보관으로 표시하지 않는다. 검수 미완료 안내는 기존 보고서 상태 줄에 표시한다.

**React SPA가 기본 프론트엔드다.** 기본 URL(`/`)에서 `web/`(Vite+React+TS, 빌드 산출물 `public/react/folio-react.js`)의 React shell이 렌더되고, route(home/dashboard/watchlist/briefing/rss/market-memory/analysis/deep-research/settings)는 React 네이티브다. 0.2 기본 nav에는 home/briefing/rss/market-memory/analysis/deep-research/settings를 노출하고 dashboard/watchlist는 딥링크 호환 route로 유지한다. `public/index.html`은 `#folioReactRoot`와 script/style 로딩만 갖는 최소 entrypoint이며, `public/app.js`는 React가 재사용하는 bridge-only 파일이다(`FolioBridge`: `renderMarkdown`, `splitReportTitle`, `briefingSourcePanelHtml`, `renderBriefingVisuals`, `updateAgentContext`, `openAgentDock` 등).

우측 전역 Action Panel은 제거되었다. 보고서 조작은 리더 내부 조작 레일과 노트 패널에서 처리한다.

## Portfolio 현황과 편집 흐름

Portfolio는 `보유·평가 | 투자 리뷰 | 프리셋 | 백테스트`를 유지한다. 기본 화면은 저장된
평가/집중도와 읽기 전용 보유 행이며 `보유 편집`에서 초안을 연다. 투자 리뷰는 요약·변화·
중요 반증/위험 뒤에 행동을 배치하고 자료·이력은 펼침으로 제공한다. 빈 화면의 바로가기는
기존 하위 탭만 이동하며 자동 생성/저장을 하지 않는다. 기존 프리미티브와 토큰을 사용하고
모바일 보유 표는 좁은 화면에 맞춰 재배치한다. API/권위와 계산 계약은 변경하지 않는다.

투자 리뷰는 투자 논리 미작성·최신 검토 미작성·검토 후 자료 부족을 구분한다. 반복되는
자료 부족 문구는 묶되 중요한 반증과 기한 경과는 작업 버튼 앞에 남긴다. 연결 자료는
기존 보고서 reader로, 날짜 이력은 해당 날짜의 저장본으로 이동한다. 이전 형식 revision 0은
읽을 수 있지만 검토 완료/Agent 반박은 비활성화하며 새 생성은 명시적 갱신에서만 실행한다.

## 설정 화면의 결과 알림

설정의 `AI` 탭에서 `AI Agent 연동`과 `AI Agent 모델 설정`을 편집한다.
AI Agent 모델 설정에는 `전역 모델 설정`과 `작업별 모델 설정`이 있으며, 작업별 화면에는 브리핑·기업분석·딥 리서치·시장 내러티브 네 행만 보인다.
`별도 설정 사용`을 켠 작업은 실행 방식·제공자·모델·추론 강도를 별도로 저장하고,
끄면 전역 설정을 따른다. 끄더라도 이전 별도 설정은 남으며,
`작업별 변경 취소`는 저장 전 변경을 되돌린다. 전역 패널과 작업별 패널은 저장·취소가
서로 독립적이다. 각 작업의 `연결 확인`은 API에서는 선택 모델 조회만, CLI에서는
설치·로그인 상태만 확인한다. 전역 AI Agent가 꺼져 있어도 작업 설정은 편집할 수 있지만
AI 실행은 허용하지 않는다.
저장 오류는 해당 패널 알림으로 표시하며 Agent 대화 설정은 별도로 유지한다.

`AI Agent 모델 설정`의 모양 계약(2026-09-07 정리):

- 패널 머리는 다른 설정 패널과 같은 `.input-panel-header`다. `.settings-provider-head`는 Toss처럼
  패널 **안** 하위 블록의 `strong` 제목용이라, 거기에 `h3`를 넣으면 규칙이 없어 브라우저 기본값
  (19.89px/700 + 위아래 여백)으로 떨어진다 — 옆 패널의 24px/800과 어긋났다.
- 위계는 패널 제목 24px → 하위 단 제목(`.settings-subsection-heading h4`) `--fs-title` 20px →
  행 제목 17px → 요약 15px이다. 하위 단을 16.5px으로 두면 자기가 묶는 행보다 작아진다.
- 작업 목록은 같은 탭 위쪽 CLI 제공자 목록(`.cli-provider-list`)과 같은 리듬을 쓴다 —
  목록이 윗선, 행이 아랫선, 행 패딩 `--sp-4`.
- 필드 열 수는 뷰포트가 아니라 **남은 폭**이 정한다(`repeat(auto-fit, minmax(150px, 1fr))`).
  창이 1100px이어도 도크가 열리면 패널이 372px까지 좁아지는데, 뷰포트 미디어 쿼리는 그때
  발동하지 않아 셀렉트가 42px로 줄어 값이 아예 보이지 않았다. 안내·검증·확인 결과는 이 격자
  **밖**, 행의 직접 자식으로 둔다 — 전 열을 점유하는 자식이 있으면 `auto-fit`이 빈 열을 접지
  못해 넓은 화면에서 오른쪽에 빈 열이 남는다.
- 패널의 면·자식 간격·패널 사이 간격은 `.settings-panel`과 `.sub-tab-panel`이 이미 갖는다.
  다시 선언하면 이 패널만 위 패널과의 거리가 18px에서 34px로 벌어진다.

각 패널의 저장·정리 결과는 **그 패널 안, 누른 버튼 바로 아래**에 뜹니다(`PanelNote`). 예전에는 화면 맨 위 한 곳에 모았는데, 문서상 1,991px에 있는 `자동화 저장`을 눌러도 메시지가 54px에 떠 뷰포트 720px 기준 두 화면 반 위에 있었습니다 — 보이지 않는 확인입니다.

- 알림은 한 번에 하나입니다. 어느 패널이 방금 무엇을 했는지가 헷갈리면 안 됩니다.
- 화면 전체를 못 불러온 오류만 상단에 남습니다. 어느 패널의 일도 아니기 때문입니다.
- 성공은 `react-dashboard-warning`, 실패는 `react-dashboard-error`이며 `role="status"`를 답니다.

## React SPA 전환 방향

`web/` React/TypeScript SPA가 routing, navigation, Agent Home, Deep Research, Dashboard, Report Reader, Notes, Settings를 소유한다. `public/app.js`는 더 이상 화면 상태나 view 전환을 관리하지 않고, 검증된 Markdown/visual/source 렌더러를 React에 제공하는 bridge-only 역할만 맡는다. React 전환 자체는 로컬 계획문서 `REACT_SPA_REWRITE_PLAN.md`에 완료 이력으로 남긴다.

`#/office`는 0.3.0의 기본 Home인 Pixel Office다. read-only `/api/pixel-office` 요약을 7개 의미 있는 오브젝트로 표시하고, 기존 `/api/jobs`의 redacted 프론트 모델을 이용해 Agent 활동·완료·실패 상태를 갱신한다. 데스크톱에서는 lazy-loaded PixiJS 게임 장면+React semantic hotspot+overlay 상세 패널을 사용하고, 980px 이하에서는 Agent 미니 장면+상태 카드+하단 시트를 사용한다. Agent는 authored waypoint 경로로 대응 가구까지 실제 이동하며 발 위치로 Y-depth를 정렬한다. 상세 dialog는 Escape, focus trap, 원래 오브젝트 focus 복귀를 지원한다. 캐릭터 preset은 프로젝트 원본 `Classic Analyst`와 `Economics Student` 두 개만 노출하며, 사용자 이름과 움직임 줄이기 설정을 함께 저장한다.

`#/home`은 React가 직접 렌더하는 기존 Agent Home이다. Home은 큰 `Folio Board` hero, 빠른 실행, 최근 보고서 칩 디자인을 유지하면서 hero와 빠른 실행 사이에 Codex/검색 메인 화면형 프롬프트 박스를 둔다. 프롬프트 전송은 `/api/agent/chat`으로 job을 만들고 `/api/jobs/{id}`를 polling하며, 수정 proposal은 `/api/agent/proposals/{id}` 승인/거절 API를 사용한다. 모델 선택은 `/api/agent-bridge/settings`의 현재 provider/adapter `modelChoices`를 따른다. 대화 로그는 보고서 evidence와 분리해 브라우저 localStorage에 저장하고, 사용자가 `새 대화`로 즉시 비울 수 있다. Home 하단에는 `/api/jobs` 기반 최근 Agent/빠른 실행 작업 목록을 표시한다.

Pixel Office와 Agent Home은 `web/src/app/agentWorkspace/`의 같은 브라우저 대화·모델·proposal·최근 작업 상태를 사용한다. 첫 실행 chooser, 각 Home의 전환 버튼, Settings > 화면에서 기본 Home을 선택한다. 명시한 보고서 딥링크는 이 선택으로 바뀌지 않는다. 두 Home에서는 전역 Agent Dock을 표시하지 않는다.

`#/dashboard`는 React monitoring route지만 0.2 기본 사용자 nav에서는 숨긴다. `/api/dashboard`로 인덱스·최근 보고서 현황을, `/api/investment-review`로 투자 리뷰 요약·체크포인트·포트폴리오 영향을 읽고, 투자 리뷰 갱신은 `POST /api/investment-review/generate`를 사용한다. Current Market 위젯 보드는 0.5에서 Legacy 모드와 함께 삭제됐고, 대시보드 차트는 `MarketChartFigure`(`/api/market/chart` + Lightweight Charts)가 그린다.

`#/briefing`은 React 저장 브리핑 route다. 목록 화면은 공통 `RouteHero`와 브리핑 생성 설정 패널, 저장 브리핑 검색 패널을 사용한다. 검색 패널은 `/api/briefings/index`의 `q`, `marketScope`, `briefingType`, `dateFrom`, `dateTo` 파라미터를 직접 사용한다. `#/briefing/{date}/{us|kr|both}` detail hash에서는 `/api/briefings/{date}?includePersonal=true&marketScope=...`를 호출해 `ReportReaderShell` 안에서 Canonical markdown을 표시한다. 브리핑 detail action rail은 AI/노트/내보내기 그룹으로 분류하고, Personal Overlay 생성, Agent 문의, Notion/Obsidian export를 직접 처리한다. note slot은 Native Notes API(`/api/investment-notes`)에 `market_memo`를 저장하고 linked notes를 조회한다. 리더 본문(`ReportBody`)은 별도 파서를 두지 않고 `FolioBridge`의 `renderMarkdown()`·`splitReportTitle()`·`briefingSourcePanelHtml()`·`renderBriefingVisuals()`를 재사용해 표·링크·리스트·가격 차트·히트맵·소스패널 parity를 확보한다.

브리핑 리더와 아카이브 카드의 시장별 제목은 `시장 세션일 + 마감/장중`을 표시한다. 리더 hero는 보고서 날짜와 실제 생성 시각(KST)을 구분하고, 구 저장본에 생성 시각이 없으면 미상으로 표시한다. URL·삭제 대상·기본 정렬은 발행일(`reportDate`) 기준을 유지한다.

브리핑 본문의 HTML 객체는 내용이 같으면 유지해 외부 차트 DOM이 관련 없는 재렌더에 지워지지 않게 한다. 주간 이야기 비중은 기존 저장 비중을 재계산하지 않는 주제별 선그래프(0–100%)이며, 결측은 선을 끊고 0과 구별한다. 날짜 선택·기사 수·전체 값 표로 터치/키보드에서도 읽고, PNG 내보내기는 선과 범례·날짜별 분모를 포함한다. 첫 문장을 차트 앞에서 읽고, 지수와 히트맵 사이에는 본문 설명을 둔다. 주간 지수의 주초 종가 기준 흐름과 전주 종가 기준 전체 성과는 범례에서 구별한다.

참고자료는 작성 입력·연결 기사·본문 참고자료의 합집합을 접어서 제공하고, 추적 query만 다른 링크는 중복 제거한다. 목록 자체를 검증된 주장 근거로 표시하지 않는다. 모바일 일정표는 내부 가로 스크롤을 사용하고 날짜·상태를 글자 단위로 접지 않는다. 인라인 본문은 페이지 세로 스크롤을 공유한다. 데스크톱 `읽기에 집중`은 조작·노트를 접고 다시 펼치며 작성 중 노트를 유지한다. 노트 닫기는 모바일 노트에만 표시한다.

`#/rss`는 React RSS route다. `/api/rss/items`로 20개 단위 feed를 읽고, 시작/종료/소스 필터와 페이지네이션을 관리한다. `POST /api/rssarchive/import` job polling으로 RSS 수집을 실행하고, `/api/rss/merge`를 통해 현재 필터 범위의 Markdown 병합 파일을 다운로드한다.

`#/market-memory`는 React Market Memory route다. `MarketStateDashboard` component가 `/api/memory/state-dashboard?limit=5`의 “현재 중기 시장 상황 + 핵심 드라이버” 구조를 표시한다. route 헤더의 `시장 메모리 업데이트` 버튼은 `/api/memory/update`로 중기 내러티브 누적과 현재 화면용 스냅샷 생성을 하나의 서버 작업으로 실행한다. CLI 작업은 화면이 열려 있는 동안 고정 타임아웃 없이 완료까지 자동 추적하고, 화면 재진입 시 저장된 job id로 같은 작업에 재연결한다. 새 외부 자료는 스냅샷 생성 후 24시간 유예 뒤 `업데이트 필요`, 스냅샷 생성 후 72시간을 초과하면 `최신성 만료`로 표시한다. 생성 방식은 설정 탭의 AI Agent 정책을 따른다.

`#/analysis`는 React Company Analysis route다. `/api/analysis-reports`로 저장 피드를 읽고, `/api/analyze?q=...&analysisStyle=beginner|advanced`로 기업 분석을 생성하며, Agent job 응답이면 `/api/jobs/{id}`를 polling한 뒤 저장 보고서를 다시 연다. 저장 카드 클릭은 `#/analysis/{reportId}` detail hash로 공통 `ReportReaderShell` 기반 reader를 열고, route 안에서 삭제와 목록 복귀를 처리한다. 저장 보고서의 `analysisCharts`는 reader 안에서 기업 분석 시각화 카드로 렌더한다.

React Shell은 레거시 shell과 같은 큰 구조를 직접 렌더한다: dark topbar, 접을 수 있는 floating 좌측 navigation rail, 가운데 scrollable route host, 우측 Agent Dock. 0.2 노출 화면인 브리핑·RSS 피드·시장 내러티브·기업분석·딥리서치·설정 목록 화면은 공통 `RouteHero`를 사용한다. 대시보드·워치리스트 route 구현은 유지하지만 기본 nav에는 노출하지 않는다. 레거시 기업분석 탭과 같은 흰색 hero 카드(골드 eyebrow, 제목, 설명, 우측 액션 슬롯)를 기준으로 맞추며, 브리핑 목록은 hero 아래에 레거시 브리핑 탭의 생성/검색 패널을 유지하고, 보고서 reader 내부의 dark report hero와 본문 레이아웃은 별도로 유지한다.

React Shell의 타이포그래피는 새 값을 만들지 않고 레거시 토큰을 따른다. 좌측 navigation title/item은 `--fs-base`, 그룹 라벨은 `--fs-xs`, route hero 제목은 `--fs-xl`, 설명은 `--fs-base`를 사용한다. 홈 화면의 큰 `Folio Board` title은 레거시 `.home-hero` display scale을 유지하되, React Home에서는 prompt 위치를 고정하고 hero만 위로 당겨 title과 prompt 사이 여백을 확보한다.

좌측 navigation 아이콘은 알파벳 배지가 아니라 탭 의미에 맞춘 outline SVG를 사용한다. 개별 아이콘 선택은 실제 UI 디자인에서 지정한 매핑을 따른다.

`#/deep-research`는 React Deep Research route이며 0.2 좌측 nav/Home 빠른 실행/command palette에 노출된다. `/api/topic-reports/plan`에서 승인 계획과 자료 preview를 받고, 승인된 envelope만 `POST /api/topic-reports` SharedJob으로 실행한다. `/api/topic-reports`로 저장 피드를 읽고 `/api/jobs/{id}`를 bounded polling한 뒤 저장 보고서를 다시 연다. 저장 카드 클릭은 `#/deep-research/{reportId}` detail hash로 공통 `ReportReaderShell` 기반 reader를 열고, route 안에서 삭제와 목록 복귀를 처리한다. 폼과 저장 피드는 `topicrpt-*`, `report-feed-*`, `input-panel`, `filter-btn` 클래스를 재사용해 기존 디자인 언어를 유지한다.

`#/watchlist`는 React Watchlist route지만 0.2 기본 사용자 nav에서는 숨긴다. `/api/watchlist`로 저장 목록을 읽고 저장하며, `/api/watchlist/resolve`로 티커/회사명을 정규화하고, `/api/watchlist/overview`로 카드용 태그·뉴스 카운트를 읽는다. 카드 클릭은 `#/watchlist/{item}` detail hash로 상세 화면을 열고, `/api/watchlist/detail`로 회사 정보·뉴스를, `MarketChartFigure`로 시세 차트를, `EarningsPanel`(`/api/market/earnings`)로 실적을 함께 보여준다. 카드와 상세 화면은 `watchlist-*`, `compact-item`, `input-panel`, `filter-btn` 클래스를 재사용한다.

`#/settings`는 React Settings route다. `/api/settings`, `/api/agent-bridge/settings`, `/api/obsidian/settings`, `/api/automation/settings`를 직접 소비하며, AI Agent/API/Notion/Obsidian/자동화 설정을 `settings-panel`, `input-panel`, `settings-grid`, `filter-btn` 클래스 위에 렌더한다. `화면` 패널은 기본 Home, Classic/Student 캐릭터, 선택 이름, 시스템 모션/움직임 줄이기만 제공한다. AI Agent 설정은 ON/OFF와 LLM CLI/API 모드 토글을 한 패널에서 관리한다. 모델 필드는 마지막으로 불러온 `modelChoices`를 select로 표시하며, 새로고침은 `/api/settings?refresh=true`와 `/api/agent-bridge/settings?refresh=true`로 model catalog를 강제 갱신한다.

포트폴리오와 standalone 투자 노트 탭은 프론트엔드에서 숨김/비활성화한다. 기존 `data/portfolio*.json`, portfolio API, native notes API/storage는 유지하며, 보고서 옆 투자 노트 패널도 계속 유지한다.

## 반응형 단계

| 폭 | 좌측 nav | Agent Dock | 상단 `.tabs` |
|---|---|---|---|
| ≥ 1200px | fixed rail | 우측 dock | 숨김 |
| < 1200px | 숨김 | 하단 sheet | 표시(스크롤 탭 fallback) |

- 가로 스크롤은 어떤 폭에서도 생기지 않아야 한다(`.tabs`만 내부 `overflow-x:auto`).
- 좌측 nav item은 펼침/접힘 모두 동일한 높이 토큰을 쓴다. 접힌 상태에서는 hover/focus 라벨 툴팁으로 아이콘의 의미를 드러낸다.

## 담당 범위

- 0.3.0 노출 범위: Pixel Office / Agent Home / 대시보드 / 워치리스트 / 브리핑 / RSS 피드(뉴스 검색 포함) / 기업 분석 / 딥 리서치 / 시장 내러티브 / 설정
- 브리핑 탭은 생성 컨트롤과 저장 보고서 피드가 **한 화면으로 통합**되어 있다(과거 `생성`/`목록` 하위 탭·사이드바 하위 탭 제거). 생성 박스는 단일 패널(`브리핑 설정`: 시장 범위 세그먼트·브리핑 유형)과 하단 액션 바(`새로고침` → `오늘 브리핑 생성` → 날짜 입력 → `이 날짜로 생성`)다. 저장 피드는 최신순 카드(제목·기준일·생성 시각)에 시장·유형·날짜·텍스트 필터와 `시장별/날짜별` 보기 모드를 제공하고, 카드별 휴지통으로 확인 후 삭제(`DELETE /api/briefings/{date}`)한다. 브리핑은 **생성 결과·카드 클릭 모두 React `ReportReaderShell`** 로 브리핑 탭 본문 자리에서 열린다(노션식). 리더가 열리면 목록/생성 패널은 숨고, 상단 브레드크럼(`브리핑 › {날짜}`)·브라우저 뒤로가기·좌측 nav의 브리핑 클릭으로 목록에 돌아온다. URL 해시 `#/briefing/{date}/{us|kr|both}`가 리더 상태의 source of truth라 새로고침·딥링크가 복원된다. 데스크톱 리더는 grid 2열: 본문이 좌측 사이드바 옆부터 우측 컬럼 앞까지 채우고, 우측 컬럼은 **조작 레일(위) + 투자 노트(아래, 상시 표시·저장 노트 자동 로드)** 다(책갈피 손잡이 제거). 기업분석·딥리서치도 React route에서는 공통 reader를 사용한다.
- 좌측 navigation, Agent Dock, 보고서 hero
- Markdown 렌더링, Notion/Obsidian/HTML 내보내기 버튼

## Global Agent Dock

The Agent Dock is a persistent global layer for non-Home routes. It opens as a right dock on desktop by default unless the user previously closed it, and becomes a bottom sheet on narrow mobile layouts. Home uses its own Agent prompt and does not render the dock. In the React Shell, closing the dock removes the right grid column and leaves only the bottom-right `AI` pill so the main route can use the freed width. Report reader modals should update `FolioAgent.currentContext` so Agent requests know the active report without changing Canonical markdown.

- **Push 레이아웃**: 도크가 열리면 `body.agent-dock-open` 클래스가 붙고, 본문(`main.page`)과 고정 리더 모달(`report-reader-modal`/`watchlist-detail-modal`/`market-widget-editor-modal`)이 `--agent-dock-width`(384px)만큼 오른쪽 여백을 확보한다. 도크는 어떤 탭·팝업에서도 같은 위치에 있으면서 내용을 가리지 않는다. (브리핑 리더는 인라인이라 본문 push로 함께 밀린다)
- **상단 고정 바 침범 금지**: 데스크톱(≥1200px)에서 도크는 `top: 54px`(고정 hero 아래, z-index 55 < hero 60)에서 시작한다. 재시작 버튼 등 상단 바 요소를 가리지 않는다.
- 리더 모달 본문 폭은 뷰포트(`50vw`)가 아니라 **모달 컨테이너 기준(`50%`)** 으로 캡한다. 도크가 열려 모달이 줄어도 우측 노트 패널이 도크 아래로 들어가지 않는다.
- 모바일(≤760px)에서는 push 대신 하단 바텀시트(최대 72vh)로 전환한다.
- 도크·카드·버튼은 folio 디자인 토큰(`--folio-*`, `--fs-*`, `--elev-*`, `--radius-pill`)만 사용한다. 임의 색상 하드코딩을 추가하지 않는다(단, provider 브랜드 색은 예외적으로 React Agent Dock provider metadata에만 둔다).
- **Provider 브랜딩**: React Agent Dock이 Agent Bridge 설정(`/api/agent-bridge/settings`)의 provider(codex/claude/antigravity)에 따라 도크 헤더 로고·타이틀, 메시지 영역 워터마크, FAB 점 색, `Agent에게 묻기` 아이콘 버튼(`.agent-logo-slot`)에 `--agent-accent`와 인라인 SVG 로고를 적용한다. Codex/Claude는 LobeHub 아이콘 페이지의 color/mono 변형을 기준으로, Antigravity는 공식 press 로고 형태를 기준으로 임베드한다. 헤더와 액션 버튼은 색상 로고(`logo`), 채팅 영역 배경 워터마크는 무채색 로고(`monoLogo`)를 쓰며 위치는 입력창 바로 위 우하단이다. 매핑은 `web/src/app/ReactAgentDock.tsx::PROVIDER_META`에 있다.
- **기본 열림**: 데스크톱(≥1200px)에서 도크는 페이지 로드 시 기본으로 열린다. 사용자가 닫으면 `localStorage.folioAgentDockClosed`로 기억해 다음 로드에도 닫힌 상태를 유지하고, 다시 열면 해제된다.
- **채팅 도구 툴바**: 입력창 아래에 파일 첨부(`+`, 텍스트 파일은 4,000자까지 본문 포함·최대 3개·200KB 제한), 모델 버전 선택(현재 provider의 CLI `modelChoices`), 노력 단계(낮음/중간/높음/최대) 컨트롤이 있다. 첨부파일은 참고 입력(hypothesis)이지 evidence가 아니다.
- **채팅 실연결**: 전송은 `POST /api/agent/chat`(job) → `/api/jobs/{id}` 폴링으로 실제 Agent CLI 응답을 받는다(어시스턴트 메시지는 `renderMarkdown()`으로 렌더). CLI가 없으면 규칙 기반 응답(`engine: "rules"`)으로 fallback. Task 의도 + 보고서 컨텍스트면 응답에 **수정 제안 카드**(요약 + diff 접기 + 승인/거절 버튼)가 붙고, `POST /api/agent/proposals/{id}` 승인 시에만 보고서가 바뀐다. 브리핑 리더가 열려 있으면 승인 직후 자동으로 다시 불러온다.
- 본문(`.main-content`)은 데스크톱에서 가운데 정렬이 아니라 좌측 사이드바 바로 옆(`margin-left: 0`)에서 시작한다.
- 도크 메시지 안 카드(수정 제안 등)의 계약 — 카드당 액션 수, 데이터 수, 실행/해석 경계, 스켈레톤 로딩 — 은 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) §5 "대화 안 카드"를 따른다.

## Native Investment Notes

보고서 옆 투자 노트 패널과 메모 탭의 기본 저장 경로는 Obsidian이 아니라 Folio native note API(`/api/investment-notes`)다. 브리핑은 `market_memo`, 기업분석은 `company_thesis`, 딥 리서치는 `topic_review`, 일반 메모 탭은 `investment_note`로 저장한다. 모든 노트는 hypothesis이며 evidence로 사용하지 않는다.

투자 노트 패널은 Markdown 초안 양식을 먼저 보여주지 않고, 생각 한 줄을 적는 자유 작성 칸과 단일 `Agent와 투자 노트 정리하기` 버튼으로 시작한다. 사용자의 원문 생각은 `rawThoughts`, Agent와의 정리 과정은 `interactionLog`, 사용자가 편집하는 최종 투자 노트는 `body`로 분리 저장한다. Agent 결과가 사용자 원문을 덮어쓰면 안 되며, 패널에는 `기록` 탭을 두어 나중에 노트를 열어도 생각 흐름을 다시 볼 수 있게 한다.

## Market State Dashboard v2

시장 내러티브 탭은 `현재 중기 시장 상황` 대시보드 하나만 노출한다. 드라이버 카드는 판단(conclusion) 헤드라인 + 추세 칩(momentum별 soft 팔레트) + `자세히` 접기(근거/부연/체크포인트/근거 카운트/연결기업) + `Agent에게 묻기` 버튼으로 구성된다. taxonomy·story map·audit·패밀리 제안 UI는 제거되었으며 백엔드 API로만 접근한다.

## 주요 파일

```text
web/src/app/
web/src/islands/
public/index.html
public/app.js
public/styles.css
public/react/folio-react.js
```

## 중요한 렌더러

- `renderMarkdown()`: 제목, 문단, 링크, 리스트, 표 렌더링. React report reader가 `FolioBridge`를 통해 호출한다.
- `splitReportTitle()`: 보고서 본문의 선행 H1을 dark report hero(골드 kicker + 제목)로 올리고 본문에서 제거한다. 저장된 markdown은 바꾸지 않으며 표시 시점에만 전처리한다.
- `MarketChartFigure`(`web/src/app/dashboard/MarketChartFigure.tsx`): 네이티브 시장 차트 **그림 한 장**. 종목 선택·설정 저장·패널 제목은 이 안에 없다 — 대시보드는 그것들을 자기가 갖고, 워치리스트 상세는 종목이 이미 정해져 있어 필요가 없다. Lightweight Charts의 `attributionLogo`는 그대로 둔다(§6 절대 규칙). 그림은 canvas라 화면 읽기 프로그램이 볼 것이 없으므로 **이름(범위·처음/마지막 종가·최고/최저 요약)·방향키 판독(`aria-live`)·데이터 표**를 그림 밖에 둔다 — 좌우 방향키 한 봉, PageUp/PageDown 열 봉, Home/End 처음·끝, Escape 해제이고, 고른 봉에 십자선과 툴팁이 함께 뜬다. 무대가 `role="img"`가 아니라 `role="group"`인 이유는 안에 TradingView 출처 링크가 있고 img는 자손을 숨기기 때문이다(axe `nested-interactive`).

## 보고서 hero / 색상

색·표면 토큰과 의미색 배정(네이비 통일, warm neutral, Overlay 퍼플/Thesis 틸)은 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) §3이 기준이다. 아래는 보고서 리더 화면 고유 사항만 남긴다.

- `.report-hero`: 딥 네이비 배경 + `.report-kicker`(골드, 대문자). 브리핑/기업분석/테마분석 상단 공통.
- 본문 `.markdown-brief`/표는 밝은 surface를 유지한다. Executive Summary dark 테이블은 후속(자동 판별 보류).
- 보고서 생성 상태(`.generation-status.report-status`)는 hero와 본문 사이에 끼우지 않고 본문 아래 보조 상태로 표시한다. 색상은 green/amber/blue를 저채도 톤으로 낮춰 보고서 본문보다 덜 튀게 한다.

## 상단바(hero) 구성

상단바는 성격별 3그룹으로 분리한다. JS는 ID만 참조하므로 그룹 컨테이너는 위치/스타일 전용이다.

```text
.hero
 ├─ .hero-brand          좌: 브랜드(Folio Board)
 ├─ .hero-status-group   중앙: 상태 텍스트(#status) + 진행바(#jobProgress) + 작업 취소(#cancelAgentJobBtn)
 └─ .hero-meta-group     우: 마지막 인덱싱 시각 + 서버 재시작(#restartServerBtn)
```

- 상태 그룹은 평소엔 텍스트만 보이고, 작업 진행 중(`.job-progress`가 보일 때)에만 `:has()`로 알약 배경이 떠 강조된다.
- 작업 취소(`.agent-job-cancel`)는 `.icon-btn`의 `display:grid`가 기본 `[hidden]`을 덮어쓰지 않도록 `.agent-job-cancel[hidden]{display:none}`로 명시한다(작업 없을 때 ×가 상시 노출되던 버그 방지).

## 디자인 시스템

디자인 언어("두 목소리")·토큰·프리미티브·패턴·금지 목록·새 화면 체크리스트는 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) **하나가 기준**이다. 예전에 이 문서에 있던 프리미티브 계약(0.5 Stage D)·다크 모드 색 계약(0.3.x)·타이포/elevation 일반 계약은 전부 그쪽으로 옮겼다. 이 문서는 화면 구조와 화면별 고정값만 다룬다.

레퍼런스 사례(왜 그 규칙이 생겼는지의 실측 사고 기록)도 DESIGN_SYSTEM.md 각 절에 함께 있다.

## UI 규칙

### 화면별 타이포·레이아웃 값

타이포 정본(크롬 역할 스케일 / 지면 읽기 스케일), 굵기, elevation 배정, reduced motion은 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) §3이 기준이다. 아래는 화면별 고정값이다.

- 입력 패널 안내문은 확대 전 16px을 유지한다.
- RSS 뉴스 카드 제목은 22px/800이다. 품질 패널 제목과 대시보드 하단 카드·지표는 확대 전 20px 및 14/16/18/24/28/36px 계층을 유지한다.
- 브리핑 차트 제목은 20px, 기간·라인/캔들 컨트롤은 15px, 가격은 최대 44.8px이다. 히트맵 종목 글자는 박스 크기에 비례하고, 섹터·산업 라벨은 종목 가독성을 해치지 않도록 6~8px 수준의 보조 라벨로 유지한다.
- 첫 실행 안내 화면(`.welcome-*`)은 제목 27px(`--wz-title`)이다. 크롬 역할 스케일의 최대치(`--fs-title` 20)보다 큰 이유는 패널 제목이 아니라 화면의 유일한 제목이기 때문이다. 카드 폭은 최대 860px, 700px 이하에서 하단 버튼이 전폭으로 바뀐다. 배경은 뒤 화면 블러이며 상세는 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)의 "첫 실행 안내 화면"을 본다.

- 히어로 영역은 브랜드와 상태 표시 중심으로 둡니다.
- 실행 버튼은 각 기능 탭 안에 둡니다.
- RSS 수집 버튼은 RSS 피드 탭에 둡니다.
- 뉴스 검색은 별도 탭이 아니라 RSS 피드 탭 아래에 둡니다.
- 브리핑 생성/자료 다시 읽기 버튼은 브리핑 탭 패널 안(`.brief-action-row`)에 둡니다. Notion 내보내기 버튼도 이 행에 나란히 배치합니다.
- RSS 피드는 한 페이지에 20개씩 보여주고 페이지 번호로 이동합니다.
- RSS 필터는 시간과 소스 조건을 함께 제공합니다.
- 모바일에서 버튼과 카드가 넘치지 않아야 합니다.
- Notion 내보내기 버튼은 `.btn.notion` 클래스를 사용합니다. (어두운 배경, Notion N 로고 SVG 포함)
- 내보내기 성공 후 버튼은 Notion 페이지 링크(`filter-btn notion` 스타일의 `<a>`)로 교체됩니다.

## 주의점

- `renderMarkdown()` 변경은 브리핑과 기업분석 모두에 영향을 줍니다.
- 표 렌더링은 `<div class="table-wrap"><table>...</table></div>` 구조입니다.
- **차트 층은 셋이다.** 기능이 멀쩡한 차트를 기술 통일만을 이유로 옮기지 않는다.
  1. **ECharts** — 새 차트와 브리핑 히트맵(`public/briefing-visuals.js`, React 밖이라 `window.echarts`를 직접 부른다). `public/vendor/echarts.js`가 `window.echarts`(SVG 렌더러)로 노출되고, 화면은 `web/src/app/charts/FolioChart`에 `option`을 넘긴다. `FolioChart`가 수명(마운트·해제·폭 변화, 숨은 곳에서 시작해도 보이면 바로잡기)·테마 전환(`chart.setTheme`, 확대 범위·범례 선택은 되돌려 놓는다)·loading/empty/error/stale 네 상태·텍스트 대체(`role="img"` + 필수 `label`, 방향키 판독, 데이터 표)를 맡는다.
  2. **Lightweight Charts** — 금융 시계열(`MarketChartFigure`, 브리핑 가격 계열). `public/vendor/lightweight-charts.js`(npm 배포본과 바이트 동일)로 서빙한다.
  3. **손 SVG** — 기업분석 `AnalysisCharts`, 워치리스트 분기 지표 `FundamentalsPanel`, Portfolio `BacktestChart`. `BacktestChart`는 단일/비교 결과가 공유하며 실제 컨테이너 폭, 날짜/값 축, 범례, 날짜 hover·터치·키보드 선택과 데이터 표를 제공한다. 이들은 CSS 토큰을 직접 따른다.

  **새 차트를 추가하는 절차**
  - 필요한 차트 종류·컴포넌트가 `web/src/vendor/echarts.ts` 등록 목록에 없으면 한 줄 더하고 `web/`에서 `npm run build:vendor`로 다시 만든 뒤 `public/vendor/echarts.js`를 함께 커밋한다(사용자 설치본은 Node 없이 이 파일을 서빙한다).
  - option은 차트 종류별 컴포넌트가 만든다 — 화면이 직접 쓰지 않는다. 색은 디자인 토큰, 금액·분기 표기는 `web/src/app/charts/chartFormat.ts`(KRW·JPY는 조·억, 그 외 T·B·M)를 쓴다. `option`은 메모이즈해서 넘긴다(참조가 바뀌면 다시 그리며 확대 범위가 초기화된다). 색을 토큰에서 만드는 차트(캐스케이드 등)는 `(tokens) => option` 함수로 넘겨 테마 전환 때 새 토큰으로 다시 만들게 한다.
  - `FolioChart`의 `label`(필수)·`table`·`keyboard`를 채운다. 그림 안에 링크·버튼이 있으면 img가 그것을 숨기므로 `role="group"`을 쓴다.
  - 앱 소스는 ECharts를 **`import type`으로만** 가져오고 실행 코드는 `window.echarts`로만 받는다(같은 라이브러리가 React 번들에 두 벌 실리지 않게. `web/tests/vendorScriptsSource.test.mjs`가 지킨다).
  - ECharts 버전은 정확 고정이다. 올릴 때는 `public/briefing-visuals.test.js`의 canary(`heatmapTileSizes`)가 먼저 걸린다 — 히트맵 라벨 계획이 ECharts의 비공개 배치 경로를 읽기 때문이다.
  - 캔버스 글꼴·색은 컴포넌트가 CSS 변수를 `getComputedStyle`로 읽는다(ECharts는 `var()`·`color-mix()`를 풀지 못하므로 해석된 값을 쓴다).
- 기업분석 본문 폭은 기본적으로 `markdown-brief`의 제한 폭을 따릅니다.

## 보고서 가설 검토 표면 (0.2.1)

- Briefing, Company Analysis, Deep Research는 공용 `HypothesisReviewCard`와
  `PersonalOverlayView`를 사용한다.
- 자동 로드는 metadata-only intelligence 조회만 수행한다. Agent/Thesis Delta는
  `최신 근거로 검토` 클릭으로만 시작한다.
- Personal Overlay는 없음, stale, legacy revision, 빈 본문 상태를 세 reader에서
  같은 문구로 표시하며 모바일 note panel에서도 세로로 쌓인다.

## Smart Collection 워크스페이스 (0.2.2)

- Smart Collection 목록/편집기는 `SmartCollectionWorkspace.tsx`와
  `SmartCollectionEditor.tsx`로 분리되어 Deep Research 안에서만 렌더링한다.
- 상세 주소는 `#/deep-research/collections/{collectionId}`이며 direct hash,
  새로고침, browser back/forward를 지원한다. 별도 top-level route/navigation은 없다.
- 상세 화면은 서버의 `/workspace`, `/changes`, `/refresh` projection만 사용해
  definition, health/reason, last refresh, change count, 외부 evidence 카드를 표시한다.
- empty, stale, noisy, source unavailable, deleted-while-open 상태는 서로 다른
  machine-visible selector와 복구 문구를 사용한다.
- `현재 자료 새로고침`은 Collection snapshot만 갱신한다. Agent는
  `Agent에게 변화 묻기` 클릭에서만 dock의 기존 대화 경로로 auto-submit되며,
  frontend는 Collection ID/revision 외의 evidence/context를 보내지 않는다.
- `이 범위로 리서치 시작`은 같은 ID/revision으로 기존 question-first draft를
  prefill한다. Collection 정의는 saved-filter metadata이며 evidence로 표현하지 않는다.

## Investment Context 카드 (0.2.3)

- `InvestmentContextCard.tsx`는 `GET /api/investment-context/summary`의 동일한
  metadata-only projection을 Home, Market Memory, Smart Collection, Deep Research에 표시한다.
- 네 표면의 ticker, stance, 예정 checkpoint, 연결 route는 같은 컴포넌트 계약을 사용한다.
  Portfolio와 Watchlist의 독립 route는 계속 기본 navigation에서 숨긴다.
- 연결된 맥락이 없으면 어떤 화면에서도 렌더링하지 않는다(로딩·실패도 마찬가지). 홈에서
  빈 카드가 상시 떠 있으면 아직 쓰지 않은 기능을 계속 광고하게 된다. 닫기는
  `folio.investmentContext.dismissed.v1`에 저장해 화면을 옮겨도 유지한다.
- 카드는 `data-layer="hypothesis"`를 유지하고 포트폴리오 수량·비중·가격이나 note body를
  렌더링하지 않는다. 외부 evidence와 Canonical 보고서 본문도 이 카드와 구분한다.
- context 자동 조회는 read-only다. Agent는 사용자가 `Agent로 위험 설명`을 눌렀을 때만
  실행되며 추천 없는 controlled 결과 또는 규칙 fallback을 카드 안에 표시한다.
- checkpoint 생성·확인은 native investment note 저장소만 변경하며, 네 route의 context
  재조회 결과가 동일하게 갱신되어야 한다.

## 홈·딥 리서치 UX 단순화 (0.3.x)

- 홈은 Agent 입력창이 유일한 중심 요소다. placeholder는 "오늘 어떤 투자 리서치를
  도와드릴까요?"이며, 모델/노력 단계 선택은 입력창의 `상세 설정` 토글 뒤로 숨긴다.
- 브리핑/RSS/기업 분석/딥 리서치 바로가기는 주 버튼 없는 간결한 빠른 실행 버튼이다.
  홈의 주 행동은 Agent 입력 하나만 유지한다.
- `AgentWorkLog`는 `collapsible` prop을 지원한다. 홈에서는 접힌 `<details>` 요약
  ("최근 작업: …")만 먼저 보여주고 펼치면 전체 기록을 보여준다. 딥 리서치는 기존 그대로다.
- 딥 리서치 단계 라벨은 한국어를 사용한다: 투자 질문 → 조사 계획 확인 → 생성 중.
  보고서 하단 추적 섹션은 "사용한 자료와 생성 과정", 사용자 입력은 "내 생각·가설 · 근거 아님",
  overlay는 "내 투자 관점과 비교 · 가설"로 표시한다.
- 추가 컨텍스트, Investment Context 카드, Smart Collection 선택, 시장 상태 배경 정책은
  `분석 조건 추가 (선택)` `<details>`(`.topicrpt-advanced`) 안에 접혀 있다. 입력값이나
  선택된 Collection이 있으면 열린 상태로 렌더링한다.
- Smart Collection은 사용자 화면에서 "저장한 자료 모음"으로 부르고 `revision`은 "버전"으로
  표기한다. 설명 문장에서 bounded research, Canonical, hypothesis 같은 내부 영문 용어를
  쓰지 않는다(짧은 영문 부제목·기능명은 허용).
- 근거 부족 확인(zero-evidence confirm)과 수정 제안 승인 절차는 단순화 후에도 숨기지 않는다.

## Agent 작업 기록 표시 규칙 (0.3.x)

D4 로컬 수용 완료(2026-09-08): 기존 실행 상세 안에 진단 정보 미리보기·로컬 다운로드,
설정에 진단 보존 관리 패널을 연결했다. 삭제와 설정 저장은 각각 미리보기·확인을 거치며
실제 자동 삭제는 기본 off다. 중첩 펼침과 모바일 체크박스 배치를 보완하고
desktop/mobile × Light/Dark 및 접근성을 검증했다. 운영 서버/실제 자료 변경은 하지 않았다.

- `DiagnosticDetail`은 기존 작업 기록과 설정의 마지막 자동화 실행에서 실행 상세를 조회한다. 작업 기록의 전체 새로고침은 항목의 수정 시각이 같아도 열린 상세를 함께 갱신한다. 로그마다 새로고침 버튼을 두지 않으며, 조회 실패의 `다시 시도`는 유지한다. 실행 ID 변경·펼침 재개에서도 현재 기록을 다시 읽고 이전 요청의 늦은 응답은 버린다.
- 실행 성공/실패/취소와 진단 범위 제한/실제 기록 손실은 구분한다. 현재 작업 상태를 확인하지 못하면 완료를 단정하지 않는다. 규칙 대체 뒤 저장에 실패한 실행을 완료로 표시하지 않으며, 실패한 단계의 종료 이벤트를 성공 완료 단계로 세지 않는다.
- 브리핑·기업분석·딥 리서치의 생성 오류는 서버가 제공한 유효한 실행 ID가 있을 때 같은 `실행 상세`를 연다. 요청 ID만 있으면 접힌 개발자 정보에 표시하고 실행 ID로 추측하지 않는다. 네트워크/응답 읽기 문제는 서버 처리 결과를 확인할 수 없는 상태로 안내하며 자동 재전송하지 않는다. 오류가 바뀌거나 새 작업으로 넘어가면 이전 진단 연결을 지운다. 일반 목록·삭제·내보내기 오류와 전역 팝업으로 범위를 넓히지 않는다.
- 진단의 다음 행동은 기존 화면으로만 연결한다. 설정 확인은 `설정에서 확인`, 결과 확인은 해당 기능의 목록(`자동화`는 설정 화면)으로 표시하며, 대기·재시도·알 수 없는 행동에는 링크를 만들지 않는다.
- 공통 실행 목록은 기존 Work Log 안의 `실패·대체 실행 찾기`를 펼쳐서 연다. `실패만`·`대체 실행만`·기간·`모든 실행 보기`로 목록을 전환하며, 현재 스냅샷·부분 검사·조회 실패·cursor 재조회 상태를 구분한다. 기존 Work Log 26필드와 숨기기 범위, 직접 실행·재생성 경계는 바꾸지 않는다.

- Work Log API는 계속 안전한 코드 값만 준다. 화면 문구는 `web/src/app/workLogCopy.ts`의
  `workLogItemCopy()`가 그 코드를 사람이 읽는 문장으로 바꿔서 만든다. 컴포넌트는 코드 값을
  그대로 렌더링하지 않는다.
- 항목 한 건은 **무슨 작업(제목) · 지금 상태(배지) · 결과 한 줄 · 보조 설명** 순서로 보여준다.
  예: "일일 브리핑 생성 / 완료 / 브리핑 1건 저장 / AI CLI · Codex".
- `tone`은 `running|done|failed|cancelled|waiting` 다섯 가지이며 배지 색과 카드 왼쪽 띠에
  함께 쓴다. 실패는 오류 코드 대신 원인 문장("AI 도구 실행이 실패했습니다")으로 표시한다.
- 승인 대기 중인 수정 제안은 별도 강조 줄(`.work-log-attention`)로 항상 보이게 둔다.
  단순화 과정에서 승인 절차를 숨기지 않는다.
- 지금 아무 일도 할 수 없는 컨트롤은 그리지 않는다. 범주 필터는 기록이 2건 이상이거나 이미
  범주를 좁혀둔 상태일 때만, 페이지 이동은 전체 건수가 한 페이지를 넘을 때만 렌더링한다.
- 홈 열은 하나의 폭(`min(100%, 920px)`)을 공유한다. 작업 기록만 내용 폭으로 줄어들면
  화면이 어긋나 보인다.
- 접혀 있을 때는 한 줄짜리 정보라 카드 테두리·배경을 없애고, 펼칠 때만 판을 세운다.
- 범주 필터와 새로고침은 한 줄(`.work-log-toolbar`)을 공유한다. 접힌 머리말 아래에 버튼만
  있는 빈 행이 생기지 않게 하기 위해서다. 좁은 화면에서도 이 줄은 유지하고 필터만 줄바꿈한다.
- 범주 라벨은 `전체 / 대화 / 작업`이다. `기록 숨기기`는 푸터의 조용한 텍스트 버튼
  (`.work-log-quiet-btn`)이고, 보존 안내와 metadata-only 고지도 푸터 작은 글씨로 둔다.
- 예전 `jobs.json` 마이그레이션은 일회성 유지보수라 Work Log가 아니라 설정의
  `이전 작업 기록` 패널(`WorkLogMigration.tsx`)에 둔다. preview → confirm 2단계와 충돌 차단은
  그대로 유지한다.
- 사전에 없는 새 코드가 오면 코드 원문을 그대로 노출해 정보가 사라지지 않게 한다.
  새 taskType/errorCode를 추가하면 `workLogCopy.ts` 사전도 함께 채운다.

## 다크 모드

다크 대응쌍 규칙(토큰만 쓰기, 두 테마 쌍 정의, 표면 채도 222°, 세그먼트 대비 3:1, 토큰 정의 누락 검사)은 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) §3 "다크 대응쌍 규칙"이 기준이다.

## Pixel Office 보류 (0.3.0)

런타임·에셋·테스트는 저장소에 남기고 사용자 화면 진입점만 제거한 상태다. 재개할 때 다시
만들지 않기 위해서다.

- 실행되는 앱에는 배선이 전혀 없다. 라우트 id `office`, 아이콘, `PixelOfficeRoute` 렌더
  분기, 첫 실행 선택 화면(`HomeModeChooser`), Agent Home의 전환 버튼(`HomeModeSwitch`)을
  모두 끊었다. `#/office`는 조용히 홈으로 되돌린다.
- 컴포넌트와 씬 코드는 `web/src/app/pixelOffice/` 아래에 그대로 있고 vitest 단위 테스트와
  타입체크를 계속 받는다. 다만 진입점이 없어 번들에 포함되지 않으므로 Pixi 청크도 빌드되지
  않는다(번들 gzip 156.6KB → 153.2KB).
- 릴리즈 패키지도 제외한다. `scripts/package_release.py`의 `EXCLUDED_PARTS`에
  `pixel_office`/`pixel-office`가 있어 백엔드 service와 0.87MB 스프라이트가 배포본에
  들어가지 않는다(403 → 354 경로).
- `preferredHomeRoute()`는 저장된 선택과 무관하게 `home`을 돌려주되 선택값 자체는 지우지
  않아 재개 시 복원된다.
- 설정 화면의 기본 Home·캐릭터 선택은 감췄다. `움직임 줄이기`는 Pixel Office와 무관한
  접근성 설정이라 남긴다.
- 재개 조건은 `.planning/pixel-office-game-scene-upgrade/DEFERRED_CHECKPOINT.md`를 따른다.

## 네이티브 차트와 테마 (0.5.4)

**TradingView 임베드는 0.5.4에 전부 걷어냈다.** 마지막 소비자였던 워치리스트 상세 모달이
`MarketChartFigure`로 바뀌면서 `public/tradingview-widgets.js`, `index.html`의 로드,
`.tv-widget-*`/`.tradingview-widget-*` CSS에 남은 소비자가 없어졌다. iframe은 생성 시점
config로 색이 굳어 테마가 바뀔 때마다 다시 심어야 했고, 앱 토큰을 따르지 않았으며,
cockpit의 "초기 payload에 외부 iframe 없음" 계약과도 어긋났다.

- 네이티브 차트는 `document.documentElement`의 `data-theme`/`class` 변화를
  `MutationObserver`로 보고 계열 색만 다시 칠한다. 다시 심을 것이 없다.
- **트레이드오프**: TradingView는 준실시간 시세와 지표를 줬고 네이티브는 yfinance 지연값이다.
  워치리스트는 리서치 맥락이므로 freshness 라벨로 지연을 밝히는 기존 방식을 따른다.
- 기간 토글의 첫 전환은 기간별 캐시 키라 네트워크를 탄다. 무대(`.cockpit-chart-stage`)가
  고정 높이라 레이아웃이 튀지 않으며, 새 기간의 축에 옛 계열이 잠깐 그려지지 않도록
  요청 시작 시 payload를 비운다.
- `data/market-widget-settings.json`은 삭제·수정하지 않는다. 대시보드 집중 종목 fallback으로만
  read-only로 읽으며 차트 위젯과 무관하다.
