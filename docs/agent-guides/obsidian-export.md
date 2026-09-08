# Obsidian 내보내기

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Obsidian 내보내기

- 브리핑, 기업분석, 테마분석(Topic Report), 시장 내러티브(active/watch)를 로컬 Obsidian Vault의 Markdown 노트로 내보낸다.
- 테마분석은 `Topic Reports/` 폴더로 내보내며 frontmatter에 `report_type`, `quality_score`, 그리고 자기참조 방지 마커(`generated_by`/`source_layer: primary_processed`/`reuse_as_evidence: false`)를 붙인다.
- Vault 경로는 `data/obsidian-settings.json`에 저장한다. 사용자 설정 파일이므로 명시 요청 없이 삭제하지 않는다.
- 내보내기 로직은 `features/obsidian/export/`에 있다. `app.py`에는 엔드포인트만 둔다.
- 태그는 Obsidian이 공백을 허용하지 않으므로 `normalize_tag()` 후 공백을 언더스코어(`_`)로 변환한다.
- `config/company_master.json`은 최상위가 배열이 아니라 `{"companies": [...]}` 구조다. 직접 iterate하지 말고 `.get("companies", [])`로 접근한다.
- `## 사용자 메모` 구분자 이하 내용은 재내보내기 시 보존한다.
- 회사명·별칭을 `[[wikilink]]`로 자동 변환한다. 길이 역순으로 처리해 부분 매칭을 방지한다.
- **자기참조 주의(Folio Board 원칙 5)**: 내보내는 노트에는 `generated_by`, `source_layer: primary_processed`, `reuse_as_evidence: false`를 붙여, 향후 Obsidian importer가 이를 evidence로 재사용하지 않도록 한다. `generated_by` 값은 `features/common/self_reference.py::GENERATED_BY_MARKER`(`"Folio Board"`) 하나로 쓰지만, 과거 `Folio OS` 값도 importer와 `web/src/app/deepResearchPayload.ts::parseLedger`가 계속 자기참조로 인식한다(dual-read, plan §4.3).

