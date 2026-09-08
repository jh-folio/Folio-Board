# Research Quality — 공통 리서치 품질 평가

Topic Report v2의 Quality Gate를 Folio OS 전체가 재사용할 수 있도록 공통화한 레이어입니다.
평가는 LLM 없이 규칙 기반으로 동작하며, Step 6의 `checkpoints`/`evidenceItems`/`sourceLedger`/`dataGaps`/`marketTape`를 읽는다.
`features/common/quality_generation/`은 이 evaluator를 생성 후 평가와 제한적 repair 기준으로 재사용합니다.

## 담당 범위

| 모듈 | 역할 |
|---|---|
| `schema.py` | score/grade/status/check key/level helper |
| `source_grounding.py` | sourceLedger/evidence/marketTape/dataGaps 기반 grounding 평가 |
| `evaluator.py` | markdown + 구조화 필드 공통 품질 평가 |
| `service.py` | 저장 artifact 로드/평가/재평가/저장 |

`features/topic_report/evaluation.py`는 호환 wrapper로 남고, 실제 평가는 이 모듈을 호출한다.

## 적용 대상

현재 Step 7 MVP 적용 대상:

- `topic_report`: 기존 Quality Gate 호환 + sourceGrounding 추가
- `briefing`: 저장 브리핑의 sources/checkpoints/marketTape/dataGaps 평가
- `company_analysis`: 저장 기업분석의 sources/markdown 기반 평가
- `thesis_delta`: markdown/evidenceItems/sourceLedger/checkpoints/counterEvidence 평가
- `regime_state`: 상태 요약, evidence counts, nextCheckpoints 평가

## API

```text
POST /api/research-quality/evaluate
GET  /api/research-quality/{artifact_type}/{artifact_id}
POST /api/research-quality/recheck/{artifact_type}/{artifact_id}
```

## 원칙

- Canonical markdown은 품질 평가로 변경하지 않는다.
- 사용자 노트와 thesis는 hypothesis다. `user_note` evidence type은 grounding에서 evidence로 세지 않는다.
- **quality 저장은 정식 커밋 배관(`canonical_reports.prepare`+`commit_sync`)만 쓴다.** `quality`는 `canonicalRevision.hash` 계산에 포함되는 필드라, 리비전 갱신 없이 파일을 직접 덮어쓰면 지문이 어긋나 그 보고서의 재생성·Personal Overlay·제안 승인이 영구히 실패한다(실측: 열람 backfill이 `2026-08-04.kr.json`을 그 상태로 만들었다). 같은 이유로 **열람(GET)은 저장물을 바꾸지 않는다** — quality가 없는 옛 보고서는 응답에만 계산해 싣고, 영구 backfill은 `POST /api/research-quality/recheck` 하나가 담당한다.
- `sourceGrounding`, `personalBiasRisk`, `hallucinationRisk`는 코드에서 계산한다.
- `briefing`의 `numericSupport`는 최종 validator가 확인한 서로 다른 `factKey`/`kind`만 센다. 참고자료의 URL·날짜·본문에 우연히 남은 숫자는 숫자 근거로 세지 않는다. 다른 artifact의 기존 숫자 평가 규칙은 유지한다.
- 평가 실패는 보고서를 깨뜨리지 않고 warning 또는 낮은 score로 남긴다.

## 테스트

```powershell
py -3 features\common\research_quality\tests\test_research_quality.py
```
