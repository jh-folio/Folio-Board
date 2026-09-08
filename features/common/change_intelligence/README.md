# Change Intelligence

Change Intelligence는 기업분석·테마분석·시장 상태가 생성되어 commit되기 직전에 같은 작업이 이미 검토한 구조화 자료를 이전 committed artifact와 비교합니다. Markdown diff를 사용하지 않고, 변화 판정을 위해 별도 Agent job을 만들지 않습니다. 브리핑에서는 새 비교·의미 판정·이벤트 projection을 만들지 않으며, 과거 브리핑 JSON과 projection은 기존 데이터 호환 및 복구를 위해 읽을 수 있습니다.

## 과거 브리핑 호환 의미 비교

과거 브리핑 JSON과 projection을 읽고 복구하는 경로에서 의미 비교 결과를 해석할 때는 실행 중인 작업의 CLI/API 선택을 우선합니다. CLI 작업은 사용하지 않는 API 모델·추론 강도 설정을 검사하지 않고, 같은 CLI·모델·추론 강도를 전달합니다. 부가 의미 비교의 설정 오류·잘못된 응답은 `not_evaluated`로 남기며 보고서 저장을 중단시키지 않습니다. 실제 본문 사실 검사와 저장 검증은 그대로 적용됩니다. 새 브리핑 저장 경로는 이 의미 비교를 호출하지 않습니다.

판정은 두 층으로 나뉩니다.

1. **규칙 비교기 (`comparator.py`)** — 어떤 단위가 생기고/사라지고/움직였는지, materiality와 증거 corroboration을 결정적으로 계산합니다. 브리핑 동인은 상한 없는 점수 합이 아니라 그날 전체 대비 순위·비중으로 비교합니다.

2. **의미 비교 (`semantic.py`)** — 순위·비중 이동은 보도량 구성의 함수라 내용 변화를 말하지 못합니다. 이 모듈은 과거 브리핑 데이터의 호환·복구와 일일 뉴스 의미 계약에서 사용하는 enum·검증 유틸을 보존하지만, 새 브리핑 저장 경로에서는 호출하지 않습니다.

### 변화의 크기는 무엇으로 재는가

**단위의 비중과 움직인 양은 다른 값이다.** 어댑터가 선언하는 `magnitude`는 "이 단위가 그날 얼마나 큰가"(동인 비중, 이슈 상수)입니다. 그것을 그대로 변화의 크기로 쓰면 매일 같은 크기로 **존재하기만 해도** 그만큼의 변화가 잡힙니다. 실제로 `change_event_index` 61건 중 `no_material_change`는 0건이었고, 브리핑은 baseline을 뺀 20건 전부가 피드에 떴습니다. 바닥은 둘이었습니다 — 이슈 상수 0.35에 건수 가산 상한 0.25가 매일 붙어 생긴 materiality 0.60, 그리고 `reliability >= 0.55`를 materiality의 **대안 조건**으로 둔 developing_signal 게이트(브리핑은 발행처가 늘 여럿이라 이 값이 언제나 0.85입니다).

그래서 변화 단위는 측정법을 함께 선언합니다.

- `continuity: "churning"` — 매 생성마다 집합이 다시 뽑히는 단위. 브리핑 이슈(`issueId`가 그 클러스터의 문서 집합 해시라 기사 한 건만 달라져도 값이 바뀝니다)와 Market Memory의 LLM 드라이버 목록이 여기 해당합니다. 등장·퇴장은 변화의 크기가 **0**이며, 내용이 달라졌는지는 의미 비교가 판정합니다. 목록에서 사라지지는 않습니다.
- `delta: {field, relative, scale, deadband}` — 직전 값과의 차이로 재는 단위. 동인은 비중 이동(`{"field": "share", "scale": 0.5}`), 지표는 상대 변동률입니다. `deadband` 이하는 0, `deadband + scale`에서 1.0입니다.
- 지표 눈금은 자산군별입니다(`adapters/briefing.py::_METRIC_DELTA_CLASSES`). 같은 %를 같은 변화로 재면 변동성 자산이 매일 상단을 차지합니다 — 예전 눈금은 2.25% 이동이면 곧 `major_change`라 유가·VIX가 수시로 넘었습니다. 눈금은 저장된 브리핑의 일간 |등락률| 분포로 검증합니다(각 지표의 **중앙값이 deadband 안에** 들어와 평범한 하루가 0이 되는지).
- 건수 가산은 **실제로 움직인 단위**만 셉니다(상한 0.12). 전부 세던 시절 지표 12개가 종가 차이만으로 늘 changed였습니다.
### 상태 게이트

