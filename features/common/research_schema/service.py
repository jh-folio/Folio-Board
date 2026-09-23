"""Read-only helpers for structured research data fields."""
from __future__ import annotations

import json
from pathlib import Path

from features.common.canonical_report_io import safe_child_path
from features.common.market_data.tape import build_market_tape
from features.common.research_schema.checkpoints import (
    checkpoints_from_markdown,
    checkpoints_from_regime_state,
    checkpoints_from_thesis_delta,
)
from features.common.research_schema.data_gaps import data_gaps_from_messages
from features.common.research_schema.evidence import evidence_items_from_list
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = data_dir()


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_json_report(folder: Path, artifact_id: str) -> dict | None:
    artifact_id = str(artifact_id or "")
    if not artifact_id:
        return None
    try:
        # The ID arrives from the URL; it may only name one file in this folder.
        direct = safe_child_path(folder, f"{artifact_id}.json")
    except ValueError:
        return None
    if direct.exists():
        return _read_json(direct)
    for path in folder.glob("*.json"):
        if artifact_id in path.stem:
            data = _read_json(path)
            if data:
                return data
    return None


def load_artifact(artifact_type: str, artifact_id: str) -> dict | None:
    artifact_type = str(artifact_type or "").strip()
    if artifact_type == "briefing":
        return _find_json_report(DATA_DIR / "briefings", artifact_id)
    if artifact_type == "topic_report":
        return _find_json_report(DATA_DIR / "topic-reports", artifact_id)
    if artifact_type == "company_analysis":
        return _find_json_report(DATA_DIR / "company-analysis", artifact_id)
    if artifact_type == "thesis_delta":
        try:
            from features.thesis_tracking.store import connect, get_delta
            conn = connect(DATA_DIR / "market-memory.sqlite3")
            try:
                return get_delta(conn, artifact_id)
            finally:
                conn.close()
        except Exception:
            return None
    if artifact_type == "regime_state":
        try:
            from features.market_memory.memory import list_states
            for state in list_states(DATA_DIR / "market-memory.sqlite3", status="all", limit=500):
                if artifact_id in {state.get("stateId"), state.get("state_id"), state.get("stateKey"), state.get("state_key")}:
                    return state
        except Exception:
            return None
    return None


def checkpoints_payload(artifact_type: str, artifact_id: str) -> dict:
    artifact = load_artifact(artifact_type, artifact_id) or {}
    checkpoints = artifact.get("checkpoints")
    if checkpoints is None:
        if artifact_type == "thesis_delta":
            checkpoints = checkpoints_from_thesis_delta(artifact, artifact_id=artifact_id)
        elif artifact_type == "regime_state":
            checkpoints = checkpoints_from_regime_state(artifact, artifact_id=artifact_id)
        else:
            checkpoints = checkpoints_from_markdown(
                artifact.get("markdown", ""),
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                topic=artifact.get("topicLabel") or artifact.get("title") or "",
            )
    return {"artifactType": artifact_type, "artifactId": artifact_id, "checkpoints": checkpoints or []}


def evidence_payload(artifact_type: str, artifact_id: str) -> dict:
    artifact = load_artifact(artifact_type, artifact_id) or {}
    evidence = artifact.get("evidenceItems")
    if evidence is None:
        evidence = evidence_items_from_list(
            artifact.get("evidence") or [],
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        )
    return {"artifactType": artifact_type, "artifactId": artifact_id, "evidenceItems": evidence or []}


def source_ledger_payload(artifact_type: str, artifact_id: str) -> dict:
    artifact = load_artifact(artifact_type, artifact_id) or {}
    ledger = artifact.get("sourceLedger")
    if ledger is None:
        ledger = source_ledger_from_items(
            artifact.get("evidenceItems") or artifact.get("sources") or [],
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        )
    return {"artifactType": artifact_type, "artifactId": artifact_id, "sourceLedger": ledger or []}


def data_gaps_payload(artifact_type: str, artifact_id: str) -> dict:
    artifact = load_artifact(artifact_type, artifact_id) or {}
    gaps = artifact.get("dataGaps")
    if gaps is None:
        summary = artifact.get("evidencePackSummary") or {}
        gaps = data_gaps_from_messages(
            summary.get("dataGaps") or [],
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        )
    return {"artifactType": artifact_type, "artifactId": artifact_id, "dataGaps": gaps or []}


def market_tape_payload(artifact_type: str = "", artifact_id: str = "", *, date: str = "") -> dict:
    artifact = load_artifact(artifact_type, artifact_id) if artifact_type and artifact_id else None
    if artifact and artifact.get("marketTape"):
        return {"artifactType": artifact_type, "artifactId": artifact_id, "marketTape": artifact["marketTape"]}
    return {
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "marketTape": build_market_tape(
            date=date or (artifact or {}).get("date") or "",
            market_snapshot=(artifact or {}).get("marketSnapshot"),
            korea_market_data=(artifact or {}).get("koreaMarketData"),
            market_windows=(artifact or {}).get("marketWindows"),
            topic_market_data=(artifact or {}).get("marketData"),
        ),
    }
