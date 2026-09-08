# Change Intelligence

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Change Intelligence

- 로직은 `features/common/change_intelligence/`에 둔다. 보고서/스냅샷 commit 시 artifact별 adapter(briefing/company/topic/market_memory)가 native 구조화 입력으로 `ChangeBasis`를 만들고 공통 comparator가 `changeSummary`를 생성한다. markdown은 comparator 입력이 아니다.
- status enum: `baseline_created | major_change | developing_signal | conflicting_uncertain | no_material_change | insufficient_basis`. `major_change`는 높은 materiality와 tier-1 근거 1개 또는 독립 tier-2 근거 2개 이상이 필요하며 unconfirmed lead만으로는 만들 수 없다.
- 권위 저장소: Briefing/Company/Topic은 보고서 JSON의 `changeSummary`, Market Memory는 `market_state_snapshots.payload_json`. `market-memory.sqlite3::change_event_index`는 양쪽에서 재구축 가능한 projection이며 projection 실패는 commit을 롤백하지 않는다.
- `change_event_index`의 PK는 `(artifact_kind, artifact_id)`다. 브리핑은 시장별로 저장되므로 `artifactId`에 시장을 붙인다(`2026-08-04.us`). 날짜만 쓰면 KR 커밋이 US 변화 이벤트를 덮어쓰고 Change Feed가 어느 브리핑을 열어야 할지 알 수 없다.
- 변화 단위의 `magnitude`는 [0,1] 범위의 상대 크기여야 한다. 브리핑 동인 점수처럼 상한 없는 합계를 절대값으로 쓰면 모든 재생성이 `major_change`가 된다. 동인은 그날 전체 점수 대비 비중과 순위로 비교한다.
- **비중과 움직인 양은 다른 값이다**(0.5.4). 어댑터가 선언하는 `magnitude`는 "이 단위가 그날 얼마나 큰가"인데 그것을 변화의 크기로 쓰면 매일 같은 크기로 존재하기만 해도 그만큼 변화가 잡힌다. 실측으로 `change_event_index` 61건 중 `no_material_change`가 **0건**이었고 브리핑은 baseline을 뺀 20건 전부가 피드에 떴다. 바닥이 둘이었다 — 이슈 상수 0.35 + 건수 가산 상한 0.25로 생긴 materiality **0.60 고정**, 그리고 `reliability >= 0.55`를 materiality의 **대안 조건**으로 둔 developing 게이트(브리핑은 발행처가 늘 여럿이라 이 값이 언제나 0.85다). 이제 단위가 측정법을 선언한다: `continuity: "churning"`(매번 다시 뽑히는 집합 — 등장·퇴장은 크기 0)과 `delta: {field, relative, scale, deadband}`(직전 값과의 차이). 건수 가산은 실제로 움직인 단위만 센다(상한 0.12).
- **지표 눈금은 자산군별이다.** 같은 %를 같은 변화로 재면 변동성 자산이 매일 상단을 차지한다 — 예전 눈금은 2.25% 이동이면 곧 major라 유가·VIX가 수시로 넘었다. `adapters/briefing.py::_METRIC_DELTA_CLASSES`가 소유하고, 저장된 브리핑의 일간 |등락률| 분포로 검증한다(각 지표의 중앙값이 deadband 안에 들어와 평범한 하루가 0이 되는지).
- **의미 비교는 직전과 현재 대표 기사가 모두 있는 단위만 판정한다.** 한쪽만 보내면 모델은 비교할 것이 없어 언제나 `new_information`을 답하고, 그 verdict가 승격 게이트를 통과시켜 강등 장치가 승격 장치가 된다(실측 2026-08-25 KR 브리핑은 판정 6건이 전부 그런 `added` 이슈였다). 그래서 **동인 `topDocs`가 이 층의 유일한 재료다** — 규칙 생성(`builder.py`)과 Agent 생성(`agent_mode/service.py`) 두 경로가 모두 저장해야 한다(Agent 경로가 빠뜨려 실제로는 이슈만 판정되고 있었다).
- **계보(`lineageId`)는 비교가 성립하는 범위다.** 종류를 나타내는 값을 계보로 쓰지 않는다 — 딥 리서치 custom 주제의 `topicKey`는 질문이 무엇이든 `custom`이라, 실측 21건이 한 계보에 묶여 18건이 `conflicting_uncertain`이었다(서로 다른 질문끼리 비교한 결과다). 정체성을 못 찾으면 보고서 자신이 계보이고 그러면 `baseline_created`가 된다 — 가짜 변화보다 "비교 기준 없음"이 정직하다.
- 변화 판정은 두 층이다. 규칙 비교기가 순위·비중·지표 이동과 증거 게이트를 결정하고, 의미 비교(`semantic.py`)가 브리핑 LLM 생성 잡 안에서 시장당 1회 대표 기사 제목을 대조해 `semanticVerdict` enum으로 내용 변화를 분류한다. `new_information/reversal`+증거 등급만 코드 게이트로 `major_change` 승격, `coverage_shift_only/no_new_information`은 강등, LLM 없으면 `not_evaluated`로 major 미확정. 변화 판정용 별도 Agent job은 만들지 않고 RSS/index job에는 change hook이 없다.
- 변화 단위의 대표 기사 제목은 `contextDocs`(hash 비교 밖)에 둔다. currentValue에 넣으면 제목 회전만으로 매일 모든 단위가 changed가 된다. 브리핑 저장 시 동인 `topDocs`(상위 3건 제목/출처/URL)와 이슈 대표 `title`을 보존한다.
- 수동 저장(`POST /api/analysis-reports`)이나 proposal 승인 편집은 새 change event를 만들지 않는다.

