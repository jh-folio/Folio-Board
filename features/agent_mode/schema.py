from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from features.common.utils import now_iso
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
CONTEXT_DIR = DATA_DIR / "agent-context"

TASK_TYPES = {
    "briefing",
    "company_analysis",
    "topic_report",
    "personal_overlay",
    "thesis_delta",
    "market_memory_llm",
    "market_state_snapshot",
    "quality_repair",
    "investment_review",
}

TASK_DIR_NAMES = {
    "briefing": "briefing",
    "company_analysis": "company-analysis",
    "topic_report": "topic-report",
    "personal_overlay": "personal-overlay",
    "thesis_delta": "thesis-delta",
    "market_memory_llm": "market-memory",
    "market_state_snapshot": "market-state",
    "quality_repair": "quality-repair",
    "investment_review": "investment-review",
}

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|credential|authorization|cookie|session[_-]?id|notion[_-]?token)",
    re.I,
)
SECRET_VALUE_RE = re.compile(
    r"(?:"
    r"sk-[A-Za-z0-9_\-]{12,}|"
    r"sk-proj-[A-Za-z0-9_\-]{12,}|"
    r"gh[opsu]_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9\-]{20,}|"
    r"authorization\s*:\s*(?:bearer|basic)\s+[^\s\"']+"
    r")",
    re.I,
)


def safe_slug(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("._-")
    return slug[:120] or fallback


def task_dir(task_type: str) -> Path:
    normalized = normalize_task_type(task_type)
    path = CONTEXT_DIR / TASK_DIR_NAMES[normalized]
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_task_type(task_type: str) -> str:
    value = str(task_type or "").strip().lower().replace("-", "_")
    if value not in TASK_TYPES:
        raise ValueError(f"Unsupported agent task type: {task_type}")
    return value


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                out[key] = "[redacted]"
            else:
                out[key] = scrub_secrets(item)
        return out
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub("[redacted]", value)
    return value


def pack_id(task_type: str, artifact_id: str) -> str:
    raw = f"{normalize_task_type(task_type)}:{artifact_id}:{now_iso()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_pack(
    *,
    task_type: str,
    artifact_id: str,
    title: str,
    prompt: str,
    context: str,
    output_contract: dict,
    write_back_contract: dict,
    save_target: str,
    artifact_type: str = "",
    metadata: dict | None = None,
    draft_artifact: dict | None = None,
    sources: list | None = None,
    source_ledger: list | None = None,
    evidence_items: list | None = None,
    checkpoints: list | None = None,
    data_gaps: list | None = None,
    market_tape: dict | None = None,
    internal: dict | None = None,
    warnings: list | None = None,
) -> dict:
    task_type = normalize_task_type(task_type)
    artifact_id = str(artifact_id or "").strip() or task_type
    pack = {
        "packId": pack_id(task_type, artifact_id),
        "taskType": task_type,
        "artifactType": artifact_type or task_type,
        "artifactId": artifact_id,
        "title": title,
        "createdAt": now_iso(),
        "status": "prepared",
        "prompt": prompt or "",
        "context": context or "",
        "agentInstructions": agent_instructions(task_type),
        "outputContract": output_contract or {},
        "writeBackContract": write_back_contract or {},
        "saveTarget": save_target,
        "metadata": metadata or {},
        "draftArtifact": draft_artifact or {},
        "sources": sources or [],
        "sourceLedger": source_ledger or [],
        "evidenceItems": evidence_items or [],
        "checkpoints": checkpoints or [],
        "dataGaps": data_gaps or [],
        "marketTape": market_tape or {},
        "internal": internal or {},
        "warnings": warnings or [],
    }
    return scrub_secrets(pack)


def agent_instructions(task_type: str) -> str:
    task_type = normalize_task_type(task_type)
    base = [
        "You are the current AI agent acting as the final Folio OS author.",
        "Use only the provided prompt/context plus clearly cited local/web material you explicitly inspect.",
        "Do not use .env, API keys, tokens, or private credentials.",
        "Respect Folio OS layers: external evidence is evidence, Folio OS reports are source-grounded, user notes are hypotheses only.",
        "Include counter-evidence, uncertainties, and concrete next checkpoints when the task asks for judgment.",
        "Do not invent unavailable numbers. State data gaps and suggested verification routes.",
    ]
    if task_type in {"briefing", "company_analysis", "topic_report", "quality_repair"}:
        base.append("Return polished Markdown for the canonical report body. Do not include Personal Overlay content.")
    elif task_type == "investment_review":
        base.append("Return polished Markdown for a Personal Overlay investment review while keeping hypotheses separate from evidence.")
    elif task_type == "personal_overlay":
        base.append("Return JSON matching the overlay contract. Do not modify the canonical report markdown.")
    elif task_type == "thesis_delta":
        base.append("Return JSON matching the Thesis Delta contract. Validate the thesis; do not defend it by default.")
    elif task_type == "market_memory_llm":
        base.append("Return JSON with an entries array matching the market-memory contract. Use only source-grounded candidate issues.")
    elif task_type == "market_state_snapshot":
        base.append("Return JSON matching the MarketStateSnapshot contract. Synthesize one market-wide medium-term state, not individual memory rows.")
    return "\n".join(f"- {line}" for line in base)


