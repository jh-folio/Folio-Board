# 딥 리서치 (Topic Research Agent v2)

화면 표시명은 **딥 리서치**입니다. 내부 폴더/API/저장 경로는 기존 호환을 위해 `topic_report` 이름을 유지합니다.

Folio Board 0.2에서는 좌측 navigation, Home 빠른 실행, command palette에 노출되는 기본 사용자 화면입니다. 실행 전에 승인 가능한 계획과 live evidence preview를 먼저 보여주며, 생성은 승인된 요청을 그대로 사용하는 SharedJob으로만 시작합니다.

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

딥 리서치 본문은 분석축·질문·근거 수에 따라 동적으로 배분하며, 완결에 필요한 만큼 쓰되 안전 상한 18,000자를 넘기지 않는 것을 목표로 한다(0.6 Phase 1, 2026-09-13 — 이전의 "일반적으로 12,000~16,000자" 목표 구간과 섹션별 최소 70% 하한은 실측 비교 후 없앴다. 아래 "본문 서술 방식" 참조). 각 근거 사용 섹션은 숨김 source ID 태그로 원장과 연결되고, 저장 전 구조·허용 출처·필수 자료·섹션 밀도를 검증한다. 초안과 채택된 보강 후보는 job 소유 checkpoint로 보관하므로 재시작 시 최신 검증 후보를 한 번만 원자 커밋할 수 있다.

설계 원칙 (CLAUDE.md §5와 동일):
- **2계층 분리**: 기본 보고서(Canonical)는 보편·자료 기반. 개인 해석은 `personalOverlay` 별도 필드에만. 기본 `markdown`은 overlay 생성으로 바뀌지 않는다.
- **enum 통제**: `reportType`(12종)·`evidenceRole`(5종)은 `topic_schema.py`에서 코드 검증. LLM 자유 텍스트 분류를 신뢰하지 않는다.
- **확증편향 방지**: 보고서에 반론/리스크 섹션 필수, Quality Gate가 counterargument/personal_bias_risk를 점검.
- **userContext ≠ evidence**: 관심 방향으로만 쓰고, 외부 자료와 충돌 시 충돌을 명시.

### 보고서 골격 (0.6 Phase 1, 2026-09-13)

```text
머리(고정) Executive Summary (질문 정의·분석 범위 포함)
본문(계획)  분석축이 그대로 섹션 — 2~8개 (질문에 대한 직접 답을 담는 이름 자유 섹션이 마지막에 온다)
꼬리(고정) 반론과 리스크 · 앞으로 확인할 체크포인트 · Source & Data Notes
```

- **머리·꼬리는 서식이 아니라 계약이다.** 꼬리는 §5 원칙 3(확증편향 방지)의 집행 장치이고, `checkpoints_from_markdown`·품질 평가의 `_SECTION_MARKERS`·리더가 **이름으로** 찾는다. 그래서 이 둘만 고정한다.
- **고정 목록을 한 번 더 줄였다(머리 3·꼬리 5 → 머리 1·꼬리 3).** Phase 1 B0/B1 실측 비교로 "촘촘한 고정보다 자유로운 서술이 낫다"가 확인된 뒤, 사용자 판단으로 이 여덟 이름 자체도 재검토했다 — "고정 내용이 너무 많다"는 지적에 따라 머리의 "Executive Summary"·"질문 정의와 분석 범위"를 하나로 합치고, 꼬리의 "시나리오"·"결론"을 이름 고정에서 뺐다. "핵심 데이터 대시보드"와 "시나리오"는 비교할 대상이 있을 때만 본문의 선택 섹션(표 포함)으로 쓴다. "결론"은 이름은 자유이되(예: "정리") **내용**(질문에 대한 직접 답, 판단이 흔들리는 조건)은 본문의 마지막 섹션에 반드시 있어야 한다 — 이건 이름으로 찾는 코드 계약이 아니라 프롬프트가 요구하는 내용 계약이다.
- **본문은 계획이 정한다**(`topic_schema.compose_sections` / `body_sections`). 예전에는 11개 전체가 고정이라, 유형별 템플릿 9개가 전부 같은 골격 안에서 강조점만 바꿨고 계획이 다른 구성을 선언할 통로도 없었다(승인 계약이 정확 일치를 요구). 결과는 주제와 안 맞는 섹션을 건너뛰지 못해 얇게 채우는 것이었다 — 실측으로 결론이 예산의 24%, 분석축 5개가 가중치 15% 섹션 하나에 밀려 축당 400자였다.
- **검증은 필수 요소만 차단한다**(`report_contract.validate_deep_report`). 머리·꼬리가 빠지면 `required_sections_missing`(blocking), 본문 구성이 계획과 다르면 `body_sections_differ`(major). 후자로 결과물을 버리지 않는다.
- **분량도 섹션 목록에서 나온다**(`depth_policy`). 머리·꼬리 비중은 고정이고 남은 몫(딥 65%, 옛 41%에서 확대 — 옛 "핵심 데이터 대시보드"·"시나리오"·"결론"의 몫이 이름 고정에서 빠지며 본문으로 넘어갔다)을 본문 섹션이 나눈다. 축이 늘면 축당 분량은 줄지만 본문 전체 몫은 유지된다.
- 본문 섹션 이름은 그대로 헤딩이 되므로 번호 접두와 `#`을 떼고, 예약 이름(머리·꼬리)과 중복을 거른다. 쓸 수 있는 본문이 2개 미만이면 기본 골격(`현재 상황 / 작동 경로 / 수혜·피해 자산과 기업`)으로 되돌린다.
- 이 축소는 `features/common/quality_generation/`(`quality_targets.py`의 필수 산출 요소 힌트, `preflight.py`의 "결론"/"정리" 완결 판정, `report_format.py`의 부분 재작성 가드)과 `features/common/research_quality/evaluator.py`(요약/판정 판정에 "정리" 동의어 추가)까지 함께 갱신했다 — 이 셋은 `topic_schema.py`의 튜플을 직접 참조하지 않고 각자 문자열을 들고 있어서, 고정 이름을 바꿀 때마다 같이 바꿔야 한다(§6 규칙 14와 같은 유형: 계약이 여러 곳에 흩어져 있으면 한쪽만 고치고 끝내기 쉽다).

