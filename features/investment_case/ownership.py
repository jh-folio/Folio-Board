"""Personal ownership reviews built on immutable journals and existing owners.

Only explicit journal confirmation writes. Projections never repair, migrate,
evaluate a thesis, advance a review anchor, or replace missing old content.
"""
from __future__ import annotations

from copy import deepcopy

from . import CaseError
from . import store
from .capture import capture, case_id
from .paths import database, identifier, now
from .ownership_validation import CONDITION_FIELDS, METHOD, REVIEW_KINDS


def content(body, slot):
    item = (body or {}).get("inputs", {}).get(slot) or {}
    return item.get("content") if item.get("status") == "preserved" else None


def _load(root, conn, journal_id, case_key):
    from .service import _body
    if not journal_id:
        return {"id": None, "status": "unavailable", "reason": "original_not_recorded"}, None
    row = store.index(conn, identifier(journal_id))
    if row and row["case_id"] != case_key:
        raise CaseError("journal_case_mismatch", 409)
    reference = {"id": journal_id, "bodyHash": (row or {}).get("file_hash"), "recordedAt": (row or {}).get("recorded_at")}
    try:
        body = _body(root, row)
        reference.update(status="purged" if body.get("personalPurgedAt") else "available", reason="personal_content_deleted" if body.get("personalPurgedAt") else None)
        return reference, body
    except CaseError as error:
        return {**reference, "status": "unavailable", "reason": error.code}, None


def entries(root, conn, case_key):
    """Metadata and review fields only; source bundles aren't duplicated here."""
    output = []
    events = {row["related_journal_id"]: dict(row) for row in conn.execute("SELECT e.kind,e.case_revision,e.related_journal_id FROM investment_case_events e JOIN decision_journal_index i ON i.operation_id=e.event_id WHERE e.case_id=? ORDER BY e.case_revision", (case_key,))} if store.case(conn, case_key) else {}
    for row in store.journals(conn, case_key):
        reference, body = _load(root, conn, row["journal_id"], case_key)
        event = events.get(row["journal_id"]) or {}
        linkage = ((store.operation(conn, row["operation_id"]) or {}).get("metadata") or {}).get("ownershipLinkage")
        output.append({**reference, "episodeId": row["episode_id"], "caseRevision": (body or {}).get("caseRevision", event.get("case_revision", -1)),
                       "kind": (body or {}).get("kind") or ("stage_change" if event.get("kind") == "transition" else event.get("kind")), "review": (body or {}).get("ownershipReview") or ({**linkage, "unavailable": True} if linkage else None),
                       "uncertainties": (body or {}).get("uncertainties", "")})
    return sorted(output, key=lambda item: (item["caseRevision"], item.get("recordedAt") or "", item["id"]))


def original_id(history, episode_id):
    # Purged/missing initial records are not silently skipped for a later one.
    return next((item["id"] for item in history if item["episodeId"] == episode_id and item["kind"] in {"decision", "stage_change", "reentry"}), None)


def condition_value(condition, inputs_body):
    if condition.get("origin") == "outside_conditions":
        return {"status": "outside_conditions", "text": None}
    reason = content(inputs_body, "reason") or {}
    if reason.get("revisionId") != condition.get("reasonRevisionId"):
        return {"status": "unavailable", "reason": "condition_revision_missing", "text": None}
    rows = (reason.get("content") or {}).get(condition.get("field")) or []
    index = condition.get("index")
    if not isinstance(rows, list) or type(index) is not int or not 0 <= index < len(rows) or not isinstance(rows[index], str):
        return {"status": "unavailable", "reason": "condition_not_preserved", "text": None}
    return {"status": "available", "text": rows[index], "reasonRevisionId": reason["revisionId"], "recordedAt": reason.get("recordedAt")}


