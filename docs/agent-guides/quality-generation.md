# Quality Generation

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

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
- `call_budget.py`는 보고서 유형별 LLM 호출 상한(딥 리서치·KR 집중 종목)을, `candidate_store.py`는 잡별 후보 체크포인트(`data/job-context/{job}/quality-candidate-{n}.json`, `write_bytes_atomic`·소유자 검증·해시 검증)를 소유한다. 예산 소진은 선택 단계(보수·판정)의 생략이지 잡 실패가 아니다.