### 질문이 계약이다 (0.5.5)

- **원문 질문이 생성 컨텍스트 최상단에 온다**(`_build_llm_context`). 40자 주제어가 제목·검색을 지배하는 동안 원문은 한 줄로 밀려 있었고, 보고서가 질문의 절반과 사용자가 직접 든 사례를 빠뜨렸다(실측: 본문에 `2021` 0회, `2024` 0회, `제약`·`어려움` 0회). 축별 분석 호출에도 원문 질문이 함께 간다 — 축만 주면 그 축을 독립 주제로 답한다.
- **질문이 나열한 사례·구간은 분석축이 된다**(`planner.ensure_question_axes` / `question_parts`). 줄머리 기호로 적은 항목을 뽑아 축에 없으면 **앞자리에** 넣는다. 축이 곧 본문 섹션이므로 축에서 빠지면 보고서에서 사라진다. 이미 덮인 항목은 중복 추가하지 않는다. 문장으로 적은 경우는 플래너 프롬프트가 받는다.
- **질문에 답했는지 검사한다**(`report_contract.unanswered_questions`). 연도가 든 질문은 그 연도가 본문에 있어야 답한 것으로 본다. 비교는 공백을 지우고 한다. 차단이 아니라 결함(severity 70)이고 보수가 고칠 본문 섹션을 가리킨다.
- **유형 템플릿은 섹션 이름을 부르지 않는다.** `compose_prompt()`가 템플릿을 기본 프롬프트 뒤에 붙이므로, 템플릿이 옛 섹션을 이름으로 지시하면 계획의 본문 섹션을 이긴다(실측: 계획 축 5개 → 보고서 섹션 7개).
- **근거 태그는 이름을 특정해 지우지 않는다.** 렌더러는 모든 HTML 주석을 지우고, 파서는 `SOURCE_TAG_NAMES`의 변형 이름을 받으며, 모르는 주석은 결함으로 남는다.

### 본문 서술 방식 (0.5.5)

독자는 그 주제를 **처음 보는 개인 투자자**다. 다만 이것은 **형식이 아니라 성질**이다.

필요한 개념을 그 자리에서 풀고, 무엇이 무엇을 움직이는지 보여 주고, 숫자로 확인하고, 질문에 답한다 — 그 순서와 문단 구성은 주제가 정한다. 번호 매긴 4단계로 지시했더니 모델이 `### 개념 / ### 작동 원리 / ### 실제로 지금 어떤가 / ### 그래서 이 질문에는` 소제목을 모든 섹션에 붙여 보고서가 서식이 됐다("소제목을 달 필요는 없다"고 적어 뒀는데도). **순서를 번호로 주면 목차로 읽힌다.** 같은 단계 소제목이 3개 이상 반복되면 `templated_step_headings` 결함으로 잡는다.

