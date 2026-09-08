# Obsidian Workflow

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Obsidian Workflow

- 로직은 `features/obsidian/workflow/`에 둔다. 기존 `features/obsidian/export/`의 Vault 설정을 재사용하고 새 설정 파일을 만들지 않는다.
- UI/API는 `company_thesis`, `market_memo`, `topic_review` 템플릿 노트를 생성할 수 있다. 이미 같은 파일이 있으면 기본적으로 덮어쓰지 않고 기존 경로를 안내한다.
- 생성 노트는 `source_layer: user_synthesis`, `reuse_as_hypothesis: true`를 가진다. `topic_review`도 Obsidian Import에서 hypothesis로 인식한다.
- Folio OS가 내보내는 1차 보고서/내러티브는 `generated_by: Folio OS`, `source_layer: primary_processed`, `reuse_as_evidence: false`를 가진다.
- frontmatter validator는 type/ticker/topic/source_layer/reuse_as_hypothesis 누락과 `generated_by`·`user_synthesis` 충돌을 감지한다.
- API는 `/api/obsidian-workflow/create-note`, `/api/obsidian-workflow/linked-notes`, `/api/obsidian-workflow/validate`를 사용한다.

