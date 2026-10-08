"""Bounded personal review input; never promotes a user's view to a verdict."""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlsplit

from . import CaseError
from .paths import identifier
from .preservation import check_text

METHOD = "ownership-review-1"
REVIEW_KINDS = frozenset({"ownership_review", "postmortem"})
CONCLUSIONS = frozenset({"maintain", "withdraw", "new_reason", "defer", "exception", "undecided"})
SCOPES = frozenset({"reason", "company", "price", "macro", "portfolio"})
CONDITION_FIELDS = frozenset({"falsification_triggers", "weakening_signals", "next_checkpoints", "key_assumptions"})


def text(value, limit=6000):
    if not isinstance(value, str) or len(value) > limit:
        raise CaseError("invalid_ownership_text")
    return check_text(value.strip())


def enum(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        raise CaseError("invalid_ownership_choice")
    return value


def moment(value, *, date_only=False):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise CaseError("invalid_ownership_time")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            dt.date.fromisoformat(value)
        elif not date_only:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
        else:
            raise ValueError()
    except ValueError:
        raise CaseError("invalid_ownership_time") from None
    return value


def refs(values):
    if not isinstance(values, list) or len(values) > 20:
        raise CaseError("invalid_ownership_refs")
    result = []
    for value in values:
        if not isinstance(value, dict) or set(value) - {"id", "revision", "url", "title"}:
            raise CaseError("invalid_ownership_refs")
        row = {key: text(value.get(key, ""), limit) for key, limit in (("id", 200), ("revision", 120), ("url", 1000), ("title", 220))}
        if not row["id"] and not row["url"]:
            raise CaseError("invalid_ownership_refs")
        if row["url"]:
            parsed = urlsplit(row["url"])
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise CaseError("invalid_ownership_refs")
        result.append(row)
    return result


def validate(value, kind):
    allowed = {"originalJournalId", "previousReviewJournalId", "condition", "observation", "signal", "evidence", "interpretation",
               "companyView", "priceView", "cashNeed", "portfolioContext", "conclusion", "resolution", "completed", "checkedScope",
               "nextCheck", "nextCheckAt", "exceptionBasis", "exceptionEndAt", "exceptionEndEvent", "postmortemAssessment", "expectedPath", "observedPath"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise CaseError("invalid_ownership_review")
    result = {key: text(value.get(key, "")) for key in ("interpretation", "companyView", "priceView", "cashNeed", "portfolioContext",
              "nextCheck", "exceptionBasis", "exceptionEndEvent", "expectedPath", "observedPath")}
    for key in ("originalJournalId", "previousReviewJournalId"):
        selected = value.get(key)
        result[key] = identifier(selected) if selected is not None else None
    result["signal"] = enum(value.get("signal", "unknown"), {"detected", "no_signal", "unknown"})
    result["evidence"] = enum(value.get("evidence", "unknown"), {"sufficient", "partial", "missing", "conflicting", "stale", "unknown"})
    result["conclusion"] = enum(value.get("conclusion", "undecided"), CONCLUSIONS)
    result["resolution"] = enum(value.get("resolution", "unresolved"), {"unresolved", "resolved"})
    if result["resolution"] == "resolved" and (result["conclusion"] in {"defer", "exception", "undecided"} or result["evidence"] in {"missing", "conflicting", "stale", "unknown"}):
        raise CaseError("unresolved_ownership_review")
    completed = value.get("completed", False)
    if type(completed) is not bool:
        raise CaseError("invalid_ownership_completion")
    scope = value.get("checkedScope", [])
    if not isinstance(scope, list) or any(not isinstance(item, str) or item not in SCOPES for item in scope) or len(set(scope)) != len(scope) or (completed and not scope):
        raise CaseError("ownership_scope_required")
    result.update(completed=completed, checkedScope=sorted(scope))
    for key in ("nextCheckAt", "exceptionEndAt"):
        result[key] = moment(value.get(key), date_only=True)
    if kind == "postmortem":
        result["postmortemAssessment"] = enum(value.get("postmortemAssessment", "uncertain"), {"original_error", "external_change", "mixed", "uncertain"})
    if kind != "postmortem" and any(value.get(key) for key in ("postmortemAssessment", "expectedPath", "observedPath")):
        raise CaseError("postmortem_fields_require_postmortem")
    condition = value.get("condition") or {"origin": "outside_conditions"}
    if not isinstance(condition, dict) or set(condition) - {"origin", "reasonRevisionId", "field", "index"}:
        raise CaseError("invalid_ownership_condition")
    origin = enum(condition.get("origin"), {"original", "current", "previous", "outside_conditions"})
    if origin in {"outside_conditions", "previous"}:
        if set(condition) != {"origin"}:
            raise CaseError("invalid_ownership_condition")
        if origin == "previous" and not result["previousReviewJournalId"]:
            raise CaseError("invalid_ownership_condition")
    else:
        if not isinstance(condition.get("reasonRevisionId"), str) or not condition["reasonRevisionId"] or len(condition["reasonRevisionId"]) > 160:
            raise CaseError("invalid_ownership_condition")
        enum(condition.get("field"), CONDITION_FIELDS)
        if type(condition.get("index")) is not int or not 0 <= condition["index"] < 100:
            raise CaseError("invalid_ownership_condition")
    result["condition"] = dict(condition)
    observed = value.get("observation") or {}
    if not isinstance(observed, dict) or set(observed) - {"text", "sourceRefs", "eventAt", "publishedAt", "collectedAt"}:
        raise CaseError("invalid_ownership_observation")
    result["observation"] = {"text": text(observed.get("text", "")), "sourceRefs": refs(observed.get("sourceRefs", [])),
                             **{key: moment(observed.get(key)) for key in ("eventAt", "publishedAt", "collectedAt")}}
    return result