- 용어에 괄호 설명을 붙이는 데서 그치지 않고 **무엇이 무엇을 움직이는지** 단계로 푼다. 표를 쓰면 표 아래에 "이 표를 어떻게 읽어야 하는지"를 덧붙인다.
- 축 브리프가 `concept`·`mechanism`을 함께 받아 본문이 쓸 재료를 갖는다(`axis_analysis`).
- **섹션 예산 하한 숫자 자체를 없앴다(0.6 Phase 1, 2026-09-13).** 예전 프롬프트는 12,000~16,000자를 요구하면서 같은 문서에서 "각 섹션을 간결하게라도 모두 완성하는 것이 우선"이라고 적어 뒀고, 모델은 뒤를 따랐다 — 실측으로 모든 섹션이 예산의 20~60%만 찼다. 이 회귀를 막던 장치가 "각 섹션 최소 70%" 고정 하한이었다. `plan/DEEP_RESEARCH_REPORT_EXPERIENCE_PLAN.md` §5.1대로 같은 고정 입력에 대해 이 하한을 포함한 엄격한 형식(B0)과 하한이 없는 자유 형식(B1)을 각 1회 실제 생성해 사용자가 눈가리고 비교한 결과, B1의 글이 더 낫다고 확인됐다 — 그래서 지금은 하한 숫자 대신 "완결에 필요한 만큼 쓴다"와 "이미 한 말을 채우기 위해 반복하지 않는다"라는 반대쪽 원칙 둘로 같은 회귀를 막는다. 채울 말이 없으면 분량을 줄이지 말고 무엇을 확인하지 못했는지와 그 한계를 그 자리에 쓰는 것은 그대로다. `test_report_templates.py::test_prompt_does_not_tell_the_model_to_be_brief`가 간결 지시 문구의 부활과 새 원칙 문구의 존재를 함께 검사한다.
- **표는 여러 항목을 한눈에 비교하는 자리에서만 필수다.** 같은 B0/B1 비교에서 B1은 표를 전부 없앤 산문만으로 썼는데, 사용자 판단은 "줄글 방식은 확실히 낫지만 표가 없는 것보단 있는 게 확실히 낫다"였다 — 표 정책만 되돌리고 줄글 방식(용어를 그 자리에서 풀고 하나로 이어지는 논지로 쓰는 것)은 그대로 채택했다. 처음에는 핵심 데이터 대시보드·시나리오·체크포인트 3개 섹션에 표를 강제했지만, 곧이어 머리·꼬리 헤딩 자체를 다시 줄이면서(위 "보고서 골격" 참고) 핵심 데이터 대시보드·시나리오는 고정 이름에서 빠져 본문의 선택 섹션이 됐다 — **표가 항상 붙는 고정 자리는 이제 체크포인트 하나뿐이고**, 그 행 수의 고정 숫자는 없애 "비교 대상 수만큼"으로 뒀다. 그 외 모든 자리(Executive Summary, 본문, 선택적으로 쓰는 시나리오 포함)는 표가 산문보다 비교를 명확히 할 때만 쓰는 양방향 규칙이다(`prompt.md`의 "표를 쓸지는 필요성이 정한다" 절).
- 본문 섹션이 꼬리(반론·체크포인트)와 겹치면 **본문은 분석을, 꼬리는 판단표를** 맡는다. 본문에서 "아래 표 참조"로 미루면 그 섹션이 비어 버린다(실측 262자).

### 축별 분석 패스 (0.5.5)

- `axis_analysis.build_axis_briefs()`가 **축마다 한 번씩** 모델을 불러 그 축의 하위 질문에 답하는 브리프를 만든다: `concept` / `mechanism` / `findings` / `numbers` / `counterEvidence` / `competingExplanations` / `whatWouldChangeThis` / `uncertainties` / `sourceIds`.
- **경쟁 가설과 반증 조건은 반대 근거와 다르다**(0.5.6). `counterEvidence`가 "어긋나는 자료"라면 `competingExplanations`는 "같은 자료의 다른 이야기"이고, `whatWouldChangeThis`는 "틀렸다면 무엇이 관측되어야 하는가"다. 새 단계를 만들지 않고 기존 브리프에 필드를 더한다 — 단계가 늘수록 CLI 비용과 실패 지점이 함께 는다. 핵심 논지 선정이 이 두 필드를 입력으로 받는다.
- 예전에는 하위 질문 12개를 만들어 **검색에만** 쓰고 버렸다. 생성 컨텍스트는 질문 목록을 넣으면서 커버리지 보고만 지시했고, 각 질문에 답하라는 말이 없었다.
- 브리프는 근거 안에서만 쓴다. 모델이 돌려준 sourceId는 **그 축이 실제로 본 근거**와 대조해 걸러낸다(지어낸 id 차단).
- 한 축이 실패해도 보고서를 죽이지 않는다 — `status`(`ok`/`empty`/`unavailable`/`skipped_budget`)로 남기고 본문 생성은 계속한다. 호출 수는 `MAX_AXIS_CALLS`(8)로 묶인다.
- 타임아웃은 `TOPIC_AXIS_CLI_TIMEOUT_SECONDS`(600) / `TOPIC_AXIS_API_TIMEOUT_SECONDS`(240)다. 축 수만큼 호출이 늘어 보고서 1건의 실행 시간이 길어진다.

