# 딥 리서치 (Topic Research Agent v2)

화면 표시명은 **딥 리서치**입니다. 내부 폴더/API/저장 경로는 기존 호환을 위해 `topic_report` 이름을 유지합니다.

Folio OS 0.2에서는 좌측 navigation, Home 빠른 실행, command palette에 노출되는 기본 사용자 화면입니다. 실행 전에 승인 가능한 계획과 live evidence preview를 먼저 보여주며, 생성은 승인된 요청을 그대로 사용하는 SharedJob으로만 시작합니다.

이 기능은 프리셋 테마(환율·금리·기업실적·주간시황·산업동향) 또는 **자유 투자 질문**에 대해 시장 데이터, 경제 지표, 시장 내러티브 기록, 로컬 뉴스를 종합하여 분석 보고서를 생성합니다. v2에서는 단순 "주제 보고서 생성기"를 넘어 **투자 질문 해결기**(주제 해석 → 리서치 계획 → 증거 묶음 → 유형별 분석 → 품질 평가 → 개인 해석 연결)로 동작합니다.

## 담당 범위

- 프리셋 테마 선택 또는 자유 입력으로 보고서 생성
- **Topic Planner**: 자유 주제를 해석해 보고서 유형·분석 축·검색어·후보 티커·데이터 갭을 만드는 리서치 계획(TopicPlan) 생성
- **심층 모드**: Planner가 하위 질문을 최대 12개(라운드당 6개) 만들고, 1차 근거가 충분하지 않을 때만 승인된 2차 질문을 실행한다. 질문별 커버리지와 실제 실행 라운드를 evidence/sourceLedger에 기록한다.
- **Evidence Pack**: 분석 축별 자료 검색·근거 역할 분류(evidenceRole)·커버리지 계산, Source Ledger
- **report_type별 템플릿**: 12종 유형 enum에 맞춰 분석 강조점을 달리하는 지침 결합
- **Quality Gate / Quality Generation**: 생성 전 품질 목표와 자료 수집 루트, evidence coverage preflight를 컨텍스트에 주입하고, 생성된 보고서를 공통 `research_quality` 레이어로 평가하며, 선택한 `qualityMode`에 따라 weak section 탐지·LLM 섹션 개선·telemetry를 `qualityGeneration`에 저장
- **Personal Overlay**: 저장된 보고서를 사용자 Obsidian 노트와 대조한 개인 해석(Step 2 재사용, 기본 markdown 불변)
- yfinance 기반 관련 티커 시장 데이터 수집
- FRED(미국 경제 지표) 및 BOK ECOS(한국은행 경제통계시스템) 거시 데이터 수집
- 시장 내러티브 메모리에서 관련 항목 검색 및 참조
- RSS/research-inbox 뉴스·자료 검색 및 참조
- LLM 보고서 생성과 규칙 기반 fallback (일반 보고서). 딥 리서치는 검증된 모델 후보가 없으면 규칙 보고서를 저장하지 않고 실패 상태를 남긴다.
- 사용자 추가 컨텍스트(userContext) 주입 — **관심 방향이지 사실/근거가 아님**
- 보고서 자동 저장(같은 주제·같은 날 덮어쓰기), 목록 조회, 다시 열기, 삭제
- 웹 UI 딥 리서치 탭은 저장 보고서를 **카드 피드**로 보여주고, 카드를 누르면 `#/deep-research/{reportId}`의 공통 `ReportReaderShell`이 열린다. 카드별 휴지통으로 삭제하며 기존 드롭다운 선택 방식은 폐기한다.
- 같은 화면의 Smart Collection 목록에서 `#/deep-research/collections/{collectionId}` 상세 워크스페이스를 열어 저장 정의, deterministic health/reason, 스냅샷 변화, 현재 외부 evidence를 확인한다. 이 nested route는 별도 top-level navigation을 만들지 않는다.
- Notion / Obsidian 내보내기

## v2 파이프라인

```text
사용자 질문 → 승인 계획/자료 preview → 사용자 승인 → live Evidence Pack(축별 근거)
→ report_type 템플릿 결합 → LLM 초안 → 구조·근거·깊이 검증 → 필요한 섹션만 최대 2회 보강
→ [선택] Personal Overlay(내 노트와 대조)
```

