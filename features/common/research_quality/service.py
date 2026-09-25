"""Research quality service: load, evaluate, and persist quality fields."""
from __future__ import annotations

from pathlib import Path

from features.common.canonical_identity import ReportKind
from features.common.canonical_report_io import safe_child_path
from features.common.canonical_report_state import load_report
from features.common.canonical_report_types import WriteKind
from features.common.canonical_reports import commit_sync, prepare
from features.common.research_schema.service import load_artifact
from features.common.utils import kst_date
from features.common.research_quality.evaluator import evaluate_artifact, evaluate_report
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = data_dir()


def _find_json_path(folder: Path, artifact_id: str) -> Path | None:
    artifact_id = str(artifact_id or "")
    try:
        # The ID arrives from the URL; it may only name one file in this folder.
        direct = safe_child_path(folder, f"{artifact_id}.json")
    except ValueError:
        return None
    if direct.exists():
        return direct
    for path in folder.glob("*.json"):
        if artifact_id in path.stem:
            return path
    return None


def _artifact_json_path(artifact_type: str, artifact_id: str) -> Path | None:
    if artifact_type == "briefing":
        return _find_json_path(DATA_DIR / "briefings", artifact_id)
    if artifact_type == "topic_report":
        return _find_json_path(DATA_DIR / "topic-reports", artifact_id)
    if artifact_type == "company_analysis":
        return _find_json_path(DATA_DIR / "company-analysis", artifact_id)
    return None


def evaluate_payload(body: dict | None = None) -> dict:
    body = body or {}
    artifact_type = str(body.get("artifactType") or body.get("artifact_type") or "topic_report")
    artifact = body.get("artifact") if isinstance(body.get("artifact"), dict) else body
    quality = evaluate_artifact(artifact_type, artifact)
    return {"ok": True, "artifactType": artifact_type, "artifactId": body.get("artifactId") or "", "quality": quality}


def get_quality(artifact_type: str, artifact_id: str) -> dict:
    artifact = load_artifact(artifact_type, artifact_id)
    if not artifact:
        raise FileNotFoundError(f"Artifact not found: {artifact_type}/{artifact_id}")
    quality = artifact.get("quality")
    if not quality:
        quality = evaluate_artifact(artifact_type, artifact)
    return {"ok": True, "artifactType": artifact_type, "artifactId": artifact_id, "quality": quality}


def recheck_quality(artifact_type: str, artifact_id: str) -> dict:
    artifact = load_artifact(artifact_type, artifact_id)
    if not artifact:
        raise FileNotFoundError(f"Artifact not found: {artifact_type}/{artifact_id}")
    quality = evaluate_artifact(artifact_type, artifact)
    path = _artifact_json_path(artifact_type, artifact_id)
    saved = False
    if path:
        # 정식 커밋 배관으로만 저장한다. `quality`는 canonicalRevision.hash 계산에
        # 포함되는 필드라, 리비전 갱신 없이 파일을 직접 덮어쓰면 지문이 어긋나
        # 그 보고서의 재생성·Personal Overlay·제안 승인이 영구히 실패한다
        # (실측: data/briefings/2026-08-04.kr.json이 그 상태로 발견됐다).
        current = load_report(path) or {}
        commit_sync(prepare(
            report_kind=ReportKind(artifact_type),
            exact_path=path,
            write_kind=WriteKind.CANONICAL,
            candidate={**current, "quality": quality},
        ))
        saved = True
    return {"ok": True, "artifactType": artifact_type, "artifactId": artifact_id, "quality": quality, "saved": saved}


def evaluate_markdown(markdown: str, **kwargs) -> dict:
    return evaluate_report(markdown, **kwargs)