### 웹 조회 패스 (0.5.5)

- **찾기와 쓰기를 분리한다**(`web_lookup.py`). 축별 브리프 호출에 "필요하면 검색도 하라"를 얹는 방식은 네 번(도구 활성화 → 팩 허가문 → 겉 프롬프트 허가 → 축별 의무) 모두 실패했다 — 실측으로 웹에서 새로 온 URL이 0~1건이었다. 브리프는 **쓰기 과제**라 팩에 근거가 있으면 모델이 충분하다고 판단한다. 같은 어댑터에 순수한 **찾기 과제**를 주면 곧바로 검색한다(사실 12건·발언 6건을 FOMC 녹취·BLS 아카이브·BOJ 성명에서 가져왔다).
- **발동 조건은 개수가 아니라 시점이다.** 로컬 색인은 보관 기간상 약 3개월이라 그 창 밖의 국면은 근거가 몇 건 잡히든 답할 수 없다 — 실측으로 "2021~2022 인플레이션" 축이 근거 4건을 받았지만 전부 2021년을 스쳐 언급한 2026년 기사였다. 호출 수는 `MAX_LOOKUPS`(4)로 묶인다.
- **찾아온 사실은 원장에 `web_xxx`로 등재해야 본문이 쓴다.** 딥 계약이 "제공된 source ID만 쓰라"고 하므로 등재하지 않으면 인용할 자격이 없는 자료가 된다(실측: 등재 전 1건 → 등재 후 12/13건 인용). 축 브리프의 sourceId 필터도 `web_`을 허용한다.
- **사용은 태그로, URL 인쇄는 따로 센다.** `fromWeb`(본문에 URL이 찍혔는가) 하나로 재던 시절, 본문이 CPI 7.0%·6.5%를 그대로 서술하는데도 1건으로 나왔다. `webSearchAudit`은 `citedSourceIds`(실사용) / `availableSourceIds`(등재) / `printedUrls`(인쇄)로 가른다.
- **한 출처는 한 ID를 갖는다.** 사실마다 새 번호를 매기면 원장이 URL로 중복을 제거하는 순간 조회 블록이 인용하라고 알려 준 ID의 일부가 원장에 없어진다 — 모델은 시킨 대로 인용하고 계약은 `unknown_source_tag`(심각도 60)로 잡는다(실측: 28건 중 10건). 번호는 URL 기준이고 같은 문서의 여러 사실은 ID를 공유한다.
- **CLI 어댑터도 웹에 닿는다**(`agent_mode/bridge.py::WEB_SEARCH_ARGS`). codex는 `-c tools.web_search=true`, claude는 `--allowedTools WebSearch`이며 샌드박스를 풀지 않고 모델 쪽 검색 도구만 켠다.

### 핵심 논지 선정 (0.5.6)

- **본문을 쓰기 전에 한 번 멈춘다**(`thesis.py::select_thesis`). 축별 브리프가 다섯 개 모여도 본문 생성은 그것을 병렬로 늘어놓았다 — 실측으로 인플레 → 금리 → 엔캐리 → 정책 → 한국 시장을 차례로 다루고 끝났고, 중심이 없으니 꼬리 섹션 넷이 같은 메시지를 되풀이했다.
- **나열을 금지한다.** 가능성을 모두 적는 것은 판단이 아니라 판단의 회피다. 근거가 약하면 `confidence`를 낮추되 **하나는 고른다**.
- `confidence`는 enum(`high|medium|low`)이며 문장 강도로 옮겨 준다(§5 원칙 4) — high는 단정형, medium은 "무게를 싣는다", low는 "경계가 필요하다".
- **버린 해석과 반증 조건을 함께 싣는다.** 논지를 세우는 일이 확증편향의 입구가 될 수 있어 계약에 박는다(§5 원칙 3). 반증 조건은 체크포인트 섹션의 뼈대가 된다.
- 논지 블록은 컨텍스트에서 축 블록 **뒤**에 둔다 — 나중 지시가 더 구체적인 것으로 읽히므로 재료보다 프레임이 뒤에 와야 이긴다(유형 템플릿 순서 버그에서 확인).
- sourceId는 축이 실제로 본 근거와 대조해 거른다. 실패하면 빈 dict를 돌려주고 본문은 예전처럼 축 브리프로 쓴다.
- 실측 효과(같은 질문 재생성): 본문 10,100자 → **14,912자**, 계약 결함 14건 → **1건**, 축 섹션 충족률 23~54% → **101~121%**, 유보 표현 천자당 3.07 → **1.83**, 발언 실명 0회 → **파월 7·월러 2회**.