def prepare(root, captured, request):
    """Pin baseline, continuation and exact condition before preview/confirmation."""
    data = deepcopy(request["ownershipReview"])
    with database(root) as conn:
        history = entries(root, conn, captured["caseId"])
        original = data["originalJournalId"]
        if original is None:
            original = original_id(history, (captured["saved"] or {}).get("episode_id"))
        original_ref, original_body = _load(root, conn, original, captured["caseId"])
        previous_id = data["previousReviewJournalId"]
        previous = None
        if previous_id:
            previous_ref, previous_body = _load(root, conn, previous_id, captured["caseId"])
            previous = (previous_body or {}).get("ownershipReview")
            if not previous or previous.get("purgedAt"):
                raise CaseError("previous_ownership_review_unavailable", 409)
            latest = next((item for item in reversed(history) if (item.get("review") or {}).get("rootReviewJournalId") == previous["rootReviewJournalId"]), None)
            if not latest or latest["id"] != previous_id:
                raise CaseError("ownership_review_changed", 409)
            # An ongoing issue keeps its baseline and condition authority.
            if data["originalJournalId"] is not None and data["originalJournalId"] != previous["originalJournalId"]:
                raise CaseError("ownership_baseline_changed", 409)
            original = previous["originalJournalId"]
            original_ref, original_body = _load(root, conn, original, captured["caseId"])
            data["previousReviewBodyHash"] = previous_ref["bodyHash"]
            if data["condition"].get("origin") != "previous":
                raise CaseError("ownership_condition_anchor_required")
            data["condition"] = deepcopy(previous["condition"])
        condition = data["condition"]
        if not previous and condition["origin"] != "outside_conditions":
            condition_body = original_body if condition["origin"] == "original" else captured
            if condition_value(condition, condition_body)["status"] != "available":
                raise CaseError("ownership_condition_changed", 409)
            condition["anchorJournalId"] = original if condition["origin"] == "original" else None
        if not previous and condition["origin"] == "current" and "reason" in request["excludedSlots"]:
            raise CaseError("ownership_condition_requires_preserved_reason")
        anchor = condition.get("anchorJournalId")
        if anchor:
            anchor_ref, anchor_body = _load(root, conn, anchor, captured["caseId"])
            data["conditionAnchorBodyHash"] = anchor_ref.get("bodyHash")
            data["conditionStatus"] = condition_value(condition, anchor_body)["status"]
            if data["conditionStatus"] != "available" and data["resolution"] == "resolved":
                raise CaseError("ownership_condition_unavailable", 409)
    data.update(schemaVersion=1, methodVersion=METHOD, originalJournalId=original, originalBodyHash=original_ref.get("bodyHash"),
                originalStatus=original_ref["status"], originalGap=original_ref.get("reason"),
                rootReviewJournalId=previous["rootReviewJournalId"] if previous else None,
                firstSeenAt=previous["firstSeenAt"] if previous else None,
                latestReviewedAt=(previous or {}).get("latestReviewedAt"),
                earliestUnresolvedDueAt=(previous or {}).get("earliestUnresolvedDueAt"))
    if previous and previous.get("resolution") != "resolved":
        due = previous.get("nextCheckAt")
        if due and due <= captured["checkedAt"][:10]:
            data["earliestUnresolvedDueAt"] = min(value for value in (due, data["earliestUnresolvedDueAt"]) if value)
    if data["resolution"] == "resolved":
        data["earliestUnresolvedDueAt"] = None
    return data


def journal_fields(prepared, journal_id, stamp):
    data = deepcopy(prepared)
    data["rootReviewJournalId"] = data["rootReviewJournalId"] or journal_id
    data["firstSeenAt"] = data["firstSeenAt"] or stamp
    data["reviewedAt"] = stamp if data["completed"] else None
    if data["completed"]:
        data["latestReviewedAt"] = stamp
    if data["condition"].get("origin") == "current" and not data["condition"].get("anchorJournalId"):
        data["condition"]["anchorJournalId"] = journal_id
    return data


def due_state(review, at):
    due, earliest = review.get("nextCheckAt"), review.get("earliestUnresolvedDueAt")
    unresolved = review.get("resolution") != "resolved"
    return {"schedule": "no_plan" if not due else "due" if due <= at[:10] else "scheduled",
            "nextCheckAt": due, "earliestUnresolvedDueAt": earliest,
            "overdueUnresolved": bool(unresolved and earliest and earliest <= at[:10]),
            "exceptionExpired": bool(review.get("conclusion") == "exception" and review.get("exceptionEndAt") and review["exceptionEndAt"] < at[:10]),
            "planMissing": not (review.get("nextCheck") or due), "dateBoundary": "UTC"}


def _condition_options(body, origin):
    reason = content(body, "reason") or {}
    result = []
    if reason.get("revisionId"):
        for field in sorted(CONDITION_FIELDS):
            for i, value in enumerate((reason.get("content") or {}).get(field) or []):
                if isinstance(value, str) and i < 100:
                    result.append({"origin": origin, "reasonRevisionId": reason["revisionId"], "field": field, "index": i, "text": value})
    return result


