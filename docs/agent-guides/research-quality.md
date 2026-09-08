# Research Quality

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Research Quality

- 공통 품질 평가는 `features/common/research_quality/`에 둔다. `features/topic_report/evaluation.py`는 호환 wrapper로 유지한다.
- 평가 입력은 Step 6의 `checkpoints`, `evidenceItems`, `sourceLedger`, `dataGaps`, `marketTape`를 우선 읽는다.
- `sourceGrounding`, `hallucinationRisk`, `personalBiasRisk`는 규칙 기반으로 계산하고 LLM 자유 텍스트를 신뢰하지 않는다.
- `user_note`는 hypothesis이며 source grounding의 evidence count에 포함하지 않는다.
- 평가 결과는 artifact의 별도 `quality` 필드에 저장한다. Canonical markdown은 품질 평가로 수정하지 않는다.
- API는 `/api/research-quality/evaluate`, `/api/research-quality/{artifact_type}/{artifact_id}`, `/api/research-quality/recheck/{artifact_type}/{artifact_id}`를 사용한다.