### 초안 재시도 (0.5.6)

- **못 쓸 초안은 쓰기만 한 번 더 시킨다**(`draft_guard.py`). 딥 실행에서 값비싼 것은 쓰기가 아니라 그 앞이다 — 근거 팩, 웹 조회(최대 4회), 축 브리프(최대 8회), 논지 선정(1회). 그런데 초안 생성은 한 번뿐이고 재시도 경로가 없어서, 마지막 쓰기 한 번이 어긋나면 앞의 모든 것이 함께 버려졌다.
- 실측(같은 질문 4회): 14,912자 계약 OK / **필수 섹션 누락으로 잡 실패**(9분을 쓰고 아무것도 남기지 못했다) / 13,541자 계약 OK / **5,569자 스텁**(하한의 46%). 같은 질문·같은 코드인데 절반이 못 쓸 초안이었다.
- **판정은 차단 사유와 명백한 스텁만 본다.** 고정 머리·꼬리 섹션 누락(`draft_sections_missing`), 하한의 60%(`MIN_DRAFT_RATIO`) 미만(`draft_stub`), 빈 본문(`draft_empty`). 문체·근거 연결은 보수 패스의 몫이라 넣지 않는다 — 여기서 걸러 버리면 보수가 할 일을 재생성이 대신한다.
- **재시도는 한 번이다.** 반복 재작성 루프를 만들지 않는다(Quality Generation 계약과 같다).
- **실패한 초안을 되돌려 주지 않는다.** 앵커가 되어 같은 실수를 되풀이한다. 무엇이 잘못됐는지와 써야 할 섹션 목록만 짚는다.
- **재시도가 더 나쁘면 처음 것을 쓴다.** 사유 수가 같으면 더 채운 쪽을 고른다. 나쁜 초안이라도 없는 것보다 낫다. 결과는 보고서의 `draftGuard`에 남는다.

### 계획 산출물 위생 (0.6)

- **`candidateTickers`는 코드가 형식을 강제한다**(`topic_schema._ticker_map`). 계약은 `{티커: 표시명}`인데 플래너가 `{"cloud_and_compute": "['AMZN', 'NVDA']"}`처럼 **그룹 이름 → 티커 목록**을 돌려줬다. 승인 계약(`normalize_tickers`)이 키를 티커로 검증하다 `invalid_ticker`로 터져, 60초짜리 계획 호출이 통째로 422가 됐다(2026-09-03 재현).
- **값이 목록 모양이면 키는 그룹 이름이다.** 키 모양으로 먼저 가르면 `payments`·`group`처럼 밑줄 없는 그룹 이름이 티커 패턴을 통과해 목록 문자열을 표시명으로 달고 들어온다.
- 그룹 이름은 표시명으로 남긴다 — 모델이 왜 묶었는지를 잃지 않는다. 산문 라벨은 건지지 않는다(대문자 낱말을 티커로 오인한다). 선행 `^`를 허용해야 대표지수(`^GSPC`·`^KS11`)가 살아남는다.
- 못 읽는 항목은 **버리되 요청을 죽이지 않는다.** 검색어 위생(`planner._clean_queries`)과 같은 자리·같은 이유다 — 프롬프트로 부탁한 것과 모델이 지킨 것은 다르다.
- **입력 검증 실패와 계획 생성 실패는 다른 코드다.** 둘 다 `ValidationError`지만 원인이 정반대라, 한 코드로 뭉뚱그리면 화면이 멀쩡한 질문에 대고 "질문을 1~500자로 입력하세요"라고 말한다. 지금 계획 쪽은 `plan_invalid`이고 안내는 "다시 시도하거나 빠른 계획으로".

### 실행 재개 (0.6)