def write_pack(pack: dict, owner_job_id: str | None = None) -> Path:
    task_type = normalize_task_type(pack.get("taskType"))
    artifact_id = safe_slug(pack.get("artifactId"), fallback=task_type)
    scrubbed = scrub_secrets(pack)
    if owner_job_id is not None:
        from features.common.jobs import write_job_pack

        pack_id = f"{artifact_id}_{pack.get('packId')}"
        return write_job_pack(owner_job_id, pack_id, scrubbed)
    path = task_dir(task_type) / f"{artifact_id}_{pack.get('packId')}.json"
    path.write_text(json.dumps(scrubbed, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _allowed_pack_roots() -> tuple[Path, ...]:
    """팩을 읽어도 되는 위치. 경계는 유지하고 목록만 갖는다.

    `ROOT`(체크아웃)만으로는 부족하다. 사용자 자료는 `FOLIO_HOME`을 따라 체크아웃 밖에
    있을 수 있고(§`features/common/workspace.py`), 그러면 워크스페이스의 팩이 전부
    경계 밖으로 판정된다. 실측: FolioOS_Sites가 이 체크아웃을 런타임으로 쓰고
    `FOLIO_HOME`만 자기 workspace로 돌린 인스턴스에서, 예약 사전작업의 시장 상태
    스냅샷이 매번 `ValueError`로 죽어 `market_state_snapshots`가 며칠간 갱신되지
    않았다 — 화면은 며칠 전 해석 그대로였다.

    **왜 이 경로만 죽었나**: 예약 사전작업은 `job_id` 없이 도는 non-durable 경로라
    팩이 `agent-context/`에 쌓인다. 브리핑 생성은 durable job이라 `job-context/`에
    들어가 이미 뚫려 있던 두 번째 허용 경로에 걸렸다. 그래서 브리핑은 멀쩡한데
    사전작업만 실패했다.

    `CONTEXT_DIR`은 import 시점에 한 번 잡히므로(`DATA_DIR = data_dir()`) 여기서
    다시 판정해 옮기기 직후에도 맞는 값을 쓴다.
    """
    from features.common.jobs import data_root
    from features.common.workspace import data_dir as current_data_dir

    roots = [ROOT, CONTEXT_DIR, current_data_dir() / "agent-context", data_root() / "job-context"]
    resolved: list[Path] = []
    for root in roots:
        try:
            candidate = Path(root).resolve()
        except OSError:
            continue
        if candidate not in resolved:
            resolved.append(candidate)
    return tuple(resolved)


def _resolved_pack_path(path: str | Path, *, strict: bool = True) -> Path:
    """허용 루트 안에 있는 팩 경로. 밖이면 `ValueError`."""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    resolved = p.resolve(strict=False) if not strict else p.resolve()
    for root in _allowed_pack_roots():
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    raise ValueError(f"pack path is outside the allowed roots: {resolved}")


def read_pack(path: str | Path) -> dict:
    resolved = _resolved_pack_path(path)
    return json.loads(resolved.read_text(encoding="utf-8"))


def update_pack_status(path: str | Path, *, status: str, result: dict | None = None) -> dict:
    resolved = _resolved_pack_path(path, strict=False)
    pack = read_pack(resolved)
    pack["status"] = status
    pack["updatedAt"] = now_iso()
    if result is not None:
        pack["result"] = scrub_secrets(result)
    scrubbed = scrub_secrets(pack)
    # scrub_secrets removes credential-shaped keys and values before persistence.
    # codeql[py/clear-text-storage-sensitive-data]
    resolved.write_text(  # lgtm[py/clear-text-storage-sensitive-data]
        json.dumps(scrubbed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return scrubbed


def agent_generation(source_count: int = 0, *, status: str = "ok_agent_authored", message: str = "", model: str = "") -> dict:
    """`model`에 실제 어댑터 id를 넣는다. 비워 두면 예전 자리표가 남는데, 그 자리표는
    품질 편차를 귀속할 수 없게 만든다 — 실측으로 유보 밀도가 0.2~0.5와 2.7~4.0으로
    갈리는 브리핑들이 전부 `current-agent-session`이라 원인 변수를 확인할 수 없었다."""
    return {
        "mode": "agent",
        "status": status,
        "provider": "external_agent",
        "model": str(model or "").strip() or "current-agent-session",
        "message": message or "AI 에이전트가 Folio OS context pack을 읽고 생성했습니다.",
        "sourceCount": int(source_count or 0),
    }
