# CLI 브리핑 출력 계약 강화 설계

## 문제

CLI context pack에는 8개의 시각자료 추천과 snapshot이 정상 포함되지만, `outputContract.requiredSections`가 양 시장의 큰 제목 3개만 요구한다. 최신 CLI 결과는 7,812자와 5개 제목만 반환해 `0~6 + 오늘의 결론` 구조를 생략했다. 프론트는 `미국장 시장 흐름`, `주도한 기업 ①/②` 등 세부 제목을 기준으로 시각자료 슬롯을 만들기 때문에 snapshot이 있어도 차트를 배치하지 못했다.

## 목표

- CLI와 API 브리핑은 동일한 active prompt, 선별 context, evidence, 시장 범위와 품질 preflight를 사용한다.
- CLI 결과는 API 결과와 동일한 섹션 구조와 작성 형식(한 줄 결론, 가운뎃점 요약, 해설 문단, 체크포인트, 참고자료)을 지킨다.
- CLI 브리핑이 선택 시장별 기존 `0~6 + 오늘의 결론` 구조를 빠짐없이 생성한다.
- 구조가 불완전한 첫 응답은 같은 context pack으로 한 번 자동 재작성한다.
- 두 번째 응답도 계약을 위반하면 기존 저장 브리핑을 덮어쓰지 않는다.
- 기존 `visualRecommendations`, `visualSnapshots`, gzip sidecar와 Canonical Markdown 경계는 유지한다.

## 설계

### 시장별 출력 계약

`features/agent_mode/service.py`에 시장 범위별 필수 제목 목록을 단일 함수로 둔다. `both`는 미국장과 한국장의 `0~6 + 오늘의 결론`을 모두 요구하고, `us`와 `kr`은 해당 시장만 요구한다. 기업명은 실행 시 달라지므로 `주도한 기업 ①`, `주도한 기업 ②`처럼 안정적인 제목 조각으로 검증한다.

`outputContract`에는 다음을 저장한다.

- `requiredSections`: 시장 범위별 필수 제목 조각
- `minimumCharacters`: `both` 10,000자, 단일 시장 5,000자
- `requiredMarkers`: 각 시장 주요 섹션의 `한 줄 결론`, 가운뎃점 요약과 해설 문단을 요구하는 작성 계약
- `retryOnViolation`: 1

CLI 전용 요약 프롬프트를 새로 만들지 않는다. 공통 `features/daily_briefing/prompt.md`와 `build_llm_context()` 결과를 그대로 context pack에 넣고, bridge 프롬프트에는 이를 축약하지 말라는 지시와 출력 계약만 명시한다.

### CLI 응답 검증과 재작성

`features/agent_mode/bridge.py`는 Markdown heading을 추출해 필수 제목 조각, 최소 길이, 한 줄 결론과 가운뎃점 요약 존재를 검사한다. 첫 응답이 실패하면 누락 제목과 작성 형식·길이 조건을 포함한 교정 프롬프트로 CLI를 한 번 더 실행한다. 두 번째도 실패하면 `RuntimeError`를 발생시키고 writeback을 호출하지 않는다.

CLI 프로세스 실행은 기존 timeout, 취소 job 등록, 자격증명 제거 환경, read-only sandbox를 재사용하는 한 함수로 분리한다. JSON 산출물은 이 Markdown 검증 대상에서 제외한다.

### 프론트 시각자료

프론트의 제목 기반 inline mount는 그대로 유지한다. 정상 계약을 통과한 CLI 결과에는 필요한 시장 흐름·주도 기업 제목이 반드시 존재하므로 지수, 히트맵, 기업 차트가 기존 snapshot으로 렌더링된다. 잘못된 구조를 억지로 임의 위치에 붙이는 fallback은 추가하지 않는다.

## 오류 처리

- 1차 위반: 자동 재작성 진행 상태를 표시한다.
- 2차 위반: 누락 제목과 길이 부족을 오류에 포함하고 저장하지 않는다.
- CLI 실행 오류·timeout: 기존 처리 유지.
- 시각자료 provider 실패: 기존 `visualWarnings`, stale/unavailable 처리 유지.

## 테스트

- `both`, `us`, `kr` 출력 계약이 정확한 필수 제목을 생성하는지 검사한다.
- 최신의 축약형 5개 제목 결과가 계약 위반으로 판정되는지 검사한다.
- 완전한 제목과 최소 길이를 가진 결과가 통과하는지 검사한다.
- 한 줄 결론 또는 가운뎃점 요약이 없는 축약 결과가 거부되는지 검사한다.
- 첫 응답 실패·두 번째 성공 시 writeback이 한 번만 호출되는지 검사한다.
- 두 번 모두 실패하면 writeback이 호출되지 않는지 검사한다.
- Agent Mode 대상 테스트와 전체 Python 회귀를 실행한다.

## 구현 결과

2026-06-21 구현 완료. Python 전체 회귀 271개, Agent Mode 24개, 프론트 24개와 Python·JavaScript 문법 검사가 통과했다. 기존 7,812자 축약 CLI 보고서는 새 계약에서 필수 제목, 최소 분량, 한 줄 결론, 가운뎃점 요약 위반으로 판정되며 저장·덮어쓰기 대상이 되지 않는다.