`major_change`는 materiality 0.7 + 증거 등급, `developing_signal`은 materiality 0.3입니다. **증거 등급만으로는 승격하지 않습니다** — 그 대안 조건이 두 번째 바닥이었습니다.

의미 비교는 **직전과 현재 대표 기사가 모두 있는 단위만** 판정합니다. 한쪽만 보내면 모델은 비교할 것이 없어 언제나 `new_information`을 답하고, 그 verdict가 승격 게이트를 통과시켜 강등 장치가 승격 장치가 됩니다(실측 2026-08-25 KR 브리핑은 판정 6건이 전부 그런 `added` 이슈였습니다). 따라서 **동인의 `topDocs`가 곧 이 층의 재료입니다** — 규칙 생성과 Agent 생성 두 경로가 모두 저장해야 합니다(Agent 경로가 빠뜨린 적이 있습니다).

상태 게이트는 코드가 확정합니다: `new_information/reversal` + 증거 등급(tier-1 하나 또는 독립 tier-2 둘)만 `major_change`로 승격하고, `coverage_shift_only/no_new_information`은 물량 기반 major를 강등합니다. LLM이 없으면 `not_evaluated`로 표시하고 지표 급변 단독 케이스(`METRIC_ALONE_MAJOR_MAGNITUDE`, 그 자산에서 드문 하루)를 제외하면 major를 확정하지 않습니다(`uncertainties: semantic_not_evaluated`). 규칙 모드 생성은 LLM을 호출하지 않습니다.

## Authority

- Company Analysis, Topic Report: 각 report JSON의 `changeBasis`, `changeSummary`
- Briefing: 새 저장본에는 Change Intelligence 필드를 만들지 않으며, 과거 저장본의 필드는 호환용으로만 읽습니다.
- Market Memory: `market_state_snapshots.payload_json`의 `changeBasis`, `changeSummary`
- `market-memory.sqlite3::change_event_index`: 두 authority를 조회하는 재구축 가능한 projection

계보(`lineageId`)는 **비교가 성립하는 범위**입니다. 종류를 나타내는 값(딥 리서치 custom 주제의 `topicKey: "custom"`)을 계보로 쓰면 아무 관계 없는 질문끼리 기준선-비교 대상이 됩니다 — 실측으로 딥 리서치 21건이 한 계보에 묶여 18건이 `conflicting_uncertain`이었습니다. 정체성을 찾지 못하면 보고서 자신이 계보이고, 그러면 기준선이 없어 `baseline_created`가 됩니다. 서로 다른 질문을 비교해 만든 가짜 변화보다 "비교 기준 없음"이 정직합니다.

입력이 없거나 Markdown뿐이면 `insufficient_basis`입니다. 확인 전 fast-origin lead 하나만으로 `major_change`를 만들 수 없습니다. `major_change`는 high materiality와 tier-1 하나 또는 독립 tier-2 둘 이상이 필요합니다.

## 데이터 경계

`changeUnits` 24개, `sourceRefs` 32개, 반대 신호·불확실성 각 12개로 제한합니다. 원문을 복제하지 않고 제목·URL·hash·tier·시각 metadata만 보존합니다. Personal Overlay와 상담은 comparator 입력이 아닙니다.
