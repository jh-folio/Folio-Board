# research_schema — 공통 구조화 데이터 스키마 (Step 6 Data Foundation Lite)

대시보드(Step 8)와 품질 평가(Step 7)가 **보고서 markdown을 파싱하지 않고** 읽을 수 있도록,
Folio OS 산출물의 핵심 구조를 최소 스키마로 통일한다.

설계 원문: 로컬 계획문서 `folio_os_roadmap_post_v1.md` §6 (저장소에 포함하지 않는다)
구현 추적: 로컬 계획문서 `IMPLEMENTATION_PLAN_POSTV1.md`

## 담당 범위

| 모듈 | 내용 | Phase |
|---|---|---|
| `enums.py` | 공통 enum + `normalize_*` 헬퍼 | P0 |
| `checkpoints.py` | Checkpoint 객체 + markdown heading extractor | P1 |
| `evidence.py` | Evidence Item 최소 스키마 (topic_report/thesis_delta 어댑터) | P2 |
| `source_ledger.py` | Source Ledger 최소 스키마 (topic_report 일반화) | P3 |
| `data_gaps.py` | Data Gap 공통 표현 | P4 |
| `service.py` | 저장된 보고서/DB에서 구조화 필드를 읽는 얇은 read helper | P6 |

> Market Tape Lite는 시장 데이터에 가깝게 `features/common/market_data/tape.py`에 둔다.

## 공통 객체

### Checkpoint

`checkpoints.py`는 `checkpoint`, `positiveSignal`, `negativeSignal`, `scope`, `confidence`,
`artifactType`, `artifactId`를 갖는 최소 객체를 만든다.

연결된 산출물:

- `briefing`: markdown의 `내일 확인할 체크포인트` 섹션을 구조화
- `topic_report`: markdown의 `앞으로 확인할 체크포인트` 섹션을 구조화
- `thesis_delta`: 기존 `nextCheckpoints`를 구조화
- `regime_state`: regime refresh 시 `nextCheckpoints`를 채움

### Evidence Item

`evidence.py`는 `role`, `type`, `freshness`, `axis`를 공통 필드로 정규화한다.
Step 9 이후 `sourceKind`, `sourcePriority`, `sourceReliability` 같은 source priority 메타를 보존한다.
`user_note` type은 hypothesis이므로 `is_countable_evidence()`에서 evidence 집계 제외로 판정한다.

### Source Ledger

`source_ledger.py`는 중복 출처를 제거하고 `sourceId`, `usedInSections`, `evidenceRole`,
`reliability`를 공통 형태로 제공한다. Step 9의 `sourceReliability`도 `reliability`로 정규화한다.
`features/topic_report/source_ledger.py`는 이 공통 모듈을 호출한다.

### Data Gap

`data_gaps.py`는 부족한 자료/추출 실패를 `severity`와 `suggestedAction`이 있는 객체로 저장한다.

## enum

| enum | 값 | 기본값 |
|---|---|---|
| evidence role | supporting / challenging / neutral / background / data_point | neutral |
| evidence type | news / rss / filing / report / market_data / macro_data / memory / regime / thesis / user_note | news |
| evidence freshness | fresh / recent / stale / unknown | unknown |
| checkpoint confidence | low / medium / high | medium |
| checkpoint scope | market / sector / company / portfolio / macro | market |
| data gap severity | low / medium / high / blocking | medium |
| market tape status | fresh / stale / missing / conflicting / estimated | missing |
| artifact type | briefing / company_analysis / topic_report / personal_overlay / thesis_delta / regime_state | topic_report |
| reliability | high / medium / low / unknown | medium |

## 원칙 (CLAUDE.md / 로드맵 §5)

- **enum 통제**: 모든 분류는 `normalize_*`로 코드 검증한다. 잘못된 값은 안전한 기본값으로 떨어진다.
- **3계층 위계**: evidence type에 `user_note`가 있어도 사용자 노트는 hypothesis다.
  `is_hypothesis_evidence_type()`가 True인 항목은 evidence 집계에서 제외한다(원칙 2).
- **2계층 분리**: 이 구조는 별도 필드로만 저장하며, Canonical markdown은 바꾸지 않는다.

## 테스트

```powershell
py -3 features\common\research_schema\tests\test_enums.py
py -3 features\common\research_schema\tests\test_checkpoints.py
py -3 features\common\research_schema\tests\test_evidence_schema.py
py -3 features\common\research_schema\tests\test_source_ledger.py
py -3 features\common\research_schema\tests\test_data_gaps.py
py -3 features\common\market_data\tests\test_market_tape.py
```