심층 모드를 켜면 Topic Planner 다음에 하위 질문 분해가 추가됩니다.

Smart Collection은 저장 필터 metadata이며 evidence가 아닙니다. Market State는 별도 source-grounded context이고 evidence count/sourceLedger/hypothesis에 포함되지 않습니다. `userContext`, Folio Note, Obsidian note, Personal Overlay는 hypothesis입니다.

Collection 상세의 refresh는 외부 자료를 다시 resolve하고 스냅샷을 명시적으로 기록합니다. `이 범위로 리서치 시작`은 Collection ID/revision만 기존 question-first 흐름에 전달하며, 승인 시 서버가 저장 정의와 현재 자료를 다시 읽습니다. `Agent에게 변화 묻기`도 ID/revision만 전달하고, 상세 진입·자료 refresh만으로 Agent를 자동 실행하지 않습니다.

```text
TopicPlan → deepResearch.subQuestions → 질문별 근거 수집 → questionCoverage/sourceLedger 라운드 기록
```

딥 리서치 본문은 분석축·질문·근거 수에 따라 동적으로 배분하며 일반적으로 보이는 본문 12,000~16,000자(안전 상한 18,000자)를 목표로 한다. 각 근거 사용 섹션은 숨김 source ID 태그로 원장과 연결되고, 저장 전 구조·허용 출처·필수 자료·섹션 밀도를 검증한다. 초안과 채택된 보강 후보는 job 소유 checkpoint로 보관하므로 재시작 시 최신 검증 후보를 한 번만 원자 커밋할 수 있다.

설계 원칙 (CLAUDE.md §5와 동일):
- **2계층 분리**: 기본 보고서(Canonical)는 보편·자료 기반. 개인 해석은 `personalOverlay` 별도 필드에만. 기본 `markdown`은 overlay 생성으로 바뀌지 않는다.
- **enum 통제**: `reportType`(12종)·`evidenceRole`(5종)은 `topic_schema.py`에서 코드 검증. LLM 자유 텍스트 분류를 신뢰하지 않는다.
- **확증편향 방지**: 보고서에 반론/리스크 섹션 필수, Quality Gate가 counterargument/personal_bias_risk를 점검.
- **userContext ≠ evidence**: 관심 방향으로만 쓰고, 외부 자료와 충돌 시 충돌을 명시.

## report_type enum (12종)

`macro_analysis`, `cross_asset_analysis`, `industry_theme`, `supply_chain_theme`, `policy_regulation`, `geopolitical_risk`, `earnings_theme`, `factor_style`, `company_basket`, `country_market`, `portfolio_implication`, `custom_research`. 정의는 `topic_schema.py`, 유형별 지침은 `templates/<type>.md`(없는 유형은 `generic.md` 폴백).

## 프리셋 테마

| 키 | 라벨 | 설명 |
| --- | --- | --- |
| `exchange_rate` | 환율 | USD/KRW 환율 전망 및 주요 통화 분석 |
| `interest_rate` | 금리 | 미국·한국 금리 환경 및 수익률 곡선 분석 |
| `earnings` | 기업실적 | 어닝시즌 동향 및 섹터별 실적 분석 |
| `weekly_market` | 주간 시황 | 주간 시장 흐름 요약 및 다음 주 주목 이벤트 |
| `industry_trend` | 산업 동향 | 주요 산업·섹터별 흐름 및 테마 분석 |
| `custom` | 직접 입력 | 사용자가 입력한 주제로 자유 생성 |

각 프리셋은 연관 티커, FRED 시리즈, BOK 시리즈, 검색 키워드, 분석 축을 정의합니다. 설정은 `features/topic_report/topic_config.py`에 있습니다.

## 데이터 소스

- **yfinance**: 관련 주가·지수·ETF·환율·원자재 데이터
- **FRED**: Fed Funds Rate, CPI, 10년물 금리, 실업률, 수익률 스프레드 등 미국 거시 지표
- **BOK ECOS**: 한국은행 기준금리, 콜금리, 원/달러 환율 등 한국 경제 지표
- **시장 내러티브 메모리**: 과거에 기록한 시장 흐름 메모 (스토리 패밀리 기반 필터링)
- **뉴스/로컬 자료**: research-inbox/rss + articles 하이브리드 검색

