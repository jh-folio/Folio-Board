"""Validate Obsidian frontmatter for Folio Board workflow notes."""
from __future__ import annotations

from pathlib import Path

from features.obsidian.export.service import get_vault_settings
from features.obsidian.importer import parser as P


def _require_vault() -> Path:
    settings = get_vault_settings()
    vault_path = str(settings.get("vaultPath") or "").strip()
    if not vault_path:
        raise ValueError("Obsidian vault 경로가 설정되지 않았습니다.")
    vault = Path(vault_path)
    if not vault.exists():
        raise ValueError(f"Vault 경로가 존재하지 않습니다: {vault_path}")
    return vault


def _has_heading(body: str, names: list[str]) -> bool:
    body_l = str(body or "").lower()
    return any(str(name).lower() in body_l for name in names)


def validate_note(path: Path, vault: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = P.parse_frontmatter(text)
    parsed = P.classify(meta, body)
    rel = path.relative_to(vault).as_posix()
    issues: list[dict] = []

    def add(severity: str, message: str, action: str = ""):
        issues.append({"severity": severity, "message": message, "suggestedAction": action})

    note_type = str(meta.get("type") or "").strip()
    if not note_type:
        add("warning", "type frontmatter가 없습니다.", "type: company_thesis / market_memo / topic_review 중 하나를 지정하세요.")

    generated_by = str(meta.get("generated_by") or "").strip()
    source_layer = str(meta.get("source_layer") or "").strip()
    if generated_by and source_layer == "user_synthesis":
        add("error", "generated_by가 있는 노트가 user_synthesis로 표시되어 있습니다.", "Folio Board 생성 노트는 source_layer: primary_processed로 유지하세요.")

    if parsed.layer == P.LAYER_HYPOTHESIS or note_type in P.HYPOTHESIS_TYPES:
        if source_layer != "user_synthesis":
            add("error", "사용자 synthesis 노트의 source_layer가 user_synthesis가 아닙니다.", "source_layer: user_synthesis를 추가하세요.")
        if meta.get("reuse_as_hypothesis") is not True:
            add("error", "reuse_as_hypothesis: true가 없습니다.", "reuse_as_hypothesis: true를 추가하세요.")
    if parsed.layer == P.LAYER_SELF_GENERATED:
        if meta.get("reuse_as_evidence") is not False:
            add("warning", "Folio Board 생성 노트는 reuse_as_evidence: false를 명시하는 편이 안전합니다.", "reuse_as_evidence: false를 추가하세요.")

    if note_type == "company_thesis":
        if not str(meta.get("ticker") or "").strip():
            add("error", "company_thesis에 ticker가 없습니다.", "ticker: NVDA 형식으로 추가하세요.")
        if not _has_heading(body, ["핵심 thesis", "핵심 Thesis", "core thesis"]):
            add("error", "company_thesis에 핵심 Thesis 섹션이 없습니다.", "## 핵심 Thesis 섹션을 추가하세요.")
    if note_type == "market_memo":
        if not str(meta.get("topic") or "").strip():
            add("error", "market_memo에 topic이 없습니다.", "topic: AI 데이터센터 전력 병목 형식으로 추가하세요.")
    if note_type == "topic_review":
        if not str(meta.get("topic") or "").strip():
            add("error", "topic_review에 topic이 없습니다.", "topic을 추가하세요.")

    status = "ok" if not any(i["severity"] == "error" for i in issues) else "needs_fix"
    return {
        "path": str(path),
        "relPath": rel,
        "title": parsed.title or path.stem,
        "type": parsed.note_type,
        "layer": parsed.layer,
        "importable": parsed.importable,
        "status": status,
        "issues": issues,
    }


def validate_vault(*, limit: int = 300) -> dict:
    vault = _require_vault()
    rows: list[dict] = []
    for path in sorted(vault.rglob("*.md"))[:limit]:
        try:
            rows.append(validate_note(path, vault))
        except Exception:
            rows.append({
                "path": str(path),
                "relPath": path.relative_to(vault).as_posix(),
                "title": path.stem,
                "type": "unknown",
                "layer": "unknown",
                "importable": False,
                "status": "needs_fix",
                "issues": [{"severity": "error", "message": "노트를 읽거나 파싱하지 못했습니다.", "suggestedAction": "파일 인코딩과 frontmatter를 확인하세요."}],
            })
    ok = sum(1 for r in rows if r["status"] == "ok")
    needs_fix = len(rows) - ok
    return {
        "ok": True,
        "vault": str(vault),
        "total": len(rows),
        "okCount": ok,
        "needsFixCount": needs_fix,
        "notes": rows,
    }
