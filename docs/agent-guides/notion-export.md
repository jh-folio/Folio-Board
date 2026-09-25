# Notion 내보내기

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Notion 내보내기

- 브리핑, 기업분석, 테마분석 보고서를 Notion 데이터베이스 페이지로 내보낸다.
- `NOTION_TOKEN`과 `NOTION_DB_ID`는 `.env`에 저장하고, 설정 탭 UI에서 입력할 수 있다.
- Notion 데이터베이스는 이름(title), 날짜(date), 유형(select), 주제(rich_text) 속성으로 구성한다.
- 내보내기 로직은 `features/notion_export/`에 있다. `app.py`에는 엔드포인트만 둔다.
- Markdown → Notion 블록 변환은 `features/notion_export/client.py::markdown_to_blocks()`가 담당한다.
- 100개 초과 블록은 PATCH로 분할 추가한다.
- 인라인 데이터베이스를 사용하는 경우 데이터베이스가 있는 상위 페이지에 통합을 공유해야 한다.
- `NOTION_TOKEN` 실제 값을 로그, 응답, 문서에 출력하지 않는다.