- **초안 이전 단계를 체크포인트로 남긴다**(`resume_store.py`). 초안 재시도와 같은 진단에서 나온 처방이다 — 값비싼 것은 쓰기가 아니라 그 앞인데(웹 조회 최대 4회, 축 브리프 축당 1회, 논지 1회), 그 셋이 전부 `build_approved_report()`의 지역 변수라 초안 호출이 죽으면 함께 사라졌다.
- 실측: 어댑터 사용량 한도(429)에 걸린 실행이 11분과 **이미 성공한 축 브리프까지** 버리고 `deep_initial_engine_failed_without_candidate`로 끝났다. 다시 누르면 같은 호출을 처음부터 태워, 한도로 죽은 실행이 남은 사용량을 또 먹었다.
- **저장 위치는 `data/topic-resume/`이며 `data/job-context/` 밖이다.** 잡이 종료되는 순간 `shared_jobs_private.cleanup_owner()`가 job-context를 통째로 지우므로(비공개 pack 계약), 거기 두면 체크포인트가 정확히 필요한 순간에 사라진다.
- 키는 `{기준일}_{planHash 12자}`로 `approved_generation_support`의 artifact_id와 같은 모양이다. **재개는 계획·기준일·선별 근거·어댑터·요청 모드가 모두 같을 때만** 성립한다(지문 불일치는 없는 것으로 본다).
- **유효기간은 24시간**이다(`TOPIC_RESUME_TTL_HOURS`). 근거 팩은 그 시점 자료의 스냅샷이라 어제 브리프로 오늘 보고서를 쓰면 어제 자료로 오늘을 말하게 된다.
- **성공한 단계만 남긴다.** `status != "ok"`인 축 브리프와 조회는 저장하지 않아 다음 실행이 그 축을 다시 시도한다. 보고서가 커밋되면 파일을 지운다 — 실패했을 때만 남아 있어야 이어받는다.
- 체크포인트 저장 실패는 생성을 죽이지 않는다. 못 남기면 다음 실행이 그 단계를 다시 할 뿐이고, 그건 이 기능 이전의 동작과 같다.
- **사용량 한도는 실패 이름을 따로 갖는다**(`bridge.AgentRateLimitError` → `fallbackReason=engine_rate_limited`). 코드 결함과 대처가 다른데(기다린다 vs 고친다) 예전에는 `adapter_failed`만 남아 CLI 세션 기록을 직접 열어야 429였다는 사실을 알 수 있었다. 한도는 exit 0 + 빈 stdout으로도 오므로 두 자리 모두에서 잡는다.

### 리서치 에디터 (0.5.6)

- **분석가와 작가를 나눈다**(`editor.py`). 최종 생성 호출이 두 역할을 겸하면 모델은 안전한 쪽으로 기운다 — 유보 표현 과잉, 꼬리 섹션 반복, 발언 익명화가 전부 그 결과다. 웹 검색에서 확인한 "찾기/쓰기 분리"와 같은 처방이다.
- 에디터가 하는 일: 결론 우선 재배열, caveat 압축(문단당 1회 원칙, **없애지 말고 모은다**), 반복 통합, 발언 실명·시점 복원, 문장 길이 변화, 메타 문장 제거.
- **금지는 프롬프트가 아니라 코드가 집행한다**(`check_edit`). 프롬프트는 부탁이지 제한이 아니라는 것을 이 프로젝트에서 반복 확인했다. 새 수치 / 새 근거 ID / 근거 태그 유실 / 반론 축소 / 섹션 변경 / 분량 급감(85% 미만) / **분량 급증(125% 초과)**을 원문과 대조해 하나라도 걸리면 **편집본을 버리고 초안을 쓴다**(보고서를 죽이지 않는다).
- **늘리는 것도 막아야 한다.** 실측으로 초안 5,569자가 편집본 13,415자로 나왔고(+141%), 새 수치·새 ID가 없어 검사를 전부 통과했지만 근거 없는 산문이 채워져 `unlinked_section` 7건과 `low_source_linkage`가 남았다. 초안이 짧은 것은 보수 패스가 다룰 일이지 에디터가 대신 쓸 일이 아니다 — 그 경계가 무너지면 보고서가 근거에 매이지 않은 글이 된다.
- 표기 변형(7.0% → 7%)은 통과시킨다. 그것까지 막으면 정당한 편집이 통째로 버려진다.
- **반론 태그는 원문에서 센다.** `visible_markdown`은 주석을 지우므로 그 위에서 세면 언제나 0이고, 근거가 통째로 빠져도 검사가 걸리지 않는다.
- **에디터에게 분량을 맡기지 않는다.** 섹션 예산을 주면 그 하한까지 채우려 하고, 그러면 확장 상한에 걸려 편집본이 통째로 버려진다(실측: 초안 10,751자를 받은 에디터가 16,086자(+50%)를 내놓아 거부됐다 — 시킨 대로 했는데 거부당한 것이다). 짧은 초안은 보수 패스가 채운다. 거부된 편집도 길이를 기록에 남긴다.
- 에디터 호출은 **웹 검색을 끈다**. 사실을 더할 통로를 만들지 않는다. 타임아웃은 `TOPIC_EDITOR_CLI_TIMEOUT_SECONDS`(1200) / `TOPIC_EDITOR_API_TIMEOUT_SECONDS`(600).

### 문체 계약 (0.5.6)

