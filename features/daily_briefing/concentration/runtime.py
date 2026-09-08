from __future__ import annotations

import json

from features.common.quality_generation.call_budget import kr_briefing_budget
from features.daily_briefing.concentration.adjudication import configured_adjudication
from features.daily_briefing.concentration.attribution import build_briefing_company_groups
from features.daily_briefing.concentration.audit import audit_concentration
from features.daily_briefing.concentration.config import applies_to, concentration_mode
from features.daily_briefing.concentration.leader_selection import select_leader_pair
from features.daily_briefing.concentration.history import load_recent_history
from features.daily_briefing.concentration.repair import configured_repair
from features.daily_briefing.concentration.signatures import build_signature


def prepare_concentration(
    groups: list[dict],
    *,
    market_scope: str,
    kind: str,
    agent_serialize: bool = True,
    report_date: str = "",
    reports_dir=None,
) -> tuple[list[dict], dict]:
    mode = concentration_mode()
    if mode == "off" or not applies_to(market_scope=market_scope, kind=kind):
        return groups, {}
    projected = build_briefing_company_groups(groups)
    signatures = [build_signature(group, index) for index, group in enumerate(projected) if group.get("company")]
    history = load_recent_history(before_date=report_date, reports_dir=reports_dir) if report_date else []
    decision = select_leader_pair(signatures, mode=mode, history=history)
    budget = kr_briefing_budget()
    # shadow는 관측 전용이라 실제 CLI/API 호출을 쓰지 않는다 — 판정은 active에서만
    # 부른다. shadow에서 부르면 브리핑마다 수십 초짜리 호출이 telemetry를 위해 든다.
    if mode == "active" and decision.get("conflictSignals"):
        budget.claim("adjudication")
        decision = configured_adjudication(decision, signatures, serialize=agent_serialize)
    effective = projected
    if mode == "active" and decision.get("finalPair"):
        by_id = {row["candidateId"]: row for row in signatures}
        subject_order = [by_id[candidate]["subject"] for candidate in decision["finalPair"] if candidate in by_id]
        rank = {subject: index for index, subject in enumerate(subject_order)}
        effective = sorted(
            projected,
            key=lambda group: (
                rank.get(str(group.get("company") or ""), len(rank)),
                -float(group.get("leaderScore") or group.get("score") or 0),
            ),
        )
    return effective, {
        "mode": mode,
        "leaderDecision": decision,
        "signatures": signatures,
        "history": {"sessionLimit": 10, "rowCount": len(history)},
        "callBudget": budget.snapshot(),
    }


def render_concentration_context(control: dict) -> str:
    if not control:
        return ""
    decision = control.get("leaderDecision") or {}
    signatures = control.get("signatures") or []
    final_ids = decision.get("finalPair") or []
    selected = [row for row in signatures if row.get("candidateId") in final_ids]
    count = len(selected)
    structure = (
        "근거 충족 기업이 0개이므로 기업 ①/②를 만들지 말고 `## 3. 오늘의 기업 신호` 한 절에서 직접 근거 부족을 설명하세요."
        if count == 0 else
        "근거 충족 기업이 1개이므로 기업 ①만 쓰고 기업 ②를 만들거나 대체 기업을 채우지 마세요."
        if count == 1 else
        "근거 충족 기업 2개를 기업 ①/②로 쓰세요."
    )
    return "\n".join(
        [
            "## 확정된 주도 기업과 인과 경로 (내부 지침)",
            "아래 finalPair의 기업과 순서를 권위값으로 사용하세요. 후보 순위를 다시 바꾸지 마세요.",
            structure,
            "같은 공통 동인은 두 번째 기업에서 짧게 참조하고, 각 기업의 고유 촉매·전달 경로·결과·근거를 중심으로 쓰세요.",
            json.dumps({"decision": decision, "selectedSignatures": selected}, ensure_ascii=False, separators=(",", ":")),
            "이 내부 구조와 점수·판정 상태를 최종 Markdown에 노출하지 마세요.",
        ]
    )


def finalize_concentration(markdown: str, control: dict, *, agent_serialize: bool = True) -> tuple[str, dict]:
    # Post-generation concentration auditing/repair is intentionally detached
    # from production writeback.  Selection and its internal telemetry remain
    # available before writing, but no natural-language body may be edited or
    # sent to another model after the writer has authored it.
    return markdown, {**(control or {}), "audit": {
        "status": "not_assessed",
        "assessmentStatus": "not_assessed",
        "repair": {"attempted": False, "applied": False, "reason": "production_detached"},
    }}


def finalize_audit(markdown: str, control: dict) -> dict:
    """Compatibility projection for callers that do not own Markdown replacement."""
    if not control:
        return control
    signatures = control.get("signatures") or []
    decision = control.get("leaderDecision") or {}
    by_id = {row.get("candidateId"): row for row in signatures}
    leaders = [str(by_id[candidate].get("subject") or "") for candidate in decision.get("finalPair") or [] if candidate in by_id]
    other = [str(row.get("subject") or "") for row in signatures if row.get("candidateId") not in set(decision.get("finalPair") or [])][:3]
    return {**control, "audit": audit_concentration(markdown, leader_subjects=leaders, other_major_subjects=other)}


def record_call(control: dict, slot: str) -> None:
    if not control:
        return
    budget = control.setdefault("callBudget", {"limits": {}, "used": {}, "remaining": {}})
    limit = int((budget.get("limits") or {}).get(slot, 0))
    used = int((budget.get("used") or {}).get(slot, 0))
    if used >= limit:
        raise RuntimeError(f"call_budget_exhausted:{slot}")
    budget.setdefault("used", {})[slot] = used + 1
    budget.setdefault("remaining", {})[slot] = max(0, limit - used - 1)


__all__ = ["finalize_audit", "finalize_concentration", "prepare_concentration", "record_call", "render_concentration_context"]
