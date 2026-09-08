# Agent 대화 (Threads)

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Agent 대화 (Threads)

- 로직은 `features/agent_mode/consultation_*.py`에 둔다(내부 식별자는 저장 데이터와의 계약이라 유지). `data/agent-threads/{id}.json` JSON-per-thread가 권위 저장소이며 research inbox/index 경로 밖이라 어떤 evidence loader·indexer도 읽지 않는다. 예전 `data/agent-consultations/`는 첫 사용 시 1회 이관한다(복사 후 삭제, 이름 충돌 시 양쪽 보존).
- **도크가 대화의 집이다.** 주제가 붙은 대화(워치리스트·포트폴리오·보고서)는 도크 아래 한 종류이며 별도 상담 패널을 만들지 않는다. 화면 용어는 전부 `대화`이고 주제는 칩으로 보여준다. `상담`은 전문가 조언을 뜻해 §5 원칙 3(사용자 생각을 옹호하지 말고 검증한다)과 충돌하므로 화면에서 쓰지 않는다.
- 세션·메시지·노트 snapshot은 `layer=hypothesis`, `sourceLayer=user_consultation`, `reuseAsEvidence=false`를 코드 상수로 강제하고 화면에도 그 경계를 표시한다.
- scope를 주지 않으면 `general`이다. 알 수 없는 kind를 `portfolio`로 떨어뜨리지 않는다(주제 없는 대화에 포트폴리오 맥락이 딸려 들어간다).
- **생성 경로는 하나다.** 스레드 러너(`job_runtime.run_consultation_job`)는 맥락 조립과 저장만 하고 생성은 도크와 같은 `chat.run_agent_chat`에 위임한다. 제안 생성·거절 같은 사건도 같은 transcript에 남겨 다음 세션의 Agent가 같은 제안을 반복하지 않게 한다.
- 모델 입력은 전체 transcript가 아니라 rolling summary + 최근 8개 메시지 + 서버가 **매번 다시 조회한** 최신 리서치 context로 구성한 32,000자 이하 pack이다. 저장된 옛 시세/브리핑을 재생하지 않는다.
- **답변 본문은 잡 결과가 아니라 스레드에서 읽는다.** 잡 결과는 `data/jobs.json`과 Work Log에 남으므로 transcript를 담지 않는다.
- user turn을 먼저 저장한 뒤 Agent job을 실행하므로 재시작 후에도 질문이 남고 retry할 수 있다. `operationId`로 중복 응답을 막는다. 저장 성공 후 폴링이 실패해도 작성칸을 되돌리지 않는다(재전송이 새 `operationId`로 같은 질문을 두 번 저장한다).
- **빈 대화는 저장하지 않는다.** 스레드는 첫 메시지에서 만들어진다. `새 대화`와 `짚어보기`는 화면 상태만 바꾸고 주제는 `pending`으로 들고 있다가 첫 질문에서 함께 넘긴다. 예전에는 도크를 열 때마다 만들어서, 아무것도 묻지 않고 떠난 대화가 목록에 남았다.
- **인사말은 대화가 아니다.** 저장·이관 모두 `storage.ts::isGreeting()` 하나로 거른다. 저장은 `id`로, 이관은 `variant`로 걸렀던 적이 있는데 인사말에는 `variant`가 없어 이관 필터가 한 번도 걸리지 않았고, 브라우저가 새로 열릴 때마다 인사말 한 줄짜리 스레드가 저장됐다(실제로 54개가 쌓였다).
- **제목은 첫 질문에서 만든다.** 기본 제목일 때만 40자로 잘라 넣고 사용자가 붙인 제목은 건드리지 않는다. 전부 `새 대화`면 목록에서 대화를 구분할 단서가 없다.
- 대화 관리(목록·전환·제목·보관·삭제)는 도크가 소유한다. 삭제는 확인을 받고 저장소도 `confirmed` 없이는 지우지 않는다.
- memory 갱신은 규칙 기반 rolling summary다. 계획의 구조화 memoryPatch 계약은 미도입 상태이며 상세는 `.planning/folio-os-0.4-x-research-intelligence/task_plan.md`의 구현 편차 기록을 본다.
- `노트로 정리` 명시적 action만 Native Investment Note snapshot을 만들며 노트에도 `consultationRef`와 hypothesis 경계가 유지된다.
- Work Log/API/exception/telemetry에 transcript·session memory·Portfolio 민감 context를 남기지 않는다.
---

