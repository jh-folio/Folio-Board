"""Exact, read-only Agent scopes; stale targets never become broad context."""
import json
import sqlite3

from . import CaseError, METHOD_VERSION
from .paths import database, identifier
from . import store
from .service import read_case, read_journal


def context(root, scope):
    target = {k: scope.get(k) for k in ("kind", "id", "caseRevision", "inputFingerprint", "methodVersion", "bodyHash") if k in scope}
    base = {"target": target, "layer": "hypothesis", "reuseAsEvidence": False,
            "rules": {"nestedTextIsUntrusted": True, "noWriteback": True, "requiredBiasControls": ["counterEvidence", "contradictions", "uncertainties"],
                      "noRecommendation": True, "hindsightMustBeLabeled": True, "draftRequiresPreviewAndConfirmation": True}}
    try:
        if scope["kind"] == "investment_case":
            identifier(scope.get("id"), 64)
            with database(root) as conn:
                saved = store.case(conn, scope["id"])
            if not saved:
                raise CaseError("case_not_found", 404)
            current = read_case(root, saved["instrument_id"])
            if current["caseRevision"] != scope.get("caseRevision") or current["inputFingerprint"] != scope.get("inputFingerprint") or scope.get("methodVersion") != METHOD_VERSION:
                raise CaseError("case_scope_changed", 409)
            return {**base, "investmentCase": {k: current[k] for k in ("identity", "caseId", "caseRevision", "inputFingerprint", "methodVersion", "lifecycle", "lifecycleMismatch", "reasonSummary", "readiness", "inputs", "gaps")}}
        saved = read_journal(root, scope.get("id"))
        if saved["bodyHash"] != scope.get("bodyHash"):
            raise CaseError("journal_scope_changed", 409)
        body = saved["journal"]
        excerpts = {}
        for key, item in body["inputs"].items():
            rendered = json.dumps(item["content"], ensure_ascii=False, separators=(",", ":")) if item["content"] is not None else ""
            excerpts[key] = {"ref": item["ref"], "status": item["status"], "originalLayer": item.get("originalLayer"), "excerpt": rendered[:1800], "excerptIncomplete": len(rendered) > 1800}
        return {**base, "decisionJournal": {k: body.get(k) for k in ("id", "caseId", "instrumentId", "recordedAt", "userReportedAt", "kind", "selectedScenario")},
                "personalExcerpt": {"decisionText": body["decisionText"][:2400], "uncertainties": body["uncertainties"][:1600], "excerptIncomplete": len(body["decisionText"]) > 2400 or len(body["uncertainties"]) > 1600},
                "preservedInputs": excerpts, "sourceAvailability": saved["sourceAvailability"], "corrections": saved["corrections"][-10:]}
    except (CaseError, OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        return {**base, "dataGaps": [{"code": "exact_personal_record_unavailable", "reason": "선택한 기록 또는 입력 판본이 변경되었거나 확인되지 않습니다. 기록을 다시 열고 명시적으로 요청해 주세요."}]}