FRED와 BOK ECOS를 사용하려면 `.env`에 API 키를 설정합니다.

```text
FRED_API_KEY=...
BOK_API_KEY=...
```

두 키 모두 없어도 yfinance 데이터와 로컬 자료만으로 보고서를 생성할 수 있습니다.

## 보고서 구조 (v2, 11섹션)

LLM 보고서는 아래 구조를 따릅니다. report_type별 템플릿이 특정 섹션의 비중을 조절합니다.

```text
1. Executive Summary           7. 반론과 리스크
2. 질문 정의와 분석 범위        8. 시나리오
3. 핵심 데이터 대시보드         9. 앞으로 확인할 체크포인트
4. 현재 상황 (분석 축 순서)    10. 결론
5. 작동 경로                   11. Source & Data Notes
6. 수혜/피해 자산과 기업
```

반론과 리스크 / 수혜·피해 / 시나리오 / 체크포인트 / Source & Data Notes는 필수입니다. 규칙 기반 fallback도 리서치 계획 요약·데이터 부족 경고·체크포인트·Source & Data Notes를 포함합니다.

## LLM 버전

LLM에는 다음 내용을 축약해서 전달합니다.

1. 테마 정의 + 분석 축 목록
2. 사용자 추가 컨텍스트 (입력한 경우 최우선 참조)
3. yfinance 시장 데이터 (Markdown 표)
4. FRED + BOK 거시 데이터 (있는 경우)
5. 관련 시장 내러티브 기록 (스토리 패밀리 다양성 유지, 최대 20건)
6. 관련 뉴스·자료 (최대 12건, RSS + research-inbox)

전체 원문을 그대로 넣지 않습니다. 자료가 없는 수치나 사실은 LLM이 추정임을 명시해야 합니다.

LLM 출력은 11개 필수 섹션을 끝까지 생성하도록 `TOPIC_REPORT_MAX_OUTPUT_TOKENS`(기본 9000)를 사용합니다. 생성 결과에 `앞으로 확인할 체크포인트` / `결론` / `Source & Data Notes` 후반 섹션이 없으면, 1회 continuation 요청을 보내 끊긴 지점부터 이어 붙입니다. continuation이 실행되면 저장 JSON의 `generation.continued`에 횟수가 기록됩니다.

## 규칙 기반 버전

LLM이 꺼져 있거나 호출에 실패하면 `features/topic_report/report_rules.py`가 보고서를 만듭니다. 시장 데이터 표, 거시 지표, 관련 뉴스 헤드라인, 시장 내러티브 요약을 섹션별로 조립합니다.

**제목의 날짜는 호출자가 정한 기준일(`as_of`)이다.** 승인 경로는 `approved.asOfDate`, 비승인 경로는 자기 `date`를 넘긴다. 예전에는 본문 H1만 실행 시각을 다시 읽어서, 자정을 넘겨 끝난 생성이나 규칙 fallback에서 JSON `date`/`title`과 H1이 하루 어긋났다.

## 프롬프트

```text
features/topic_report/prompt.md
```

## 저장 위치

보고서는 생성 시 자동 저장됩니다. id는 `날짜:topicKey:라벨` 기준이라, 같은 주제를 같은 날 다시 생성하면 새 파일을 쌓지 않고 최신본으로 덮어씁니다(덮어쓸 때 기존 Personal Overlay는 보존). 자동 저장되므로 생성 직후 Personal Overlay·품질 재평가를 바로 쓸 수 있습니다.

**승인 경로는 여기에 `planHash`를 판별자로 더한다**(`날짜:topicKey:라벨:planHash`). 승인 경로의 `topicKey`는 늘 `custom`이고 `topicLabel`은 `topic_subject()`가 40자로 끊은 주제어라, 같은 주제로 시작하는 다른 질문("AI 데이터센터 전력 병목: 발전 설비 수혜주는?" / "…: 규제 리스크는?")이 같은 id가 되어 뒤 보고서가 앞 보고서를 새 revision으로 교체했다. planHash는 계획 payload에서 나오므로 **같은 계획 재실행만** 같은 id가 되어 덮어쓰기 의도는 그대로다. 판별자가 없는 호출(비승인 경로, 기존 저장 파일)은 예전 키 그대로라 저장된 id가 그대로 재현된다.

