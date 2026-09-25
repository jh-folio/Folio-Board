# 자동 새로고침 (Content Revisions)

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 자동 새로고침 (Content Revisions)

- `GET /api/content-revisions`는 저장소별 마지막 변경 시각(`briefing`/`companyAnalysis`/`topicReport`/`marketMemory`/`rss`/`note`/`portfolio`/`watchlist`)만 돌려준다. 로직은 `features/common/content_revision.py`이며 **파일 mtime만 읽고 내용을 열지 않는다** — 몇 초 간격 폴링을 견뎌야 하기 때문이다.
- 디렉터리는 **자신의 mtime도 함께** 본다. 자식 파일만 보면 가장 최근 파일이 삭제될 때 값이 내려가 삭제가 신호로 전달되지 않는다.
- 화면은 `web/src/app/useContentRevision.ts`로 구독한다. 값이 **달라지면**(커질 때만이 아니라) 목록을 다시 읽는다. 첫 응답은 기준점이라 화면을 여는 순간 두 번 읽지 않는다.
- 탭이 보이지 않으면 묻지 않고, 탭으로 돌아오면 기다리지 않고 바로 확인한다.
- 이 신호는 출처를 가리지 않는다. 자동화, 다른 탭, Agent 도크가 만든 변화가 모두 같은 경로로 화면에 반영된다. 예전에는 자기가 실행한 작업이 끝났을 때만 다시 읽어서, 자동 생성된 브리핑은 사용자가 직접 새로고침하기 전까지 목록에 없었다.

