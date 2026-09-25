# Obsidian Integration

Obsidian Integration은 Folio Board와 로컬 Obsidian Vault 사이의 양방향 흐름을 담당합니다.

```text
Folio Board Canonical 보고서 → Obsidian Markdown 내보내기
사용자 Obsidian 노트(thesis/memo/review) → Folio Board hypothesis로 회수
```

Folio Board가 내보낸 노트는 다시 evidence로 쓰지 않고, 사용자가 직접 쓴 노트만 Personal Overlay와 Thesis Tracking의 hypothesis 입력으로 사용합니다. 이 판정은 `generated_by` 값을 직접 비교하지 않고 존재 유무로만 하므로, 이름이 `Folio OS`였던 과거 내보내기도 계속 걸러집니다(아래 "사용자 노트 회수").

## 하위 폴더

| 폴더 | 역할 |
| --- | --- |
| `export/` | 브리핑, 기업분석, 테마분석, 시장 내러티브를 Vault Markdown으로 저장 |

브리핑 내보내기는 시장 단위를 보존합니다. `both`로 저장된 브리핑은 `Briefings/브리핑 {date} 미국장.md`와 `Briefings/브리핑 {date} 한국장.md`로 나뉘며, frontmatter에 `market`, `briefing_type`, `tags`, 자기참조 방지 마커를 포함합니다. 브라우저가 전달한 PNG 차트는 `Briefings/assets/`에 저장하고 해당 시장 노트에만 링크합니다. 이미지 저장 실패나 업로드 불가 상태는 Canonical Markdown 내보내기를 막지 않습니다.
| `importer/` | Vault Markdown frontmatter를 읽어 hypothesis/self_generated/unknown으로 분류 |
| `workflow/` | company thesis, market memo, topic review 템플릿 생성과 frontmatter 검사 |

## Vault 설정

Vault 경로는 설정 탭에서 저장하며 위치는 아래 파일입니다.

```text
data/obsidian-settings.json
```

이 파일은 사용자 설정이므로 명시 요청 없이 삭제하지 않습니다. Vault는 프로젝트 폴더 바깥에 두는 것을 권장합니다. 그래야 Folio Board가 내보낸 노트가 다시 `research-inbox` 자료처럼 인덱싱되는 자기참조를 피할 수 있습니다.

## 내보내기

자동 생성되는 Vault 구조:

```text
{Vault}/
  Briefings/
  Companies/
  Topic Reports/
  Narratives/
  Thesis Delta/
```

내보내는 노트에는 항상 자기참조 방지 마커가 붙습니다.

```yaml
generated_by: Folio Board
source_layer: primary_processed
reuse_as_evidence: false
```

과거(리네이밍 전)에 내보낸 노트는 `generated_by: Folio OS`를 그대로 갖고 있습니다. 재내보내기 전까지 값을 일괄 갱신하지 않으며, importer는 신·구 값을 똑같이 자기참조로 인식합니다.

재내보내기 시 `---\n## 사용자 메모\n` 구분자 이하의 사용자 작성 내용은 보존합니다. 회사명·별칭은 `[[wikilink]]`로 자동 변환하며, 긴 이름부터 처리해 부분 매칭을 줄입니다.

## 사용자 노트 회수

`importer/`는 Obsidian 노트를 `data/market-memory.sqlite3`의 `obsidian_note_index` 테이블에 저장합니다. 별도 DB를 만들지 않고 thesis/regime과 같은 knowledge graph DB에서 join합니다.

노트 분류:

| 조건 | layer | importable |
| --- | --- | --- |
| `type: company_thesis`, `market_memo`, `topic_review` 또는 `source_layer: user_synthesis` | `hypothesis` | true |
| Folio Board(구 Folio OS 포함) 생성 노트 또는 `reuse_as_evidence: false` | `self_generated` | false |
| 그 외 | `unknown` | false |

사용자 노트는 evidence가 아니라 hypothesis입니다. Personal Overlay와 Thesis Delta는 이 노트를 옹호하지 않고 최신 외부 자료와 대조합니다.

**재스캔은 Vault의 현재 상태를 반영합니다.** 이번 스캔에서 보이지 않은 행은 `prune_missing_notes()`가 지우고 요약의 `removed`로 보고합니다. note_id가 `sha1(rel_path)`라 노트를 지우거나 이름·폴더를 바꾸면 새 행이 생기는데, 옛 행을 남기면 없는 파일이 계속 hypothesis로 조회되고 이름만 바꾼 노트가 두 건으로 집계됩니다. 읽기에 실패한 파일도 Vault에 있으므로 본 것으로 칩니다 — 일시적 읽기 실패는 삭제가 아닙니다.

## 템플릿과 검사

`workflow/`는 사용자 2차 사고를 쓰기 위한 기본 노트를 만듭니다.

```text
Thesis/             # company_thesis
Narratives/         # market_memo
Personal Reviews/   # topic_review
```

생성 노트는 `source_layer: user_synthesis`, `reuse_as_hypothesis: true`를 가집니다. 같은 경로에 파일이 있으면 기본적으로 덮어쓰지 않고 기존 경로를 알려줍니다.

## API

```text
GET  /api/obsidian/settings
POST /api/obsidian/settings
POST /api/briefings/{date}/export-obsidian
POST /api/export-obsidian/analysis
POST /api/export-obsidian/topic-report
POST /api/export-obsidian/narratives
POST /api/obsidian-workflow/create-note
GET  /api/obsidian-workflow/linked-notes
POST /api/obsidian-workflow/validate
```

## 관련 코드

- `export/formatter.py`: frontmatter, wikilink, 사용자 메모 보존
- `export/service.py`: Vault 설정, 보고서/내러티브 노트 쓰기
- `importer/parser.py`: frontmatter 파서와 계층 분류
- `importer/note_index.py`: `obsidian_note_index` 저장소
- `importer/service.py`: Vault 스캔과 hypothesis 조회
- `workflow/templates.py`: 사용자 노트 템플릿
- `workflow/note_factory.py`: 템플릿 파일 생성
- `workflow/validator.py`: frontmatter 검사

## 테스트

```powershell
py -3 features\obsidian\importer\tests\test_parser.py
py -3 features\obsidian\workflow\tests\test_templates.py
py -3 features\obsidian\workflow\tests\test_validator.py
```

## 주의점

- Obsidian 연동은 사용자가 버튼을 눌렀을 때만 실행합니다.
- export 노트는 `primary_processed`, import 가능한 사용자 노트는 `user_synthesis` 계층을 유지합니다.
- 파서는 Folio Board가 다루는 frontmatter 부분집합만 지원합니다. 복잡한 중첩 YAML은 대상이 아닙니다.

### 보고서 인용 보존

기업분석·딥 리서치 본문의 일반 Markdown 인용 링크를 그대로 내보낸다. 기업명 자동 wikilink는 기존 Markdown 링크의 라벨·URL 및 코드 내부를 바꾸지 않는다. 기존 사용자 노트와 자기참조 방지 frontmatter는 유지한다.