def _since_reviewed(root, conn, case_key, history, current):
    """New inputs since this issue's last explicit completion, within its scope."""
    scope_slots = {"reason": ("reason", "delta"), "company": ("company", "research"),
                   "price": ("price", "readiness"), "macro": ("macro",), "portfolio": ("review",)}
    for item in reversed(history):
        review = item.get("review") or {}
        # A missing/purged entry might have completed a newer review. Do not
        # quietly compare with an older known completion instead.
        if item["status"] != "available" or review.get("purgedAt"):
            return {"status": "unavailable", "reason": "review_history_gap", "journalId": item["id"]}
        if not review.get("completed") or not review.get("reviewedAt"):
            continue
        _, baseline = _load(root, conn, item["id"], case_key)
        if baseline is None:
            return {"status": "unavailable", "reason": "review_history_gap", "journalId": item["id"]}
        from .ownership_comparison import _axis
        slots = sorted({slot for scope in review.get("checkedScope") or [] for slot in scope_slots.get(scope, ())})
        rows = _axis(baseline, current, slots)
        return {"status": "available", "journalId": item["id"], "reviewedAt": review["reviewedAt"],
                "checkedScope": review["checkedScope"],
                "changedSlots": [row["slot"] for row in rows if row["status"] == "changed_input"],
                "unchangedSlots": [row["slot"] for row in rows if row["status"] == "unchanged_input"],
                "gapSlots": [row["slot"] for row in rows if row["status"] in {"unavailable", "incomparable"}],
                "refs": [{"slot": row["slot"], "status": row["status"], "before": row["before"].get("ref"), "after": row["after"].get("ref")} for row in rows]}
    return {"status": "not_reviewed"}


def _projection(root, conn, case_key, current, original_ref, original_body, history, at):
    from .ownership_comparison import compare
    latest = {}
    timeline = []
    for item in history:
        review = item.get("review")
        if not review:
            continue
        anchor = review.get("condition", {}).get("anchorJournalId")
        _, anchor_body = _load(root, conn, anchor, case_key) if anchor else ({}, None)
        summary = {**item, "conditionView": condition_value(review.get("condition") or {"origin": "outside_conditions"}, anchor_body),
                   "due": due_state(review, at)}
        latest[review["rootReviewJournalId"]] = summary
        timeline.append(summary)
    issues = []
    for root_id, item in reversed(list(latest.items())):
        related = [entry for entry in history if (entry.get("review") or {}).get("rootReviewJournalId") == root_id]
        issues.append({**item, "sinceReviewed": _since_reviewed(root, conn, case_key, related, current)})
    return {"schemaVersion": 1, "methodVersion": METHOD, "caseId": case_key, "checkedAt": at,
            "sourceLayer": "hypothesis", "reuseAsEvidence": False,
            "original": original_ref, "comparison": compare(original_body, current),
            "conditionOptions": _condition_options(original_body, "original") + _condition_options(current, "current"),
            "issues": issues, "timeline": list(reversed(timeline)),
            "originalOptions": [{key: item.get(key) for key in ("id", "recordedAt", "kind", "episodeId", "status")} for item in history if item["kind"] not in REVIEW_KINDS],
            "historyGaps": [{"id": item["id"], "reason": item.get("reason")} for item in history if item["status"] == "unavailable"],
            "notice": "내 검토 기록입니다. 검토 완료와 조건 해소는 별개이며 기존 이유·Portfolio 검토 기한은 바뀌지 않습니다."}


def view(root, instrument, original_journal_id=None):
    captured = capture(root, instrument)
    with database(root) as conn:
        saved = store.case(conn, captured["caseId"])
        if (saved or {}).get("revision", 0) != captured["caseRevision"]:
            raise CaseError("inputs_changed", 409)
        history = entries(root, conn, captured["caseId"])
        chosen = original_journal_id or original_id(history, (captured["saved"] or {}).get("episode_id"))
        reference, original = _load(root, conn, chosen, captured["caseId"])
        result = _projection(root, conn, captured["caseId"], captured, reference, original, history, captured["checkedAt"])
    return {**result, "mode": "current", "instrumentId": instrument, "caseRevision": captured["caseRevision"], "inputFingerprint": captured["inputFingerprint"],
            "current": {"recordedAt": None, "capturedAt": captured["checkedAt"], "refs": captured["sourceRefs"]},
            "portfolioPresence": captured["portfolioPresence"]}


def historical(root, journal_id):
    from .service import _body
    with database(root) as conn:
        row = store.index(conn, identifier(journal_id))
        body = _body(root, row)
        review = body.get("ownershipReview")
        if not review:
            raise CaseError("ownership_review_not_found", 404)
        reference, original = _load(root, conn, review.get("originalJournalId"), body["caseId"])
        history = [entry for entry in entries(root, conn, body["caseId"]) if entry["caseRevision"] <= body["caseRevision"]]
        result = _projection(root, conn, body["caseId"], body, reference, original, history, body["recordedAt"])
    return {**result, "mode": "historical", "instrumentId": body["instrumentId"], "journalId": journal_id, "review": review, "caseRevision": body["caseRevision"],
            "originalHashChanged": bool(reference.get("bodyHash") != review.get("originalBodyHash")),
            "current": {"recordedAt": body["recordedAt"], "capturedAt": None, "refs": {key: item["ref"] for key, item in body["inputs"].items()}},
            "notice": "이 검토를 확인한 당시 입력입니다. 이후 자료로 채우지 않으며 삭제된 본문은 비교 공백으로 남깁니다."}