```text
data/topic-reports/YYYY-MM-DD_<topic_key>_<id>.json
```

## 관련 코드

- `features/topic_report/service.py`: 보고서 생성·저장·목록·조회·삭제 + 재평가/overlay attach
- `features/topic_report/topic_schema.py`: report_type/evidenceRole enum, TopicPlan 정규화
- `features/topic_report/planner.py`: Topic Planner (규칙 해석 + 선택적 LLM 정제)
- `features/topic_report/plan_edits.py`: 승인 전 계획 수정 적용(허용 항목만, 서버가 적용)
- `features/topic_report/evidence.py`: Evidence Pack (축별 검색, 역할 분류, 커버리지)
- `features/topic_report/source_ledger.py`: Source Ledger (출처 원장)
- `features/topic_report/templates.py` + `templates/*.md`: report_type별 지침 결합
- `features/topic_report/evaluation.py`: Quality Gate 호환 wrapper (`features/common/research_quality/evaluator.py` 호출)
- `features/common/research_quality/`: 공통 품질 평가 레이어
- `features/common/quality_generation/`: 생성 품질 목표/자료 루트, preflight, prompt hints, 최대 1회 repair, `qualityGeneration` 저장
- `features/topic_report/topic_config.py`: 프리셋 테마 정의 (`PRESET_TOPICS`, `get_topic_config()`)
- `features/topic_report/data_fetcher.py`: yfinance 시장 데이터 수집
- `features/topic_report/macro_data.py`: FRED + BOK ECOS 거시 지표 수집
- `features/topic_report/report_rules.py`: 규칙 기반 보고서 생성 (v2 섹션 포함)
- `features/personal_overlay/service.py`: overlay 생성 재사용 (`generate_overlay`/`with_overlay`)
- `features/obsidian/export/service.py`: `export_topic_report_to_obsidian()` (자기참조 마커 포함)
- `features/notion_export/service.py`: `export_topic_report()` — Notion 내보내기
- `app.py`: 테마분석 API 라우팅
- `public/app.js`: `renderTopicReport()`, `renderTopicPlanPanel()`, `renderTopicQualityPanel()`

## 계획(TopicPlan) 만들기

