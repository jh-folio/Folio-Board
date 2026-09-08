"""Obsidian Import — 사용자 Obsidian Vault의 2차 사고 노트를 frontmatter 타입별로 회수한다.

Folio Board 2계층 모델의 입력단(hypothesis 회수)이다. Obsidian export의 역방향이며,
같은 Vault(`data/obsidian-settings.json`)를 양방향으로 사용한다.

설계 원칙(CLAUDE.md §5):
- 사용자 노트(user_synthesis)는 evidence가 아니라 hypothesis다.
- Folio Board(구 Folio OS)가 내보낸 노트(generated_by / source_layer: primary_processed /
  reuse_as_evidence: false)는 self_generated로 보고 import에서 제외한다(자기참조 금지).
  `generated_by`는 `bool()` 진리값으로만 판정하므로(`parser.py::classify`) 신·구 표시명
  어느 쪽이 적혀 있어도 안전하다 — 값을 직접 비교하지 않는다.
- research-inbox는 절대 건드리지 않는다(인덱서와 독립된 read 경로).
"""
