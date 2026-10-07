"""Public action enums and explicit choices; optional personal prose stays optional."""
import datetime as dt
import re

from . import CaseError, STAGES, KINDS, SLOTS
from .capture import case_identity
from .paths import identifier
from .preservation import check_text


def request(value):
    if not isinstance(value, dict):
        raise CaseError("invalid_action")
    allowed = {"instrumentId", "expectedCaseRevision", "action", "selection", "excludedSlots", "selectedScenario", "decisionText", "uncertainties",
               "userReportedAt", "kind", "previousJournalId", "toStage", "targetJournalId", "purgeSlots", "purgePersonal", "correctionSlot"}
    if set(value) - allowed:
        raise CaseError("unexpected_action_field")
    result = dict(value)
    case_identity(result.get("instrumentId"))
    if type(result.get("expectedCaseRevision")) is not int or result["expectedCaseRevision"] < 0:
        raise CaseError("invalid_case_revision")
    if result.get("action") not in {"create", "transition", "journal", "correction", "purge"}:
        raise CaseError("invalid_action")
    selection = result.get("selection") or {}
    if not isinstance(selection, dict) or set(selection) - {"companyId", "researchId", "snapshotId", "reviewDate"}:
        raise CaseError("invalid_source_selection")
    for item in selection.values():
        if item is not None and (not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", item)):
            raise CaseError("invalid_source_selection")
    result["selection"] = selection
    for key in ("excludedSlots", "purgeSlots"):
        rows = result.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(k, str) or k not in SLOTS for k in rows) or len(set(rows)) != len(rows):
            raise CaseError("invalid_input_slots")
        result[key] = sorted(rows)
    for key, limit in (("decisionText", 12_000), ("uncertainties", 8_000)):
        text = result.get(key, "")
        if not isinstance(text, str) or len(text) > limit:
            raise CaseError("personal_text_too_long")
        result[key] = check_text(text)
    result["kind"] = result.get("kind", "decision")
    if result["kind"] not in KINDS:
        raise CaseError("invalid_journal_kind")
    if result["action"] != "journal" and result["kind"] != "decision":
        raise CaseError("journal_kind_requires_journal_action")
    if result["action"] == "journal" and result["kind"] == "stage_change":
        raise CaseError("stage_change_requires_transition")
    if result.get("toStage") is not None and result["toStage"] not in STAGES:
        raise CaseError("invalid_lifecycle")
    if result["action"] == "transition" and not result.get("toStage"):
        raise CaseError("lifecycle_required")
    if result["action"] == "create" and result.get("toStage", "researching") != "researching":
        raise CaseError("initial_lifecycle_must_be_researching")
    if result["action"] == "journal" and result.get("toStage") and result["kind"] != "reentry":
        raise CaseError("separate_lifecycle_action_required")
    if result["action"] in {"purge", "correction"} and result.get("toStage"):
        raise CaseError("separate_lifecycle_action_required")
    for key in ("previousJournalId", "targetJournalId"):
        if result.get(key) is not None:
            identifier(result[key])
    if result["kind"] in {"partial_change", "reason_replaced", "reentry"} and not result.get("previousJournalId"):
        raise CaseError("previous_journal_required")
    if result["action"] in {"purge", "correction"} and not result.get("targetJournalId"):
        raise CaseError("target_journal_required")
    if result.get("correctionSlot") is not None and result["correctionSlot"] not in SLOTS:
        raise CaseError("invalid_input_slots")
    if result["action"] == "correction" and not result.get("correctionSlot"):
        raise CaseError("correction_slot_required")
    if type(result.get("purgePersonal", False)) is not bool:
        raise CaseError("invalid_purge_scope")
    result["purgePersonal"] = result.get("purgePersonal", False)
    if result["action"] == "purge" and not result["purgePersonal"] and not result["purgeSlots"]:
        raise CaseError("purge_scope_required")
    reported = result.get("userReportedAt") or {"value": None, "precision": "unknown"}
    if not isinstance(reported, dict) or set(reported) != {"value", "precision"}:
        raise CaseError("invalid_user_reported_time")
    try:
        if reported["precision"] == "unknown":
            if reported["value"] is not None:
                raise ValueError()
        elif reported["precision"] == "date":
            if not isinstance(reported["value"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reported["value"]):
                raise ValueError()
            dt.date.fromisoformat(reported["value"])
        elif reported["precision"] == "datetime":
            if not isinstance(reported["value"], str) or len(reported["value"]) > 40 or dt.datetime.fromisoformat(reported["value"].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError()
        else:
            raise ValueError()
    except (ValueError, TypeError):
        raise CaseError("invalid_user_reported_time") from None
    result["userReportedAt"] = reported
    scenario = result.get("selectedScenario")
    if scenario is not None and (not isinstance(scenario, dict) or set(scenario) != {"snapshotId", "label", "horizon"} or not isinstance(scenario["snapshotId"], str) or scenario["label"] not in {"base", "conservative", "optimistic"} or type(scenario["horizon"]) is not int or scenario["horizon"] not in {5, 10}):
        raise CaseError("invalid_selected_scenario")
    result["selectedScenario"] = scenario
    return result