- 계획은 **주제어(subject) 위에 세운다.** 사용자는 질문칸에 배경까지 한 문단으로 적는데, 그 240자를 주제 라벨로 쓰면 축 질문 다섯 개가 전부 같은 문단이 되고 검색어에 질문 전문이 들어간다. `topic_subject()`가 첫 구획(콜론·줄바꿈·` - `·문장 끝 앞)을 40자 이내로 끊어 쓴다. 원문 질문은 `topic`에 그대로 남는다.
- **40자 상한은 `normalize_topic_plan()`의 코드 게이트다.** 예전에는 LLM이 값을 비웠을 때만 `topic_subject()`로 떨어지고, 값이 있으면 200자 절단만 거쳐 배경 문단이 그대로 보고서 제목이자 저장 라벨이 됐다. 검색어에는 `_clean_queries()` 게이트가 있는데 제목에는 없었다(§5 원칙 4 — 프롬프트는 부탁이지 제한이 아니다).
- **한 단어 질의와 질문 전문 질의는 만들지 않는다.** 계획의 `searchQueries`는 그대로 `search_keywords`가 되어 근거 검색을 돌린다. 실제로 `피크`는 전력망 기사를, 질문 전문은 그날 시장 기사 아무거나 물어왔다(FTS에서 토큰이 OR로 풀린다). 2어절 이상 40자 이하만 남긴다.
- 조사 제거 목록에 `의`가 빠져 있어 `반도체의`가 검색어로 살아남았다. `_PARTICLES`가 단일 출처다.
- **미리보기가 기본적으로 엔진에게 계획을 맡긴다**(`plannerEngine=auto`). 설정에서 엔진 경로를 넣은 순간부터 사용자는 Agent 사용을 허락한 것으로 본다 — 계획을 보려고 버튼을 두 번 누르게 하는 것은 확인이 아니라 절차다. 빠른 계획이 필요하면 `plannerEngine=rules`를 고른다. CLI는 40~50초가 걸리므로 화면이 그 사실을 먼저 말한다.
- `POST /api/topic-reports/plan/replan`은 계획을 받은 뒤 다시 쓸 때 쓴다. `instruction`이 있으면 **지금 계획을 그 요청대로 고치고**, 없으면 처음부터 다시 쓴다. `revise`와 같은 `_swap_plan` 경로다.
- **화면의 계획 수정은 요청 문장 하나다.** 칸을 하나씩 편집하게 했더니 축 다섯 개에 텍스트 영역이 열한 개였다. 사람이 계획을 고칠 때 하는 말은 "밸류에이션 축은 빼고 공급 쪽을 자세히"에 가깝지 각 칸을 다시 타자하는 것이 아니다. 수정 요청은 `현재 계획`과 함께 엔진에 넘어가며, 규칙 계획에서 다시 시작하지 않는다 — 다시 시작하면 사용자가 앞서 받아 든 계획이 통째로 사라져 무엇이 반영됐는지 알 수 없다.
- `POST /api/topic-reports/plan/revise`(PlanEdits)는 항목 단위 수정을 하는 결정적 경로로 남는다. 화면은 쓰지 않으며 엔진 없이 계획을 고쳐야 하는 호출자용이다.
- **테스트는 Agent CLI를 부르지 않는다.** `tests/conftest.py`가 `run_agent_prompt`를 막는다. 막지 않았을 때 실제 CLI가 돌아 스위트가 멈춰 섰다.
- 플래너는 **API 키와 Agent CLI 둘 다 쓴다.** 이 설치처럼 `AI_AGENT_MODE=cli`로 도는 환경에서는 `selected_llm_config()["apiKey"]`가 비어 있어, 보고서를 쓰는 엔진이 멀쩡히 있는데도 계획은 늘 규칙으로 떨어졌다. 키가 없으면 `run_agent_prompt()`로 같은 프롬프트를 보낸다. 타임아웃은 `TOPIC_PLANNER_TIMEOUT_SECONDS`(기본 120초).
- LLM 결과에도 같은 검색어 위생을 코드가 다시 적용한다(§5 원칙 4 — 프롬프트는 부탁이지 제한이 아니다).
- `plannerMode`(`rules|llm|preset|edited`)가 계획에 남고 화면이 그대로 표시한다. 무엇이 쓴 계획인지 모르면 얼마나 믿을지 정할 수 없다.

## 승인 전 계획 수정

- `POST /api/topic-reports/plan/revise`는 `confirm-degraded`와 같은 모양이다 — 무결성 확인 → 승인 권한 확인 → **서버가** payload를 고침 → planHash 재계산 → 기존 승인 supersede.
- 클라이언트가 계획을 통째로 밀어넣는 통로는 없다. `PlanEdits`에 적힌 항목(주제 이름·보고서 유형·리서치 질문·검색 질의·축별 질문/질의/제거)만 반영하고 `expectedSections`, deep research 고정 문구 같은 서버 소유 값은 그대로 둔다.
- 축은 **key로 찾을 뿐 새로 만들 수 없다.** 축 목록은 보고서 유형이 정한다. 마지막 축은 뺄 수 없다.
- 축을 빼면 그 축을 가리키던 하위 질문도 함께 지운다. 남겨두면 실행이 없는 축을 조사한다.
- 계획이 바뀌면 앞서 받은 `근거 없음` 확인은 다른 계획에 대한 것이므로 `degradedConfirmation`을 비운다.

## API

