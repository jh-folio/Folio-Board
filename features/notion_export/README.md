# Notion 내보내기

이 기능은 브리핑, 기업분석 보고서, 테마분석 보고서를 Notion 데이터베이스 페이지로 내보냅니다.

## 담당 범위

- 브리핑 Notion 내보내기
- 기업분석 보고서 Notion 내보내기
- 테마분석 보고서 Notion 내보내기
- Notion 통합 토큰과 데이터베이스 ID 설정 관리
- Markdown → Notion 블록 변환

## Notion 데이터베이스 구조

Notion에 하나의 데이터베이스를 만들고 아래 속성을 준비합니다.

| 속성명 | 유형 | 설명 |
| --- | --- | --- |
| 이름 | 제목 (title) | 페이지 제목 |
| 날짜 | 날짜 (date) | 브리핑 날짜 또는 보고서 생성일 |
| 유형 | 선택 (select) | 기업분석/테마분석은 기존 유형, 브리핑은 `미국장 · 시황중심`처럼 시장·브리핑 유형 조합 |
| 주제 | 텍스트 (rich_text) | 기업분석은 회사명, 테마분석은 테마명 (브리핑은 비워둠) |

## 설정

웹 UI 설정 탭에서 입력하거나 `.env`에 직접 추가합니다.

```text
NOTION_TOKEN=secret_xxx      # Notion 통합 토큰
NOTION_DB_ID=xxxxxxxxxxxxxxx  # 대상 데이터베이스 ID
```

Notion 통합(Integration)을 만들 때 대상 페이지나 데이터베이스에 통합을 공유(Share)해야 접근할 수 있습니다.

## 관련 코드

- `features/notion_export/client.py`: Notion API HTTP 클라이언트 (urllib 전용, 외부 라이브러리 없음)
  - `_notion_request()`: Notion REST API 호출
  - `create_page()`: 데이터베이스에 새 페이지 생성 및 블록 추가 (100블록 초과 시 PATCH 분할 처리)
  - `parse_inline()`: 인라인 Markdown → Notion rich_text 변환 (bold, italic, code, link)
  - `markdown_to_blocks()`: Markdown 전체 → Notion 블록 목록 변환 (heading, bullet, numbered, divider, table, image, paragraph)
    - **표는 표로 보냅니다.** 연속한 `| ... |` 행은 `table` 블록 하나와 `table_row` 자식으로 변환하고 구분 행(`|---|`)은 건너뜁니다. 예전에는 표 행이 어떤 구조 규칙에도 걸리지 않아 문단 수집 루프가 표 전체를 한 문단으로 이어 붙였습니다. 셀 수가 모자란 행은 가장 넓은 행 기준으로 빈 셀을 채웁니다(Notion은 모든 행의 셀 수가 `table_width`와 같아야 합니다).
    - rich_text 한 조각은 `RICH_TEXT_LIMIT`(2,000자)에서 절단합니다. 초과하면 Notion이 400을 내어 내보내기 전체가 실패합니다.
- `features/notion_export/service.py`: 내보내기 비즈니스 로직
  - `notion_config()`: `.env`에서 NOTION_TOKEN, NOTION_DB_ID 읽기
  - `public_notion_settings()`: 설정 UI용 마스킹된 값 반환
  - `export_briefing(date, briefing)`: 브리핑 내보내기. `both` 저장 브리핑은 미국장/한국장 페이지로 분리하고, 구조화된 `chartImages`가 있으면 해당 시장 PNG만 업로드합니다. imgbb 키나 이미지 업로드가 없으면 텍스트 페이지를 계속 생성합니다.
  - `export_analysis(report)`: 기업분석 내보내기
  - `export_topic_report(report)`: 테마분석 내보내기
- `features/llm_settings/settings_service.py`: `public_settings()` / `save_settings()`에서 Notion 설정 포함
- `app.py`: Notion 내보내기 엔드포인트 3개

## API

```text
POST /api/briefings/{date}/export-notion
POST /api/export-notion/analysis
POST /api/export-notion/topic-report
```

`/api/export-notion/analysis`는 요청 본문으로 저장된 보고서 JSON을 받습니다.
`/api/export-notion/topic-report`도 동일하게 보고서 JSON을 받습니다.

성공 응답:
```json
{
  "ok": true,
  "notionUrl": "https://www.notion.so/...",
  "pageId": "...",
  "title": "..."
}
```

## 주의점

- Notion API 버전: `2022-06-28`
- `NOTION_TOKEN`이나 `NOTION_DB_ID`가 없으면 내보내기 시 오류를 반환합니다.
- Notion 인라인 데이터베이스를 사용하는 경우 해당 데이터베이스가 속한 **상위 페이지**에 통합을 공유해야 합니다. 데이터베이스 자체에 직접 공유가 표시되지 않아도 상위 페이지 공유로 접근 권한이 부여됩니다.
- 내보낸 페이지는 자동 삭제나 수정을 하지 않습니다. 중복 내보내기 방지는 사용자가 직접 관리합니다.
- 실제 `NOTION_TOKEN` 값을 로그, 답변, 문서에 출력하지 않습니다.

### 보고서 인용 보존

기업분석·딥 리서치의 Markdown 인용 링크는 Notion rich_text의 link로 전달한다. 출처 ID·생성 링크 경계용 HTML 주석은 변환 시 제거해 읽는 화면에 내부 주석을 노출하지 않는다. 실제 계정 전송과 로컬 payload 검증은 별도다.
