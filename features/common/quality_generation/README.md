# Quality Generation

Quality Generation은 보고서가 생성되기 전에 품질 목표와 자료 보강 경로를 알려주는 공통 레이어입니다. 브리핑 production 저장 경로는 authored Markdown을 보존하며 semantic quality 평가·문체 검사·수리·모델 호출을 수행하지 않습니다.

## 흐름

```text
quality targets -> preflight -> evidence coverage block -> generation
  -> qualityGeneration telemetry (briefing production: content not assessed)
```

`quality_targets.py`는 보고서 유형별로 필요한 evidence mix, 자료 수집 경로, 필수 출력 요소, source boundary를 정의합니다. 브리핑, 기업분석, 테마분석은 모두 이 블록을 LLM context에 받아 첫 초안부터 같은 기준으로 쓰이도록 합니다.

## 정책

- 기본 모드는 `diagnose_only`입니다. 기존 생성 결과를 바꾸지 않고 진단만 저장합니다.
- `llm_section_improve`는 약한 섹션이 있고 현재 품질 점수가 80 이하일 때만 최대 1회 LLM 재작성합니다.
- `strict`는 같은 보강 조건을 사용하되 A-/85점 기준의 엄격 경고를 남깁니다.
- 재작성은 기존 `sourceLedger`, `evidenceItems`, `dataGaps`, quality warnings, preflight risks 범위 안에서만 합니다.
- 새 숫자, 새 출처, 새 주장을 만들지 않습니다.
- 보강 후보가 quality score/status를 낮추거나 weak section을 늘리면 적용하지 않습니다.
- 브리핑 production 저장은 quality/fact/style/model 보수를 호출하지 않고 `SharedRepairBudget`를 사용하지 않습니다. 명시적 사용자 `quality_repair` 작업은 일반 생성과 분리합니다.
- 브리핑의 `qualityGeneration`은 `contentAssessment: not_assessed`, `qualityBefore/After: null`, `repairApplied: false`를 기록해 이전 semantic 결과를 되살리지 않습니다. 본문과 구조·출처 렌더링은 보존합니다.
- 사용자 노트는 항상 `hypothesis`이며 evidence가 아닙니다.
- `qualityGeneration`에는 token usage/estimate, evidence coverage, weak sections before/after, quality before/after를 남깁니다.

## API

```text
POST /api/quality-generation/preflight
POST /api/quality-generation/repair
POST /api/quality-generation/run
```

Existing report generation APIs accept:

```json
{"qualityMode": "diagnose_only | llm_section_improve | strict"}
```

Generated reports store:

```json
{
  "quality": {},
  "qualityGeneration": {
    "mode": "llm_section_improve",
    "preflight": {},
    "repairApplied": true,
    "repairCount": 1,
    "repairType": "llm_section_rewrite",
    "weakSectionsBefore": [],
    "weakSectionsAfter": [],
    "changedSections": [],
    "qualityBefore": {},
    "qualityAfter": {},
    "telemetry": {},
    "warnings": []
  }
}
```


## 호출 예산과 후보 저장소 (0.5.4)

- `call_budget.py` — 보고서 유형별 LLM 호출 상한. 딥 리서치(`deep_research_budget`)와 KR 집중 종목(`kr_briefing_budget`)이 쓴다. 예산 소진은 선택 단계(보수·판정)의 생략이지 잡 실패가 아니다.
- `candidate_store.py` — 잡별 딥 리서치 후보 체크포인트. `data/job-context/{job}/quality-candidate-{n}.json`에 원자 쓰기(`write_bytes_atomic`)로 남기고, 읽을 때 소유자(잡 id)와 본문 해시를 검증한다. 서버 재시작 시 `features/topic_report/candidate_recovery.py`가 RUNNING 잡을 수락된 후보로 완성한다 — 이 복구는 어떤 예외에도 기동을 막지 않는다.