```text
GET    /api/topic-reports/presets
GET    /api/topic-reports
POST   /api/topic-reports/plan                       # 승인 가능한 TopicPlan + 자료 preview
POST   /api/topic-reports/plan/revise                # 승인 전 계획 수정 (새 planHash로 승인 교체)
POST   /api/topic-reports/plan/replan                # AI로 계획 다시 쓰기 (명시적 action)
POST   /api/topic-reports/confirm-degraded           # zero-evidence 규칙 fallback 명시 확인
POST   /api/topic-reports                             # 승인 envelope를 202 SharedJob으로 실행
GET    /api/topic-reports/{report_id}?includePersonal # personalOverlay 포함 조회
POST   /api/topic-reports/{report_id}/evaluate         # Quality Gate 재평가
POST   /api/topic-reports/{report_id}/personal-overlay # 개인 해석 생성
DELETE /api/topic-reports/{report_id}
POST   /api/export-notion/topic-report
POST   /api/export-obsidian/topic-report
```

`POST /api/topic-reports`는 `/plan`에서 받은 `approvedRequest`와 approval을 수정 없이 사용한다. direct와 CLI 모두 같은 구조이며, 결과 보고서는 SharedJob의 committing 단계에서 내부 저장된다. 별도 공개 save API는 없다.

```json
{
  "approvedRequest": {"schemaVersion": 2, "planRevision": 2, "...": "plan 응답 값"},
  "approval": {"id": "apr_<uuid>", "token": "<43-char base64url>"},
  "execution": {
    "mode": "direct",
    "adapter": "auto",
    "fallbackPolicy": "rules_on_engine_failure"
  }
}
```

## 저장 JSON 주요 필드 (v2)

`markdown`, `topicPlan`, `evidencePackSummary`, `materialResolution`, `depthPolicy`, `researchTraceSummary`, `sourceUsage`, `evidenceItems`, `sourceLedger`, `checkpoints`, `dataGaps`, `marketTape`, `quality`, `qualityGeneration`, `personalOverlay`(기본 null), `generation`, `marketData`, `sources`, `deepResearch`, `researchResolution`, `marketStateResolution`, `executionProvenance`.

Step 6 Data Foundation Lite 이후 `checkpoints`/`evidenceItems`/`sourceLedger`/`dataGaps`/`marketTape`는 `features/common/research_schema/`와 `features/common/market_data/tape.py`의 공통 스키마를 사용한다. 기본 `markdown`은 구조화 필드 생성으로 바뀌지 않는다.
Step 7 Research Quality 이후 기존 저장 보고서의 `quality`가 없거나 구버전이면 조회 시 공통 evaluator로 재평가해 최신 `sourceGrounding` 필드를 포함한다.
Step 11 Quality Generation 이후 새 생성 보고서는 `qualityGeneration.mode/preflight/repairApplied/repairCount/repairType/weakSectionsBefore/weakSectionsAfter/qualityBefore/qualityAfter/telemetry/warnings`를 저장한다. 생성 전에는 Evidence Pack 축별 커버리지, challenging evidence, marketData/FRED/BOK 한계, Source & Data Notes를 품질 목표와 evidence coverage preflight로 주입한다. `llm_section_improve`는 sourceLedger/evidence/dataGaps 범위 안에서 약한 섹션만 LLM으로 최대 1회 재작성한다.

심층 모드 보고서는 `topicPlan.deepResearch`, `evidencePackSummary.questionCoverage`, `evidencePackSummary.deepResearch`, `sourceLedger[].researchQuestionId`, `sourceLedger[].researchRound`를 함께 저장한다. 독자 화면은 `researchTraceSummary`만 먼저 보여주고 전체 원장은 기본 접힘으로 표시한다. `quality` 점수·등급·상태와 candidate 비교값은 개발·자동 보강용 내부 지표이며 독자 화면에 직접 노출하지 않는다.

## 주의점

- yfinance 조회 실패 시 해당 티커 데이터는 생략되며 보고서 생성은 계속됩니다.
- FRED/BOK API 키가 없어도 yfinance 데이터와 로컬 자료로 fallback합니다.
- 로컬 자료가 없으면 시장 데이터만으로 분석합니다. LLM은 자료가 없는 수치를 추정임으로 표시해야 합니다.
- **Personal Overlay·재평가는 저장된 보고서에만** 동작합니다(파일 기준). overlay 생성은 기본 `markdown`을 수정하지 않습니다.
- Obsidian export 노트에는 `source_layer: primary_processed`, `reuse_as_evidence: false`가 붙어 Obsidian importer가 다시 evidence로 쓰지 않습니다(원칙 5).
