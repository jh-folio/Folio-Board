# 백그라운드 작업과 증분 인덱싱

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 백그라운드 작업과 증분 인덱싱

- `/api/index`와 `/api/rssarchive/import`는 오래 걸리는 작업을 직접 응답하지 않고 job을 생성한다.
- 작업 상태는 `/api/jobs/{job_id}`에서 조회한다.
- 프론트는 상단 `#status`와 진행률 바에 job 상태를 표시한다.
- `build_index(incremental=True)`는 `research-index.sqlite3`의 `file_manifest` 테이블을 사용해 파일 크기/수정시각이 변하지 않은 자료를 건너뛴다.
- market-relevant 문서는 SQLite `documents` 테이블에 저장하고, 관련 없는 파일도 `file_manifest`에 저장해 다음 인덱싱 때 재처리하지 않는다.
- `data/index.json`은 더 이상 문서 목록이나 파일 매니페스트를 포함하지 않으며, `generatedAt`, `count`, `incremental`, `sqlite` 같은 상태 요약만 저장한다.
- SQLite/FTS 동기화는 `contentHash`가 같은 문서의 chunk embedding 재생성을 건너뛴다.
- job 결과에는 전체 `documents`를 저장하지 않는다. `count`, `generatedAt`, `incremental`, `sqlite` 같은 요약만 저장한다.