- **측정할 수 있는 둘만 잰다.** "자연스러움"은 계약에 넣지 않는다 — 규칙으로 강제한 서술 형식이 오히려 품질을 해친 실패를 두 번 겪었다(11개 섹션 고정 골격, 4단계 초심자 소제목).
- **유보 표현 밀도**(`hedge_stats`): 천자당 `HEDGE_DENSITY_LIMIT`(2.5) 초과면 `hedge_overuse`. 한 표현이 10회 이상이면서 천자당 1.5를 넘으면 `hedge_repetition` — 총량이 적어도 한 표현만 스무 번 나오면 글이 같은 자리에서 계속 멈춘다(실측: 유보 31회 중 23회가 `수 있다`). Source & Data Notes는 데이터 한계 서술이 그 섹션의 일이므로 밀도에서 뺀다.
- **결함은 고칠 자리를 가리킨다.** `repairable_sections`가 `section`이 빈 결함을 건너뛰므로, 자리를 주지 않으면 그 결함은 점수만 깎고 보수 경로가 손댈 수 없다(실측: 유보 쏠림 결함이 잡혔는데 보수 시도가 0회였다). 유보는 가장 몰린 섹션, 발언 귀속은 그 근거를 인용한 섹션을 가리킨다.
- **발언 귀속**(`unattributed_speech`): 인용한 발언 근거의 화자를 본문이 밝혔는가. **이름이 아니라 직함으로 본다** — 원문이 "Jerome H. Powell"이고 본문이 "파월"이라 글자가 겹치지 않지만 `의장`·`총재`·`이사`는 두 표기에 함께 남는다. 인용하지 않은 발언까지 귀속을 요구하지 않는다.

### 근거 수집 계약 (0.5.5)

- **질의는 이어 붙이지 않고 하나씩 검색해 RRF(k=60)로 합친다**(`common/research_library/search/multi_query.py`). FTS5는 토큰을 OR로 풀기 때문에 검색어 여러 개를 공백으로 이으면 어느 한 토큰만 스친 문서가 상위로 온다 — 실측으로 금리 리포트의 근거 목록에 인도 중앙은행·터키 물가·프랑스 강관회사 의결권 공시가 실렸다. 여러 질의에 함께 걸린 문서가 위로 가고, 질의 하나가 실패해도 나머지 순위가 남는다. 정렬은 완전 결정적이다(승인 경로가 `selectedEvidenceIds`로 근거 구성을 재검증한다).
- **보도자료는 근거에서 뺀다**(`search/filters.py::is_press_release`). 브리핑과 RSS 화면은 이미 걸렀지만 텍스트 질의 검색 경로는 경로 접두만 보고 `source_type`을 보지 않았다. 규칙을 아는 곳은 이 함수 하나이며 `daily_briefing.is_news_document()`도 이것을 부른다.
- **딥 모드에서도 축별 검색이 반드시 돈다**(`evidence.py`). 예전에는 하위 질문 검색만 돌아서, 질문이 배정되지 않은 축은 자기 검색어(`term premium fiscal supply` 등)를 한 번도 쓰지 못한 채 0건으로 기록됐다 — 자료가 없어서가 아니라 찾지 않아서 생긴 0건이다.
- **커버리지는 검색이 찾은 자료로 센다.** 그 축/질문 이름으로 새로 admit된 항목만 세면, 전역 중복 제거 때문에 앞선 질문이 같은 문서를 먼저 가져간 축이 0건으로 남는다. 그 0건이 그대로 "로컬 자료가 부족합니다" 데이터 갭이 되어 본문 한계 서술로 실렸다. 문서 자체는 계속 한 번만 팩에 들어간다.
- **하위 질문은 축을 너비 우선으로 채우고 질문마다 다른 검색어를 받는다**(`planner.py`). 라운드1 상한은 `topic_schema.DEEP_MAX_ROUND_1_QUESTIONS`(10)이며 계획 생성기와 승인 계약(`approved_plan_schema.py`)이 같은 상수를 읽는다. 6이던 시절에는 축이 5개일 때 첫 축만 질문을 받고 라운드2 반증 질문까지 상한에 밀려 사라졌다.

### 자료 깊이 계약 (0.5.5)

