"""Defensive, versioned schema for the dated Investment Review artifact.

The review is a Personal Overlay document, never a Canonical report.  Keep the
normalizer deliberately permissive at the boundary: old/corrupt local files
must be viewable, but are never silently rewritten while being read.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

IMPACT_CHOICES = {"positive", "watch", "negative", "neutral"}
IMPACT_DEFAULT = "neutral"
THESIS_VERDICTS = {"maintained", "strengthened", "weakened", "at_risk", "broken", "insufficient_evidence"}
REVIEW_REASON_CODES = {"thesis_review_needed", "checkpoint_due", "checkpoint_pending"}
REVIEW_STATES = {"draft", "reviewed", "stale", "due"}
CHANGE_KINDS = {"verdict", "checkpoint", "narrative", "risk"}
CHANGE_STATES = {"added", "removed", "changed"}
RISK_KEYS = {"portfolio_concentration", "saved_backtest", "correlation_volatility"}
RISK_STATUSES = {"available", "unavailable"}
EXPOSURE_TYPES = {"narrative", "sector", "currency"}
REASON_CODES = {
    "review_missing", "legacy_input_basis_unknown", "provider_observed_at_unknown",
    "input_changed_during_generation", "input_basis_mismatch", "checkpoint_due",
    "checkpoint_pending", "thesis_review_needed", "thesis_missing",
    "explicit_narrative_link_missing", "portfolio_analytics_projection_unavailable",
    "compatible_saved_backtest_missing", "previous_risk_not_comparable",
    "previous_review_not_comparable", "input_fingerprint_changed",
    "review_changed_reopen_challenge",
    "first_review", "previous_verdict_not_comparable", "previous_checkpoint_not_comparable",
    "previous_narrative_not_comparable",
    "canonical_report_selection_limited", "position_roster_truncated",
    "checkpoint_snapshot_limited",
}
INPUT_BASIS_STATUSES = {"complete", "partial", "legacy_unknown"}
FRESHNESS_STATUSES = {"fresh", "partial", "stale", "unknown"}
MAX_LIST = 40
MAX_TEXT = 1200


def _text(value: object, limit: int = MAX_TEXT) -> str:
    # Do not stringify a malformed nested object.  Besides producing a poor UI
    # value, ``str({"secret": ...})`` would turn an unknown key into visible
    # text and let it cross the review's public projection boundary.
    if isinstance(value, (Mapping, list, tuple, set)):
        return ""
    return str(value or "").strip()[:limit]


def _items(value: object, limit: int = MAX_LIST) -> list:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, (dict, str, int, float, bool))][:limit]


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _reason(value: object) -> dict:
    item = _mapping(value)
    code = _text(item.get("code"), 80)
    out = {"code": code if code in REASON_CODES else "additional_confirmation_needed"}
    ticker = _text(item.get("ticker"), 24).upper()
    if ticker and re.fullmatch(r"[A-Z0-9._-]{1,24}", ticker):
        out["ticker"] = ticker
    return out


def _string_list(value: object, *, limit: int = 12, text_limit: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item, text_limit) for item in value if _text(item, text_limit)][:limit]


def _number(value: object, *, minimum: float = 0, maximum: float = 1) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


def _counter_evidence(value: object) -> list[dict]:
    out: list[dict] = []
    for item in _items(value, 12):
        title = _text(item.get("title") if isinstance(item, Mapping) else item, 240)
        if title:
            out.append({"title": title})
    return out


def _safe_change_value(value: object) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = _text(value, 240)
    return text or None


def _change_value(kind: str, value: object) -> object:
    """Project only the typed before/after shapes the reader can explain.

    A review file is local-but-untrusted input.  In particular, retaining an
    arbitrary nested mapping here would bypass the public projection boundary.
    """
    if value is None:
        return None
    if kind == "verdict":
        verdict = _text(value, 32)
        return verdict if verdict in THESIS_VERDICTS else None
    row = _mapping(value)
    if not row:
        return None
    if kind == "checkpoint":
        out = {key: _text(row.get(key), 64) for key in ("status", "direction", "dueBy") if _text(row.get(key), 64)}
        last = _checkpoint_last_verdict(row.get("lastVerdict"))
        if isinstance(last, dict) and any(last.values()):
            out["lastVerdict"] = last
        return out or None
    if kind == "narrative":
        out = {"tickers": _string_list(row.get("tickers"), limit=24, text_limit=24),
               "momentum": _text(row.get("momentum"), 32)}
        weight = _number(row.get("weight"))
        if weight is not None:
            out["weight"] = weight
        return {key: item for key, item in out.items() if item not in ("", [])} or None
    if kind == "risk":
        out = {"status": _text(row.get("status"), 24)}
        concentration = _mapping(row.get("concentration"))
        safe_concentration = {key: _number(concentration.get(key)) for key in ("top1", "top3", "top5")
                              if _number(concentration.get(key)) is not None}
        holdings = concentration.get("holdings")
        if isinstance(holdings, int) and 0 <= holdings <= 10000:
            safe_concentration["holdings"] = holdings
        if safe_concentration:
            out["concentration"] = safe_concentration
        contributions = []
        for item in _items(row.get("riskContributions"), 16):
            contribution = _mapping(item)
            ticker = _text(contribution.get("ticker"), 24).upper()
            weight = _number(contribution.get("weight"))
            if ticker and weight is not None:
                contributions.append({"ticker": ticker, "weight": weight})
        if contributions:
            out["riskContributions"] = contributions
        return {key: item for key, item in out.items() if item not in ("", [])} or None
    return None


def _checkpoint_last_verdict(value: object) -> str | dict:
    """Keep the small tracked-checkpoint verdict shape, never its raw JSON."""
    if not isinstance(value, Mapping):
        return _text(value, 240)
    row = _mapping(value)
    evidence: list[dict] = []
    for source in _items(row.get("evidence"), 8):
        item = _mapping(source)
        memory_id = _text(item.get("memoryId"), 160)
        role = _text(item.get("role"), 48)
        if memory_id or role:
            evidence.append({"memoryId": memory_id, "role": role})
    return {
        "verdict": _text(row.get("verdict"), 40),
        "at": _text(row.get("at"), 64),
        "evidence": evidence,
    }


def _checkpoint_reviews(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        identifier = _text(row.get("id"), 160)
        if not identifier:
            continue
        rows.append({
            "id": identifier,
            "ticker": _text(row.get("ticker"), 24).upper(),
            "item": _text(row.get("item"), 240),
            "direction": _text(row.get("direction"), 40),
            "status": _text(row.get("status"), 40),
            "lastVerdict": _checkpoint_last_verdict(row.get("lastVerdict")),
            "dueBy": _text(row.get("dueBy"), 32),
        })
    return rows


def _market_states(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        label = _text(row.get("label"), 240)
        if not label:
            continue
        rows.append({
            "label": label,
            "stateId": _text(row.get("stateId"), 160),
            "stateKey": _text(row.get("stateKey"), 160),
            "momentum": _text(row.get("momentum"), 32),
            "confidence": _number(row.get("confidence")),
            "status": _text(row.get("status"), 32),
            "updatedAt": _text(row.get("updatedAt"), 64),
        })
    return rows


def _thesis_changes(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        ticker = _text(row.get("ticker"), 24).upper()
        if not ticker:
            continue
        verdict = _text(row.get("verdict"), 32)
        rows.append({
            "ticker": ticker,
            "name": _text(row.get("name"), 160),
            "verdict": verdict if verdict in THESIS_VERDICTS else "insufficient_evidence",
            "summary": _text(row.get("summary"), 480),
            "updatedAt": _text(row.get("updatedAt"), 64),
        })
    return rows


def _portfolio_impacts(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        ticker = _text(row.get("ticker"), 24).upper()
        if not ticker:
            continue
        impact = normalize_impact(row.get("impact"))
        item = {
            "ticker": ticker,
            "name": _text(row.get("name"), 160),
            "impact": impact,
            "reason": _text(row.get("reason"), 480),
            "linkedNarratives": _string_list(row.get("linkedNarratives"), limit=12, text_limit=160),
        }
        weight = _number(row.get("weight"))
        if weight is not None:
            item["weight"] = weight
        rows.append(item)
    return rows


def _key_checkpoints(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        checkpoint = _text(row.get("checkpoint") or row.get("label"), 240)
        if not checkpoint:
            continue
        rows.append({
            "id": _text(row.get("id"), 160),
            "checkpoint": checkpoint,
            "ticker": _text(row.get("ticker"), 24).upper(),
            "dueAt": _text(row.get("dueAt") or row.get("dueBy"), 32),
            "direction": _text(row.get("direction"), 40),
            "status": _text(row.get("status"), 40),
        })
    return rows


def _linked_notes(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        title = _text(row.get("title"), 240)
        if title:
            rows.append({"title": title, "type": _text(row.get("type"), 64),
                         "ticker": _text(row.get("ticker"), 24).upper(),
                         "updatedAt": _text(row.get("updatedAt"), 64)})
    return rows


def _legacy_exposure(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        narrative = _text(row.get("narrative") or row.get("label"), 240)
        count = row.get("count")
        if not narrative or not isinstance(count, int) or not 0 <= count <= 10000:
            continue
        rows.append({"narrative": narrative, "count": count})
    return rows


def _recent_reports(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, 16):
        row = _mapping(value)
        report_type = _text(row.get("type"), 32)
        identifier = _text(row.get("id"), 160)
        if report_type not in {"briefing", "analysis", "topic"} or not identifier:
            continue
        rows.append({"type": report_type, "id": identifier, "title": _text(row.get("title"), 240),
                     "date": _text(row.get("date"), 32), "view": _text(row.get("view"), 32)})
    return rows


def _quality_summary(value: object) -> dict:
    row = _mapping(value)
    score = _number(row.get("score"), minimum=0, maximum=100)
    out = {"status": _text(row.get("status"), 32), "grade": _text(row.get("grade"), 16),
           "warnings": _string_list(row.get("warnings"), limit=8, text_limit=240),
           "suggestedFixes": _string_list(row.get("suggestedFixes"), limit=8, text_limit=240)}
    if score is not None:
        out["score"] = score
    return {key: item for key, item in out.items() if item not in ("", [])}


def _stats(value: object) -> dict:
    row = _mapping(value)
    integer_fields = ("marketStrengthening", "marketTotal", "thesisStrengthened", "thesisWeakened",
                      "positionsPositive", "positionsWatch", "checkpointCount")
    out = {key: max(0, min(10000, int(row.get(key)))) for key in integer_fields
           if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)}
    distribution_keys = {"thesisDistribution": THESIS_VERDICTS, "impactDistribution": IMPACT_CHOICES}
    for key, allowed_names in distribution_keys.items():
        source = _mapping(row.get(key))
        distribution: dict[str, int] = {}
        for name, count in source.items():
            safe_name = _text(name, 40)
            if safe_name in allowed_names and isinstance(count, (int, float)) and not isinstance(count, bool):
                distribution[safe_name] = max(0, min(10000, int(count)))
        out[key] = distribution
    return out


def _market_tape(value: object) -> dict:
    row = _mapping(value)
    items: list[dict] = []
    for value in _items(row.get("items"), 16):
        item = _mapping(value)
        label = _text(item.get("label"), 80)
        if not label:
            continue
        tape = {"label": label, "status": _text(item.get("status"), 16),
                "size": "lg" if _text(item.get("size"), 8) == "lg" else "sm"}
        for key in ("value", "changePct"):
            numeric = item.get(key)
            if isinstance(numeric, (int, float)) and not isinstance(numeric, bool):
                tape[key] = numeric
            else:
                tape[key] = None
        items.append(tape)
    out = {"items": items}
    as_of = _text(row.get("asOf"), 64)
    if as_of:
        out["asOf"] = as_of
    return out


def _basis_reports(value: object) -> list[dict]:
    rows: list[dict] = []
    for value in _items(value, MAX_LIST):
        row = _mapping(value)
        kind = _text(row.get("kind"), 32)
        identifier = _text(row.get("id"), 160)
        if kind not in {"briefing", "company_analysis", "topic_report"} or not identifier:
            continue
        item = {"kind": kind, "id": identifier, "asOf": _text(row.get("asOf"), 64),
                "tickers": _string_list(row.get("tickers"), limit=12, text_limit=24),
                "marketWide": row.get("marketWide") is True,
                "marketScope": _text(row.get("marketScope"), 16).casefold()}
        report_kind = _text(row.get("reportKind"), 32)
        if report_kind in ({"briefing", "daily", "weekly"} if kind == "briefing" else {kind}):
            item["reportKind"] = report_kind
        for display_key in ("title", "relatedReason"):
            display = _text(row.get(display_key), 240)
            if display:
                item[display_key] = display
        revision = row.get("revision")
        if isinstance(revision, int) or (isinstance(revision, str) and revision.isdigit()):
            item["revision"] = int(revision)
        else:
            content_hash = _text(row.get("contentHash"), 128)
            if content_hash:
                item["contentHash"] = content_hash
        rows.append(item)
    return rows


def _basis_theses(value: object) -> list[dict]:
    return [{"ticker": _text(row.get("ticker"), 24).upper(), "thesisUpdatedAt": _text(row.get("thesisUpdatedAt"), 64),
             "deltaId": _text(row.get("deltaId"), 120), "verdict": _text(row.get("verdict"), 40),
             "deltaGeneratedAt": _text(row.get("deltaGeneratedAt"), 64)}
            for value in _items(value, MAX_LIST) if (row := _mapping(value)) and _text(row.get("ticker"), 24)]


def _basis_states(value: object) -> list[dict]:
    return [{"stateId": _text(row.get("stateId"), 160), "stateKey": _text(row.get("stateKey"), 160),
             "updatedAt": _text(row.get("updatedAt"), 64), "momentum": _text(row.get("momentum"), 32)}
            for value in _items(value, MAX_LIST) if (row := _mapping(value)) and _text(row.get("stateKey"), 160)]


def _basis_analytics(value: object) -> dict:
    row = _mapping(value)
    signature = _mapping(row.get("compatibilitySignature"))
    positions = []
    for value in _items(signature.get("positions"), MAX_LIST):
        item = _mapping(value); ticker = _text(item.get("ticker"), 24).upper(); weight = _number(item.get("weight"))
        if ticker and weight is not None:
            positions.append({"ticker": ticker, "weight": weight, "currency": _text(item.get("currency"), 12).upper()})
    backtest = _mapping(row.get("backtest"))
    ref = {key: _text(backtest.get(key), 128 if key == "fingerprint" else 80)
           for key in ("id", "methodVersion", "baseCurrency", "window", "start", "end", "fingerprint")
           if _text(backtest.get(key), 128 if key == "fingerprint" else 80)}
    return {"methodVersion": _text(row.get("methodVersion"), 96), "snapshotFingerprint": _text(row.get("snapshotFingerprint"), 128),
            "compatibilitySignature": {"positions": positions, "baseCurrency": _text(signature.get("baseCurrency"), 12).upper()},
            "backtest": ref or None}


def normalize_impact(value, default: str = IMPACT_DEFAULT) -> str:
    value = _text(value, 32).lower()
    return value if value in IMPACT_CHOICES else default


def empty_review(date: str = "") -> dict:
    """A useful non-persisted empty response for missing storage."""
    return {
        "schemaVersion": 2, "sourceSchemaVersion": 2, "date": _text(date, 10),
        "reviewRevision": 0, "reviewState": "draft", "generatedAt": "", "reviewedAt": "",
        "previousReviewedAt": "", "mode": "rule", "summary": "아직 저장된 투자 리뷰가 없습니다.",
        "inputBasis": {"status": "partial", "capturedAt": "", "fingerprint": "", "marketData": {"status": "partial", "priceAsOf": "", "fxAsOf": ""}},
        "freshness": {"status": "unknown", "dueCount": 0, "reasons": [{"code": "review_missing"}]},
        "positionRoster": [], "coverage": {}, "reportSelection": {},
        "positionReviews": [], "sharedExposures": [], "portfolioRisks": [], "changesSincePrevious": [],
        "checkpointReviews": [], "baseReviewRevision": 0,
        "counterEvidence": [], "uncertainties": [{"code": "review_missing"}], "staleReasons": [],
        "marketTape": {}, "stats": {}, "exposure": [], "recentReports": [], "marketState": [],
        "thesisChanges": [], "portfolioImpacts": [], "keyCheckpoints": [], "linkedNotes": [],
        "qualitySummary": {}, "warnings": [], "markdown": "", "stale": False,
    }


def _legacy(date: str, value: Mapping) -> dict:
    out = empty_review(date)
    # A legacy file is read-only compatibility input, not a free-form public
    # payload.  Project only the old display fields and normalize every nested
    # collection before it can reach the UI or a context pack.
    out["date"] = _text(value.get("date") or date, 10)
    out["generatedAt"] = _text(value.get("generatedAt"), 64)
    out["mode"] = "agent" if _text(value.get("mode"), 16) == "agent" else "rule"
    out["summary"] = _text(value.get("summary"))
    out["marketTape"] = _market_tape(value.get("marketTape"))
    out["stats"] = _stats(value.get("stats"))
    out["exposure"] = _legacy_exposure(value.get("exposure"))
    out["recentReports"] = _recent_reports(value.get("recentReports"))
    out["marketState"] = _market_states(value.get("marketState"))
    out["thesisChanges"] = _thesis_changes(value.get("thesisChanges"))
    out["portfolioImpacts"] = _portfolio_impacts(value.get("portfolioImpacts"))
    out["keyCheckpoints"] = _key_checkpoints(value.get("keyCheckpoints"))
    out["linkedNotes"] = _linked_notes(value.get("linkedNotes"))
    out["qualitySummary"] = _quality_summary(value.get("qualitySummary"))
    out["warnings"] = _string_list(value.get("warnings"), limit=12, text_limit=240)
    # v2-shaped fields occasionally appeared in experimental legacy files;
    # do not pass their raw mappings through the compatibility projection.
    out["checkpointReviews"] = _checkpoint_reviews(value.get("checkpointReviews"))
    out["counterEvidence"] = _counter_evidence(value.get("counterEvidence"))
    out["uncertainties"] = [_reason(item) for item in _items(value.get("uncertainties"), 12)]
    out.update({
        "schemaVersion": 2, "sourceSchemaVersion": 1, "reviewRevision": 0,
        "reviewState": "stale", "reviewedAt": "", "previousReviewedAt": "",
        "inputBasis": {"status": "legacy_unknown", "capturedAt": "", "fingerprint": "", "marketData": {"status": "partial", "priceAsOf": "", "fxAsOf": ""}},
        "freshness": {"status": "unknown", "dueCount": 0, "reasons": [{"code": "legacy_input_basis_unknown"}]},
        "staleReasons": [{"code": "legacy_input_basis_unknown"}], "stale": True,
    })
    return out


def normalize_review(review: dict | None, *, date: str = "") -> dict:
    if not isinstance(review, Mapping):
        return empty_review(date)
    source_version = review.get("sourceSchemaVersion")
    schema_version = review.get("schemaVersion")
    if source_version == 1 or (schema_version not in (2, "2") and "inputBasis" not in review):
        return _legacy(date or _text(review.get("date"), 10), review)
    base = empty_review(date)
    # Never spread a stored v2 document back into its public projection.
    # These files are user-local and may be malformed, so top-level and nested
    # unknown keys must not reach UI, Agent context, or a later write.
    allowed_top_level = set(base) | {"baseReviewRevision"}
    out = {key: review[key] for key in allowed_top_level if key in review}
    out = {**base, **out}
    out["schemaVersion"] = 2
    out["sourceSchemaVersion"] = 2
    out["date"] = _text(out.get("date") or date, 10)
    try:
        out["reviewRevision"] = max(0, int(out.get("reviewRevision") or 0))
    except (TypeError, ValueError):
        out["reviewRevision"] = 0
    try:
        out["baseReviewRevision"] = max(0, int(out.get("baseReviewRevision") or 0))
    except (TypeError, ValueError):
        out["baseReviewRevision"] = 0
    out["reviewState"] = _text(out.get("reviewState"), 16).lower()
    if out["reviewState"] not in REVIEW_STATES:
        out["reviewState"] = "draft"
    out["generatedAt"] = _text(out.get("generatedAt"), 64)
    out["reviewedAt"] = _text(out.get("reviewedAt"), 64)
    out["previousReviewedAt"] = _text(out.get("previousReviewedAt"), 64)
    out["mode"] = "agent" if _text(out.get("mode"), 16) == "agent" else "rule"
    out["summary"] = _text(out.get("summary"))
    raw_basis = _mapping(out.get("inputBasis"))
    basis = {}
    status = _text(raw_basis.get("status"), 32).lower()
    basis["status"] = status if status in INPUT_BASIS_STATUSES else "partial"
    basis["capturedAt"] = _text(raw_basis.get("capturedAt"), 64)
    basis["fingerprint"] = _text(raw_basis.get("fingerprint"), 128)
    # Provider observation times are unknown by contract; keep the shape but
    # do not preserve arbitrary subkeys or fake as-of values.
    market_reason = _text(_mapping(raw_basis.get("marketData")).get("reason"), 120)
    basis["marketData"] = {"status": "partial", "priceAsOf": "", "fxAsOf": ""}
    if market_reason:
        basis["marketData"]["reason"] = market_reason
    portfolio = _mapping(raw_basis.get("portfolio"))
    revision = portfolio.get("revision")
    basis["portfolio"] = {"revision": revision if isinstance(revision, (int, float, str)) else 0, "updatedAt": _text(portfolio.get("updatedAt"), 64)}
    basis["theses"] = _basis_theses(raw_basis.get("theses"))
    basis["marketStates"] = _basis_states(raw_basis.get("marketStates"))
    basis["checkpointWatermark"] = _text(raw_basis.get("checkpointWatermark"), 128)
    basis["canonicalReports"] = _basis_reports(raw_basis.get("canonicalReports"))
    # Omission is intentional for previous v2 snapshots: adding this field at
    # read time would change their fingerprint shape and make them stale.
    if _text(raw_basis.get("reportSelectionVersion"), 16) == "u5-v1":
        basis["reportSelectionVersion"] = "u5-v1"
    thesis_status = _text(raw_basis.get("thesisAuthorityStatus"), 16)
    if thesis_status in {"available", "unavailable"}:
        basis["thesisAuthorityStatus"] = thesis_status
    basis["analytics"] = _basis_analytics(raw_basis.get("analytics"))
    previous = _mapping(raw_basis.get("previousReview"))
    previous_revision = previous.get("reviewRevision")
    basis["previousReview"] = {"date": _text(previous.get("date"), 10), "reviewRevision": previous_revision if isinstance(previous_revision, (int, float, str)) else 0}
    # Provider observation time is unknown.  A review that carries this
    # market-data projection cannot claim a complete input basis.
    if basis["status"] != "legacy_unknown":
        basis["status"] = "partial"
    out["inputBasis"] = basis
    raw_freshness = _mapping(out.get("freshness"))
    status = _text(raw_freshness.get("status"), 16).lower()
    freshness = {"status": status if status in FRESHNESS_STATUSES else "unknown"}
    try:
        freshness["dueCount"] = max(0, min(MAX_LIST, int(raw_freshness.get("dueCount") or 0)))
    except (TypeError, ValueError):
        freshness["dueCount"] = 0
    freshness["reasons"] = [_reason(item) for item in _items(raw_freshness.get("reasons"), 12)]
    try:
        overdue = max(0, min(MAX_LIST, int(raw_freshness.get("overdueUnresolvedCount") or 0)))
    except (TypeError, ValueError):
        overdue = 0
    if "overdueUnresolvedCount" in raw_freshness:
        freshness["overdueUnresolvedCount"] = overdue
    evaluated_at = _text(raw_freshness.get("evaluatedAt"), 64)
    if evaluated_at:
        freshness["evaluatedAt"] = evaluated_at
    out["freshness"] = freshness
    for key in ("positionReviews", "sharedExposures", "portfolioRisks", "changesSincePrevious", "counterEvidence", "uncertainties", "staleReasons"):
        out[key] = _items(out.get(key))
    changes: list[dict] = []
    for value in out["changesSincePrevious"]:
        item = _mapping(value)
        kind, change, key = _text(item.get("kind"), 32), _text(item.get("change"), 16), _text(item.get("key"), 160)
        if kind in CHANGE_KINDS and change in CHANGE_STATES and key:
            changes.append({"kind": kind, "key": key, "change": change,
                            "from": _change_value(kind, item.get("from")),
                            "to": _change_value(kind, item.get("to"))})
    out["changesSincePrevious"] = changes[:MAX_LIST]
    positions: list[dict] = []
    basis_theses = {row.get("ticker"): row for row in basis.get("theses") or [] if isinstance(row, Mapping)}
    basis_readiness_known = basis.get("thesisAuthorityStatus") == "available"
    for value in out["positionReviews"]:
        item = _mapping(value)
        ticker = _text(item.get("ticker"), 24).upper()
        if not ticker:
            continue
        verdict = _text(item.get("thesisVerdict"), 32)
        due = []
        for checkpoint in _items(item.get("dueCheckpoints"), 12):
            row = _mapping(checkpoint); identifier = _text(row.get("id"), 160); label = _text(row.get("label"), 240); due_at = _text(row.get("dueAt"), 32)
            if identifier and label:
                due.append({"id": identifier, "label": label, "dueAt": due_at})
        signals = []
        for signal in _items(item.get("quantitativeRiskSignals"), 8):
            row = _mapping(signal); weight = _number(row.get("weight"))
            if _text(row.get("kind"), 40) == "current_weight" and weight is not None:
                signals.append({"kind": "current_weight", "weight": weight, "baseCurrency": _text(row.get("baseCurrency"), 12).upper()})
        refs = []
        for reference in _items(item.get("canonicalReferences"), 8):
            row = _mapping(reference); kind = _text(row.get("kind"), 32)
            if kind in {"briefing", "company_analysis", "topic_report"} and _text(row.get("id"), 160):
                report_kind = _text(row.get("reportKind"), 32)
                allowed_report_kinds = {"briefing", "daily", "weekly"} if kind == "briefing" else {kind}
                ref = {"kind": kind, "reportKind": report_kind if report_kind in allowed_report_kinds else kind, "id": _text(row.get("id"), 160), "asOf": _text(row.get("asOf"), 64), "tickers": _string_list(row.get("tickers"), limit=12, text_limit=24), "marketWide": row.get("marketWide") is True, "marketScope": _text(row.get("marketScope"), 16).casefold()}
                title = _text(row.get("title"), 240)
                related_reason = _text(row.get("relatedReason"), 240)
                if title:
                    ref["title"] = title
                if related_reason:
                    ref["relatedReason"] = related_reason
                refs.append(ref)
        position = {"ticker": ticker, "name": _text(item.get("name"), 160),
                          "thesisVerdict": verdict if verdict in THESIS_VERDICTS else "insufficient_evidence",
                          "reviewReasons": [reason for reason in _string_list(item.get("reviewReasons")) if reason in REVIEW_REASON_CODES],
                          "counterEvidence": _counter_evidence(item.get("counterEvidence")),
                          "uncertainties": [_reason(reason) for reason in _items(item.get("uncertainties"), 12)],
                          "dueCheckpoints": due, "quantitativeRiskSignals": signals, "canonicalReferences": refs}
        for readiness_key in ("thesisPresent", "latestReviewPresent"):
            if isinstance(item.get(readiness_key), bool):
                position[readiness_key] = item[readiness_key]
        # Only U.5 snapshots recorded whether the authority read succeeded.
        # Earlier v2 files must stay unknown rather than treating an omitted
        # thesis basis row as proof the user never wrote one.
        if basis_readiness_known and "thesisPresent" not in position:
            thesis = basis_theses.get(ticker)
            position["thesisPresent"] = isinstance(thesis, Mapping)
            position["latestReviewPresent"] = bool((thesis or {}).get("deltaId")) if isinstance(thesis, Mapping) else False
        positions.append(position)
    out["positionReviews"] = positions[:MAX_LIST]
    roster = []
    for value in _items(out.get("positionRoster"), 100):
        item = _mapping(value)
        ticker = _text(item.get("ticker"), 24).upper()
        verdict = _text(item.get("thesisVerdict"), 32)
        if not ticker or verdict not in THESIS_VERDICTS:
            continue
        row = {"ticker": ticker, "thesisVerdict": verdict}
        for readiness_key in ("thesisPresent", "latestReviewPresent"):
            if isinstance(item.get(readiness_key), bool):
                row[readiness_key] = item[readiness_key]
        roster.append(row)
    out["positionRoster"] = roster
    raw_coverage = _mapping(out.get("coverage"))
    coverage = {}
    for key in ("totalPositionCount", "rosterIncludedCount", "detailIncludedCount", "omittedRosterCount", "omittedDetailCount"):
        value = raw_coverage.get(key)
        if isinstance(value, int) and 0 <= value <= 100000:
            coverage[key] = value
    out["coverage"] = coverage
    raw_selection = _mapping(out.get("reportSelection"))
    selection = {}
    for key in ("candidateCount", "includedCount", "excludedCount"):
        value = raw_selection.get(key)
        if isinstance(value, int) and 0 <= value <= 100000:
            selection[key] = value
    out["reportSelection"] = selection
    out["checkpointReviews"] = _checkpoint_reviews(out.get("checkpointReviews"))
    exposures: list[dict] = []
    for value in out["sharedExposures"]:
        item = _mapping(value)
        exposure_type = _text(item.get("type"), 32)
        key = _text(item.get("key"), 160)
        if exposure_type not in EXPOSURE_TYPES or not key:
            continue
        weight = _number(item.get("weight"))
        row = {"type": exposure_type, "key": key, "stateKey": _text(item.get("stateKey"), 160), "label": _text(item.get("label"), 240), "tickers": _string_list(item.get("tickers"), limit=24, text_limit=24), "momentum": _text(item.get("momentum"), 32)}
        if weight is not None: row["weight"] = weight
        exposures.append(row)
    out["sharedExposures"] = exposures[:MAX_LIST]
    risks: list[dict] = []
    for value in out["portfolioRisks"]:
        item = _mapping(value)
        risk_key = _text(item.get("riskKey"), 64)
        method = _text(item.get("methodVersion"), 96)
        status = _text(item.get("status"), 24)
        if risk_key not in RISK_KEYS or not method or status not in RISK_STATUSES:
            continue
        concentration = _mapping(item.get("concentration"))
        normalized_concentration = {key: _number(concentration.get(key)) for key in ("top1", "top3", "top5") if _number(concentration.get(key)) is not None}
        holdings = concentration.get("holdings")
        if isinstance(holdings, int) and 0 <= holdings <= 10000: normalized_concentration["holdings"] = holdings
        backtest = _mapping(item.get("backtestRef"))
        normalized_backtest = {key: _text(backtest.get(key), 128 if key == "fingerprint" else 80) for key in ("id", "methodVersion", "baseCurrency", "window", "start", "end", "fingerprint") if _text(backtest.get(key), 128 if key == "fingerprint" else 80)}
        contributions = []
        for contribution in _items(item.get("riskContributions"), 16):
            row = _mapping(contribution); ticker = _text(row.get("ticker"), 24).upper(); weight = _number(row.get("weight"))
            if ticker and weight is not None:
                contributions.append({"ticker": ticker, "weight": weight})
        risk = {"riskKey": risk_key, "methodVersion": method, "status": status, "uncertainty": _text(item.get("uncertainty"), 240), "riskContributions": contributions}
        if normalized_concentration: risk["concentration"] = normalized_concentration
        if normalized_backtest: risk["backtestRef"] = normalized_backtest
        risks.append(risk)
    out["portfolioRisks"] = risks[:MAX_LIST]
    out["counterEvidence"] = _counter_evidence(out["counterEvidence"])
    for key in ("uncertainties", "staleReasons"):
        out[key] = [_reason(item) for item in out[key]]
    out["marketState"] = _market_states(out.get("marketState"))
    out["thesisChanges"] = _thesis_changes(out.get("thesisChanges"))
    out["portfolioImpacts"] = _portfolio_impacts(out.get("portfolioImpacts"))
    out["keyCheckpoints"] = _key_checkpoints(out.get("keyCheckpoints"))
    out["linkedNotes"] = _linked_notes(out.get("linkedNotes"))
    out["warnings"] = _string_list(out.get("warnings"), limit=12, text_limit=240)
    out["exposure"] = _legacy_exposure(out.get("exposure"))
    out["recentReports"] = _recent_reports(out.get("recentReports"))
    out["qualitySummary"] = _quality_summary(out.get("qualitySummary"))
    out["stats"] = _stats(out.get("stats"))
    out["marketTape"] = _market_tape(out.get("marketTape"))
    out["markdown"] = _text(out.get("markdown"), 24000)
    out["stale"] = out["reviewState"] == "stale"
    return out
