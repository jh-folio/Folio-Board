"""Bounded, deterministic news-selection primitives for Q5/S1.

This module deliberately stops before search orchestration, report generation, and
any write.  It supplies two small pieces that those callers can compose later:

* an in-memory prior-session baseline selector; and
* a pre-Top-N candidate assessment pass with conservative source-identity
  deduplication.

The pass does not infer consensus, semantic change, or a market verdict.  It
only preserves facts already present in a candidate and records when a fact is
not available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import re
from copy import deepcopy
from itertools import islice
from typing import Any, Iterable, Mapping
from urllib.parse import urldefrag, urlsplit, urlunsplit

from features.common.change_intelligence.basis import content_hash
from features.common.canonical_report_state import canonical_content_hash
from features.common.research_schema.enums import normalize_evidence_role
from features.common.research_schema.evidence import is_countable_evidence


BASELINE_SELECTOR_VERSION = "q5-s1-v1"
MAX_CANDIDATES = 96
MAX_DEEP_EVENTS = 24
MAX_EXCERPT_CHARS = 1200
SUPPORTED_ACTIVE_MARKETS = frozenset({"us", "kr"})
SUPPORTED_MODES = frozenset({"off", "shadow", "active"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _date(value: Any) -> str:
    return _text(value)[:10]


def _valid_date(value: Any) -> bool:
    raw = _date(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return False
    try:
        date.fromisoformat(raw)
    except ValueError:
        return False
    return True


def _lower(value: Any) -> str:
    return _text(value).lower()


def _parse_time(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed


def _ordered_time_key(value: Any) -> tuple[int, str]:
    """Return a safe comparison key without guessing malformed dates."""
    parsed = _parse_time(value)
    if parsed is not None:
        # Naive cutoff values are date-only legacy metadata; treat them as UTC
        # midnight so a date and timestamp do not compare by tuple type.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return (1, parsed.isoformat())
    raw = _text(value)
    return (0, raw) if raw else (0, "")


def _report_market(report: Mapping[str, Any]) -> str:
    value = report.get("market") or report.get("marketScope")
    if value:
        return _lower(value)
    markets = report.get("includedMarkets") or report.get("markets")
    if isinstance(markets, (list, tuple, set)) and len(markets) == 1:
        return _lower(next(iter(markets)))
    return ""


def _market_metadata(report: Mapping[str, Any], market: str) -> Mapping[str, Any]:
    """Read the existing per-market metadata contract without changing report data."""
    try:
        from features.daily_briefing.schema import briefing_market_metadata

        scope = _lower(report.get("marketScope") or report.get("market"))
        section = report.get("briefings")
        section = section.get(market) if isinstance(section, Mapping) else None
        if scope == market or isinstance(section, Mapping):
            metadata = briefing_market_metadata(dict(report), market, section)
            return metadata if isinstance(metadata, Mapping) else {}
    except Exception:
        pass
    return {}


def _matches_market(report: Mapping[str, Any], market: str) -> bool:
    direct = _report_market(report)
    if direct == market:
        return True
    # An aggregate report may carry a per-market section.  Accept that section
    # only when the established metadata helper identifies the exact market.
    return _lower(_market_metadata(report, market).get("marketScope")) == market


def _report_kind(report: Mapping[str, Any]) -> str:
    return _lower(report.get("kind") or report.get("briefingKind") or "daily") or "daily"


def _status_values(report: Mapping[str, Any]) -> list[str]:
    generation = report.get("generation")
    values = [report.get("status"), report.get("generationStatus"), report.get("jobStatus")]
    if isinstance(generation, Mapping):
        values.append(generation.get("status"))
    return [_lower(value) for value in values if _text(value)]


def _is_completed(report: Mapping[str, Any]) -> bool:
    statuses = _status_values(report)
    failures = {"failed", "failure", "error", "cancelled", "canceled", "aborted", "interrupted"}
    if any(value in failures for value in statuses):
        return False
    if any(value in {"completed", "complete", "success", "succeeded", "ready", "committed", "ok", "ok_local_only", "ok_agent_authored", "ok_web_search"} for value in statuses):
        return True
    revision = report.get("canonicalRevision")
    # Atomic canonical reports may intentionally have no top-level status.  A
    # persisted markdown plus a revision marker is the commit owner in that
    # shape; transient failure/cancel states above still take precedence.
    return bool(_text(report.get("markdown")) and isinstance(revision, Mapping) and revision.get("number") and revision.get("hash"))


def _version(report: Mapping[str, Any]) -> str:
    revision = report.get("canonicalRevision")
    candidates = (
        report.get("selectionVersion"),
        report.get("newsSelectionVersion"),
        report.get("policyVersion"),
        report.get("baselineVersion"),
        report.get("version"),
        revision.get("version") if isinstance(revision, Mapping) else None,
        revision.get("number") if isinstance(revision, Mapping) else None,
    )
    return next((_text(value) for value in candidates if _text(value)), "")


def _cutoff(report: Mapping[str, Any]) -> str:
    for key in ("cutoff", "sourceCutoff", "dataCutoff", "inputCutoff", "asOf"):
        value = _text(report.get(key))
        if value:
            return value
    metadata = report.get("selectionMetadata")
    if isinstance(metadata, Mapping):
        for key in ("cutoff", "sourceCutoff", "dataCutoff"):
            value = _text(metadata.get(key))
            if value:
                return value
    basis = report.get("changeBasis")
    if isinstance(basis, Mapping) and _text(basis.get("asOf")):
        return _text(basis.get("asOf"))
    for key in ("generatedAt", "committedAt", "savedAt"):
        value = _text(report.get(key))
        if value:
            return value
    return ""


def _cutoff_source(report: Mapping[str, Any]) -> str:
    for key in ("cutoff", "sourceCutoff", "dataCutoff", "inputCutoff", "asOf"):
        if _text(report.get(key)):
            return key
    metadata = report.get("selectionMetadata")
    if isinstance(metadata, Mapping):
        for key in ("cutoff", "sourceCutoff", "dataCutoff"):
            if _text(metadata.get(key)):
                return f"selectionMetadata.{key}"
    basis = report.get("changeBasis")
    if isinstance(basis, Mapping) and _text(basis.get("asOf")):
        return "changeBasis.asOf"
    for key in ("generatedAt", "committedAt", "savedAt"):
        if _text(report.get(key)):
            return key
    return "unknown"


def _session_date(report: Mapping[str, Any], market: str = "") -> str:
    if market:
        metadata = _market_metadata(report, market)
        value = _date(metadata.get("sessionDate"))
        if value:
            return value
    for key in ("sessionDate", "marketSessionDate", "analysisSessionDate"):
        value = _date(report.get(key))
        if value:
            return value
    windows = report.get("marketWindows")
    if isinstance(windows, Mapping):
        for key in ("usRegularSessionDate", "krCurrentSessionDate", "krPreviousSessionDate"):
            value = _date(windows.get(key))
            if value:
                return value
    return _date(report.get("date"))


def immutable_report_hash(report: Mapping[str, Any]) -> str:
    """Hash a report snapshot in a stable way for a baseline pin.

    The existing canonical hash excludes personal overlays and revision/job
    projection fields.  Keep that ownership rule here so changing a personal
    note cannot invalidate a Canonical baseline pin.
    """
    canonical = dict(report)
    # These are private/derived fields outside the Canonical content contract.
    for key in ("notes", "personalNotes", "volatileProjection", "changeSummary", "changeIntelligence", "quality", "qualityGeneration"):
        canonical.pop(key, None)
    return canonical_content_hash(canonical)


def _has_source_after_cutoff(report: Mapping[str, Any], cutoff: str) -> bool:
    if not cutoff:
        return False
    cutoff_key = _ordered_time_key(cutoff)
    refs = report.get("sourceRefs") or report.get("sources") or []
    if not isinstance(refs, (list, tuple)):
        return False
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        published = ref.get("publishedAt") or ref.get("published_at") or ref.get("date")
        if _text(published) and _parse_time(published) is not None and _ordered_time_key(published) > cutoff_key:
            return True
    return False


def _declared_contamination(report: Mapping[str, Any]) -> bool:
    for key in ("contaminated", "baselineContaminated", "currentDataIncluded", "includesCurrentData"):
        if report.get(key) is True:
            return True
    status = _lower(report.get("baselineStatus") or report.get("selectionStatus"))
    return status in {"contaminated", "baseline_contaminated"}


@dataclass(frozen=True)
class BaselineSelection:
    status: str
    market: str
    kind: str
    reason: str = ""
    reason_codes: tuple[str, ...] = ()
    report_id: str = ""
    session_date: str = ""
    cutoff: str = ""
    version: str = ""
    content_hash: str = ""
    report: Mapping[str, Any] | None = None
    pin: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.report, Mapping):
            object.__setattr__(self, "report", deepcopy(dict(self.report)))
        object.__setattr__(self, "pin", deepcopy(dict(self.pin or {})))

    @property
    def baseline_status(self) -> str:
        return self.status

    @property
    def selector_version(self) -> str:
        return _text(self.pin.get("selectorVersion")) or BASELINE_SELECTOR_VERSION

    @property
    def cutoff_provenance(self) -> str:
        return _text(self.pin.get("cutoffProvenance")) or "unknown"

    @property
    def canonical_revision(self) -> Mapping[str, Any] | None:
        value = self.pin.get("canonicalRevision")
        return value if isinstance(value, Mapping) else None

    def __getitem__(self, key: str) -> Any:
        """Small mapping-compatible bridge for existing dict-oriented callers."""
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "market": self.market,
            "kind": self.kind,
            "reason": self.reason,
            "reasonCodes": list(self.reason_codes),
            "reportId": self.report_id,
            "sessionDate": self.session_date,
            "cutoff": self.cutoff,
            "version": self.version,
            "selectorVersion": self.selector_version,
            "contentHash": self.content_hash,
            "pin": dict(self.pin),
            "report": dict(self.report) if isinstance(self.report, Mapping) else None,
        }


def select_prior_briefing_baseline(
    reports: Iterable[Mapping[str, Any]] | None,
    *,
    market: str,
    kind: str = "daily",
    current_session_date: str,
    current_cutoff: str = "",
    selector_version: str = BASELINE_SELECTOR_VERSION,
    current_report_id: str = "",
) -> BaselineSelection:
    """Select the nearest prior completed report from an in-memory collection.

    Filenames, directory order, and report publication date are never used as
    identity.  The market, kind, and session date are exact lineage keys.  A
    candidate whose cutoff reaches the current run is contaminated; malformed
    or absent metadata is missing and never a usable baseline.
    """
    target_market = _lower(market)
    target_kind = _lower(kind) or "daily"
    target_session = _date(current_session_date)
    if not _valid_date(target_session) or (current_cutoff and _parse_time(current_cutoff) is None):
        return BaselineSelection(
            status="baseline_missing",
            market=target_market,
            kind=target_kind,
            reason="baseline_missing",
            reason_codes=("baseline_missing",),
        )
    matching: list[tuple[str, Mapping[str, Any], str, str, str]] = []
    contaminated = False
    incomplete = False
    for report in reports or ():
        if not isinstance(report, Mapping):
            continue
        if not _matches_market(report, target_market) or _report_kind(report) != target_kind:
            continue
        session = _session_date(report, target_market)
        if not _valid_date(session) or session >= target_session:
            continue
        if _text(report.get("id")) == _text(current_report_id) and current_report_id:
            continue
        candidate_cutoff = _cutoff(report)
        candidate_version = _version(report)
        if candidate_cutoff and _parse_time(candidate_cutoff) is None:
            incomplete = True
            continue
        digest = immutable_report_hash(report)
        declared_hash = _text(report.get("immutableHash") or report.get("baselineContentHash"))
        if declared_hash and declared_hash != digest:
            incomplete = True
            continue
        if (
            _declared_contamination(report)
            or (current_cutoff and candidate_cutoff and _ordered_time_key(candidate_cutoff) >= _ordered_time_key(current_cutoff))
            or _has_source_after_cutoff(report, current_cutoff)
        ):
            contaminated = True
            continue
        if not _is_completed(report) or not candidate_cutoff:
            incomplete = True
            continue
        # The selector version is a policy pin for this run; it is not required
        # to have been written into older canonical reports.  Preserve their
        # actual canonical revision as the baseline version below.
        matching.append((session, report, candidate_cutoff, candidate_version or "unknown", digest))
    if not matching:
        codes: list[str] = []
        if contaminated:
            codes.append("baseline_contaminated")
        if incomplete or not codes:
            codes.append("baseline_missing")
        status = "baseline_contaminated" if contaminated and not incomplete else "baseline_missing"
        return BaselineSelection(
            status=status,
            market=target_market,
            kind=target_kind,
            reason=codes[0],
            reason_codes=tuple(codes),
        )
    session, report, cutoff, selected_version, digest = max(matching, key=lambda row: (row[0], _ordered_time_key(row[2]), row[4]))
    report_id = _text(report.get("id")) or f"{target_kind}:{target_market}:{session}"
    pin = {
        "reportId": report_id,
        "id": report_id,
        "market": target_market,
        "kind": target_kind,
        "sessionDate": session,
        "cutoff": cutoff,
        "version": selected_version,
        "selectorVersion": _text(selector_version) or BASELINE_SELECTOR_VERSION,
        "canonicalRevision": deepcopy(report.get("canonicalRevision")) if isinstance(report.get("canonicalRevision"), Mapping) else None,
        "contentHash": digest,
        "cutoffProvenance": _cutoff_source(report),
    }
    return BaselineSelection(
        status="baseline_ready",
        market=target_market,
        kind=target_kind,
        report_id=report_id,
        session_date=session,
        cutoff=cutoff,
        version=selected_version,
        content_hash=digest,
        report=report,
        pin=pin,
    )


def _normalise_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    raw, _fragment = urldefrag(raw)
    try:
        parts = urlsplit(raw)
        if not parts.netloc:
            return raw
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))
    except ValueError:
        return raw


def _source_identity(candidate: Mapping[str, Any]) -> str:
    explicit = _text(candidate.get("sourceId") or candidate.get("source_id"))
    if explicit:
        return f"source_id:{explicit}"
    url = _normalise_url(candidate.get("url"))
    if url:
        return f"url:{url}"
    path = _text(candidate.get("path"))
    if path:
        return f"path:{path}"
    publisher = _lower(candidate.get("publisher") or candidate.get("source"))
    title = " ".join(_lower(candidate.get("title")).split())
    date = _date(candidate.get("publishedAt") or candidate.get("date"))
    return f"fallback:{publisher}|{title}|{date}"


def _event_key(candidate: Mapping[str, Any]) -> str:
    identity = _source_identity(candidate)
    period = _text(candidate.get("observedPeriod") or candidate.get("period"))
    correction = _text(candidate.get("correctionOf") or candidate.get("revisionOf"))
    revision = _text(candidate.get("revisionAt") or candidate.get("revisionId"))
    # Explicit correction and a new observation period are deliberately part of
    # the identity.  A ticker/company is never an event identity.
    return "|".join((identity, f"period:{period}", f"correction:{correction}", f"revision:{revision}"))


def _candidate_id(candidate: Mapping[str, Any], index: int) -> str:
    return _text(candidate.get("id") or candidate.get("candidateId")) or f"candidate_{content_hash(_event_key(candidate))[:14]}"


def _candidate_markets(candidate: Mapping[str, Any]) -> set[str]:
    value = candidate.get("market") or candidate.get("marketScope")
    if value:
        return {_lower(value)}
    values = candidate.get("markets") or candidate.get("includedMarkets")
    if isinstance(values, (list, tuple, set)):
        return {_lower(item) for item in values if _text(item)}
    return set()


def _prior_report_context(candidate: Mapping[str, Any]) -> bool:
    if candidate.get("isPriorReportContext") is True or candidate.get("priorReportContext") is True:
        return True
    layer = _lower(candidate.get("sourceLayer") or candidate.get("source_layer") or candidate.get("origin"))
    source_type = _lower(candidate.get("sourceType") or candidate.get("type"))
    artifact_type = _lower(candidate.get("artifactType") or candidate.get("artifact_type"))
    return (
        layer in {"prior_report", "prior_report_context", "source_grounded_report"}
        or source_type in {"prior_report", "briefing"}
        or artifact_type in {"briefing", "source_grounded_report"}
    )


def _is_source_evidence(candidate: Mapping[str, Any], prior_context: bool) -> bool:
    """Only count external news/RSS evidence; reports and generated notes stay context."""
    if prior_context or not is_countable_evidence(dict(candidate)):
        return False
    source_type = _lower(candidate.get("sourceType") or candidate.get("source_type") or candidate.get("type") or "news")
    if source_type not in {"news", "rss"}:
        return False
    generated_by = candidate.get("generated_by") or candidate.get("generatedBy")
    source_layer = _lower(candidate.get("sourceLayer") or candidate.get("source_layer"))
    if _text(generated_by) or source_layer in {"hypothesis", "user_consultation", "generated"}:
        return False
    if candidate.get("reuseAsEvidence") is False or candidate.get("reuse_as_evidence") is False:
        return False
    # An article/RSS row needs at least one stable source locator.  A company
    # name or ticker is never enough to turn a row into evidence.
    locator = _text(candidate.get("sourceId") or candidate.get("source_id") or candidate.get("url") or candidate.get("path") or candidate.get("source"))
    path = _lower(candidate.get("path"))
    if any(token in path.replace("\\", "/").split("/") for token in ("reports", "filings")):
        return False
    return bool(locator)


def _explicit_role(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("evidenceRole") or candidate.get("role")
    raw = _lower(value)
    return normalize_evidence_role(value) if raw in {"supporting", "challenging", "neutral", "background", "data_point"} else "unknown"


def _role_decision(candidate: Mapping[str, Any]) -> str:
    for key in ("selectionRole", "roleDecision", "editorialRole"):
        value = _lower(candidate.get(key))
        if value in {"core_flow", "judgment_change", "new_signal", "checkpoint_result", "unassigned"}:
            return value
    # Rules preserve a declared role but do not manufacture one from sentiment,
    # company names, or article frequency.
    return "unassigned"


def _assessment(candidate: Mapping[str, Any], index: int, *, target_market: str, deep: bool) -> dict[str, Any]:
    cid = _candidate_id(candidate, index)
    context = _prior_report_context(candidate)
    markets = _candidate_markets(candidate)
    market_match = "match" if target_market in markets else ("mismatch" if markets else "unknown")
    source_evidence = _is_source_evidence(candidate, context)
    if context:
        status = "excluded_prior_report_context"
    elif market_match == "mismatch":
        status = "excluded_market_mismatch"
    elif not source_evidence:
        status = "insufficient_evidence"
    else:
        status = "assessed"
    deep_allowed = bool(deep and status == "assessed")
    excerpt = _text(candidate.get("summary") or candidate.get("content"))[:MAX_EXCERPT_CHARS] if deep_allowed else ""
    return {
        "candidateId": cid,
        "eventKey": _event_key(candidate),
        "sourceIdentity": _source_identity(candidate),
        "status": status,
        # `assessmentStatus` follows the Q5 additive vocabulary: a row can be
        # evaluated while still being ineligible for evidence use.
        "assessmentStatus": "evaluated" if status == "assessed" else status,
        "eligible": status == "assessed",
        "evidenceLayer": "prior_report_context" if context else ("evidence" if source_evidence else "unavailable"),
        "marketMatch": market_match,
        "sourceEvidence": source_evidence,
        "priorReportContext": context,
        "evidenceRole": _explicit_role(candidate),
        "roleDecision": _role_decision(candidate),
        "correction": bool(_text(candidate.get("correctionOf") or candidate.get("revisionOf") or candidate.get("revisionAt"))),
        "observedPeriod": _text(candidate.get("observedPeriod") or candidate.get("period")),
        "deepAssessment": deep_allowed,
        "excerpt": excerpt,
    }


def assess_news_candidates(
    candidates: Iterable[Mapping[str, Any]] | None,
    *,
    market: str,
    kind: str = "daily",
    candidate_limit: int = MAX_CANDIDATES,
    deep_limit: int = MAX_DEEP_EVENTS,
) -> list[dict[str, Any]]:
    """Assess at most the bounded pre-Top-N candidate set.

    This function intentionally returns assessment rows, not a new editorial
    ranking.  Input order is retained as the caller's existing operational
    ordering; the rules below only remove exact conservative source duplicates.
    """
    target_market = _lower(market)
    limit = max(0, min(int(candidate_limit), MAX_CANDIDATES))
    deep_cap = max(0, min(int(deep_limit), MAX_DEEP_EVENTS))
    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    deep_count = 0
    for index, candidate in enumerate(list(candidates or [])[:limit]):
        if not isinstance(candidate, Mapping):
            continue
        event_key = _event_key(candidate)
        previous = seen.get(event_key)
        row = _assessment(
            candidate,
            index,
            target_market=target_market,
            deep=previous is None and deep_count < deep_cap,
        )
        if previous is None and row["eligible"] and deep_count < deep_cap:
            deep_count += 1
        if previous is not None:
            # A correction/new-period has a different key above.  Therefore a
            # duplicate here really is the same source identity, not merely the
            # same company or ticker.
            row["status"] = "excluded_duplicate"
            row["assessmentStatus"] = "excluded_duplicate"
            row["eligible"] = False
            row["duplicateOf"] = rows[previous]["candidateId"]
            row["deepAssessment"] = False
            row["excerpt"] = ""
        else:
            seen[event_key] = len(rows)
        rows.append(row)
    return rows


def _operational_ids(candidates: Iterable[Mapping[str, Any]] | None, top_n: int) -> list[str]:
    cap = max(0, int(top_n))
    return [_candidate_id(row, index) for index, row in enumerate(islice(candidates or (), cap)) if isinstance(row, Mapping)]


def evaluate_news_selection(
    candidates: Iterable[Mapping[str, Any]] | None,
    *,
    market: str,
    kind: str = "daily",
    mode: str = "off",
    top_n: int = 24,
    candidate_limit: int = MAX_CANDIDATES,
    deep_limit: int = MAX_DEEP_EVENTS,
) -> dict[str, Any]:
    """Apply Q5 mode boundaries around the pure assessment pass.

    ``off`` performs zero assessment work.  ``shadow`` records bounded rows but
    leaves the operational selection untouched.  ``active`` is allowed only for
    US/KR daily; unsupported requests fall back to the same untouched selection
    as shadow.  The current rules have no authority to rank or replace articles.
    """
    requested = _lower(mode) if _lower(mode) in SUPPORTED_MODES else "off"
    target_market = _lower(market)
    target_kind = _lower(kind) or "daily"
    candidate_rows: list[Mapping[str, Any]] | None = None
    if requested == "off":
        operational = _operational_ids(candidates, top_n)
    else:
        candidate_rows = list(candidates or [])
        operational = _operational_ids(candidate_rows, top_n)
    effective = requested
    fallback_reason = ""
    if requested == "active" and (target_market not in SUPPORTED_ACTIVE_MARKETS or target_kind != "daily"):
        effective = "shadow"
        fallback_reason = "active_scope_unsupported"
    if effective == "off":
        return {
            "mode": requested,
            "effectiveMode": effective,
            "workPerformed": False,
            "fallbackReason": fallback_reason,
            "selectedCandidateIds": operational,
            "operationalSelection": operational,
            "assessments": [],
            "coverage": {"status": "not_run", "candidateCount": 0, "assessedCount": 0, "unassessedCount": 0},
        }
    if candidate_rows is None:
        candidate_rows = list(candidates or [])
    rows = assess_news_candidates(candidate_rows, market=target_market, kind=target_kind, candidate_limit=candidate_limit, deep_limit=deep_limit)
    input_count = len(candidate_rows)
    assessed_count = sum(1 for row in rows if row.get("assessmentStatus") == "evaluated")
    deep_assessed_count = sum(1 for row in rows if row.get("deepAssessment") is True)
    deep_unassessed_count = max(0, assessed_count - deep_assessed_count)
    coverage_status = "complete" if input_count <= min(max(0, int(candidate_limit)), MAX_CANDIDATES) and deep_unassessed_count == 0 else "partial"
    return {
        "mode": requested,
        "effectiveMode": effective,
        "workPerformed": True,
        "fallbackReason": fallback_reason,
        "selectedCandidateIds": operational,
        "operationalSelection": operational,
        "assessments": rows,
        "coverage": {
            "status": coverage_status,
            "candidateCount": input_count,
            "assessedCount": assessed_count,
            "unassessedCount": max(0, input_count - len(rows)),
            "dedupedCount": sum(1 for row in rows if row.get("status") == "excluded_duplicate"),
            "deepAssessedCount": deep_assessed_count,
            "deepUnassessedCount": deep_unassessed_count,
        },
    }