- **계획의 `requiredMacroData`를 실제로 조회한다**(`macro_data.resolve_fred_series`). 예전에는 계획에 적어 화면에 보여주기까지 하고서 custom 고정값 3종(FEDFUNDS/UNRATE/DGS10)만 받아왔다 — 기대인플레이션(`T10YIE`)과 실질금리(`DFII10`)를 계획이 요청했는데도 보고서는 "장기금리 상승을 분해할 자료가 없다"고 적었다. **요청 시리즈는 LLM이 쓴 자유 텍스트이므로 `FRED_SERIES_META` 허용 목록으로 거른다**(§5 원칙 4).
- **FRED 관측치는 일간 기준 약 7년을 받아 분기 요약으로 싣는다.** 14개만 받던 시절 월간 시리즈는 1년, 일간 시리즈는 3주였다. 전년 대비도 인덱스가 아니라 **날짜**로 찾는다 — `obs[12]`는 월간에서만 1년이고 일간(DGS10)에서는 12영업일이라 표의 "전년 대비"가 사실은 2주 변화였다.
- **거시 지표의 변화는 단위가 갈린다.** 금리처럼 이미 퍼센트인 계열은 `%p`, 지수·수준값은 `%`다(`change_unit()`). 단위 없이 절대 차이를 실었더니 모델이 근원 CPI 지수의 1년 차이 8.11포인트를 "전년 대비 +8.11%"로 읽어 본문에 실었다(실제 약 2.5%).
- **가격 시계열은 긴 구간을 한 번 받아 분기 종가로 싣는다**(`data_fetcher._quarterly_closes`, 기본 10년). 통계·상관관계는 계속 `history_period` 창에서만 계산한다 — 창을 늘리면 "1년 상관계수 -0.939" 같은 기존 해석의 의미가 조용히 바뀐다.
- **관련도 상위 근거에는 저장된 기사 본문을 함께 싣는다**(`evidence_text.py`). 실측으로 근거 29건 중 19건이 전문 보유였고 저장 본문 합계가 88,792자인데 모델에게 간 것은 스니펫 약 11,600자, **가진 자료의 13%**였다. 상한은 `TOPIC_EVIDENCE_BODY_CHARS`(2,000) / `TOPIC_EVIDENCE_BODY_BUDGET`(50,000) / `TOPIC_EVIDENCE_BODY_DOCS`(14)로 조절한다. 본문 앞에 사이트 메뉴가 섞이는 것을 추측으로 지우지 않는다 — 요약 문장을 본문에서 되찾는 방식은 실측 40건 중 10건만 맞았다.

### 저장 계약 주의 (0.5.5)

- **보고서 JSON에 실리는 값은 JSON 타입만이다.** `common/canonical_json.py`가 `None|bool|int|float|str|list|dict` 외에는 `assert_never`로 죽는다. `marketData.tickers[].quarterlyHistory` 같은 시계열도 tuple이 아니라 `[분기, 값]` list로 만든다 — tuple로 두면 계획·검색·생성이 다 끝난 뒤 저장 직전에 실패해 CLI 수 분이 통째로 버려진다(실측: 진행률 90%에서 `internal_error`).
- **딥 파이프라인의 계약 위반 실패는 `validation_failed`로 나온다**(`approved_jobs._failure_code`). 실패 결과는 status/errorCode 고정 계약이라 자유 필드를 실을 수 없어, 원인을 ErrorCode로 전한다.

### 품질 눈금 (0.5.5)

- **계약 결함도 점수에 상한을 건다**(`deep_pipeline.apply_contract_ceiling`, 0.5.6). 결함 14건인 보고서가 **93점 / A / pass**를 받았다 — 근거 없는 섹션 7개·분량 미달·본문 구성 불일치를 전부 안고서. 계약은 제대로 잡았는데 점수가 그것을 읽지 않아 사용자에게는 A로 보였다. 심각도 70 이상이면 69점, 40 이상이면 89점, 주요 결함 3건 이상이면 79점이며 이유는 `quality.contractCeiling`에 남는다(실측 그 보고서는 69 / C+ / warn). 계약 결함은 딥 파이프라인만 아는 것이라 평가기를 일반적으로 두고 여기서 씌운다.
- **근거가 0건인 분석 축이 있으면 점수에 상한을 건다**(`common/research_quality/evaluator.py`). 가중 평균만으로는 축 5개 중 3개가 0건이고 본문이 그 사실을 반복해 적은 보고서가 **87점 / A- / pass**를 받는다. 축 절반 이상이 비면 59점, 하나라도 비면 74점이 상한이고 이유는 `quality.coverageCeiling`에 남는다. 축 하나가 통째로 비는 것은 감점이 아니라 결격이다.

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
- `features/topic_report/axis_analysis.py`: 축별 분석 패스(하위 질문에 답하는 브리프 → 본문 섹션의 뼈대)
- `features/topic_report/evidence_text.py`: 관련도 상위 근거의 기사 본문 첨부(자료 폴더 밖 경로 차단, 분량 예산)
- `features/common/research_library/search/multi_query.py`: 질의별 검색 결과 RRF 합산
- `features/common/research_library/search/filters.py`: 보도자료 판정(브리핑과 공유)
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
